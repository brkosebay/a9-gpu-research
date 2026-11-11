# Henrik's G9P WebGL/Firefox batch: what G5P already has, and what to port (2026-11-09)

Generated-by: LLM (design lane: read-only study and specs). No device step was run and no kernel or Mesa source was
edited. One host-only Apple probe was compiled (`scripts/gpu/henrik-port/vsuni-binop-probes.py`, §3 spec B).

Grades: **[V]** read in code, Apple compiler output or a log; **[I]** inferred; **[M]** needs the device run in §4.

Sources:
- Henrik's commits: `OrchardLinux/mesa` 91afab1780 … eb839e973e, and kernel `OrchardLinux/orchard` 711ec3e3fa.
  Patches are saved in `build/henrik-port/*.patch`.
- Ours:
  - shipping Mesa r39-11.1 `g5p-r39-11.1-perf@5494db5d351` (`build/third_party/orchard-mesa-r39-9-perf`);
  - Lane B branch `g5p-laneb2-ab@9e3f3959a09` (`build/third_party/mesa-g5p-laneb2-ab`);
  - kernel tree `build/orchard-pr2/cs/vdm-long-kwork/kernel/source`.
- `pvr_arch_queue.c` is identical on both Mesa branches. Compiler line numbers below are r39-11.1 unless marked (B2).

## 0. The short answer

1. **The compiler-side wins are mostly already in G5P.**
   - Henrik's blend gains (electricflower 14→60 fps and so on) come from replacing `nir_lower_blend`'s f32/integer tile
     code. **G5P never used `nir_lower_blend` for graphics.** The `pco_nir.c:1067` call is the generic pco path. G5P
     pipelines branch off at `pvr_arch_pipeline.c:3138` into their own backend
     (`pvr_g5p_nir.c` → `pco_g5p_compile_general_link`). That backend appends Apple's native f16 epilogues
     (`g5p_blend.c`, built from Apple's 45 A9 blend probes) [V].
   - Vertex uniforms already come from the common store through a per-draw PDS loader and are used as ALU operands.
   - Vertex attributes arrive in the unified store through PDS, so there are no attribute loads and no attribute waits.
   - **`docs/gpu/henrik-brief-20261109.md` §1 is wrong on this point** ("Our G5P still uses `nir_lower_blend` … his
     blend win should apply directly"). Fix it before the owner sends the note.
2. **The big port is `fd62672cee`'s second half: stop serializing submissions on the CPU.**
   - Today `pvr_clear_last_submits_syncs()` (`pvr_arch_queue.c:1160`) blocks every `vkQueueSubmit` until **all** jobs
     of the previous submission have retired (`vk_sync_wait_many(…, UINT64_MAX)` at `:1200`).
   - That matches our profile: Firefox's `zfq0` thread spends 50.7 % of samples inside `vkQueueSubmit`, the GPU has a
     job pending only 20–26 % of the time, and Firefox makes 3–5 jobs per frame (webgl-perf-r39-8/-9).
3. **One real compiler gap:** vertex ALU operands read the common store inline only below dword 32
   (`vkind()`, `pco_g5p_general.c:2879`). Above that each read is a `mov.shared` into a temp.
   - Apple's A9 vertex programs read up to dword 255 inline. Shown today for fma (v_u80all) and fadd/fmul (new probe).
   - The old comment's "sh32 wedged the TA" was a common-store **size** bug, fixed in `5069bd6a02b`
     (vertex-temps.md §round 3), not the encoding.
4. **One freeze fix:** a failed submission must still signal what it promised (`eb839e973e`). Ours doesn't, so a
   Zink flush thread can wait forever after a GPU loss.

## 1. Commit by commit

| Henrik | What it does on A10 | G5P today | Evidence | What a port needs |
|---|---|---|---|---|
| **91afab1780** blend table (SrcAlpha/1−SrcAlpha, One/One, SrcAlpha/One, RGB-only mask) | replaces `nir_lower_blend` for those blends | **Done, more general.** Premultiplied and straight-over have measured epilogues. Every other core factor/op goes through the general f16 epilogue. Write masks (including Zink's RGB-only 0x7) go through `g5p_blend_masked` → `blend_build(…, write_mask)`. | `pco_g5p_general.c` `blend_mode()` (B2 `:6035`), `g5p_blend.c:758`, `pvr_arch_g5p_blend.c:27`. Default on, `PVR_G5P_BLEND_GENERAL=0` off. | Nothing |
| **6448de770e** native One/One | 4 half FMAs on the tile read | **Done** (general epilogue; One/One is one of the 45 Apple probes) | same | Nothing |
| **b18b56e292** write VS outputs as they come | fish VS 28→16 regs | **Partly.** `eager_vout` exists, but only as a retry for programs above 12 temps, keeping the smaller (`:7781-7797` B2). Programs ≤12 temps keep their flown "outputs last" bytes on purpose. Apple writes `vout` as soon as a value is final: v_u80all opens with 4 `vout` before any ALU (`build/henrik-port/vsuni/decoded.json`) [V]. | `pco_g5p_general.c` (B2) `:244`, `:7781` | **[M] first:** fish VS temps from `PVR_G5P_PRESSURE_LOG`, and TA ms/frame from T2. Spec D (§2) only if TA time matters. |
| **f0bc62debf** VS in fewer registers | fish VS 44→32, geometry 23.5→6.4 ms | **Own ladder, different allocator** (bank-1/bank-0, remat, compact, homes, schedule, splits; `:7700-7880` B2) | — | No code port. Compare register counts on the fish VS (§4). |
| **7cd135d879** compile VS in both input orders | keep the smaller | **N/A.** G5P attributes are DMA'd into the unified store by the PDS (`fetch_list`, `pvr_arch_g5p_gfx.c:760-777`). No shader-side loads to reorder. | `pvr_arch_g5p_gfx.c:771` | Nothing |
| **a21fa811b8** wait for attribute loads at first read | Drawbench 18→16 µs | **N/A** (no USC attribute loads, see above) | — | Nothing |
| **f2a55c2b9d** VS uniforms from the common store, per-draw DMA | 65→36 µs/draw | **Done** (round 19). The vertex loader (`pvr_arch_g5p_upload.c`, PDS_STATE_UPDATE) DMAs UBO ranges into the common store, 256-dword limit `PCO_G5P_VS_COMMON_DWORDS`. Above 256 total, all UBOs fall back to memory (Apple's `f_u1024all` rule). | `pco_g5p_general.h:35`, `pco_g5p_general.c` (B2) `:2239-2265` | Nothing |
| **757c7fbeb1** VS uniforms as ALU operands | no register per uniform | **Partly.** Inline only for dword < 32 (`vkind()` `:2879`). Higher dwords go through `mov.shared` to a temp: one instruction plus one live register each. The bank-0 retry materializes all of them (`:2984`). | `pco_g5p_general.c:2874-2883` | **Spec B** |
| **fd62672cee** stop serializing submissions | Aquarium/Firefox 42→50 fps | **Not done.** (a) Stride realign wait: N/A. G5P has no realign copy; non-dword strides are refused (`pvr_arch_g5p_vertex.c:53`), seen only in CTS logs, never in Firefox. (b) **Each submit waits for the previous one: present** (`pvr_arch_queue.c:1160-1222`, called at `:1336`). | queue.c | **Spec A** (shared pvr code, near-verbatim) |
| **8eb57990e0** GPU blits by default | Aquarium 34→37-40 | **Done:** `728cde909c9` (vk_meta blit, default on, `PVR_G5P_GPU_BLIT=0` off) | git | Nothing |
| **eb839e973e** Firefox/WebGL bundle | many | **Needed:** (1) `prev_wait` merge in `pvr_process_queue_waits` (spec A requires it; ours overwrites `next_job_wait_sync[i]` at `:1295`); (2) failed submission signals its syncs (ours, `:1376-1384`, only sets lost). **Already ours:** firstInstance (`pvr_arch_g5p_gfx.c:1820`), RGBA8↔BGRA8 row copies (`752a5e90b7d`), partial render areas (own handling/refusals, `pvr_arch_g5p.c:844`). **G9P-only:** register sharing above r31, rematerialize_loads, capture/replay, cross-process submit lock (our kernel serializes, §5). | queue.c | **Spec A** (items 1, 2) |

## 2. Ranked port list (A9: Aquarium, WebGL, Firefox)

**Does each path bottleneck on A9?**
- **Submission serialization: yes [V].**
  - `zfq0` is half of all HW-WebRender samples, all inside `vkQueueSubmit`. GPU pending only 20–26 %.
  - Init→signal per job: 5.7–8.7 ms mean, p90 to 15.6 ms. With the CPU wait, every Zink flush costs the previous
    flush's whole latency on the CPU thread.
- **Blend: no** (already native).
- **Vertex: unknown [M].**
  - Henrik's fish VS was the A10's biggest single cost (23.5 ms/pass). Our fish VS compiles in a different allocator.
  - The Aquarium fish VS uses ~48–52 std140 uniform dwords (lightWorldPos, viewInverse, viewProjection, worldPosition,
    nextPosition, five scalars) plus the address prefix. So roughly 20 of them sit past dword 31 [I from
    `aquarium.html`].
  - T2's per-job `gta` (TA GPU µs) is the measurement that decides it.

| # | Port | From | Expected gain on A9 | Confidence | Risk |
|---|---|---|---|---|---|
| 1 | **Spec A:** async submits, plus leftover-wait merge and failure signalling | fd62672cee + eb839e973e | **Aquarium HW / Firefox: +10–25 % fps [I]**, upper bound = the `wait last submit` µs/frame that `PVR_G5P_WAITLOG=1` prints in the serial arm. Also labwc: its frame N+1 submit no longer waits for frame N. | High that the wait exists [V]; size [M] | Medium: sync semantics. Off-switch `PVR_G5P_SERIAL_SUBMITS=1`. VM edits (BO create/destroy) now meet in-flight jobs more often (kernel EBUSY → `G5P_WS_VM_RETRY` waits); logged. |
| 2 | **Spec A item:** failed submit signals its syncs | eb839e973e | 0 fps. Removes a desktop-freeze path after a GPU loss (owner: freezes first). | [V] code | Low |
| 3 | **Spec B:** VS uniform operands inline to dword 255 | 757c7fbeb1 (Apple form re-derived for A9) | Fewer VS instructions and temps on shaders with >~28 uniform dwords: fish, seaweed, glmark2 jellyfish/refract. Size [M] via TA µs. | Encoding [V] (Apple's bytes, our encoder already emits them); gain [I] | Low–medium: changes VS bytes. Off-switch `PVR_G5P_VS_INLINE_UNIFORMS=0`. Night CTS before it ships by default. |
| 4 | Spec C: kernel, killable VM-bind locks + post-event poll as a param | 711ec3e3fa 0005, 0009 | 0 fps (lock); poll 50→20 µs: ≤0.05 ms/job [I], measurable with T2 | [V] code | Low |
| 5 | Spec D (not written yet): eager VS outputs for every straight-line VS, keep the smaller | b18b56e292 (+7cd135d879's keep-smaller rule) | Only if T2 shows TA ≥ ~25 % of frame GPU time [M] | Apple shape [V] | Medium: changes every flown VS's bytes; night CTS |
| 6 | Blend, GPU blit, uniform DMA, attribute waits/orders | 91afab, 6448de, 8eb579, f2a55c, a21fa8, 7cd135 | **0: already ours or N/A** | [V] | — |

**Caveats on row 1:**
- The size depends on how often VM edits hit EBUSY once jobs overlap the CPU. `drm-vm.inc:785-792` lets a resident
  render VM's MAP/UNMAP pass queued jobs, so the wait may not move much [I]. The `vm-edit` log line settles it.
- The "stride refusals never in Firefox" claim rests on the logs in `build/gpu`, which is where the HW-WebRender
  refusal logs live.

The **kernel complement to #1 is Lane A** (T2 `orchard-vdm-t2-20261109`: joint TA+3D publish, WQ_HIGHPRI, 50 µs post-event poll). Then F5 pipelining. Spec A lets `zfq0` record and submit job N+1 while job N runs. T2/F5 shorten what the GPU side does per job. They stack.

## 3. Codex-ready specs

Common to every brief: **no new tests, no gates, build and stop.**
- Build the package the usual way (`scripts/gpu/orchard/mesa-package`, as r39-11.1 was built; kernel via the T2
  entry's build script).
- Report: branch, head sha, library sha256 and package path. Nothing else.
- Commit trailers, each commit, as our earlier ports:
  ```
  Source: OrchardLinux/mesa <full sha> (<what was taken>).
  Co-developed-by: Henrik Klee
  Generated-by: LLM
  ```

### Spec A: async submissions on G5P (Mesa, shared pvr code)

**Branch:** `g5p-r39-11.2-submit` from `g5p-r39-11.1-perf@5494db5d351` (the installed ICD, so the A/B is env-only on one
package). The commit must also cherry-pick cleanly onto `g5p-laneb2-ab`, because `pvr_arch_queue.c` is identical there.

**Credit:**
- `Source: OrchardLinux/mesa fd62672ceef85fd9f5706f7d0d0632952f74ce98 (no CPU wait on the last submission's syncs)`
- `Source: OrchardLinux/mesa eb839e973e309e18f4b02e76c098dc9e7ceb3e4a (pvr_process_queue_waits prev_wait; failed
  submission signals its syncs)`

**File `src/imagination/vulkan/pvr_arch_queue.c` only:**

1. **Env helpers** (file scope, near the top, after includes):
   ```c
   static bool pvr_g5p_env_on(const char *name)  /* set and not "0" */
   ```
   Then two cached statics:
   - `pvr_g5p_serial_submits()` → `pvr_g5p_env_on("PVR_G5P_SERIAL_SUBMITS")`;
   - `pvr_g5p_waitlog()` → `pvr_g5p_env_on("PVR_G5P_WAITLOG")`.

   Cache each in a `static int x = -1`.
2. **`pvr_clear_last_submits_syncs()` (`:1160`).** At the top, before building `waits[]`:
   ```c
   if (PVR_HAS_FEATURE(&queue->device->pdevice->dev_info, apple_g5p) && !pvr_g5p_serial_submits())
      return VK_SUCCESS;
   ```
   Above it, a comment in Henrik's words:
   - keep the last submission's syncs instead of waiting for them on the CPU;
   - the next jobs and barriers wait for them on the GPU, and a barrier's first scope reaches into earlier submissions;
   - each one is replaced when its job type signals again (`pvr_update_job_syncs`, `:243`);
   - the kernel holds its own fence references;
   - `PVR_G5P_SERIAL_SUBMITS=1` gives the old behaviour.

   Leave the G9P path untouched (that is Henrik's tree to merge).
3. **`pvr_driver_queue_submit_jobs()` (`:1329`).** Time the `pvr_clear_last_submits_syncs()` call with
   `os_time_get_nano()`. When `pvr_g5p_waitlog()`, print:
   ```
   G5P wait: last-submit <us> us serial=<0|1>
   ```
   Print it every call, so the serial arm measures exactly what the default arm saves.
4. **`pvr_process_queue_waits()` (`:1266`), port eb839e973e's hunk verbatim:**
   - `STACK_ARRAY(..., wait_count + 1)`;
   - per job type `i`, after the `stage_wait_count == 0` `continue`: if `queue->next_job_wait_sync[i]` is set, append
     it as one more wait (`prev_wait`);
   - on `vk_sync_create` failure, restore `queue->next_job_wait_sync[i] = prev_wait`;
   - after a successful `null_job_submit`, `vk_sync_destroy(prev_wait)`.
5. **`pvr_process_queue_signals()` (`:1224`).** A signal must also follow the waits that this or an earlier
   submission left for job types that ran no job.
   - Grow `signal_waits` to `[PVR_JOB_TYPE_MAX * 2]`.
   - In the per-type loop, also append `queue->next_job_wait_sync[i]` when it's set, regardless of the stage mask.
     It is conservative and only matters when no job of that type consumed the wait.

   This closes a hole that the old CPU drain hid. Before, the drain only ran at the *next* submit, so this signal
   could fire ahead of its own batch's waits.
6. **`pvr_driver_queue_submit()` (`:1376`), port eb839e973e's hunk.** On `result != VK_SUCCESS`, before the
   `VK_ERROR_DEVICE_LOST` check:
   ```c
   for (i < submit->signal_count) vk_sync_signal(&driver_queue->device->vk, submit->signals[i].sync, submit->signals[i].signal_value);
   ```
   Add a comment saying why: Zink's flush thread in a compositor otherwise waits forever after a GPU loss.
7. **Unchanged:**
   - `pvr_update_job_syncs()`;
   - `pvr_queue_finish()` (it already destroys leftovers, `:214-224`);
   - the G5P transfer path's CPU wait on its own incoming sync (`:680`). That one is required: the CPU reads
     GPU-written memory.

**File `src/imagination/vulkan/winsys/apple_g5p/pvr_g5p_winsys.c`, logging only.**
- In `G5P_WS_VM_RETRY` (`:397`) and in the render-submit backpressure loop (`:1371-1395`), when
  `getenv("PVR_G5P_WAITLOG")` is set, print one line per completed wait:
  ```
  G5P wait: vm-edit <us> us
  G5P wait: backpressure <us> us
  ```
- Use a file-static cached flag. No behaviour change.

**Build and stop.**

### Spec B: vertex uniform operands inline up to common dword 255 (Mesa, G5P compiler)

**Branch:** on top of spec A (`g5p-r39-11.2-submit`), second commit. Re-express it on `g5p-laneb2-ab` later. Same
function there: `vkind()` at B2 `:2913`.

**Credit:** `Source: OrchardLinux/mesa 757c7fbeb16a1abec7b259eb56bed40fb242ae1c (vertex uniforms as ALU operands;
re-derived for A9 from applegpu_g5p output)`.

**Apple evidence, all host-only [V]:**
- `vsuni-probes.py` → `build/henrik-port/vsuni/decoded.json`, v_u80all `+372`: `9e590283 81 11 02 41 84014c00`. That is
  `fma.shared_a` reading dword 32 inline with extension byte `(s>>5)<<1 = 0x02`. 252 inline `fma.shared_a` reads,
  dwords 0…255.
- New `scripts/gpu/henrik-port/vsuni-binop-probes.py` → `build/henrik-port/vsuni-binop/decoded.json`:
  - `v_fadd80` and `v_fmul80` read every uniform as `binary.shared` inline;
  - the last one is `99110203 c1 85 04 41 44 01 7000` (dword ≥64, extension 0x04, route parcel 0x70), fast and strict
    alike;
  - `v_iadd80` decodes to no known form, so integer ops keep today's limit.
- Our `shared_src()` (`g5p_usc.c:736`) already encodes this exact field for 0…255: `raw[2] = (index>>5)<<1`,
  `raw[3] = 0x41`. It is byte-identical to Henrik's A10 `0x4100 | ((u>>5)&7)<<1`. **No encoder change.**

**File `src/imagination/g5p/pco_g5p_general.c` only.**

**Design rule:** one predicate. `vkind()` is also what `vs_dst()` (`:2885`) and the literal paths use to decide
"this operand has a register". So the limit is raised **inside `vkind()`**. A high dword then follows exactly the
bookkeeping a low shared dword follows today. The forms Apple's output does not cover materialize it through their
existing register paths.

Do **not** add a second predicate for the emit sites. If the emit site and `vs_dst()` disagree, `vs_dst()` takes a
`->reg` the inline uniform never got, and a destination register can be corrupted.

`vkind()` is only called from vertex emitters: `vs_dst`, `vs_fbin`, `vs_ffma`, `vs_bitwise`, `vs_minsub`, `vs_int`
[V].

1. **Next to `vkind()` (`:2879`):**
   ```c
   /* PVR_G5P_VS_INLINE_UNIFORMS: unset or not "0" = 256 (Apple's limit), "0" = 32 (r39-11.1) */
   static unsigned vs_inline_limit(void);       /* cached static */
   static bool vs_hi(struct gctx *c, struct ref r)
   {  return vkind(c, r) == VK_SHARED && V(c, r.def, r.comp)->imm >= 32; }
   ```
   `vkind()` tests `v->imm < vs_inline_limit()` instead of `< 32`.
2. **Replace the `vkind()` comment.** Text:
   - inline shared ALU sources are witnessed up to dword 255 for `fma.shared_a` (multiplicand A, register addend) and
     float `binary.shared` (fadd/fmul) (cite both probe files);
   - the sh32 TA wedge was the loader's common-store size (vertex-temps.md round 3, fixed by `5069bd6a02b`);
   - every other shared form keeps a dword ≥ 32 out of the instruction (`vs_hi`).
3. **`vs_fbin` (`:2895`): no change.** Only fadd/fmul reach it. High dwords go to `binary.shared` (`:2993`), the
   witnessed form. The literal path (`:2915`) and the bank-0 materialization (`:2984`) behave as for a low dword.
4. **`vs_ffma` (`:3037`).** Directly after the two `register_fma` lines (`:3078-3079`) add:
   ```c
   /* dword >= 32 only as fma.shared_a's multiplicand (v_u80all); shared_ac and the 0x58 shared addend are witnessed below 32 only */
   register_fma |= vs_hi(c, r[2]) || ((vs_hi(c, r[0]) || vs_hi(c, r[1])) && vkind(c, r[2]) == VK_SHARED);
   ```
   - `register_fma` takes the existing register path: `mov.shared` into scratch, then a register FMA. That is today's
     route for every untaken shared tuple.
   - The literal path at `:3055` needs no change.
5. **Integer paths: keep a high dword out of their shared forms.** In each loop that picks a shared operand, add
   `|| vs_hi(c, r[i])` to the `continue` condition:
   - `vs_minsub` `:3817`: isub/min/max shared, emits at `:3825`/`:3828`;
   - `vs_int` `:3931`: iadd/imul shared, emit at `:3958`.

   Those values then fall through to the functions' register forms, as a shared+shared pair does today.
   - `vs_bitwise` `:3735` only tests "is register", so a high dword simply skips the literal form. It has no shared
     emit ("No shared-operand bitwise encoding is used", `:3750`) [V].
6. **Logging.**
   - Count inline reads of dword ≥ 32 in a new `gctx` field `hi_inline` (increment at `:2993` and `:3109` when
     `imm >= 32`).
   - Extend the existing `PVR_G5P_PRESSURE_LOG` line (`:7151` B2 / its r39-11.1 twin) with
     `size=%u hi_inline=%u blake3=%08x`. Program bytes, the counter, and the first 4 bytes of
     `nir->info.source_blake3`, so one shader can be followed across arms.
7. **Unchanged:** `mov.shared` users, fragment code, the 256-dword common-store plan, the encoders
   (`shared_src()` already refuses indices > 255).

**Build and stop.**

### Spec C: kernel, two small 711ec3e3fa analogues (on the T2 branch `a9/gpu-vdm-t2-20261109@9a0a283e51da`)

**Credit:**
- `Source: OrchardLinux/orchard 711ec3e3fad61400ac354326e80840110bac9390 (0005 VM lock killable; 0009 shorter render
  wait poll)`
- `Co-developed-by: Henrik Klee`
- `Assisted-by: LLM` (kernel tree convention as in Henrik's patch)

1. **`drivers/gpu/drm/apple-g5p/drm-vm.inc`, `g5p_vm_bind()` (`:746`):**
   - `mutex_lock(&f->lock)` (`:761`) → `if (mutex_lock_killable(&f->lock)) return -EINTR;`
   - the core lock (`:792`) → `if (mutex_lock_killable(&to_g5p(drm)->core->lock)) { ret = -EINTR; goto out; }`,
     with `locked` staying false on that path;
   - nothing else moves.

   Why: the core lock is held from TA publish to 3D retire, so a mapper stuck behind a hung job could not be killed.
   libdrm's `drmIoctl` restarts on `EINTR`, so userspace is unchanged.
   Line numbers are from the vdm-long tree. T2 doesn't touch `drm-vm.inc`, but locate the sites by function name.
2. **`drivers/gpu/apple-g5p/render-user-evwait.h`:** `G5P_EW_POST_US` becomes a 0600 module param
   `render_user_post_event_us`. This is the knob T2 itself changed: `git show 9a0a283e51da` in the `linux-a9-src`
   volume has `G5P_EW_POST_US` 100U → 50U, plus the matching `drm-latency123.inc` param text and `WQ_HIGHPRI`.
   - Default = the T2 value (50). Clamp 10…100.
   - Read once per job into the plan in `g5p_ew_plan()`'s caller (`drm-latency123.inc:252`), so a job never sees a
     mid-wait change.
   - Henrik's A10 value 20 becomes a same-boot A/B arm (§4), not a new default.

**Build and stop.**

## 4. Device measurement (orchestrator)

**Prerequisites:**
- the T2 kernel entry (`orchard-vdm-t2-20261109`) booted, so `g5p_gpu_stats` / `g5p_jobtimes` exist (Lane A §5);
- the spec A+B package installed over r39-11.1 (`pacman -U`, rollback = r39-11.1).

All arms below run on **one package and one boot**; only env vars and module params change. Desktop unlocked, as
`tablet`. Stats need root, as in Lane A.

*(Device/host command block omitted; it targets the private workspace.)*
- **Report per arm:** fps; GPU ms/frame and GPU busy % from `jobtimes-summary.py --stats`; TA `gta` and 3D `gtd`
  medians per job.
- **From the Firefox log:**
  - `G5P wait: last-submit` µs/frame (serial arm: the ceiling of what async saves);
  - `vm-edit` / `backpressure` wait µs/frame (async arms: where the wait moved, if anywhere);
  - the `G5P pressure: stage=vs …` lines (spec B adds `size`, `hi_inline` and `blake3`). The lines carry no shader
    name, so pick the fish VS like this:
    - take the `stage=vs` lines with `hi_inline>0` in the `async` arm;
    - match each `blake3` to the same value in `async-noinl`;
    - report `bank1`/`bank0`/`size` for both;
    - the fish VS is the largest such shader once 500 fish are on screen;
    - if it's ambiguous, rerun one arm with `G5P_PRINT_NIR=1` and find the `fishWaveLength` uniform's arithmetic.
- `WAITLOG` and `PRESSURE_LOG` cost some CPU. Rerun the winning arm once without them for the headline fps.
- **Stop** at the first `RENDER-V3 lost`, fault or hang. If only the async arm hangs, the cause is sync ordering:
  record which fence was pending and keep `PVR_G5P_SERIAL_SUBMITS=1` in place.

*(Device/host command block omitted; it targets the private workspace.)*
- Pull `out/*.jsonl` to `build/gpu/xsweep/linux-<date>/`.
- fps = frames between warmup end and the last frame, the same arithmetic as the iOS table below.

**iOS references** (`build/gpu/xsweep/ios-20261109/heavy2__*.jsonl`, Safari 16.6, the same arithmetic):

| aquarium-500 | aquarium heavy2 | electricflower | video | city | spacerocks | fishtank | toon | field | sprites | blob | dyn-cubemap |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 60.0 | 59.4 | 60.0 | 60.0 | 60.0 | 35.0 | 60.0 | 60.0 | 52.2 | 18.9 | 59.0 | 48.8 |

**Our last Linux numbers are stale** (r39-2 ICD, default preset, frames/elapsed:
`build/gpu/webgl-samples/device-r39-2`).
- electricflower ≈18, video ≈21, spacerocks ≈12, fishtank ≈12.5, toon-shading ≈13.7, field ≈12, sprites ≈5.7,
  blob ≈21. Aquarium broke on that ICD.
- toon-shading at ~14 fps on a trivial scene (A10: 53→60) says the floor is per-frame overhead, not blend or ALU.
- **Take a serial-arm baseline on the current ICD before reading any gain.**

## 5. Kernel: 711ec3e3fa against ours

Our A9 GPU runs on our own `drm/apple-g5p` driver. Henrik's six patches target `drm/imagination` (`pvr_apple.c`,
A10). The A10 files are in our tree but don't drive the A9.

| His patch | Ours | Action |
|---|---|---|
| 0004 arm a submission's jobs together (cross-app TA/3D interleave hung the GPU) | **Inherent.** The executor runs one job at a time and holds the core lock from TA publish to 3D retire (Lane A §2 [V]). T2's joint publish keeps that. **F5 (pipelining) must keep TA/3D of one job adjacent across contexts.** | Write it into F5's design |
| 0005 VM context lock killable when mapping | `g5p_vm_bind` takes `f->lock` and `core->lock` with plain `mutex_lock` (`drm-vm.inc:761`, `:792`). A job hung up to its timeout makes the mapper unkillable. | Spec C.1 |
| 0006 stop the firmware when probe fails | Different bring-up (autoboot delayed work, `a9-gpu-drm.c:606-640`). Not checked whether a late probe failure leaves the firmware running. | Low, review item |
| 0007 trace oops (`pvr_job_create`) | N/A (pvr trace) | — |
| 0008 `pvr_page_destroy` unwinding a failed map | Our MMU code is our own; its `-ENOMEM` unwind wasn't checked here | Low, review item |
| 0009 render waits in 20 µs steps instead of 1 ms | The 1 ms `usleep_range` is only the knob-0 legacy mode. Default is event wait with a 100 µs post-event sleep (`render-user-evwait.h:19`), 50 µs in T2. | Spec C.2 (A/B 50 vs 20) |

## 6. For the orchestrator

1. Fix `henrik-brief-20261109.md` §1's blend sentence. Replace it with: "G5P graphics never went through
   `nir_lower_blend`; its native epilogues already cover his table. What we take is his submission work."
2. Send spec A, then B, to one Codex run on one branch (`g5p-r39-11.2-submit`), plus spec C on the T2 kernel branch.
3. Fly §4 step 0 on the T2 boot, then step 1.
4. Next target after that: whichever of `gta` (VS → spec D), the moved wait (`vm-edit` → a kernel VM-edit-while-busy
   change, the Apple way) or the 3D floor (Lane A F1/F5) dominates the async arm.

## Result: §4 step 0, Aquarium 500 fish, HW WebRender (2026-11-09, T3 kernel, joint=1, `g5p-port-submit@aec53763c59`)

One boot, three arms, run by `scripts/gpu/port-submit-arms.sh`. Data: `build/port-submit/device/`. fps is Aquarium's own averageFPS, median of ~63 samples. GPU busy % and GPU ms/job come from `g5p_gpu_stats` over the whole arm window (~91 s, including the Firefox launch, so busy % is understated).

| Arm | fps median | GPU busy % | GPU ms/job (TA + 3D) | TA publish→event | 3D publish→event | queue→worker |
|---|---:|---:|---:|---:|---:|---:|
| serial | 26 | 34.5 | 2.85 (0.39 + 2.46) | 1.03 ms | 4.40 ms | 3.2 ms |
| async-noinl (spec A) | **29** | 39.8 | 3.01 | 1.00 ms | 4.40 ms | 3.5 ms |
| async (A+B) | 29 | 38.8 | 3.00 | 1.02 ms | 4.39 ms | 3.4 ms |

- **Spec A (async submits): +3 fps (+12%).** No faults, no recoveries.
- **Spec B (inline VS uniforms): 0 fps, and a drawing bug.** The owner saw Aquarium's fps/fish overlay box drawn without its text in the async arm only. B changed 7 distinct VS (`hi_inline>0`, blake3 (captured state words omitted)); one of them miscompiles WebRender's text path. **B stays off** (`PVR_G5P_VS_INLINE_UNIFORMS=0`) until it's fixed.
- Where the time goes: per job the GPU works ~2.85 ms. We hold the core for ~5.5 ms (TA 1.0 ms wall vs 0.39 ms GPU; 3D 4.4 ms wall vs 2.46 ms GPU), and the next job waits ~3.3 ms in the queue. The GPU sits idle about 60% of the time while jobs queue. That's the per-job latency Lane A2 is working on, and it's larger in Aquarium (3D ~1.9 ms/job) than in the microbench (~0.39 ms).

## Result: §4 step 1, WebGL xsweep serial vs async (2026-11-09, T3 boot, joint=1, port-submit ICD, B off)

`scripts/gpu/xsweep-arms.sh` (heavy preset, warmup 4 s, 12 s measured; same fps arithmetic as iOS). Data: `build/gpu/xsweep/linux-20261109c/`. No GPU faults in either arm.

| sample | iOS | serial | async | gain |
|---|---:|---:|---:|---:|
| aquarium (heavy) | 59.4 | 5.0 | 5.3 | +5% |
| electricflower | 60.0 | 33.5 | 35.7 | +7% |
| video | 60.0 | 58.5 | 53.7 | −8% |
| city | 60.0 | 30.5 | 32.4 | +6% |
| spacerocks | 38.8 | 26.4 | 28.9 | +9% |
| fishtank | 60.0 | 19.6 | 20.5 | +5% |
| toon-shading | 60.0 | 33.9 | 37.9 | +12% |
| field | 52.2 | 24.0 | 25.6 | +7% |
| sprites | 18.3 | 1.9 | 2.0 | +3% |
| blob | 58.8 | 22.0 | 22.5 | +3% |

- Async (spec A) gains +3 to +12% on 9 of 10 samples. video −8% (near 60, frame-paced; recheck).
- Against the stale r39-2 numbers this is ~2–3× (electricflower 18→36, toon 13.7→38, fishtank 12.5→20.5).
- Worst gaps vs iOS: sprites 2 vs 18, aquarium-heavy 5 vs 59, fishtank 20 vs 60.
- **dynamic-cubemap excluded:** it renders into a cubemap face, a twiddled colour target. G5P refuses it ("twiddled PBE is step 7"), WebGL loses its context, and the content process dies and takes the sweep page with it. That's a feature gap (iOS 48.8 fps).
- Also on this boot: one `RENDER-V3 lost why=ta-silent` at uptime 1952 s, during the aborted 77-sample run (sample not yet identified). It recovered in 235 ms.
- **1M triangles now pass** with joint=1: 15.77 ms wall, 14.71 ms GPU (TA 6.64 + 3D 8.07), against iOS 19.59 ms. Joint publish is Lane C's C2.

## Result: spec B fixed (`g5p-port-submit-b2@b4337daeabe`), 2026-11-09, M1 boot, joint=1

Root cause: a refusal, not a miscompile. With B on, WebRender's `ps_text_run` VS (uniforms above dword 32, bank-0 retry) was refused ("uniform ALU with a register in vertex bank 0"), so its draws never ran. Fix in `vs_fbin`: the bank-0 retry uses the register path. Report: `build/port-submit-b2/REPORT.md`.

Device, Aquarium 500 with B on (`async-inl` arm): **overlay text visible (owner confirmed)**, 29 fps median (B off: 29). Refusals: the same 2 "discard under depth/stencil requires an unsupported punch-through variant" as the B-off arm, so B adds none. B still gives no fps on Aquarium. It stays opt-in until a workload shows a gain. Known latent gap: `vs_ffma` has the same bank-0-retry pattern (would refuse, never draw wrong; no current program hits it).
