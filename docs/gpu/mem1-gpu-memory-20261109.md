# mem1: who allocates STK's 2 MiB BOs, and the fixes (2026-11-09, night)

Follows `fable-open-questions-20261109.md` §1 and the F1.1 device run (`build/gpu/stk-split-20261109.host.log`).
Branch `g5p-mem1` = 5 commits on `g5p-fix1` (worktree `build/third_party/mesa-g5p-port-submit`), head `4c3d3f73ee2`.
Package `build/mem1/`, commands `build/mem1/DEVICE-COMMANDS.txt`. No kernel change. Nothing here ran on the device.

Grades: [V] read in source, [T] tested here (Zink on lavapipe, in the build container), [I] inferred from the
device numbers, [M] to measure on the device.

## 1. Root cause

**The 2 MiB BOs are Zink's slab parents, one kernel BO each, and past 256 of them we refuse every render.**

1. Zink suballocates every allocation of up to 1 MiB from a slab, and a slab's backing buffer is always 2 MiB
   (`zink_bo.c:1351-1355`, "twice the largest entry"; 4 MiB for some 3/4 sizes). Our ICD made every allocation of
   2 MiB or more a kernel BO of its own (`PVR_G5P_DATA_THRESHOLD`, `pvr_g5p_hooks.h` `memory_bo_type`). So 281 BOs
   of 2 MiB is 281 Zink slabs. [V] "heap=3" in Zink's message is its own enum (`ZINK_HEAP_DEVICE_LOCAL_VISIBLE`),
   not a Vulkan heap: we have one memory type and one heap. [V]
2. **The 256-BO wall.** `g5p_ws_render_resources()` returned `-ENOMEM` ("too many render resources") whenever
   arena chunks + own BOs exceeded `DRM_G5P_RENDER_MAX_RESOURCES` = 256, whatever the job touched
   (`pvr_g5p_winsys.c:1386` in fix1). STK at 256 held 281 + 7 + 1 BOs plus chunks. [V] Evidence in the device data:
   the last `arena stats why=submit` line of the 256 run has `data_bos=58`, while the kernel showed 281 BOs at
   t=30: no render was submitted after the track load (that line prints at least every 5 s of submits). [I] This is
   also why the two numbers looked inconsistent ("the 2 MiB BOs are not our arena and not textures"): the stats line
   was stale. Zero-flight check: `grep -c 'too many render resources'` in that run's `stk.log` (commands, step 0). [M]
3. **What fills the slabs: textures, and about as many bytes of dead upload staging.** [V mechanism, I share]
   - Every texture upload on our driver goes through a staging buffer of the level's size (`zink_image_map`,
     `zink_resource.c:3399-3421`; no `VK_EXT_host_image_copy`). After the copy is recorded the buffer is garbage,
     but the batch holds a reference until it completes, and `pb_slabs` cannot reuse the entry before that
     (`bo_can_reclaim`, and `pb_slabs_reclaim_locked` gives up after 2 busy entries, `pb_slab.c:74-98`).
   - A loading loop has no draw, so nothing flushes. Zink's only guard counts every referenced resource against
     **80 % of the heap** (`clamp_video_mem`, `zink_screen.c:4036`; `check_oom_flush`, `zink_batch.c:1199`): with
     our 768 MiB heap, 614 MiB. The 256 run was at 568 MiB and still loading.
   - Our buffer requirements add a page to every page-multiple size (`PVR_BUFFER_MEMORY_PADDING_SIZE`,
     `pvr_device.c:1033-1040`), so a 256 KiB staging buffer takes a 384 KiB slab entry and a 1 MiB one (512² level
     0) does not fit a slab at all and went to the code arena.
   - Model for one 256² RGBA8 mip chain: image 349 KiB in a 384 KiB entry (5 per slab = 419 KiB); staging 256K →
     419K, 64K → 96K, 16K → 32K, the rest 16K each ≈ 645 KiB if every level is uploaded. So **55–60 % of the slab
     bytes during a load are dead staging**: of 568 MiB, ≈ 250 MiB textures (≈ 590 textures) and ≈ 320 MiB
     staging. Cross-check: 590 textures at 512² are 590 × 1.41 MiB ≈ 830 MiB, which is why the 512 run hit the
     768 MiB VM limit. [I]
4. **Freed memory was not returned.** Freed slab entries are reclaimed only when an allocation of some size class
   finds its slabs full, and Zink's buffer cache only expires entries when another is added: after a mass free the
   slabs stay allocated while the app asks for nothing more. [V] Measured on lavapipe: 400 textures deleted, 4 idle
   frames: +172 MiB stays (fix1 Zink), falls to +37 MiB with the trim. [T]
5. **Memory types are correct as they are.** Our BOs are mapped write-combined (`shmem->map_wc =
   !dev_is_dma_coherent`, kernel `drm-vm.inc:243`), so `HOST_CACHED` must not be advertised. [V] Consequence: Zink
   does every buffer read-back through a staging copy (`zink_resource.c:3246`); that is a kernel question (cached
   BOs + cache maintenance), not this lane.
6. Not the cause: the arena (8.7 MiB at 256), Zink's buffer cache (≤ heap/8 = 96 MiB, 0.5 s), its buffer-object
   cache (≤ 12 MiB). [V]

## 2. What mem1 changes

| Commit | Change | Switch back |
|---|---|---|
| `f5620244392` | pvr: arena chunk growth capped at 16 MiB, chunk table 128 (F1.5): slack ≤ 16 MiB, was ≤ 96 | `PVR_G5P_ARENA_CHUNK_MIB=64` |
| `75cc2cfb190` | pvr: legacy-renderpass 4× MSAA resolves in the PBE (4c) | `PVR_G5P_MSAA_PBE_RESOLVE=0` |
| `e1667377ae4` | pvr: application data is carved from **data chunks** (8 MiB RW kernel BOs); data starts at 1 MiB, not 2; the 256 limit is checked on what the job names; `PVR_G5P_ARENA_LOG` "data stats" | `PVR_G5P_DATA_CHUNK_MIB=0`, `PVR_G5P_DATA_KIB=2048` |
| `e87014a085e` | zink: a batch holding ≥ heap/32 (24 MiB here) of dead upload staging is flushed and waited for | `ZINK_STAGING_FLUSH_MIB=0` |
| `4c3d3f73ee2` | zink (+ `pb_cache`): on a flush, once a second, reclaim idle slab entries and expired cached buffers | `ZINK_TRIM_MS=0` |

Notes:
- **Data chunks.** A chunk is an own BO, so jobs list it by the address ranges they read and write, exactly as they
  listed a Zink slab BO before; hazard tracking still resolves an address to the application's allocation, not the
  chunk (`pvr_g5p_winsys_bo_range()`), so its granularity is unchanged. An allocation above half a chunk stays its
  own kernel BO (≤ 192 in 768 MiB). An empty chunk is released at once, except one spare. A chunk the kernel
  refuses (pin limit) falls back to a BO of the allocation's size. 4× fewer VM edits while loading (each waits for
  the render jobs), and a 4× shorter resource list when a job's reads are unknown.
- **1 MiB threshold.** Zink allocates everything above its 1 MiB slab entries directly; at 2 MiB, 512² mip chains
  (1.4 MiB, STK's bulk at default settings) filled the RWX code arena, which is released only from the tail and
  whose addresses hazard tracking cannot resolve. Trade-off [M]: those textures now count in a job's read list
  (32 allocations), so a job sampling more than 32 of them lists every own BO (~100 chunks, not 281 BOs).
- **Two Zink commits.** The owner's rule is no Zink modifications (2026-11-04, about caps and quirks). These are
  general allocator fixes with no driver check, like the two sync fixes fix1 already carries, and the retention
  cannot be fixed from the Vulkan side: the only lever there is the reported heap (`PVR_G5P_HEAP_MIB`, in this build
  for the A/B), which would also force a flush + stall whenever one frame references more than 80 % of it.
  **Orchestrator: confirm or drop them** (both switch off by env; the ICD commits stand alone).
- `PVR_G5P_HEAP_MIB=n` (measurement): the heap we report. `PVR_G5P_ARENA_LOG=2`: one line per data slice.

## 3. Expected on the device [M]

- STK 256, mid-load (fix1: 568 + 37 MiB in 288 BOs, MemAvailable 177 MB, no frames): ≈ 250–320 MiB of images,
  staging ≤ ~60 MiB, ≈ 40–50 kernel BOs, **≈ −250 to −300 MiB** and STK renders. If `image_kib` alone is above
  600 MiB the demand is real and only F1.2 (ETC2 transcode, −75 %) helps.
- STK 512: staging no longer takes about half of the 768 MiB, so roughly twice the textures fit; the set is still
  ≈ 830 MiB of RGBA8 [I], so some failures can remain until F1.2. The arena stays at tens of MiB (was 286+).
- After a level unload: freed chunks go back within ~2 s (trim), instead of staying until the next load.
- Arena slack: ≤ 16 MiB (was ≤ 96).

## 4. What was and was not tested

- [T] Both Zink commits, on lavapipe in the build container (`scripts/gpu/mem1-upload-smoke.c`, 400 × 256² and
  200 × 512², busy mode so uploads take the staging path): 0 wrong texels with a flush every 1 MiB and every
  16 MiB; held memory 1.47× → 1.25× the texels (2 × the limit in flight, as designed); after delete +172 → +37 MiB.
- [T] ICD and GL stack build as fix1 did (same container, build dirs, options).
- **Not run anywhere:** the winsys data chunks, the 1 MiB threshold, the arena cap and the MSAA hook need the A9
  kernel. First flight = `DEVICE-COMMANDS.txt` step 2 (smoke), then the STK split.

## 5. Next (ranked)

1. Fly mem1 (steps 0–3), then the switch runs (step 4) to attribute the saving per change.
2. F1.2 ETC2 transcode: the remaining 4× on real texture bytes.
3. Buffer padding: `+1 page` on page-multiple VkBuffers costs a slab class (256K → 384K). Move the 4-byte read-ahead
   guarantee into the winsys (a guard page per kernel BO) and drop it from the requirements; needs one hardware
   check of the vertex-fetch read-ahead. Small once staging is bounded.
4. `VK_EXT_host_image_copy`: uploads of idle images without staging or a job (Zink uses it when present).
5. F1.4 residency (evictable idle BOs): unchanged, the real fix for "pinned for life".

## Result: device flight (orchestrator, 2026-11-10 ≈23:45 UTC Nov 9)

Kernel f5d. Logs: `build/gpu/mem1-flight-20261110.host.log` (smoke) and `build/gpu/mem1-stk-20261110.host.log` (STK
split). No GPU fault or recovery.

- **Smoke PASS:** 400 textures of 256² + mips (133 MiB of texels), 0 wrong texels, 24 kernel BOs, no allocation
  errors. glmark2 texture/shading at 355/358 fps.
- **STK split, 60 s, HD textures off, same boot:**

| | fix1 256 | mem1 256 | fix1 512 | mem1 512 |
|---|---:|---:|---:|---:|
| STK kernel BOs | 291 | **83** | 230 | **102** |
| STK pinned MiB (t=45) | 611 | 612 | 765 | 767 |
| MemAvailable at t=45 | 383 MB | 335 MB | 224 MB | 238 MB |
| alloc_fail | 0 | 0 | 5097 | 5176 |
| refused_renders | 0 | 0 | 0 | 0 |
| mem1 data stats: image / buffer KiB | — | 320931 / 92550 | — | 584383 / 74825 |

- **mem1 cuts the BO count 3.5× but not the memory.**
  - The 256-BO render wall did not occur in fix1 either (refused_renders=0), so that part of the model is wrong.
  - The staging share is ~75–93 MiB, not ~300.
  - **Textures dominate: 321 MiB at 256 and 584 MiB at 512 of RGBA8, i.e. S3TC decompressed.**
- **Next: F1.2, the S3TC→ETC2 (or ASTC) transcode** in mesa/st. It is ≈4× on the dominant term (expected
  ~320 → ~80 MiB at 256, ~584 → ~146 MiB at 512). The mem1 commits stay (fewer kernel BOs, MSAA fix); the Zink
  trims are kept but do not move this workload.
- STK never reached the race in 60 s in any arm (loading on 2 cores). A score needs a full-length run.
