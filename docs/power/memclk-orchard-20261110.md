# memclk-orchard: testing a memory overclock with the Orchard boot chain (2026-11-10)

> **Published extract.** Only the measurement section (§11) is published. The workspace version also
> plans how a DRAM retrain above 1200 MHz could be inserted early in the boot chain. That material is
> out of scope for this repository and is not included. What matters for the GPU: Linux boots the A9 in
> SoC/memory performance state 13 (DRAM 800 MHz); iOS uses state 12 (DRAM 1200 MHz) under load, and
> switching at runtime is a plain PMGR register write that the kernel can make. The results below are the
> first runtime switch. The kernel side is in [lane SOC](../release/orchard-0.4/lane-soc/README.md).
## 11. F0 and F1 results (orchestrator, 2026-11-11, cold-booted `orchard-opt1-20261110`)

**F0: Orchard runs in SoC state 13** (PMGR+0x68000 = 0xddd, SoC live code 10 = 631 mV; the iOS runtime
sequencer is in auto mode, routing 0x1782). Branch A.

**F1 `set 12` at runtime:** sequencer reached 0xccc in 475 µs, SoC live code 48; back to 13 in 269 µs.

CPU (`memclk-bw 64`, 1 thread / 2 threads):

| | state 13 | state 12 | gain |
|---|---|---|---|
| read GB/s | 8.81 / 10.27 | 15.06 / 16.13 | +71 % / +57 % |
| write GB/s | 4.89 / 4.92 | 7.17 / 8.00 | +47 % / +63 % |
| copy GB/s | 3.40 / 3.29 | 5.06 / 4.92 | +49 % / +50 % |
| DRAM latency | 234 ns | 202 ns | −14 % |

GPU (stock 723 MHz, glmark2 census fullscreen 1536x2048, same boot, s12 then s13):

| scene | s13 fps / GPU ms | s12 fps / GPU ms | fps gain |
|---|---|---|---|
| build | 385 / 2.26 | 543 / 1.44 | +41 % |
| texture | 351 / 2.38 | 499 / 1.61 | +42 % |
| shading | 336 / 2.83 | 440 / 2.25 | +31 % |
| bump | 377 / 2.17 | 540 / 1.47 | +43 % |
| effect2d | 289 / 3.16 | 370 / 2.46 | +28 % |
| pulsar | 397 / 2.10 | 547 / 1.37 | +38 % |
| desktop | 38 / 23.70 | 51 / 17.14 | +34 % |
| buffer | 135 / 4.12 | 221 / 2.48 | +64 % |
| ideas | 289 / 3.02 | 371 / 2.13 | +28 % |
| jellyfish | 254 / 3.95 | 321 / 3.13 | +26 % |
| shadow | 88 / 11.16 | 128 / 7.55 | +45 % |
| conditionals | 387 / 2.14 | 503 / 1.66 | +30 % |
| function | 385 / 2.13 | 527 / 1.33 | +37 % |
| loop | 349 / 2.58 | 393 / 2.29 | +13 % |

ALU microbench unchanged (144.5 vs 143.6 GFLOP/s), as expected: the gain is memory/fabric, not the
shader clock. State 12 at stock GPU clock beats a 948 MHz GPU overclock in state 13 on every scene
(e.g. shadow 128 vs 89 fps, build 543 vs 383). The GPU overclock ladder (oc-opt1 §12) was measured in
state 13; its flat GPU ms/frame was this memory limit.

Notes:
- The s12 rung's STOP was a false positive: FAULT_RE's bare `recover` matched
  `omarchy-usb-recover: usb0-stall-bounce` (fixed: `apple-g5p-drm.*recover`). The census completed.
- That usb0 stall (peer unreachable ≥15 s, 3/3 bounces, at 352 s during the shadow scene) happened only
  in state 12, once. Watch for it in F2; it may be load-related rather than state-related.
- The device was left in state 13.

Next: state 12 held by the kernel (F2, `a9/memclk-orchard-1`), and the Apple policy (does iOS hold 12 under
load and drop to 13 when idle? AppleS8000PMGR in Ghidra) before it goes into the 0.4 PR set.
