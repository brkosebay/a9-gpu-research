# A9 (G5P) GPU research notes

Research notes on the GPU of the Apple A9 (S8000/S8003, iPad 5, boards J71s/J71t/J72s/J72t) running under
Linux. The A9's GPU is a PowerVR Rogue (Series 7XT, "G5P" in Apple's drivers). It runs Apple's own firmware
and uses Apple's own shader ISA. Our kernel driver talks to that firmware; our Vulkan driver (in Mesa's
PowerVR driver) and Zink provide OpenGL ES on top.

This repository holds the **research and measurements** behind the Orchard 0.4 GPU work: what the firmware
and iOS do, what we changed and why, and the numbers before and after. It is a curated selection, built
from a private lab workspace by a scripted, audited export. The driver code is not here (see
[Where the code lives](#where-the-code-lives)). Our porting tools are, under [tools/](tools/README.md).

The foundational notes from 2026-11-02 (firmware interface, UAPI, shader ISA, first triangle) are in the
earlier repository [brkosebay/a9-gpu](https://github.com/brkosebay/a9-gpu).

## Scope

This is interoperability research for running Linux on hardware the author owns. It contains **no Apple
code or firmware**: no binaries, no disassembly or decompiler listings, no captured command buffers and no
copied data tables. Apple behaviour is described in our own words: register and field meanings,
sequences, conditions and numbers. Apple functions are cited by address and by the names we gave them
in our analysis. Nothing here covers bypassing a platform security feature, and the boot path is out
of scope. Per-device data (serials, MACs, calibration, NVRAM) is not included.

## Start here: porting another Apple PowerVR GPU

If you are bringing up Linux GPU support on an older Apple PowerVR GPU (A7, A8/A8X, A9/A9X), read these in order:

1. **[FIRST-TRIANGLE.md](FIRST-TRIANGLE.md)**: the bring-up path from power-on to first pixels, in order. Each step says what it needs, what went wrong, how we knew, and where the evidence is.
2. **[HARD-PROBLEMS.md](HARD-PROBLEMS.md)**: a symptom-indexed catalogue of the hard problems we solved or characterised after first pixels: firmware handshake, power, job submission, Mesa/Zink, memory, video and tooling.
3. **[PORTING-OLDER-GENERATIONS.md](PORTING-OLDER-GENERATIONS.md)**: for each subsystem, what is probably common across the generation, what is chip-specific, and how to re-derive it. It also says how to use these notes with an AI agent.
4. **[tools/](tools/README.md)**: our scripts for firmware extraction from the kernelcache, META disassembly, the glmark2 GPU census, Metal compiler probing and the RAM census (MIT).

## Status on 2026-11-11

The Orchard 0.4 integration kernels run the labwc desktop and Firefox with hardware WebRender on
the GPU. These are the results from the 2026-11-11 flights. Each number links to its
flight record.

| Change | Result | Record |
|---|---|---|
| **GPU firmware self-park.** The firmware parks itself whenever its rings go empty, as on iOS. Linux never wrote the host control word that allows it (`ctrl+0x20`, the "never-park" veto). The pin and the sampler were not the cause. | Device-proven on integration-h2. GPU idle at pstate 0 in 80/80 samples, 50/50 glmark2 runs park after each, no faults. The cost is about 1.1–1.2 ms of extra latency per job while it wakes. | [lane IP](docs/release/orchard-0.4/lane-ip/README.md), [lane IP2](docs/release/orchard-0.4/lane-ip2/README.md), [FLIGHT-H2](docs/release/orchard-0.4/integration/FLIGHT-H2.md) |
| **Doorbell fix.** Ring a parked firmware right away, as Apple does, instead of polling up to 2 ms for a GPC that only powers on after the bell. | **+22 % fps**: glmark2 build (fullscreen, state 12) 340–365 → 431–438 fps. Host time per bell 394–410 µs → 2–3 µs. TA wait 1544–1659 µs → 1254–1265 µs. | [lane BELL](docs/release/orchard-0.4/lane-bell/README.md), [FLIGHT-H3](docs/release/orchard-0.4/integration/FLIGHT-H3.md) |
| **SoC/memory performance state 12.** Linux left the SoC in state 13 (DRAM 800 MHz). iOS raises it to state 12 (DRAM 1200 MHz) under load. The 0.4 kernel holds 12, with 13 across suspend. | **+24 % to +43 % fps on every real glmark2 scene**, with lower GPU ms/frame on every one. For example, build 245 → 341 fps (2.44 → 1.52 ms) and shadow 71 → 97 fps (11.31 → 7.66 ms). CPU read bandwidth +44 %. On the earlier opt1 kernel (no park), build went from 385 to 543 fps. State 12 at the stock GPU clock beats a 948 MHz GPU overclock in state 13. | [FLIGHT-H2](docs/release/orchard-0.4/integration/FLIGHT-H2.md), [lane SOC](docs/release/orchard-0.4/lane-soc/README.md), [memclk F0/F1](docs/power/memclk-orchard-20261110.md) |
| **Twiddled render targets and GPU mip blits.** The twiddled PBE colour-target store was already encoded and proven, but it was gated behind a probe. Now it is the default. Supported twiddled mip chains are generated on the GPU, and small or unaligned tails stay on the CPU. | glmark2 terrain 2 → **17 fps** and refract 2 → **30 fps** on rc2. All 16 scenes run, with no refusals. A visual check of the mips by the owner is pending. | [PBE note](docs/gpu/pbe-twiddled-20261111.md), [FLIGHT-RC2](docs/release/orchard-0.4/integration/FLIGHT-RC2.md) |
| **GPU RAM census.** We set accounting rules and ranked the RAM design. BO and pin counters are device-wide and must not be multiplied per client. Zink's 2 MiB slab parents are one kernel BO each. The firmware's parameter-pool growth on iOS is feedback-driven. | There is no closed RAM balance yet. The ranked design starts with counting real commitment. Its estimates are hypotheses and overlap. | [GPU RAM](docs/ram/gpu-ram-20261111.md), [mem1](docs/gpu/mem1-gpu-memory-20261109.md) |
| **AMC PMU.** We exposed the DRAM traffic counters as perf events. | The counters work. GPU writes are counted accurately, CPU writes are undercounted. | [FLIGHT-H3](docs/release/orchard-0.4/integration/FLIGHT-H3.md), [lane AMC](docs/release/orchard-0.4/lane-amc/README.md), [CLPC](docs/power/clpc-20261111.md) |

Lane titles that say "host only, not device-proven" were written before the flights. The flight records
above are the later device results.

**Still open:**
- **System sleep (s2idle)** is the release blocker. On cold boot it was refused after a 1 s drain. The cause is a deferred close that was never released. A second refusal, `busy=accepted`, came from a set-once flag counted as work. Fixes for both are built but not flown. Warm (kexec) boots keep every power domain on, so GPU sleep is refused by name there. That is pending a decision. See [lane SLEEP](docs/release/orchard-0.4/lane-sleep/README.md).
- **Next performance target: frames in flight.** About 0.4 ms per job over no-park is the firmware's real wake. Keeping the next frame queued (as Metal does) should hide it. The analysis and a Mesa change (built, not flown) are in [frames-in-flight](docs/gpu/frames-in-flight-20261111.md).

## Map of the docs

**Bring-up (2026-10-22 to 2026-11-02)**
- [docs/gpu/agx-g5p-bringup.md](docs/gpu/agx-g5p-bringup.md): power, Fender, reset/SLC/MMU, META boot, LDR load, the ring. The curated experiment docs it leads to are listed in [FIRST-TRIANGLE.md](FIRST-TRIANGLE.md).

**Status**
- [docs/gpu/STATUS.md](docs/gpu/STATUS.md): the broad status as of 2026-11-06 (what works, open problems). The table above supersedes its numbers.
- The four flight records: [G](docs/release/orchard-0.4/integration/FLIGHT-G.md) (the IP0 failure), [H2](docs/release/orchard-0.4/integration/FLIGHT-H2.md) (self-park, state 12), [H3](docs/release/orchard-0.4/integration/FLIGHT-H3.md) (doorbell, AMC) and [RC2](docs/release/orchard-0.4/integration/FLIGHT-RC2.md) (twiddled targets, s2idle).

**Firmware, power and the job path** (docs/release/orchard-0.4/)
- [lane IP](docs/release/orchard-0.4/lane-ip/README.md): idle park the Apple way. [lane IP2](docs/release/orchard-0.4/lane-ip2/README.md): why the first integration never consumed the boot command. [lane BELL](docs/release/orchard-0.4/lane-bell/README.md): the doorbell.
- [lane GS](docs/release/orchard-0.4/lane-gs/README.md), [lane GS4](docs/release/orchard-0.4/lane-gs4/README.md), [lane SLEEP](docs/release/orchard-0.4/lane-sleep/README.md): GPU system sleep, its contract and the warm-boot differences.
- [lane SOC](docs/release/orchard-0.4/lane-soc/README.md), [lane AMC](docs/release/orchard-0.4/lane-amc/README.md): the SoC performance state and the memory-traffic counters.
- [lane G](docs/release/orchard-0.4/lane-g/README.md), [lane M](docs/release/orchard-0.4/lane-m/README.md): how the kernel and Mesa series are split for review.

**Design and root causes** (docs/gpu/)
- [apple-idle-power-design](docs/gpu/apple-idle-power-design-20261109.md): how iOS idles the GPU at two levels.
- [freeze-root-cause](docs/gpu/freeze-root-cause-20261109.md): a whole-SoC freeze on GPU context churn. [r39-silent-recovery](docs/gpu/r39-silent-recovery.md): recovery from a silent GPU loss.
- [vdm-zink-lifetime-fix](docs/gpu/vdm-zink-lifetime-fix.md), [mem1](docs/gpu/mem1-gpu-memory-20261109.md): object lifetime and memory.
- [pbe-twiddled](docs/gpu/pbe-twiddled-20261111.md), [tex1](docs/gpu/tex1-compressed-textures-20261110.md): render-target layout and compressed textures.

**Performance** (docs/gpu/, docs/power/)
- [microbench-gap](docs/gpu/microbench-gap-20261109.md): our driver vs iOS on microbenchmarks. [lane-b2-beyond-apple](docs/gpu/lane-b2-beyond-apple.md): fp16, co-issue, texture scheduling, pass merging.
- [heavy-census](docs/gpu/heavy-census-20261109.md), [opt1-o04-flight](docs/gpu/opt1-o04-flight-20261110.md): glmark2 fps, GPU busy % and GPU ms/frame per scene.
- [aquarium-idle-gpu-critical-path](docs/gpu/aquarium-idle-gpu-critical-path.md), [aquarium-cpu-profile](docs/gpu/aquarium-cpu-profile-20261109.md), [webgl-perf-r39-9](docs/gpu/webgl-perf-r39-9.md), [firefox-wr3](docs/gpu/firefox-wr3-20261108.md): WebGL and Firefox.
- [oc-opt1](docs/power/oc-opt1-20261110.md): GPU performance states, the clock encoding, thermal policy and the overclock ladder. [memclk-orchard §11](docs/power/memclk-orchard-20261110.md): state 12 vs 13. [clpc](docs/power/clpc-20261111.md): the CLPC traffic counters and a governor design.
- Lab notebooks, long and dated: [perf60-clock](docs/gpu/experiments/perf60-clock.md) (from 340 MHz toward iOS's 723 MHz), [perf60-fillrate](docs/gpu/experiments/perf60-fillrate.md) (load/store waste), [perf60-hendrik](docs/gpu/experiments/perf60-hendrik.md) (the A10 side's tips, checked on A9).

**Working with the A10 (G9P) port**
- [henrik-g9p-port-study](docs/gpu/henrik-g9p-port-study.md), and our letters [a9-reply](docs/gpu/hendrik/a9-reply-20261102.md), [a9-update](docs/gpu/hendrik/a9-update-20261103.md) and [g9p-es3](docs/gpu/hendrik/g9p-es3.md).

Notes on reading:
- Labels: **[P]** proven from code or data, **[V]** verified on the device, **[I]** inferred.
- Paths such as `build/…`, `/var/tmp/…` or branch names like `j71t-04/…` refer to the private workspace or the device. They are kept as provenance and are not part of this repository.
- Links to files that are not published were turned into plain text. Removed passages are marked in place.

## Where the code lives

The code goes upstream to OrchardLinux as the Orchard 0.4 pull requests, **not public yet**:
- **OrchardLinux/linux**: the G5P DRM driver (firmware self-park, doorbell, sleep), the S8000 SoC performance state, and the AMC PMU.
- **OrchardLinux/mesa**: G5P on the shared PowerVR Vulkan driver (twiddled PBE, GPU mip blits, memory).
- **OrchardLinux/orchard**: the patch layers, the device tree and the release packaging.

An earlier Mesa PR is already open: [OrchardLinux/mesa#2](https://github.com/OrchardLinux/mesa/pull/2).

## Credits

- **Henrik and OrchardLinux**, for the A10 (T8010, G9P) GPU work this builds on and shares a driver with,
  and for the tips checked in perf60-hendrik.
- **The Asahi Linux lineage**: m1n1, the Apple GPU reverse-engineering work, and the Apple platform kernel
  support that HoolockLinux and OrchardLinux carry to the older SoCs.
- Mesa's PowerVR (Imagination) driver, which the G5P support extends.

The notes were written largely by an AI coding agent (Claude) working for the repository owner, who ran the device.

## Licence

The text in this repository is offered under [CC BY 4.0](LICENSE.md). The scripts under `tools/` are MIT ([tools/LICENSE.md](tools/LICENSE.md)).
Trademarks belong to their owners. This project has no affiliation with Apple or Imagination.
