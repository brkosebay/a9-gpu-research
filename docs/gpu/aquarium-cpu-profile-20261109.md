# Aquarium 500 fish, CPU profile on the port-submit async ICD (2026-11-09)

Question: Lane A2 found that in Aquarium (26 fps, 38.5 ms/frame) the GPU has **no job queued for ~20 ms/frame**. What fills that time?

Capture: `scripts/gpu/perf-aquarium-icd.sh portsubmit-async-500 500` on the T3 boot (joint=1). ICD `/var/tmp/port-submit` (spec A async on, B off), HW WebRender via Zink. perf `cpu-clock` 99 Hz, dwarf call graphs, 25 s, all Firefox + labwc PIDs, plus a 25 s `trace-cmd` of `dma_fence`/`drm`. Data: `build/gpu/perf-portsubmit-20261109/` (`stacks/perf.data`, `trace-report.txt.zst`, `thermal.tsv`). fps during the capture: median 26 (65/77 samples).

## First read (on-device `perf report`, unsymbolized)

- Total sampled CPU ≈ 31.5 s over 25 s on 2 cores, so **~63% busy**. The CPU is not saturated, which suggests the idle-GPU time is cross-thread waiting (frame pacing, fences, IPC), not raw CPU throughput. Unconfirmed until the critical path is traced.
- By library: libxul 29.7%, kernel 18.4%, libc 16.0% (memcpy, mutexes), **libvulkan_powervr_mesa 12.6%**, libgallium/Zink 7.3%.
- By thread: firefox main 16.1%, **firefox:gdrv0 12.0%**, **firefox:zfq0 10.5%** (Zink flush queue; memcpy and kernel time), Isolated Web Content 10.3%, Renderer 7.8%, CanvasRenderer 7.7%, labwc 7.1%.

## Thermal

1 Hz sampler (`scripts/gpu/thermal-sampler.sh`), ~60 s overlapping the end of the capture: soc0 max 69.5 °C, soc1 66.3 °C, **tcc2 max 79.3 °C** (passive trip 80 °C), battery 37.3 °C, CPU cooling state 0 throughout (no cpufreq cap). The CPU never throttled. The GPU is not wired to the Linux thermal framework; any firmware-side GPU limiting is not observed yet.

## Next (profiling lane)

- Symbolize with the unstripped port-submit build (build ID in `stacks/buildids.txt`; tool `scripts/gpu/orchard/r39-9/rank-stacks.py`).
- Join perf samples with `dma_fence` signal/wait times per frame to get the per-frame critical path: WebGL CanvasRenderer → Zink → G5P submit (gdrv0) → GPU → present → compositor.
- Name the waits that keep the GPU idle for ~20 ms/frame, and spec the cut (driver CPU waste first: copies, waits, per-draw overhead).
