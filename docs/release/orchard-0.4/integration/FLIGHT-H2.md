# integration-h2 flight (2026-11-11, orchestrator)

Bundle `orchard-04-integration-h2.tar.gz` (sha256 `a8802631…1a56`): integration-g2 (lane IP2) plus lane SOC. Release
`7.3.0-rc1-orchard-apple-16k-topic-integration04h2`. The entry was installed from a cold opt1 boot into
`/var/tmp/orchard04h2`, then cold-booted from DFU with the PSCI launcher. Raw results: device
`/var/tmp/orchard04h2/results/ip2/`; the opt1 cold-boot reference log is `flight-h2/dmesg-opt1-cold-reference.txt`.

Netconsole: `scripts/boot/netconsole.sh enable` uses `scripts/omarchy/ssh.sh` (wrong user for Orchard roots). The
broadcast `remote_mac` also never reached the Mac. What works is configfs set through `scripts/orchard/ssh.sh` with
`remote_mac` = the Mac's USB interface MAC (en16), listener on UDP 6667 → `flight-h2/netconsole.log`.

## IP block

| Step | Result |
|---|---|
| IP0 | **PASS.** Every expected line, in order: `GPUPERF poweron q=4 … policy4=0`, `GPUPERF boot … ovr=400/400 … policy28=4/4`, `poweron q=4 r1_1000=00000004`, `R74E ALIVE … state=00000004 … power_abort=0`, `R74B cmd8-consumed consumer=1 producer=1`, `control-wait result=0`, `autoboot complete: GPU up`, `G5P self-park armed why=autoboot ctl20=1 policy4=16 envelope=3851 pin=400/400`. No `GPUPERF self-park` line. |
| IP1 | **PASS.** Idle: pstate 0 in 80/80 samples, target 4; `suspend_ready` = `ready` 5/5. |
| IP2 | **PASS** on the shipped Mesa (`/opt/orchard/g5p`, labwc's environment): 16/16 scenes rc 0, no S3 line. On the first try with the block's `ST=/var/tmp/o04` stack, terrain hung: that old stack refuses the scene ("non-linear colour target"), loses the Zink context and glmark2 waits forever on a syncobj. That is a test-stack issue, not the kernel. The shipped stack refuses the same scene and carries on. |
| IP3 | **PASS.** 50/50 glmark2 build runs rc 0, parked after each (50/50), no S3 line, mean 319 fps. |
| IP4 | Answered by the analysis below: the firmware parks between frames. |

SoC state: 12 from boot (`PMGR+0x68000 = 0xccc`, sequencer auto), so lane SOC's S2 passes.

## Why self-park costs throughput (glmark2 build, fullscreen, state 12)

Per-job `g5p_gpu_stats` in µs: no-park opt1 F1 runs vs. h2.

| run | fps | TA work | 3D work | bell | TA wait | queue | overhead |
|---|---|---|---|---|---|---|---|
| opt1, state 13, no park (F1) | 385 | 283 | 1676 | 2 | 1155 | 1828 | 886 |
| opt1, state 12, no park (F1) | **543** | 200 | 1098 | **1** | **865** | 1072 | 739 |
| h2, state 12, self-park | **340–365** | 102 | 1174–1198 | **394–410** | **1544–1659** | 2279–2517 | 1418–1546 |

- **The GPU work per frame is unchanged:** 3D is about 1.1–1.2 ms in both, and TA is even shorter on h2. State 12 helps as F1 showed.
- **What's added is about 1.1–1.2 ms of latency per job:**
  1. **Bell, about 0.4 ms per job (host CPU, ours).** In a park epoch the doorbell path keeps integration-e's settle wait (up to 2 ms for the GPC nibble) before ringing. A parked GPC reads off, so every job's submitter waits for most of the wake. Apple rings at any nibble (lane IP §2) and doesn't wait.
  2. **TA wait, +0.7–0.8 ms per job (firmware wake).** The GPC power-on alone is about 550 µs (`GPUPERF poweron … on_ns=550375`), plus the firmware's restart.
- **Why it parks mid-stream:** the firmware's idle tail parks as soon as the engines are idle and the root rings are empty. There's no hold-off (lane IP §1.1, `0x10009bd8`). Our stack has at most about one frame in flight (jobs/frame 1.16), so the rings empty between frames and it parks in 5 of 16 samples under load. iOS runs the same firmware. Either Metal keeps the rings non-empty (several frames in flight), or iOS pays the same; that isn't measured.
- **Fix candidates, in order:**
  1. Ring without the settle wait in park epochs (Apple's order). This removes about 0.4 ms of host blocking per job, and the CPU overlaps the wake.
  2. Keep work queued ahead: Mesa submits frame N+1 before N completes. That's iOS's shape and keeps the rings non-empty.
  3. An iOS probe: sample `policy+0x34` under a high-fps Metal load. Does iOS park mid-animation?

  Never toggle `ctrl+0x20` off live: with the 16 ms sampler on, that is the latency123 wedge configuration.

## SOC S3 (same h2 boot, same shipped Mesa): PASS

- memclk-bw, 1 thread: state 12 read 12.54 / write 6.77 / copy 4.71 GB/s; state 13: 8.68 / 4.98 / 3.21 GB/s
  (read +44 %).
- Switches: 12 → 13 → 12 read back `0xddd` / `0xccc`, pending 0.
- glmark2 fullscreen, state 12 vs 13: **+24 % to +43 % fps on every real scene**, and GPU ms/frame lower on every one.
  Examples: build 341 vs 245 fps (1.52 vs 2.44 ms), shadow 97 vs 71 (7.66 vs 11.31 ms), desktop 41 vs 33. Terrain and
  refract are refused by Mesa and don't count. Raw data: `flight-h2/soc/`.
- With self-park, absolute fps is still below the no-park kernels: h2 at state 13 builds 245 fps, against 392 on
  integration-c (no park, state 13). See the park/wake cost above; lane BELL is the first fix.
