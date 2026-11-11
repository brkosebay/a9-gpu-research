# Heavy-workload census (2026-11-09, orchestrator)

Stack: kernel `vdm-f5c-20261109` (cold boot), Mesa `g5p-cpu1` (ICD `/var/tmp/cpu1`, private Zink GL stack
`/var/tmp/cpu1/mesa`). Zink reports **OpenGL ES 3.1**. Settings: depth 2, ordered_waits=1, job_time_log=0,
touch_live_pm=1. Script: `scripts/gpu/glm-census.sh` (one scene at a time, fullscreen 1536×2048, `g5p_gpu_stats`
around each).

## glmark2-es2-wayland, fullscreen

| scene | fps | GPU busy % | GPU ms/frame | jobs/frame | note |
|---|---:|---:|---:|---:|---|
| build | 305 | 68 | 2.32 | 1.18 | |
| texture | 290 | 72 | 2.55 | 1.19 | |
| shading | 296 | 75 | 2.61 | 1.18 | |
| bump | 319 | 71 | 2.29 | 1.18 | |
| effect2d | 257 | 81 | 3.22 | 1.20 | |
| pulsar | 308 | 70 | 2.32 | 1.18 | |
| **desktop** (blur, 4 windows) | **34** | 82 | **25.0** | **11.5** | many render-to-texture passes; per-pass cost |
| buffer (map) | 123 | 50 | 4.42 | 1.47 | CPU/upload-bound |
| ideas | 211 | 66 | 3.34 | 1.24 | |
| jellyfish | 228 | 84 | 4.08 | 1.21 | |
| **terrain** | **—** | — | — | — | **refused**: "a non-linear colour target (twiddled PBE is step 7)", then **hang** (main thread stuck in drm_syncobj wait, killed) |
| **shadow** | **84** | **89** | **11.0** | 3.25 | GPU-bound: shadow-map pass + sample |
| **refract** | **—** | — | — | — | **"zink: couldn't allocate memory: heap=0 size=89489408"**: the winsys arena is capped at 128 MiB |
| conditionals / function / loop | 295–312 | 69–76 | 2.3–2.6 | 1.18 | |

## vkmark (Vulkan direct, no Zink), fullscreen, `-p fifo`

Every scene sits at the 60 fps vsync cap, except `clear` at 50. Score 59. With fifo this says nothing about GPU
headroom; rerun with `-p immediate`.

## Bugs and targets found

1. **Hang after a refused command buffer** (terrain). A refusal must fail loudly, not strand a wait. Lane `fix1`.
2. **GPU memory capped at 128 MiB** (refract). Real apps and games need more. Lane `fix1`.
3. **Twiddled render targets unsupported** (terrain; plan step 7, transfer spec Stage 3). Blocks render-to-texture
   into tiled images. Next lane.
4. **Per-pass cost** (desktop: 11.5 jobs/frame, ~2.2 ms each). Heavy microbench pair (render-to-texture ping-pong,
   many small passes) measures it against iOS.
5. Simple scenes leave the GPU 25–30 % idle at ~300 fps: per-job fixed overhead (~1 ms) on 1.2 jobs/frame.

## vkmark, `-p immediate` (uncapped)

Score **303**. Per scene: vertex 354–358, texture 341–343 (16× aniso costs nothing), shading 308–355,
effect2d edge 300 / **blur 153**, desktop 293, cube 404, **clear 50 fps (20 ms)**.
- `clear` at 20 ms/frame is an outlier. A full-screen clear probably runs through the **CPU transfer path**
  (vkCmdClearColorImage → CPU fill), which is transfer spec Stage 4, "remaining classes". It should be a GPU clear.
- Blur at half of edge: sampling-heavy, so the heavy microbench (blur 9/13 taps) compares it against iOS.

## SuperTuxKart `--benchmark` (GLES 3.1 via Zink, private stack)

Starts and renders (renderer string `zink Vulkan 1.2 (PowerVR Apple A9)`), then **segfaults after 17 s** with 1321
`zink: couldn't allocate memory` errors (heap 0, ~1.4 MB; heap 4, ~1.0 MB). Same root as refract: the GPU memory
budget is exhausted. Lane `fix1` has this evidence.

## Rerun on f5d with `render_user_pm_record=1` (2026-11-09 ≈23:15 UTC)

Same census script, ICD `/var/tmp/cpu1`. Kernel f5d, tag6 only when dirty. No fault or recovery. terrain and refract
still fail: twiddled RT refused, and the cpu1 stack lacks fix1.

| scene | fps before (f5c) | fps f5d pm1 | Δ | GPU busy % now |
|---|---:|---:|---:|---:|
| build | 305 | 387 | +27 % | 81 |
| texture | 290 | 355 | +22 % | — |
| shading | 296 | 341 | +15 % | — |
| bump | 319 | 385 | +21 % | 82 |
| effect2d | 257 | 295 | +15 % | 90 |
| pulsar | 308 | 406 | +32 % | — |
| desktop (blur) | 34 | 39 | +15 % | 88 |
| buffer | 123 | 134 | +9 % | — |
| ideas | 211 | 284 | +35 % | 85 |
| jellyfish | 228 | 247 | +8 % | 95 |
| shadow | 84 | 89 | +6 % | 95 |
| conditionals / function / loop | 312 / 309 / 295 | 400 / 406 / 347 | +18–31 % | — |

Aquarium 500 on the same boot, alternating: pm1 31.0 / 33.0, pm0 32.0 / 31.0 (CPU-bound; within noise). Overall
Aquarium is now 31–33 fps, against 26 at the start of 2026-11-09.

**Decision: make `render_user_pm_record=1` the default** in the next kernel (one-line default change on
`a9/gpu-vdm-f5d-20261109`).
