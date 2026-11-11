# Lane SOC: A9 SoC/memory performance state for Orchard 0.4

Status: built and packaged, **not device-tested**. Device test: `DEVICE-COMMANDS-soc.txt` (not published).

Labels: **[P]** proven (read in code or measured), **[V]** verified on the device, **[I]** inferred.

## 0. Bottom line

- Orchard leaves the A9 in SoC/memory state 13 (PMGR+0x68000 = 0xddd, DRAM 800 MHz) [V, memclk-orchard §11].
  iOS's state 12 (DRAM 1200 MHz) at runtime gave CPU read 8.8 → 15.1 GB/s and glmark2 +13–64 % at the stock GPU
  clock [V, same doc].
- **iOS is load-driven** [P code, I runtime]. The CLPC kext (AppleS8000CLPC) runs a closed loop on DRAM bandwidth
  counters and CPU memory stall. When the demand crosses half-scale it turns on PMGR's SOC-FAST virtual device,
  which raises the SOC perf domain to state 12. When the load is gone it decays back to 13.
- **The 0.4 topic does what Henrik's T8010 driver does:** 12 at probe, 13 across suspend, 12 on resume. It is an
  S8000 variant of Orchard's `apple-pmgr-misc`, plus a per-chip pending timeout (iOS's 8 ms for the A9). Linux has
  no AMC bandwidth monitor, so it can't reproduce CLPC's signal yet. The static form is what Orchard already ships
  for the same register on A10. A load-driven vote is proposed as a follow-up (§2.3).
- Topic: kernel `j71t-04/soc-perf` `ab2fdae02` (3 commits), orchard `j71t-04/soc-perf` `eecad63`.
  Integration: orchard `j71t-04/soc-perf-integration-h` `5e703f9` = integration-g `b7ed084` + topic.
  Bundle: `build/orchard-0.4/lane-soc/bundle/orchard-04-integration-h.tar.gz`, sha256 `ed726aae…87ec`.

## 1. What iOS does (Ghidra, iOS 16.7.10 j71t kernelcache, about 1 h)

Functions were renamed in the shared analysis and saved (`scripts/ghidra-mcp.sh save` → `SAVED ok`).

### 1.1 Who requests the SOC domain state, and on what signal [P]

The requester found is **CLPC**, the `AppleS8000CLPC` kext (kmod info at `fffffff007a91e80`). Whether AGX,
display or the media drivers request the SOC domain directly was **not searched**. Its tunables are a table of {id, internal name, ADT name}
at `fffffff007a92198…`. The ADT `clpc` node supplies the values.

1. **`AppleCLPCSoCThroughputController`**:
   - `_create` `fffffff006488480`, `_init` `fffffff006488178`, `_setProperty` `fffffff0064882dc`, vtable
     `fffffff006efd180`.
   - The update is at `fffffff006488528` (vtable +0x88). Ghidra has no function there, so it carries a disassembly
     comment.
   - Inputs are named samples: `cpu-read`, `cpu-write`, `gfx-read`, `gfx-write`, `mem` and `fabric` (bandwidth
     counters).
   - It runs four integrators:
     - CPU: `(cpu-read + cpu-write)·2⁻³⁰ − soc-throughput-cpu-threshold`;
     - GPU: `(gfx-read + gfx-write)·2⁻³⁰ − soc-throughput-gpu-threshold`;
     - memory;
     - fabric.
   - Each one does `e += err · (err > 0 ? ki-up : ki-down)` and clamps `e` to [0, 1] (`AppleCLPC_clampEffort01`
     `fffffff0064a1b80`).
   - The controller's effort is the maximum of the four. Its domain (vtable +0x98) is **1 = SOC**.
   - The j71t ADT has thresholds and gains for CPU and GPU only, so the memory and fabric terms are absent there.
2. **`AppleCLPCSoCStallController`**:
   - `_init` `fffffff006490fd0`, `_update` `fffffff006491220`.
   - Its input is the `clpc-core-stall` metric, gated on `core-cycle` ≠ 0.
   - It integrates `stall − soc-stall-target` with `soc-stall-ki-up/-down`. Its domain is also SOC.
3. **`AppleCLPC_controlUpdate`** `fffffff00648b318`:
   - It runs once per CLPC sample (`sampling-interval-ms`).
   - For each domain it takes the maximum effort over that domain's controllers, applies the limiters (minimum),
     then the domain floor.
   - If the domain is dynamic, it calls `AppleCLPC_applySOCControlEffort` `fffffff00648a1c0`.
4. **`AppleCLPC_applySOCControlEffort`**:
   - It computes `level = N · e / 0x10001`, where N = `num-soc-states` and e is in 16.16.
   - When the level changes, it calls `ApplePMGR_requestDeviceLevelByGateIndex` `fffffff005a43c1c` →
     `ApplePMGR_requestDeviceLevel` `fffffff005a382a4`. That turns on gate `soc-fast-device-index + level − 1` for
     the new level and turns off the old one.
5. **CLPC init** `fffffff00648c8e0` (comment there):
   - `num-soc-states` defaults to 1, which means static.
   - If the ADT has `soc-fast-device-index` it becomes 2, unless the ADT gives `num-soc-states`.
   - The j71t ADT has `soc-fast-device-index` and no `num-soc-states`, so N = 2 and **the state is fast when
     e > ½**.
   - `AppleCLPC_setProperty` `fffffff00648a7b0`: id 1 = `DynamicSOCControl` (only if N > 1), id 2 =
     `SOCPerformanceState` (the fixed state when dynamic is off). The ADT sets `dynamic-soc-control`.
6. **PMGR side**:
   - The gate is the ADT pmgr virtual device **SOC-FAST**.
   - `ApplePMGR_updateDevicePerfDomains` `fffffff005a388c4` runs after a device level change. For each perf domain
     it picks the highest perf index whose device set contains a powered device, then calls
     `ApplePMGR_setDevicePerfState` `fffffff005a39b30` → `AppleS8000PMGR_setPerfState` `fffffff005e92094`.
   - The SOC branch of `setPerfState` maps index *i* to state 13 − *i*, accepts only 12/13, does one
     read-modify-write of PMGR+0x68000 and optionally polls bit 31 for 0x2ee00 ticks (8 ms)
     (perf60-hendrik §3, unchanged).

### 1.2 When iOS sits in 13 and when in 12 [P mechanism, I runtime]

- The demand rises only while CPU or GPU DRAM traffic exceeds its threshold, or while CPU cores stall on memory
  beyond the target. It falls while traffic is below the threshold.
- Display scanout is not one of the inputs [I: the counters are named per CPU/GFX port].
- So an idle iOS with the display on should sit in 13, and GPU rendering or CPU streaming should take it to 12.
- **Not measured on iOS.** The iOS probe at the end of DEVICE-COMMANDS reads CLPC's control effort and the SOC
  residency at idle, under GPU load, under CPU memory load and during video.
- Other powered devices could also hold SOC index 1 if PMGR's index-1 device set contains them. The
  ISP/VENC/VDEC/JPEG-FAST virtual devices are candidates; they were not resolved [I]. The probe's video arm answers
  that for VDEC.

### 1.3 Hysteresis and rate limits [P form, values private]

- The hysteresis is the integrator itself. It rises at `ki-up · excess` per sample and decays at
  `ki-down · deficit` per sample, clamped to [0, 1]. The switch point is e = ½.
- There is no separate timer or rate limit in the SOC path.
- The sample period is the clpc node's `sampling-interval-ms`.
- One transition costs about 0.5–0.7 ms [V, F1 and perf60-hendrik §5].
- This report doesn't state the gain or threshold values, or the timings derived from them, because they come
  from the private ADT.

### 1.4 Sleep/wake and GPU park/wake [I]

- **GPU park/wake:** CLPC's GPU input is the GFX bandwidth counter, not the AGX power state. A parked GPU makes no
  traffic, so the demand decays. A direct AGX → SOC request was not searched for.
- **Sleep:** the ApplePMGR power-transition path (`FUN_5a2ab00`) sets voltage-control mode 0 (perf60-hendrik §3).
  CLPC's controller reset (vtable +0x90 zeroes the integrators) exists, but its caller on sleep was not traced
  within the time box. With no load, iOS goes into sleep in 13 or decays there.
- `ApplePMGR_restoreRunMaxDeviceStates` `fffffff005a2ce18` re-powers RunMax devices on the way back up. Not
  resolved for SOC-FAST.

### 1.5 Ordering around the switch [P]

- iOS writes nothing else around the switch: no voltage write, no AMC write, no GPU-firmware message.
- PMGR's sequencer moves the SoC rail from the state record. The only acknowledgement is the bit-31 poll
  (perf60-hendrik §3; confirmed again: the CLPC → PMGR path adds only reporting).

## 2. Design

### 2.1 Choice: static high while running (Henrik's T8010 pattern)

- **Probe:** set 0xc. **Suspend (noirq):** 0xd. **Resume (noirq):** 0xc.
- Linux makes one read-modify-write of the low nibble, then polls bit 31 for up to 8 ms, exactly as iOS does.
- **No sequencer gates, no module parameter, no sysfs.** The gates in release8 and memclk-orchard-1 were bring-up
  checks, and iOS doesn't do them.
- The driver relies on the boot chain leaving PMGR's voltage sequencer in iOS's runtime mode. That is [V] for
  Orchard's cold boot (F0: `0xa0000[12:8]` clear, routing `0x1782`) and [V] for a runtime write (F1). For the
  driver itself it is untested.
- **Why not load-driven now:**
  1. CLPC's signal is DRAM bandwidth per port plus CPU stall. Linux has no driver for the AMC counters. A
     GPU-utilization proxy would be a new policy, not iOS's.
  2. Orchard already ships the static form for the same register and states on the T8010, whose iOS uses the same
     CLPC design.
  3. A desktop that renders is in 12 whenever it draws, so the measured gain is what users see.
- **Timeout:**
  - Henrik's 1 ms poll is close to the 0.5–0.7 ms the A9 takes, so it would warn spuriously on a slow change.
  - The `bool wait_pending` becomes `u32 pending_timeout_us` in match data: T8010 keeps 1000 µs, S8000 gets 8000 µs.
  - T8010 behaviour is unchanged.
- **DT:**
  - `pmgr_misc: power-management@20e068000` in `s800-0-3.dtsi`, `compatible = "apple,s8000-pmgr-misc"`, the same
    `soc-ps` region as the T8010. It is a sibling of `pmgr`, as Henrik's is.
  - `s800-0-3.dtsi` uses `apple,s8000-*` for both S8000 and S8003, so there is no separate S8003 compatible.
  - Enabled SoC-wide, as T8010's is.
- **Config:** none. apple-16k already has `CONFIG_APPLE_PMGR_MISC=y` for the T8010, and the A9 is apple-16k only.

### 2.2 Power cost [I, measured in S4]

- State 12 raises the SoC rail from a nominal 631 mV to 750 mV (perf60-hendrik §3; LLB rail table) and runs DRAM
  and fabric 1.5× faster.
- Dynamic power on that rail scales with roughly V²·f, about 1.4× from voltage alone, and leakage grows faster than
  linearly with V.
- iOS pays this only under load. Static 12 pays it whenever the screen is on and idle, and not in s2idle, where the
  driver drops to 13.
- The absolute SoC-rail idle power is unknown. S4 measures battery current and SoC temperature A/B/A at idle.
- If the idle cost is material, the follow-up below is the fix. The 0.4 topic stays as is.

### 2.3 Follow-up (not in 0.4): load-driven, upstream-acceptable

- A devfreq device on apple-pmgr-misc with two OPPs (13, 12) and the **passive governor parented to G5P's GPU
  devfreq**, or an interconnect provider for the A9 memory path with apple-g5p-drm voting bandwidth while jobs run.
- Either reproduces only CLPC's GPU half. The CPU half needs AMC bandwidth or CPU stall counters: a perf PMU
  driver for the AMC, then a devfreq governor that integrates as CLPC does.
- Switching costs about 0.6 ms, so per-frame decisions are affordable.
- Do this only if S4 shows a material idle cost or the iOS probe shows video/media holding 12.

## 3. Changes

### 3.1 Kernel topic `j71t-04/soc-perf` (linux-a9-src:/src/orchard04-lane-soc, base OrchardLinux/linux main `564a3550e`)

| SHA | Commit |
|---|---|
| `b0e6dc4945504758ff1f60673d921cab20287319` | dt-bindings: soc: apple: pmgr-misc: Add the S8000 |
| `f5c6074290ac43a3415925d9565402959f27a013` | soc: apple: pmgr-misc: Run the S8000's SoC and memory states high |
| `ab2fdae02fa3319dd014461c80e65481488eddc5` | arm64: dts: apple: s800-0-3: Add the SoC performance state |

- Diffstat: 4 files, +39/−8 (binding, `apple-pmgr-misc.c`, Kconfig help, `s800-0-3.dtsi`).
- Every commit has `Assisted-by: LLM`, no Signed-off-by, and the author from the global git config.
- `checkpatch.pl`: the only error is the expected missing Signed-off-by; there are 0 warnings.
- `make dt_binding_check DT_SCHEMA_FILES=apple,t6000-pmgr-misc.yaml` ran in a throwaway `python:3.11-slim`
  container (dtschema 2026.9, removed after; the build image has none). It returned 0, with no findings for this
  binding; its only line is the existing parse warning for `apple,z2-multitouch.yaml`.
- `dt-validate` of h's `j71t.dtb` against the processed schema found nothing for pmgr-misc or `20e068000`.
  Receipt: `build/orchard-0.4/lane-soc/dtcheck/result.txt`.

### 3.2 Orchard topic `j71t-04/soc-perf` `eecad635ddf08c02f154112c20e666b0732aca81` (on main `e46f9e845`)

- `kernel/patches/drivers/soc-apple/0014-dt-bindings-soc-apple-pmgr-misc-Add-the-S8000.patch`
- `kernel/patches/drivers/soc-apple/0015-soc-apple-pmgr-misc-Run-the-S8000-s-SoC-and-memory-s.patch`
- `kernel/patches/devices/s8000/0007-arm64-dts-apple-s800-0-3-Add-the-SoC-performance-sta.patch`
- `chips/s8000.toml`, `chips/s8003.toml` and `devices/j71t/device.toml` get comment lines only, with no status
  change.
- `tools/catalog/generate matrix` reports no change.
- The export (`export.log`) reproduces the branch exactly ("applied to 564a3550e they reproduce j71t-04/soc-perf
  exactly"). The DT commit needed `--topic ab2fdae02=devices/s8000`; without it the exporter proposed a new
  `devices/s800` directory.

### 3.3 Integration-h `j71t-04/soc-perf-integration-h` `5e703f94fa19d4251e8a0bbac6ccd29b65dbc17e`

- It is `b7ed084` (integration-g) + a `--no-ff` merge of the topic.
- The conflicts were EOF comment appends in the three TOMLs; both sides are kept and the matrix check is clean.
- Patch numbers coexist with other lanes' files under the same number (soc-apple 0014 and s8000 0007 already exist
  under other names in g). Whoever publishes second re-exports.

## 4. Build receipts

- **Disk:** 67 GiB free before the build.
- **Command:** `ORCHARD_KERNEL_TEST_SUFFIX=integration04h JOBS=6 scripts/orchard/build-orchard-kernel.sh
  build/orchard-0.4/lane-soc/orchard-h out-integration04h j71t`. Exit 0, 562 applied patches, 77 modules, vermagic
  PASS.
- **Warnings:** only the inherited whitespace notes (drm 0010, soc-apple 0011). `apple-pmgr-misc.o` compiled clean.
- **Log:** `build/orchard-0.4/lane-soc/kernel-build-h.log`.
- **Release:** `7.3.0-rc1-orchard-apple-16k-topic-integration04h`.
- **Hashes:**
  - `Image.gz` `9be706a21057…`;
  - `j71t.dtb` `299b9e9601e4…`;
  - `initrd` `036f5df20f3f…`.
- **DT check:** `j71t.dtb` = g's + exactly the new node (`compatible = "apple,s8000-pmgr-misc"`, `reg = <0x02
  0xe068000 0x00 0x04>`, `reg-names = "soc-ps"`, plus its `__symbols__` entry). Nothing was removed, ignoring
  renumbered unreferenced label phandles.
- **Other boards:** the node is in all 10 built S8000/S8003 DTBs (j71s, j72s, n66, n69u, n71, j71t, j72t, n66m,
  n69, n71m) and in none of the 4 S8001 DTBs.
- **Image and initrd:** the decompressed Image carries the match string. The config is byte-identical to g's. The
  fresh initrd carries the stable USB identity and the compiled DT (asserted).
- **Package:** `python3 scripts/orchard/package-orchard04h-socperf.py`. It reads g's packet without modifying it
  and writes `build/orchard-0.4/lane-soc/bundle/`. Userspace, runner and opt1 are g's byte for byte. It adds
  `tools/perf60-memclk.py` and `tools/memclk-bw`.
- **Bundle:** entry `orchard-04-integration-h`, archive `orchard-04-integration-h.tar.gz`, SHA256
  `ed726aaec030…`. Receipt `bundle/build-receipt-h.json`.
- **Orchard unit suite on `5e703f9`:** 773 tests, 7 failures, 1 error, 3 skips, the same names as g (§7).

## 5. Device test (orchestrator)

`DEVICE-COMMANDS-soc.txt` (not published), with `idle-arm.sh` (not published) for S4.

- **Class:** day, DFU-class. h carries integration-g unchanged, and g isn't device-tested, so fly g's IP block
  first or treat its risks as h's.
- Lane SOC's own change is warm-class: one hop from g with the changed DT, then one same-DT hop. Those hops and the
  rollback are the first Orchard-chain hops that start from state 12.
- The suspend arm carries the suspend topic's own risk.
- S3 gates on same-boot ratios (h12 vs h13, same tool and stack) and on CPU-only `memclk-bw`. F1's absolute fps
  came from the opt1 kernel and is a reference only.

| Step | Must show |
|---|---|
| S2 | Node bound. No `pmgr-misc`/`soc state change` lines. `read`: state=12, pending 0, live code at state 12's record code. |
| S3 | `memclk-bw` and glmark2 in state 12 match F1's s12 row; a same-boot `set 13` matches F1's s13 row. Report GPU ms/frame and fps per scene. |
| S4 | Idle battery current and SoC temperature, 12/13/12, 300 s each. This is the idle cost of static 12. |
| S5 | `rtcwake -m freeze`: dynamic debug shows pstate 13 on suspend and 12 on resume; `read` after resume = 12. |
| S6 | Same-DT warm hop: `read` = 12, no warnings, bandwidth as S3. |
| iOS probe | Optional: SOC residency and CLPC effort at idle, GPU, CPU-memory and video load (confirms §1.2). |

## 6. PR draft (OrchardLinux/orchard)

**Title:** kernel: run the A9's SoC and memory performance states high

**Problem.**
- The A9 (S8000/S8003) boots with SoC and memory in their low performance state, DRAM at 800 of 1200 MHz, and
  nothing on Linux raises it.
- On a J71t, writing the high state at runtime takes CPU read bandwidth from 8.8 to 15.1 GB/s and write from 4.9 to
  7.2 GB/s. glmark2 scenes run 13–64 % faster at the same GPU clock.

**Changes.**
- `apple-pmgr-misc` gains an S8000 variant (`drivers/soc-apple` 0014–0015, `devices/s8000` 0007). It uses the
  T8010's register and states, set high at probe and low across suspend.
- iOS's PMGR driver accepts only these two states for the A9 SoC domain and waits up to 8 ms for a change, which
  takes about 0.6 ms on the J71t. Each chip now gives its own wait in match data. The T8010 keeps 1 ms; the S8000
  uses iOS's 8 ms.
- The node is in `s800-0-3.dtsi`. No config change: apple-16k already builds the driver.
- iOS raises this state from its performance controller under memory load. Linux has no memory bandwidth monitor
  for these chips yet, so the A9 runs it high while awake, as the T8010 does.

**Other devices affected.** Every S8000/S8003 board gets the node:
- iPad 5: J71s, J71t, J72s, J72t;
- iPhone 6s/6s Plus/SE: N71, N71m, N66, N66m, N69, N69u.

Only the J71t has run state 12, and only by a runtime write; the driver itself is untested on every board.
S8001 (A9X) is not touched.

**Dependencies and merge order.**
- It needs Henrik's T8010 pmgr-misc patches (`drivers/soc-apple` 0011–0012, on main).
- It is independent of the other 0.4 topics.
- The topic is based on main `e46f9e8`. On `origin/main` `f825c57` (checked 2026-11-11), `drivers/soc-apple`
  still ends at 0013 and `devices/s8000` at 0006, so 0014, 0015 and 0007 are free there. Re-export if a
  soc-apple or s8000 topic lands first.
- The suspend behaviour uses the driver's existing noirq hooks, so it is exercised only with the suspend topic.

**Device test still required.**
- J71t: the driver binds and reads state 12 after a cold boot and after a warm hop.
- Bandwidth and glmark2 match the runtime-12 numbers.
- Idle battery current and SoC temperature at 12 vs 13.
- s2idle/rtcwake: 13 on suspend, 12 after resume.

**Proposed CHANGELOG line.** "A9 (iPad 5, iPhone 6s/SE): memory runs at full speed while awake, about 1.5× the CPU
memory bandwidth and up to 1.6× the GPU frame rate in memory-bound scenes."

## 7. Orchard unit suite

- On `5e703f9`: 773 tests, 7 failures, 1 error, 3 skips. The FAIL/ERROR names are identical to lane IP's run on
  `b7ed084` (`diff` of the sorted names is empty). That is the known baseline: root lookup on macOS, NFS
  validation, Wi-Fi random address.
- Command: from the orchard-h worktree, `PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 ../../orchard/.venv/bin/python
  -m unittest discover -s tests -v`. The checkout's `.venv` provides the `orchard` package metadata; without it
  about 30 packaging tests error for environmental reasons.
- Log: `soc-orchard-integration-h-tests.log` (not published). The export log and build receipt
  are copied next to it.
