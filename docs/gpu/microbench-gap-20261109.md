# GPU microbench gap: our driver vs iOS (2026-11-09)

Same tests, same sizes (1536×2048 BGRA8, 5 warmup + 30 measured, median), same output format.

- **iOS:** Metal, iOS 16.7, `tools/ios-gpu-microbench`, log `build/ios-gpu-microbench/run-ios-20261109T130009Z.log`. Timing: GPU timestamps (`GPUEndTime − GPUStartTime`).
- **Linux:** our PowerVR/G5P Vulkan driver as installed on the `orchard-vdm-long-20261108` entry (kernel `7.3.0-rc1-orchard-apple-16k-topic-vdm-warmport-20261108`, cold boot), `tools/linux-gpu-microbench`. Logs: `build/linux-gpu-microbench/device-20261109T133501Z/{run-graphics,run-load-upload}.log`.
- **Timing caveat:** our driver exposes no timestamp queries, so Linux numbers are `timing=fence-wall`: CPU wall time from `vkQueueSubmit` to the fence signal. That includes submit, kernel, firmware and wait overhead. iOS numbers are GPU-only. The fixed per-job overhead is therefore part of every Linux row.

| Test | iOS ms | Linux ms | Linux / iOS |
|---|---:|---:|---:|
| overhead empty_64x64 | 0.156 | 1.336 | 8.6× |
| clear_store | 1.025 | 2.612 | 2.5× |
| fill_opaque layers=1 | 1.110 | 2.789 | 2.5× |
| fill_opaque layers=4 | 1.061 | 2.789 | 2.6× |
| fill_opaque layers=16 | 2.146 | 2.657 | 1.2× |
| fill_blend layers=4 | 2.808 | 3.329 | 1.2× |
| tex_sample fetches=1 | 1.448 | 3.351 | 2.3× |
| tex_sample fetches=4 | 2.485 | 3.715 | 1.5× |
| alu 64 mads fp32x4 | 9.189 | 48.957 | **5.3×** (33 vs 175 GFLOP/s) |
| tris 1M | 19.591 | **TA fault** | — (device lost, kernel recovered in 236 ms) |
| load_action load | 1.029 | 2.787 | 2.7× |
| load_action clear | 1.013 | 2.767 | 2.7× |
| load_action dontcare | 1.016 | 2.886 | 2.8× |
| upload replace_region_2048 (CPU) | 5.295 | 3.401 | 0.6× (ours faster) |
| upload blit_buf2tex_2048 | 2.177 | 3.469 | 1.6× |
| compute stream_64MB_rw | 8.466 | not run | compute jobs don't retire yet |

## Reading

1. **Fixed per-job cost dominates small jobs.** An empty pass costs 1.34 ms against 0.16 ms. Every full-screen single-pass test sits at about 2.6–2.9 ms whatever it does (clear, load, don't-care, 1 or 4 opaque layers), while iOS is at about 1.0 ms. At 16 layers we're within 1.2× of iOS. So the GPU's raw fill rate is close; the floor of about 1.3–1.7 ms per job is ours (submit, kernel, firmware, completion path). Splitting it needs GPU timestamps in our driver.
2. **Shader arithmetic is about 5× slower:** 33 against 175 GFLOP/s, with the job overhead negligible at 49 ms. That's code quality in our compiler (pco/G5P) on the mad loop. It's the biggest throughput gap.
3. **Texture sampling:** 2.3× at 1 fetch per pixel, 1.5× at 4. Partly the per-job floor, partly the sampling path.
4. **1M triangles faults the TA:** a correctness bug on large geometry. It needs a fix before any geometry-throughput comparison.
5. Load, clear and don't-care cost the same on both sides, so tile load/store isn't where the time goes.

## Next targets

- **A. Per-job floor (1.3 ms → 0.16 ms):** add GPU start/end timestamps (Apple's way, from the kext) so job time splits into GPU and overhead, then cut the submit/kernel/firmware/completion path.
- **B. ALU codegen (5.3×):** compare our ISA for the mad loop with Apple's compiled `microbench.metal` for the same shader.
- **C. TA fault on 1M triangles.**
- **D. Compute retirement.**

## Result: Lane B F1+F2 (Mesa `g5p-laneb-f1f2@819833730a2`, on `0e178ff53d8e`), 2026-11-09

Same boot, same kernel, base ICD vs the F1/F2 ICD from `/var/tmp/laneb-f1f2` (logs `build/laneb-f1f2/device-*/{base,f1f2}.log`):

| Test | base ms | F1+F2 ms | iOS ms |
|---|---:|---:|---:|
| alu 64 mads fp32x4 | 48.82 (33.0 GFLOP/s) | **11.88 (135.5 GFLOP/s)** | 9.19 (175 GFLOP/s) |
| fill_opaque 1 / 4 / 16 | 2.88 / 2.78 / 2.89 | 2.72 / 2.69 / 2.91 | 1.11 / 1.06 / 2.15 |
| tex_sample 1 / 4 | 3.49 / 3.87 | 3.36 / 3.89 | 1.45 / 2.49 |

- `alu` is 4.1× faster. The ALU shader compiles to 269 instructions, fully unrolled (Apple: 261). The remaining ~2.7 ms over iOS is about the per-job floor (Lane A) plus wall-time vs GPU-time measurement.
- The other rows are unchanged within noise, and there were no GPU faults or recoveries.
- **Not default yet:** F1 and F2 change many fragment shaders, so they need the overnight CTS regression run before they replace the installed ICD.

### Correction: F1+F2 rebased onto the device's real base (r39-9.1)

The first F1+F2 build was on `0e178ff53d8e`, but the device runs r39-9.1 (Mesa head `728cde909c93`, library sha256 `144f5046…`). `0e178` copies buffer→image per texel on the CPU, so its `blit_buf2tex` read 50 ms. That was a base mismatch, not F1. Rebased build: `g5p-laneb-f1f2-r39@3e5f633a519`, library `76a1fcab…`; same boot, base vs F1+F2 (logs `build/laneb-f1f2/device-r39-*`):

| Test | base ms | F1+F2 ms |
|---|---:|---:|
| alu | 48.81 | **11.97** (4.08×) |
| blit_buf2tex_2048 | 3.50 | 3.55 |
| all other rows | — | within ±8% (noise) |

No GPU faults or recoveries. Still pending before it becomes the default: the overnight CTS regression run.

### Lane B2 Spec A (texture-sample batching, `g5p-laneb2-ab@9e3f3959a09`)

- `--check tex` (4-fetch output vs a CPU bilinear reference) **passes** on base, F1+F2 and A: `max_err=1 bad=0/4096` (nearest would give 70, a flipped V 101). The 4-fetch test really is bilinear.
- Timing, wall clock: tex1 3.46 / 3.35 / 3.42 ms, tex4 3.89 / 3.84 / 3.93 ms (base / F1+F2 / A). No measurable change yet: the ~1.3 ms per-job floor dominates. Re-measure with T2's GPU timestamps.

## Result: T3 kernel, same-boot arms A–D (2026-11-09, `vdm-t3-20261109`, real PowerVR ICD, GPU timestamps)

The first run of `runner/device-ab.sh` hit **llvmpipe**: the runner doesn't set `PVR_I_WANT_A_BROKEN_VULKAN_DRIVER=1`, so the loader fell back to lavapipe. That run is void (kept on the device as `/var/tmp/lane-a-t3-llvmpipe-void`). Rerun with `sudo env PVR_I_WANT_A_BROKEN_VULKAN_DRIVER=1 VK_DRIVER_FILES=/usr/share/vulkan/icd.d/powervr_mesa_icd.json bash runner/device-ab.sh`. Data: `build/lane-a-t3/gpu-20261109/`.

Wall ms per job (median, 100 iters); GPU ms from the w550 timestamps:

| Test | GPU ms | A joint=0 | B joint=1 | C +touch_live_pm | D +20 µs poll |
|---|---:|---:|---:|---:|---:|
| overhead empty_64x64 | 0.028 | 1.42 | **0.92** | 1.03 | 1.19 |
| clear_store | 1.29 | 2.58 | 2.50 | 2.50 | 2.48 |
| fill_opaque 1 | 1.40 | 2.66 | 2.52 | 2.53 | 2.51 |
| fill_opaque 16 | 1.47 | 2.66 | 2.47 | 2.53 | 2.50 |

- Joint TA/3D publish (B) is worth keeping: −0.5 ms on an empty job, −0.15 ms on full-screen jobs. touch_live_pm (C) and the 20 µs poll (D) give nothing measurable.
- **Where the floor goes** (per job, `jobs-A.txt`, full-screen fill): TA phase 1,040 µs wall vs **112 µs** GPU TA work, so ~930 µs of latency from doorbell to TA completion. 3D phase 1,670 µs wall vs 1,282 µs GPU (~390 µs). The GPU does 1.4 ms of work and we spend about 1.3 ms around it.
- Next: Lane A2 (TA-done latency), Lane C (TA fault on 1M triangles), both as specs.

## Result: GPU-timestamp re-measure of the compiler builds (2026-11-09, T3 boot, joint=1)

`scripts/gpu/microbench-icd-arms.sh`, one boot, 30 iters. Log: `build/linux-gpu-microbench/t3-icd-arms/mb-icd-arms-20261109T155852Z.log`. GPU ms = w550 TA+3D timestamps; iOS = Metal GPU timestamps.

| Test | base | F1+F2 | Lane B2 spec A | port-submit (A+B) | iOS |
|---|---:|---:|---:|---:|---:|
| alu 64 mads | 47.32 | **10.49** | 10.49 | 10.49 | 9.19 |
| tex_sample 1 | 1.98 | 2.04 | 2.04 | 2.01 | 1.45 |
| tex_sample 4 | 2.43 | 2.45 | 2.43 | 2.46 | 2.49 |
| fill_opaque 1 / 16 | 1.41 / 1.45 | 1.41 / 1.46 | 1.39 / 1.46 | 1.41 / 1.48 | 1.11 / 2.15 |
| fill_blend 4 | 1.84 | 1.84 | 1.84 | 1.84 | 2.81 |
| clear_store | 1.26 | 1.28 | 1.27 | 1.27 | 1.03 |
| empty pass | 0.028 | 0.027 | 0.028 | 0.028 | 0.156 (wall-ish) |

- On GPU time, F1+F2 is 4.5× faster on ALU and within 14% of iOS.
- Spec A (tex batching) changes nothing, even on GPU time: tex4 is already at iOS parity. Dropped.
- The GPU-side work is within ~1.3× of iOS everywhere, and faster on 16-layer fill and blend. **The remaining gap is the ~1.2 ms per-job host/firmware floor (Lane A2).**
