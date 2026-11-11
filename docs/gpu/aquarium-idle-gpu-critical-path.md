# Aquarium 500 fish: what fills the GPU-idle time (2026-11-09)

Generated-by: LLM (Opus profiling/design lane). No device access, no commits. Companion spec for removing the CPU
transfer path: `docs/gpu/gpu-transfer-path-spec.md`.

Grades: **[V]** read in data/code/Ghidra, **[D]** derived from [V] numbers, **[I]** inferred, **[M]** needs a capture (§5).

## 0. Answer (short)

- In the capture window the GPU has **no job outstanding for 16.9 ms of every 43.8 ms frame (38 %)** [V fence trace].
  The CPU is not saturated: during those gaps only ~1.1 of 2 cores are busy [D]. So the idle time comes from
  serialization between threads and processes, not CPU throughput.
- About 13.7 ms/frame of the idle sits **between pipeline stages** (WebGL frame → WebRender composite → labwc composite
  → flip → next rAF). The driver's own CPU work inside those gaps, ranked:

| # | cause (driver) | GPU-idle ms/frame attributable | CPU ms/frame | evidence |
|---|---|---:|---:|---|
| D1 | **CPU transfer path**: `vkCmdCopyBuffer` runs as a CPU memcpy on the one Firefox submit thread (zfq0), after a host `drmSyncobjWait` for the GPU to drain | **≈4.7** (3.3 copy inside idle + ≈1.4 restart bubbles) | 2.0 on-core / 4.7 wall; zfq0 blocked 8.7 wall | §2.1, §3 |
| D2 | **Per-draw recording overhead** (WebGL, 500 draws, gdrv0): read tracking, suballocator, LL/SC atomics and mutexes | ≤2.5 (gdrv0 runs during idle; on the critical path only in the last ms before the WebGL submit) | 4.0 | §2.2 |
| D3 | **Rogue load-op shader compiled on every `vkCmdBeginRendering` with LOAD**, 1.92×/frame, and G5P never uses the result | ≤0.5 | 1.4 | §2.3 |
| D4 | Submit-path syncobj churn (≈190 chain + 140 stub fence objects per frame) and command-buffer reset on zfq0 | ≈0.7 | 2.8 | §2.1 |
| D5 | `PVR_G5P_PERF_LOG=2` per-transfer fprintf (**harness artifact**: the capture script defaults to 2) | (inside D1) | 0.5 | §2.1 |
| — | Kernel/firmware per-job overhead (Lane A2, ≈1 ms/job × 6.1 jobs/frame) | 0 (it is inside the *busy* time) | — | A2 F5 |

- **Top fix:** remove the CPU transfer path. Commit 1 (no new hardware feature): gate the debug logging and narrow
  the host wait to the BOs the copy really touches. Then the copies move to the GPU (`gpu-transfer-path-spec.md`
  Stages 0–1). **Commit 2, small and independent:** skip the dead Rogue load-op compile on G5P (§4.2).
- Firefox's own share (content JS, parent main thread, IPC, compositor cadence) is the rest of the idle. It is not
  driver waste. It is ranked in §3 but not specced.

### Corrections to the brief

- `firefox:gdrv0` is **not** our G5P async submit thread. It is Mesa's gallium `u_threaded_context` driver thread: it
  records the WebGL context's Vulkan commands (`pvr_rogue_CmdDrawIndexed` is 39 % of it). Every `vkQueueSubmit`,
  including our ioctl, runs on **zfq0**, Zink's per-screen flush queue, which serves both Firefox GL contexts.
- The window holds **570 WebGL frames in 25.0 s = 22.8 fps = 43.8 ms/frame**. AQFPS reads 15–31 inside the window; its
  "median 26" covers the whole 77 s run. Lane A2's 38.5 ms and "~20 ms idle" come from a different capture. All
  per-frame numbers here are normalized to the 570 fence-trace frames.

## 1. Per-frame timeline (dma_fence trace + driver perf log, joined) [V]

Tooling: the trace's `apple_g5p` fences line up 1:1 with the driver's `G5P perf submit` lines (2504 = 2504; init is
0.28 ms after submit start). That gives each fence a job identity: WebGL draw 1024² (vdm ≈ 41–83 k), WebGL→compositor
GPU blit 1024² (already GPU since r39-9), WR main 2048×1536 LOAD, WR 2048² (×0.95/frame), WR 1024×512 (×0.47/frame),
labwc (context 14). Transfer start/wait/cpu come from `G5P perf transfer` (CLOCK_MONOTONIC, the same clock: a
transfer's wait ends 132 µs median after a g5p signal).

Cadences: WebGL 22.8 Hz, WR main 22.2 Hz, labwc 39.3 Hz. Jobs/frame: Firefox 4.39, labwc 1.72.
GPU wall per batch: WebGL 8.1 ms (submit → blit done), WR 15.8 ms median (submit → main done, 3–4 jobs).

Representative frame (t = 3270.000 s + ms):

```
  8.2  zfq0 submits WR batch (2048² ×2, 1024×512, 2048×1536)  ── GPU busy 8.2 → 29.8 (WR, then labwc 27027)
 44.3  zfq0 submits WebGL draw + blit (FF#2105/6)              ── GPU busy 44.6 → 52.9
 52.9 ─ GPU IDLE 19.5 ms (labwc job 72.4–77.3 only) ─────────────────────────────────────────────
 75.4  zfq0 XFER cpu 1.46 ms (2048×32 RGBA32UI copy)
 81.9–91.3  Renderer ⇄ zfq0 ping-pong: 6 transfer-only submits (0.3 ms CPU each, 1–2 ms apart),
            Renderer observes each zink timeline point before the next
 98.6 ─ GPU IDLE ends: WebGL batch FF#2107/8
100.5  XFER **waits 5.26 ms for the WebGL jobs** (an unrelated context), copies 0.09 ms
106.0  WR batch FF#2109–2112 submitted (could have been queued at 100.5)
115.5  XFER **waits 11.6 ms** (WR jobs drain), then copies 0.83 ms; zfq0 blocked the whole time
128.3  GPU idle again; 129.7 / 137.2 more transfer-only submits (0.37, 2.36 ms CPU)
140.1  next WR composite
```

GPU-idle gaps by the job that ended them and the job that started next (570 frames) [V]:

| previous → next job | n | ms/frame | median gap | who runs in the gap (thread-CPU ms per gap-second) |
|---|---:|---:|---:|---|
| labwc → WebGL | 384 | **4.84** | 4.6 | firefox main 172, gdrv0 libc 132, zfq0 transfer 55 + submit 48, Renderer zink 48 |
| labwc → labwc | 208 | 3.20 | 8.2 | firefox main 183, gdrv0 72+72, labwc 72 (compositor-paced, no Firefox job) |
| blit (WebGL done) → WR 2048² | 163 | **2.04** | 2.25 | firefox main 278, zfq0 submit 96, **Renderer load-op compile 87**, zfq0 transfer 61 |
| labwc → WR main / WR 2048² | 184 | 3.07 | 4.8–5.6 | firefox main, gdrv0, Renderer (load-op 21–66), zfq0 transfer 79 |
| WR main → labwc | 238 | 1.54 | 2.8 | firefox main 218, Isolated Web Content 195, zfq0 transfer 138, labwc 115 |
| blit → labwc | 118 | 1.04 | 2.1 | |
| others | | 1.1 | | |
| **total** | | **16.85** | | |

Thread on-CPU share during GPU-idle vs GPU-busy [D, perf 99 Hz]: firefox main 24 % vs 18 %, gdrv0 17 vs 14,
zfq0 14 vs 13, Renderer 11 vs 9, CanvasRenderer 8 vs 11, Isolated Web Content 5 vs 18 (JS overlaps the GPU),
labwc 5 vs 11.

## 2. Symbolized hot paths (driver vs Firefox) [V]

Symbolization: perf 7.3.1 unpacked in container `linux-a9-r39-6b` (`/tmp/a2idle/root`, not installed system-wide).
symfs uses build-ID-matched libraries: our `libvulkan_powervr_mesa.so` `a4880fe3…` (`/port-submit/build`, symtab
intact), and the container's libc `d04ac300…`, libgallium `4ff85259…` (dynsym only), libstdc++, libm, wayland, etc.
Firefox 158 libxul is not available (the repo has 159), so Firefox work is attributed by thread only. Kernel samples
are attributed by their user caller (no System.map for the T3 kernel). Per-frame figure = samples × 10.1 ms / 570.

### 2.1 zfq0 (327 samples, 5.8 ms/frame)

| path | ms/frame | class |
|---|---:|---|
| `vk_common_QueueSubmit → pvr_driver_queue_submit` total | 3.6 | |
| … `pvr_rogue_g5p_transfer_submit → g5p_run → g5p_copy → memcpy` | 1.3 | **driver CPU copy** |
| … `fprintf` (`G5P perf transfer-cmd`/`transfer` lines) | 0.48 | debug path (PERF_LOG=2) |
| … `drmSyncobjWait` inside transfer submit (on-CPU part; the wall time is 8.7 ms/frame) | 0.05 | **driver sync** |
| … `g5p_drm_submit_render_typed` ioctl (kernel) | 0.6 | submit |
| … `g5p_ws_null_job_submit → drmSyncobjTransfer` (barrier and merge null jobs) | 0.5 | syncobj churn |
| … syncobj create/destroy/signal/export | 0.3 | syncobj churn |
| `vk_common_ResetCommandPool → pvr_cmd_buffer_free_resources → pvr_bo_suballoc_free` (LL/SC atomics) | 0.69 | cmdbuf reset |
| libc LL/SC lock/unlock helpers (callers lost in unwinding) | 0.5 | locks |

Transfer accounting from the driver's own log (wall clock, 570 frames) [V]: **4.81 transfer submits/frame, CPU copy
4.71 ms/frame wall, host wait 8.71 ms/frame wall**. 1.16 waits/frame exceed 1 ms (mean 7.5 ms). 3.74 of the 4.81 carry
no GPU job (the Renderer ping-pong). CPU-copy wall time inside GPU-idle gaps: **3.28 ms/frame**. What the long waits
waited on, classified by the job that signalled at wait end [D]:
- WR copy waiting on WebGL jobs: 3.0 ms/frame;
- WebGL-batch copy waiting on WR main: 2.6 ms/frame;
- copy waiting on labwc jobs: 1.9 ms/frame;
- same-stream waits: 0.9 ms/frame.

Most of this is cross-context, i.e. the false dependency described in §3 D1.

Syncobj objects: 109 136 chain-node inits + 80 046 stub fences on zfq0 in 25 s = **191 + 140 per frame** [V trace].

### 2.2 gdrv0 (374 samples, 6.6 ms/frame), WebGL command recording

| path | ms/frame | class |
|---|---:|---|
| `pvr_rogue_CmdDrawIndexed` inclusive | 2.6 | per-draw |
| … `pvr_rogue_g5p_perf_draw → note_read` (BO read set for cache maintenance, linear search per draw) | 0.71 | per-draw tracking, always on |
| … `pvr_bo_suballoc` (`pvr_gpu_upload_pds`, `upload_general`; `__aarch64_ldadd4_acq_rel`) | 0.71 | per-draw uploads |
| libc `__aarch64_swp4_rel`/`pthread_mutex_lock` LL/SC loops (A9 has no LSE; callers lost, adjacent to suballoc) | 1.56 | locks/atomics |
| `pvr_rogue_CmdBeginRendering → load-op compile` | 0.50 | D3 |
| libgallium (Zink/tc) + no-stack samples | 1.4 | Firefox/Zink |

### 2.3 Renderer (243, 4.3 ms/frame) and CanvasRenderer (239, 4.2 ms/frame)

- Renderer: **`pvr_rogue_CmdBeginRendering → pvr_rogue_mrt_load_ops_setup → pvr_rogue_load_op_shader_generate →
  pvr_uscgen_loadop → build_shader → NIR→PCO compile`: 50 samples, 0.89 ms/frame (20.6 % of the thread)**.
  Zink/gallium self 1.28, present 0.21, the rest Firefox/no-stack.
- Combined with gdrv0, the load-op compile costs 1.4 ms/frame, for 1.92 LOAD renders/frame (WR main 2048×1536,
  half the WR 2048², WR 1024×512 per the `job` lines).
- CanvasRenderer: Zink/gallium 1.3 ms/frame, no-stack 1.5, driver < 0.4 (a few draws, meta blit). Mostly Firefox/Zink.

`pvr_arch_load_op_shader_generate` has no cache. More importantly, **G5P never reads its output**:
`pvr_arch_cmd_buffer.c` builds the background object in `pvr_arch_g5p_job_init()`, and the
`hw_render->load_op_state` branch is skipped for `apple_g5p` [V `pvr_arch_cmd_buffer.c:1740-1744`]. G9P already returns
early in `pvr_arch_mrt_load_ops_setup()` for the same reason [V `pvr_arch_mrt.c`].

## 3. Ranked causes, with evidence

**D1, CPU transfer path (largest driver cause).** In steady state Aquarium every CPU transfer is a buffer→buffer
`vkCmdCopyBuffer` laid out as RGBA32UI rows (3.84/frame 2048×32 = 1 MiB, plus 8×1, 1024×1, 4×1 tails). These are
Zink's staging→buffer uploads for WebRender's buffers.

`pvr_process_transfer_cmds` → `pvr_arch_g5p_transfer_submit` host-waits `next_job_wait_sync[TRANSFER]`, which is the
barrier null-job over every earlier job of the barrier's source stages on the queue. Zink's single VkQueue carries
both Firefox contexts, so a WR copy waits for WebGL jobs and vice versa. Then it memcpys on zfq0.

Two effects:
1. Nothing behind it can be queued while zfq0 waits. When the GPU drains, the next job is published only after the
   copy plus ~1 ms of firmware TA latency (A2 §1).
2. The copy's wall time lands inside GPU idle: 3.28 ms/frame.

Bubbles: 1.16/frame × (submit + firmware start ≈ 1.2 ms) ≈ 1.4 ms/frame. **≈4.7 ms/frame attributable** [D].

**D2, per-draw recording**, 4.0 ms/frame CPU on gdrv0. gdrv0 is the third most frequent thread in the last 3 ms
before a WebGL submit (16 samples, behind zfq0 28 and Renderer 20). So it is partly on the critical path. Upper bound
2.5 ms/frame [D]. Fix direction (not specced here): per-cmd-buffer upload arena without per-upload atomics/mutex;
`note_read` via BO-generation cache instead of a linear scan + `pvr_g5p_winsys_bo_range` per draw.

**D3, load-op compile:** 1.4 ms/frame CPU, ≤0.5 ms/frame GPU idle (Renderer's load-op samples inside idle gaps).
One-line fix, §4.2.

**D4, submit-path churn:** 2.8 ms/frame CPU on zfq0 (ioctls, ~330 fence objects/frame, cmdbuf reset). About
0.7 ms/frame falls inside idle.

**Firefox/compositor (not driver):**
- labwc→WebGL 4.8 ms/frame: next rAF, JS, WebGL IPC, recording.
- labwc→labwc 3.2 ms/frame: an extra labwc composite with no Firefox job, 39 Hz vs 22.8 Hz.
- WR→labwc 1.5 ms/frame: present round trip.
- Firefox parent main thread: 8.9 ms/frame CPU, the busiest thread, unsymbolized.

The driver items above sit inside these gaps. Removing them shortens the chain but does not remove Firefox's stage
latency.

Projected ceiling if D1–D4 vanish: idle 16.9 → ≈9–10 ms/frame, frame ≈36 ms (≈27–28 fps) [I]. Lane A2 F5 hides
≈1 ms/job of firmware latency inside the busy part on top of that.

## 4. Fix spec (implementer: Codex. **No new tests, no gates. Build and stop.**)

Branch from `g5p-port-submit` (`aec53763c59`), worktree `build/third_party/mesa-g5p-port-submit`. Build in Docker
`linux-a9-r39-6b` as `build/port-submit/REPORT.md` does (only `libvulkan_powervr_mesa.so`, keep the unstripped copy).

### 4.1 Commit 1: CPU-transfer quick wins

Exactly Stage 0 of `docs/gpu/gpu-transfer-path-spec.md` §3 (S0.1 logging gate, S0.2 BO-precise host wait).

### 4.2 Commit 2: skip the dead Rogue load-op compile on G5P

- `src/imagination/vulkan/pvr_arch_mrt.c`, `pvr_arch_mrt_load_ops_setup()`: after the
  `pvr_device_tile_buffer_ensure_cap()` block and the `pvr_rendering_info_needs_load()` early return, and before
  `pvr_mrt_add_missing_output_register_write()`, add:
  ```c
  /* G5P builds its LOAD background from its own programs (pvr_arch_g5p_job_init(),
   * g5p_load_background()); Rogue's load-op program was compiled and uploaded per
   * vkCmdBeginRendering and never read. */
  if (PVR_HAS_FEATURE(&device->pdevice->dev_info, apple_g5p))
     return VK_SUCCESS;
  ```
  `*load_op_state` stays NULL. The consumers already handle NULL:
  - `pvr_arch_mrt_load_op_state_cleanup()` returns on NULL;
  - `pvr_arch_cmd_buffer.c:1769` is skipped for G5P.
- `src/imagination/vulkan/pvr_arch_pass.c`, the two `pvr_arch_load_op_shader_generate()` call sites (lines ≈210, ≈330,
  render-pass creation): same guard before the generate call, returning VK_SUCCESS with the load op left without
  programs. This is cold, but keeps G5P from compiling programs it never uses.
- Expected: Renderer −0.9 ms/frame, gdrv0 −0.5 ms/frame CPU; up to −0.5 ms/frame GPU idle.
- Smoke: Aquarium 500 renders, fps logged.

## 5. Orchestrator asks (device captures)

**A1, off-CPU critical path (settles who each idle gap waits on).** The Renderer ⇄ zfq0 ping-pong and the
labwc→WebGL gap need sched events and Zink symbols.
1. Build an unstripped `libgallium` from the port-submit tree in `linux-a9-r39-6b`:
   `cd /port-submit/build && ninja src/gallium/targets/dri/libgallium-27.0.0-devel-arch1.9.1.so`.
   Stage it next to the ICD as `/var/tmp/port-submit/lib/` and add `LD_LIBRARY_PATH=/var/tmp/port-submit/lib` to the
   launcher.
2. Make the harness's trace events extensible. In `scripts/gpu/perf-aquarium-icd.sh`, change
   `-e dma_fence -e drm` to `-e dma_fence -e drm ${TRACE_EXTRA:-}`.
3. Run:
   *(Device/host command block omitted; it targets the private workspace.)*
   Pull it into `build/gpu/perf-portsubmit-sched-20261110/`.
   - `PVR_G5P_PERF_LOG=1` removes the per-transfer fprintf artifact.
   - The CPU-transfer numbers then come from the Stage-0 aggregated summary line, or from a second run at level 2.

**A2, before/after for commits 1–2:** the same command with the new ICD, labels `s0-500` and `s0lo-500`. Around each run, dump
`S=$(ls /sys/kernel/debug/dri/*/g5p_gpu_stats | head -1)` and `${S%/*}/g5p_jobtimes` with `sudo cat`, as in
`build/port-submit/DEVICE-COMMANDS.txt` lines 55–69. Report GPU ms/frame and busy % from those (the Lane A2 method),
fps, and GPU-idle ms/frame (`/tmp/a2idle/py/gapkind.py` on the trace).

## 6. Reproduction (host)

Scripts used (scratch, not committed): `/tmp/a2idle/py/{samples,rank,gaps,gapkind,cycle,idlewho,prewebgl,overlap,
waiton,frame,stages}.py`. The container perf is at `/tmp/a2idle/root/usr/bin/perf` (with
`LD_LIBRARY_PATH=/tmp/a2idle/root/usr/lib`), symfs `/tmp/a2idle/symfs`.

*(Device/host command block omitted; it targets the private workspace.)*

## Result: baseline for commits 1–2 (orchestrator, 2026-11-09 17:10 UTC)

Setup: kernel `vdm-f5-20261109`, depth 2, joint=1. ICD `g5p-port-submit-b2` (sha256 `c2f0aaa4…`), staged in
`/var/tmp/aq-base`. Env: `SERIAL_SUBMITS=0 VS_INLINE_UNIFORMS=0 PERF_LOG=1`, with sched events. Data:
`build/gpu/aq-s0-20261109/base-sched-500/`. Summary: `scripts/gpu/aq-idle-summary.py DIR 26`.

- 26.0 fps median (min 12, max 36), 38.5 ms/frame.
- 5.19 jobs/frame.
- GPU 2.97 ms/job mean, about **15.4 GPU ms/frame**.
- A fence is outstanding 58.9 % of the time. **GPU idle 15.8 ms/frame** (41 %). The earlier capture at
  PERF_LOG=2 gave 16.9 ms/frame.
- The gap between outstanding (22.7 ms/frame) and executing (15.4 ms/frame) is about 7 ms/frame. That is the
  firmware/kick latency inside jobs (Lane A2, about 1.4 ms/job).

The after-run uses the same command, with `LAUNCHER=/var/tmp/aq-s0/firefox` and label `s0-sched-500`.

## Result: S0 + load-op skip on device (orchestrator, 2026-11-09 17:25 UTC)

ICD: Mesa `g5p-aq-s0`, commits `4af93fdd5e0` (S0.1 + S0.2 with the amendments) and `12ed2523de9` (load-op skip),
sha256 `1c5aa4dd…`, staged in `/var/tmp/aq-s0`. Same kernel, env and command as the baseline. Data:
`build/gpu/aq-s0-20261109/s0c-sched-500/`.

| Aquarium 500 | baseline (b2) | S0 | Δ |
|---|---:|---:|---:|
| fps median | 26.0 | 29.0 | +12 % |
| GPU jobs/s | 135.0 | 144.5 | +7 % |
| GPU ms/job (mean) | 2.97 | 2.97 | 0 |
| GPU busy (executing) | 15.4 ms/frame, 40 % | 14.8 ms/frame, 43 % | |
| GPU idle (no fence outstanding) | 15.8 ms/frame, 41 % | 12.6 ms/frame, 36.5 % | −3.2 ms/frame |

- Copy waits at PERF_LOG=2 (diagnostic run): about 2.6 waits kept and 1.4 skipped per transfer. The wait is still
  0.8–2.6 ms per transfer, so it is narrowed but not gone. The CPU memcpy itself is untouched (Stage 1).
- Stability: no GPU fault, refusal or recovery in any run. One early run sat at 1 fps from page load. The device's
  root disk was found full (4.2 MB free) during the next run, because every Aquarium run leaves a ~210 MB Firefox
  profile. Two later S0 runs, one at PERF_LOG=2 and one after cleanup, did not stall. The stall is attributed to the
  full disk, which is likely but not proven. The harness now refuses to start below 1 GiB free and deletes the profile.
- Next in this lane: Stage 1 of `gpu-transfer-path-spec.md` (buffer copies on the GPU), which removes the remaining
  copy wait and the ≈3.3 ms/frame memcpy.

## Result: Stage 1 GPU buffer copies on device (orchestrator, 2026-11-09 ≈17:50 UTC)

ICD: Mesa `g5p-aq-s1` `1bbd0d4805f` (S0 + load-op skip + Stage 1 with the exact-extent amendment), sha256 `7fa61d32…`.
Same kernel (F5, depth 2), env and harness. Data: `build/gpu/aq-s0-20261109/s1g{0,1}-sched-500/`.

| Aquarium 500 | GPU_COPY=0 | GPU_COPY=1 |
|---|---:|---:|
| fps median | 28.0 | 25.0 |
| jobs/frame | 5.2 | 9.1 |
| GPU ms/job (median / mean) | 3.24 / 2.98 | 1.07 / 2.00 |
| GPU ms/frame | 15.6 | 18.3 |
| GPU idle ms/frame | 12.7 | 10.2 |

- GPU copies work: no fault, refusal or recovery, and the scene renders. They **lose 3 fps**. Each copy becomes its own
  TA+3D job, with about 3.9 extra jobs/frame. Each pays about 0.7–1 ms of fixed firmware latency for microseconds of
  real work. That adds about +2.7 GPU ms/frame, which costs more than the 2.5 ms/frame of idle time it removes.
- This is the spec's cost model. `PVR_G5P_GPU_COPY` stays default **0**. It becomes a win when either:
  - F5b lets a copy job's TA overlap the previous 3D; or
  - Stage 1c makes copies 3D-only, which needs the P1 iOS probe: do Metal blits kick only the 3D channel?
- Re-measure GPU_COPY=1 on the F5b kernel.

## Result: vsync pacing test (orchestrator, 2026-11-09 ≈20:20 UTC)

Kernel f5c, full private stack. Same boot, same harness, no sched events. Launcher `/var/tmp/f5b/firefox-z-asap`
adds `user_pref("layout.frame_rate", 0)` (ASAP refresh driver).

| arm | fps median | GPU jobs | TA+3D ticks |
|---|---:|---:|---:|
| ASAP (`layout.frame_rate=0`) | **23.0** | 9632 | 726 M |
| vsync-paced (default) | **28.5** | 12082 | 898 M |

- **Unpacing makes it slower, not faster.** Vsync quantization is not what limits Aquarium.
- With ASAP, Firefox's refresh driver runs as often as it can and competes for the A9's two cores. Fewer GPU jobs get
  produced. So the frame chain is sensitive to CPU contention: CPU time saved anywhere on these threads should turn
  into fps.
- This supports the CPU critical-path lane (`aquarium-cpu-critical-path-spec.md`, in progress): cut driver CPU
  (per-draw recording, submit churn, CPU copies) rather than chase GPU-side or pacing waits.
