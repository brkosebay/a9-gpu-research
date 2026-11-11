# integration-h3 flight (2026-11-11, orchestrator)

h3 = integration-h2 + AMC PMU (lane CLPC-int) + doorbell without settle (lane BELL, drivers/drm 0033). Bundle sha256
`47419b2e…`. Installed from the running h2 boot into `/var/tmp/orchard04h3`. The hop plan was legacy loader,
`pristine_dt_changed=true`, reset guard cold, as expected. Warm hop with `sudo orchard-restart`. Netconsole with the
fixed `scripts/boot/netconsole.sh enable` (port 6667, unicast MAC) works.

## Warm boot (h2's IP5, lane SOC S6, BELL B0): PASS

New boot ID. `autoboot complete: GPU up`; `G5P self-park armed why=autoboot ctl20=1 policy4=16 envelope=3851
pin=400/400`; park `self_park=1 armed=1 park_epoch=1`, already parked. SoC state 12 after the hop. `apple_amc` PMU
registered.

## Doorbell (BELL B1–B3): PASS, +22 % fps

| glmark2 build, fullscreen, state 12, per job | fps | bell | TA wait | queue |
|---|---|---|---|---|
| h2 (2 ms settle before each bell) | 340–365 | 394–410 µs | 1544–1659 µs | 2279–2517 µs |
| **h3 (ring after one GPC read)** | **431–438** | **2–3 µs** | **1254–1265 µs** | **1506–1584 µs** |
| opt1, state 12, no park (F1) | 543 | 1 µs | 865 µs | 1072 µs |

- B1: the first job after a 20 s idle park ran, and kicks read `gpc=00000000 settle=0`.
- B3: 20/20 cycles rc 0, parked after each, 0 S3 lines, mean 412 fps.
- The remaining ~0.4 ms per job over no-park is the firmware's real wake. Fix candidate 2: frames in flight.

## AMC PMU (lane CLPC-int): counters work; GPU write is accurate, CPU write undercounts

`perf stat -a -e '{apple_amc/cpu_read/,…/gfx_write/}'`:

| run | state | cpu_read | cpu_write | gfx_read | gfx_write |
|---|---|---|---|---|---|
| idle 10 s | 12 | 282 MB | 41 MB | 0 | 0 |
| idle 10 s | 13 | 283 MB | 42 MB | 26 MB | 25 MB |
| memclk-bw 128 MiB ×1 | 12 | 5.30 GB | 0.30 GB | 0 | 0 |
| memclk-bw 128 MiB ×1 | 13 | 5.39 GB | 0.30 GB | 0 | 0 |
| glmark2 build 5 s, 427 fps | 12 | 2.36 GB | 0.32 GB | 6.52 GB | **31.39 GB** |
| glmark2 build 5 s, 302 fps | 13 | 1.96 GB | 0.30 GB | 5.75 GB | **23.34 GB** |

- **gfx_write matches the framebuffer arithmetic within about 2 %:** 1536×2048×4 B = 12.6 MB per frame; about
  2560 frames → 32 GB at 12, about 1850 → 23 GB at 13. Attribution is clean: CPU-only work shows 0 gfx.
- **cpu_write reads about 6× low** (0.30 GB against at least about 1.9 GB written by memclk-bw's write and copy
  passes), so its scale factor or event selector is wrong. cpu_read is plausible in magnitude. This is the open
  calibration (docs/power/clpc-20261111.md §4.3), and the governor can't use cpu_write until it's fixed.

## PBE stage (lane PBE, Mesa c0da45436a17): renders, but terrain/refract hit a CPU copy fallback

Same boot, state 12, census before (shipped `3a00235254b5`) and after (PBE stage; rollback tarball
`/var/tmp/orchard04h3/g5p-shipped-3a00235254b5.tar.gz`):
- **terrain / refract: no more refusal, rc 0, but 2 fps.** GPU time is 23.80 / 13.55 ms per frame, so the GPU isn't
  the limit. One glmark2 thread runs at 95 % CPU. perf: `pthread_once` 51 % (per element), `g5p_copy` 17 %,
  `g5p_element.part.0` 15 %, `util_format_z24_unorm_s8_uint_as_r8g8b8a8_pack_rgba_float` 8 %,
  `r8g8b8a8_unorm_unpack_rgba_float` 4 %. That's a per-element CPU image copy in the Vulkan driver.
- Other scenes are 0–9 % lower after the install (build 438 → 399, pulsar 435 → 399, ideas 269 → 280). SoC stayed at
  45 °C. Not yet separated from run-to-run noise. A rollback rerun A/B is needed before attributing it to PBE.
- The device keeps the PBE stage installed for the lane PBE2 follow-up. Roll back with the tarball above.
