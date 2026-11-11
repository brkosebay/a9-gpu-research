# Lane FIF: keep the G5P fed between frames (2026-11-11, Opus 5.5)

*(Passage removed: boot-chain or iOS-side tooling detail, out of scope for this repository.)*

| What | Value |
|---|---|
| Mesa branch | `fif/frames-in-flight` in `build/orchard-0.4/prep/mesa` |
| Mesa head | `7c2cc5b70af10cb4a2e6f7bd64f57e342f8cadd6`: two commits (`2b48dbd9b28` change, `7c2cc5b70af` off-switch fix) on `publish04/rc2` `4543c70aef091b5ec61cde1a4f85a7b35731dea0`. The checkout is back on `publish04/rc2`. |
| Kernel | unchanged (rc2 `7.3.0-rc1-orchard-apple-16k-topic-rc2`) |
| Switch | `PVR_G5P_FRAMES_IN_FLIGHT` = 2 (default) / 3; **0 or 1 = rc2 behaviour**, read per process |

## 0. Bottom line

- **The main limiter is ours, in userspace.** GL's swap throttle waits for the *previous* frame
  (`dri_flush` / `kopper`: one frame in flight). The CPU therefore starts recording frame N+2 only after N has
  retired. The firmware's rings then empty between frames, and the firmware parks with no hold-off.
- **The h3 per-job stats (glmark2 build, 3 runs) show it:**
  - 69–70 % of jobs reach TA completion with no successor queued (`aheadwhy[10]`);
  - 26 % still have none when their 3D ends, so the next job wakes a parked GPU;
  - the GPU is 60–61 % busy.
- **The fix:** Zink on G5P lets two frames be in flight (`pipe_caps.throttle_frames`). Kopper asks for enough
  swapchain images that an acquire doesn't re-impose the old pacing. In the winsys, a full kernel queue now
  waits for the job 8 back instead of draining the context.
- **Expected:** glmark2 build 431–438 → about 520–550 fps: the 391 µs/job average wake goes, which lands at
  the never-parked 543. Upside is about 600 if back-to-back jobs also overlap better. Both hold only if the
  CPU's frame time stays below the GPU's.
- **iOS [P]:** at 60 Hz Safari WebGL, iOS also parks about once per frame. It doesn't park between a frame's
  jobs.

## 1. Apple: how iOS keeps the A9 fed

| # | Finding | Grade |
|---|---|---|
| A1 | `AGXChannelQueue_submitBlockInvoke` (`fffffff006cbb948`) writes each submission into the channel's firmware ring: 16-byte entries at `ch[0x19]`, write index `ch+0xd4`, modulo `ch+0x4c`. It **kicks the firmware at once** (`ff2ca0` member table → `submitTAChannelToFirmware` `c86454` / 3D `c86510`). It defers only while the queue's pending list (`queue+0xd0`) is non-empty or the queue is blocked (`+0x4c`). There is no wait for an earlier job's retire. The ring size comes from `AGXChannel_initFirmwareQueue` (`c89420`: `ch+0x48` → queue header `+0x14`). | [V] Ghidra (this lane re-read; matches lane-a2 §3) |
| A2 | A ParamBuffer per prepare from a 127-entry pool (`6cb9afc`). So TA N+1 builds while 3D N runs, and many TAs can be in flight. | [V] earlier lanes |
| A3 | The firmware's idle tail parks as soon as the engines are idle and every root ring is empty. There is no hold-off (`0x10009bd8`, lane IP §1.1). iOS runs this same firmware with `ctrl+0x20 = 1`. | [V] lane IP |
| A4 | **iOS parks mid-animation at 60 Hz, once per frame.** Data: Safari WebGL Aquarium, 2026-11-09 run `build/gpu/apple-idle-power/20261109T123520Z/device/ioreport-safari`, 134 steady 119 ms samples. Per sample: 14 TA submits (≈118/s, 2 per frame); GPU performance state OFF entered **7–9 times** (≈60–75/s, about one per frame); OFF residency **median 53 %**. So iOS doesn't keep the rings non-empty across vsync idle: it pays one wake per frame, at the frame's first job, not per job. | [P] numbers; [I] IOReport element layout (value[1] = entries, value[2] = residency). The same decode reads "Fender State" as always OFF, which is implausible, so that channel isn't used. |
| A5 | Metal apps keep up to 3 drawables (`CAMetalLayer.maximumDrawableCount`) and many command buffers per queue. A non-vsync'd Metal load therefore has the next frame queued while one runs. | [I] public API defaults, not read in this kernelcache |

**Not settled:** does iOS park between back-to-back command buffers when two or three are in flight and nothing
waits for vsync? The Safari timeline in that run was refused (0 samples) and kdebug recorded 0 events, so the
IOReport sampler is the readout. An iOS-side probe for it is prepared.
- It runs `metal-triangle --inflight 1` against `--inflight 3` (new option, default 1 = old behaviour) at
  1536×2048, 2000 triangles, no sleep, 12 s per arm, ×2.
- **Predicted [I]:** with 3 in flight, OFF entries per TA submit fall from about 1 to about 0 and OFF share to
  about 0. With 1 in flight, about 1 park per command buffer.

## 2. Serialization map: what stops job N+1 being queued before N completes

h3, glmark2 build fullscreen, state 12, rc2 Mesa (`build/orchard-0.4/integration/flight-h3/bell/run{1,2,3}.stats`).
Per job, µs:

| run | jobs/s | TA | 3D | busy | ahead | none at TA done | ioctl | queue | prep | TA wait | 3D wait | tail | host touch | bell | wall |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| run1 | 480 | 103 | 1159 | 61 % | 74 % | 70 % | 43 | 1547 | 172 | 1265 | 1300 | 151 | 270 | 2.4 | 2083 |
| run2 | 474 | 103 | 1155 | 60 % | 74 % | 69 % | 46 | 1584 | 174 | 1256 | 1308 | 152 | 275 | 2.5 | 2110 |
| run3 | 474 | 102 | 1159 | 60 % | 73 % | 69 % | 43 | 1571 | 178 | 1261 | 1297 | 156 | 277 | 2.5 | 2110 |
| opt1 no park (F1) | | 200 | 1098 | | | | | 1072 | | 865 | | | | 1 | (543 fps) |

The ahead column is about 29 % started at N's TA completion plus about 44 % from N's 3D wait (F5c). Every job
not started ahead (26 %) found the context queue empty when its predecessor's 3D ended.

**Ranked, by how much each one empties the queue in steady state:**

1. **GL swap throttle, one frame in flight.** Mesa gallium/dri `dri_flush()` and `kopper_flush_frontbuffer()`
   call `fence_finish(previous frame)` on every SwapBuffers (`pipe_caps.throttle`, on for Zink). The next
   frame's first job arrives one CPU recording time after the previous frame retired.
   - glmark2: 69 % of jobs have no successor queued at TA completion, and 26 % none at 3D completion. Those 26 %
     pay the firmware wake: TA wait 1256–1265 µs against 865 µs never-parked (+0.4 ms average), or about 1.5 ms
     for each woken job.
   - **This lane removes it** (§3).
2. **Firmware self-park, no hold-off (A3).** Not a serializer by itself: it turns every empty-queue moment into
   a GPC power-on plus firmware restart (≈0.55 ms power-on alone, `on_ns=550375`). It is Apple's behaviour
   (A4). The fix is keeping the queue non-empty, not a hold-off.
3. **Kernel F5 depth 2** (`drm-render-v3.inc`).
   - N+1 is published (TA+3D joint) only once N's TA completes, and is re-tried from N's 3D wait. It is never
     across contexts. Today that is not the limit: when a successor exists, it is started.
   - **Next limit once userspace queues deeper: `G5P_RV3_AHEAD_CHAIN 8`.** After 8 consecutive ahead starts,
     one job retires with the core lock released. The next job is then picked serially, the rings empty briefly
     (retire + pick + prep, about 0.3 ms), and the firmware parks: about one wake per 9 jobs, ≈ +0.12 ms/job
     average.
   - Today it fires 13–24 times per 10 s (`aheadwhy[7]`). With FIF=2 it should fire on about every 9th job.
   - The chain does two jobs. It lets a VM bind or idle step that waits for the core lock run. It is also the
     only point where **another context's job** gets picked: the worker runs `rd->ahead` before
     `g5p_rs_pick`. So a fix must break the chain when a lock waiter exists *or* another entity has a ready
     job, never only the former, or labwc starves behind a client.
   - **Watch item for FIF=2:** a compositor job can now wait behind up to 8 client jobs (≈ 8 × 1.3 ms at
     glmark2 rates).
4. **Winsys full-queue backpressure** (`pvr_g5p_winsys.c`). The kernel refuses a 17th queued job per context
   (`G5P_RU_MAX_QUEUED 16`). The winsys then waited for the context's **last** job (a full drain → empty rings →
   park) and slept 1 ms. A 9-job video frame with two frames queued (18) would hit it.
   - **This lane changes it** to wait for the job 8 submissions back (§3).
   - Counted on device by `PVR_G5P_WAITLOG=1` "G5P wait: backpressure".
5. **Render-target edits drain the context** (`g5p_render_vm_idle(c, false)`, kernel `drm-render.inc:552`).
   - **VM binds don't drain.** Own-BO create/destroy and dmabuf import run beside queued jobs once a job has
     retired on the binding (`live && r->live_maps`). Only before the first retire, during a recovery, or for a
     bad context are they refused.
   - `CREATE_RENDER_TARGET` and destroy need `queued == 0`. `g5p_ws_rt_create_idle` then waits for the
     context's last job, a full drain. Targets are pooled by size, so this happens on a new size (window resize,
     a new canvas or video size), not per frame.
   - Counted on device: "G5P wait: vm-edit" (BO paths, expected about 0 in steady state) and `PVR_G5P_WS_LOG`
     "CREATE_RENDER_TARGET … waited".
6. **CPU transfers inside `vkQueueSubmit`.** G5P transfers run on the CPU; `g5p_transfer_submit()` waits for the
   GPU jobs whose ranges overlap, then copies. The GPU idles behind the CPU copy.
   - Firefox's `zfq0` queue thread is CPU-bound, about 50 ms CPU/frame in HW WebRender (webgl-perf-r39-8). That
     is the Aquarium-in-Firefox limit, not frames in flight.
   - Separate lane: GPU transfers, `gpu-transfer-path-spec.md`.
7. **Ruled out:**
   - Mesa's per-submit CPU wait: Henrik's `fd62672cee` is ported for G5P as `bb51b7b4f25` (`pvr_clear_last_submits_syncs()`
     returns early on G5P; `PVR_G5P_SERIAL_SUBMITS=1` restores it).
   - Henrik's stride-copy wait: `g9p_realigns` is filled only by `pvr_arch_g9p_gfx.c`, so it never fires on G5P.
   - Zink's implicit-sync wait before present: off for `VK_DRIVER_ID_IMAGINATION_OPEN_SOURCE_MESA`.
   - Zink's batch throttle: only above 5000 states.
   - ZINK precise sync: barriers only, no waits.
   - Submit ioctl (43–46 µs) and bell (2.5 µs).
   - The kernel's 275 µs/job host "touch" (cache visibility sweep in the sampler) is executor CPU that overlaps
     the GPU. It is listed for the per-job host-cost lane, not this one.

## 3. The change (Mesa `2b48dbd9b28` + `7c2cc5b70af`, G5P-gated)

| File | Change |
|---|---|
| `src/gallium/include/pipe/p_defines.h`, `auxiliary/util/u_screen.c`, `docs/gallium/screen.rst` | New `pipe_caps.throttle_frames`, default 1. |
| `src/gallium/frontends/dri/dri_drawable.{c,h}`, `dri_screen.{c,h}`, `kopper.c` | `throttle_fence` becomes a ring of `DRI_THROTTLE_MAX_FRAMES` (3). `dri_throttle_frame()` waits for the frame `throttle_frames` swaps back, then stores the new fence. All three users are converted: `dri_flush`, `kopper_flush_frontbuffer` and drawable destroy. With 1 (every non-G5P driver) it is byte-for-byte today's wait. |
| `src/gallium/drivers/zink/zink_screen.c`, `zink_types.h` | On G5P, `frames_in_flight = CLAMP(PVR_G5P_FRAMES_IN_FLIGHT, 1, 3)`, default 2, exposed as `throttle_frames`. Other drivers: 1. |
| `src/gallium/drivers/zink/zink_kopper.c` | With frames > 1, the swapchain asks for `max(minImageCount, frames + 2)` images (capped by `maxImageCount`): one per frame in flight, one shown, one drawn. Wayland WSI already gives 4 without a FIFO-protocol compositor, so this costs one 12.6 MB image (1536×2048) per Zink window only when labwc advertises `wp_fifo_v1`. |
| `src/imagination/vulkan/winsys/apple_g5p/pvr_g5p_winsys.c` | With frames > 1, each context keeps a ring of 8 syncobjs (one `SYNCOBJ_TRANSFER` per accepted job, ≈ a few µs). On EBUSY the submit waits for the oldest of them, then retries at once if that wait blocked. Jobs of one context complete in order, so the queue is then at most 8 deep, never empty. VM-edit retries keep the full drain (they need an idle context). |

**Correctness:**
- **Fences and implicit sync:** unchanged. Every job still signals its own syncobj and the kernel's dma_resv
  fence, which is what the compositor waits on. Presenting frame N+1 before N completes already happens on rc2.
- **Lost context:** a lost batch's fence still completes `fence_finish`, so an older slot gives the same result
  one frame later. The recent-ring wait has the same 2 s deadline and EBUSY/DEVICE_LOST mapping as before.
- **Off switch:** `PVR_G5P_FRAMES_IN_FLIGHT=0`/`1` restores rc2's throttle, image count and backpressure wait
  (the context's last job, then a 1 ms sleep) in that process. `7c2cc5b70af` makes the backpressure part exact.
- **Render-target starvation risk:** with two frames in flight, a context goes idle less often. One submitting
  thread converges: it is the thread that creates the target, so its queue drains while it waits. A process with
  several GL contexts on one winsys context (Firefox: WebRender plus a WebGL canvas thread) could keep the queue
  non-empty for the 2 s bound, and a new target size would then fail with `VK_ERROR_OUT_OF_DEVICE_MEMORY` and
  lose that context. Not observed, not testable on the host. It is a stop condition in §5.

**Build:**
- `scripts/gpu/g5p-stage-at-commit.py 7c2cc5b70af --container linux-a9-fif-build` (own container from
  `linux-a9-vdm-zink-seed:20261108`, removed afterwards): rc=0, 1,421/1,421 steps.
- The first build at `2b48dbd9b28` was also clean, with no warnings in the touched files. Its stage was
  superseded and deleted.
- `libvulkan_powervr_mesa.so` and `libgallium-27.0.0-devel.so` report `git-7c2cc5b70a` and carry the switch
  string.
- Before building: host 70 GiB free, Docker VM 21 GiB.

## 6. Expected gain and where the time goes next

| Workload | rc2 (h3/owner) | Expected with FIF=2 | Why |
|---|---|---|---|
| glmark2 build | 431–438 fps; GPU 60 % busy; 2.11 ms wall/job, 1.26 ms GPU/job | **≈520–550 fps** (+20–25 %), busy ≈75 %; upside ≈600 | Removing the average wake (TA wait 1256 → 865 µs, −391 µs/job) gives 1.72 ms/job, about 528 fps at 1.10 jobs/frame, next to the never-parked 543. Upside: depth-2 overlap ceiling ≈ 3D 1.16 + about 0.2 ms per job (≈620–670 fps), minus the chain-8 wake (≈0.12 ms/job). Requires CPU frame time < GPU frame time; if not, fif2's `nonext` stays high and the CPU is the next limit. |
| glmark2 other high-fps scenes | per census | same direction | Same mechanism. |
| Desktop/compositor at 60 Hz | GPU idle between frames | ≈ no change | Like iOS (A4): one park per vsync'd frame is the Apple way. Only frames over budget gain. |
| Firefox Aquarium 500 | CPU-bound (`zfq0` ≈ 50 ms/frame, r39-8) | ≈ no change | Item 6 (CPU transfers in vkQueueSubmit) is the limit. |
| YouTube / 1080p H.264 (≈9 jobs/frame, 269 jobs/s, 58 % busy) | not steady 60 | small, unless item 4 fires | The 18-job two-frame queue no longer drains on EBUSY. In-frame gaps are then CPU-side (item 6 and Firefox's own threads), since dmabuf imports are live binds. F4/F5's wait counts and busy % decide. |

**Next targets, in order:**
1. Kernel: break the F5 ahead chain only when a core-lock waiter exists or another context has a ready job
   (§2 item 3). Never the first condition alone.
2. Render-target create/destroy beside queued jobs (item 5), if F4/F5 or the WS log show those waits.
3. GPU transfers instead of CPU copies inside vkQueueSubmit (item 6, Firefox).
4. The firmware's per-job TA latency (TA wait 865 µs against 200 µs of TA work even never-parked), which
   lane-a2's iOS probe still has to compare with iOS.
