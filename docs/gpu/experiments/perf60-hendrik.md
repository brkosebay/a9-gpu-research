# perf60-hendrik: what the A10 stack does for 60 fps that ours doesn't

2026-11-02 night. Research only: no device access, no kernel or Mesa edits. One new runner tool
(`scripts/gpu/perf60-memclk.py`). Sources were cloned shallow into `build/third_party/` (gitignored):

| repo | path | rev |
|---|---|---|
| OrchardLinux/gpu (notes) | `orchard-gpu/` | `577de26` |
| OrchardLinux/linux (sparse: imagination, soc/apple, dts) | `orchard-linux/` | `df7c930` |
| OrchardLinux/m1n1 | `orchard-m1n1/` | `bd689a1` |
| OrchardLinux/mesa | `orchard-mesa.git` (fetched; `orchard-mesa-src` is the older `fece465` export) | `6ccd31a` |

Tags: **[P]** proven (code or measurement, cited), **[I]** inferred.

## 0. The arithmetic that sets the ranking

- **Henrik:** about 10 renders per frame, chain 10.6 ms at state 6 (1008 MHz), so about 1 ms per render.
  At state 1 his frame was 33 ms, at state 6 18.5 ms, and with the compile skip 16.7 ms
  (`orchard-gpu/a10/bringup/performance.md:21-27`) [P].
- **Ours:** 2 full-panel renders at 29–37 ms each. Of that, about 4.2 ms is fixed 3D and about 7 ms is
  firmware-internal TA, both paid per job whatever the pixel count (`perf60-fillrate.md` §8.1–8.2) [P].
- So 2 × 11 ms ≈ 22 ms of fixed cost already exceeds 16.7 ms. Even a 2.1× clock and a 2× memory clock on
  the rest leave about 25–30 ms per frame.
- **The gap to Henrik is mostly per-job fixed cost, then clock, then fill rate.**
- His stack has no job overlap either: scenes are serialized
  (`orchard-gpu/a10/bringup/kernel.md:578-583`, rule 2) [P]. So overlap is not what got him to 60 fps.

## 1. Ranked items

### 1. Keep the GPC powered: no per-job park and re-wake (largest possible gain; already flying)

- **His stack:** the GPU is powered once and stays on, and the firmware never powers it down in that setup (paraphrased)
  (`docs/gpu/hendrik/a10-gpu-reply-20261102.md` §2.8) [P].
  - His firmware's DVFS and power controllers are gated off by two init words, P+0x93c and P+0x944 = 0
    (`orchard-gpu/a10/bringup/power-display.md:51-72`) [P].
  - So nothing in the firmware ever writes Fender+0x1000.
- **Ours:** at job start, Fender showed `0x10` (a park request in flight) 22 times and `0x11` 80 times. That is
  a park/re-wake churn around each job (`perf60-clock.md` §1, pin-100 result) [P observation].
  - It is a candidate share of the fixed ~7 ms TA and ~4 ms 3D cost [I].
- **Experiment:** the pin-100 flight that is running now (`perf60clk-4a0eafe14b`, overrides via
  `ctrl+0x1038/0x1040`). Read it like this:
  - **`pol34=1 ps=00000001` steady (no `0x10`) and `ta_ms`/`td_ms` medians fall:** this is the lever. Keep pin 100
    as the base for everything below.
  - **Steady, but `ta_ms` unchanged (~7 ms):** the churn is not the TA cost. Drop this hypothesis. The TA cost is
    then firmware work at 340 MHz, and item 2 is the only lever on it.
  - **Not steady (`pol8=2`, `x=0`):** the overrides did not hold. Item 2a is blocked too.
- **DFU risk:** none beyond pin 100's (RAM words, pstate unchanged), and that hop is already flying.

### 2. GPU clock: pstate 4 (723 MHz), about 2.1× on everything GPU-clocked

**How Henrik changes the clock [P]** (`orchard-linux/drivers/gpu/drm/imagination/pvr_apple.c`):

| step | his code | A9 equivalent |
|---|---|---|
| OPP table | m1n1 `dt_set_gpu_pstates()` (`orchard-m1n1/src/kboot_gpu.c:500-551`, called at `:585` for chips without an AGX power model) adds one `oppNN` per nonzero `sgx` `perf-states` row: `opp-hz`, `opp-microvolt`, `opp-level = state` | Our ADT has the same table: 0/340/474/550/723 MHz (`docs/power/README.md` "Data actually supplied by the live ADT") [P]. The m1n1 side works unchanged [I]. |
| governor | devfreq `simple_ondemand`, 20 ms polling, up threshold 40 %, down differential 10; busy = time with jobs in flight (`pvr_apple.c:342-372, 394-420`) | none |
| the write | `devfreq_target` → `pvr_apple_request_power_state(level)`: `writel(0x10 \| state, fender+0x1000)`, then poll until `(val & 0x1f) == state`, 100 µs period, 100 ms timeout (`pvr_apple.c:287-301, 319-340`) | **R1+0x1000** (Fender `0x201e00000` + 0x1000): same format, `state \| 0x10` request, low 5 bits read back, bit 4 = busy. Apple's kext setter `6ca4ccc` and the firmware setter `0x1001c88c` both write it (`docs/power/ds-gpu-dvfs.md` §3.1, §3.4) [P]. |
| idle check | **none.** Only a host mutex; it changes the state with jobs in flight | the firmware's setter polls with no abort (`perf60-clock.md` B4) |
| voltage | none: the hardware sets the matching voltage itself (paraphrased) (`power-display.md:20-30`) | the same: the state word selects the PSINFO record at `0x20e070000 + 0x10*n`, and no host or firmware PMIC write exists (`ds-gpu-dvfs.md` §3.4) [P code, I hardware response] |
| firmware | DVFS gated off (P+0x93c/0x944 = 0), so it never fights the host | **on:** `meta+0x6c8 = 1`, and the firmware writes R1+0x1000 itself (`0x1001c88c`) |

- **`+0x1004`, Henrik's question:** our firmware's pstate setter writes only `+0x1000`. `R1+0x1004` is just stored
  as 0 on every idle main-loop tick, and its meaning is unknown.

**Is host-driven pstate selection viable on A9?** Not alongside our current firmware construction [P/I]:

- The only bypass is `meta+0x6c8 = 0` (`dc_variant=7`). It drops r73b/r74/r74f/r74g/r87b and with them TYPED_V3
  (`nopatch.md:400`) [P]. So Henrik's model (firmware DVFS off, host writes R1+0x1000) means a different boot
  construction, not a knob.
- With `6c8 = 1`, a host write to R1+0x1000 races the firmware's own setter, which re-requests 0/1 on its policy
  passes (the churn in item 1) [I].
- So on A9 the clock goes **through the firmware policy**: `ctrl+0x1040 = pin`, the firmware's own override
  input. That is the `perf60clk` route.
- **Also needed:** every host R0 access must license on any settled nonzero pstate (`gpc_any_pstate=1`), as
  Apple's `submitDeviceControl` does (`perf60-clock.md` B3). Henrik never had that rule.

**Experiments:**

- **2a. Safest first step (already DEVICE-READY):** `scripts/gpu/perf60-clock-device.sh hop 200`, and only after
  item 1 shows the overrides hold.
  - PASS = `pol34=2 ps=00000002` and `bad_lines=0`. Then `hop 400`.
  - **DFU risk: yes, for pin ≥ 200.** No Linux boot has left pstate 1. A state whose voltage doesn't follow
    would freeze the SoC.
- **2b. Load-driven DVFS, Henrik-style:** only after 2a passes at 400.
  - Devfreq with `simple_ondemand` on the m1n1 OPP table, with the target callback writing
    `ctrl+0x1040 = level * 100` (not R1+0x1000). Same 20 ms period, 40/10 thresholds.
  - First prove that a change to `ctrl+0x1040` after release is picked up. The firmware reloads it every policy
    pass (`perf60-clock.md` §1), so this is likely [I].
  - Our config already has `CONFIG_PM_DEVFREQ=y`, `DEVFREQ_GOV_SIMPLE_ONDEMAND=y` and `PM_OPP=y`, so no config
    change is needed.
  - Same DFU risk class as 2a.
- **Henrik's trap to copy:** `pm_runtime_forbid()` powers on before the OPP table was read, so the first load
  requested state 0 and reset the iPad (`power-display.md` "Pitfall"). Never let a table lookup yield 0 for a
  power-on request.

### 3. SoC/memory clock: PMGR+0x68000 (cheapest test; gain grows after item 2)

**His code [P]:**

- `orchard-linux/drivers/soc/apple/apple-pmgr-misc.c:17-19` (low nibble = desired state, bit 31 = pending),
  `:29-30` (T8010 low `0xd`, high `0xc`), `:66-89` (read-modify-write of the nibble, then poll bit 31 clear,
  1 µs/1 ms) and `:190-198` (T8010: `DEV_SOC` from `0xd` to `0xc` at probe).
- DT node: `arch/arm64/boot/dts/apple/t8010.dtsi:567-569`, `reg = <0x2 0x0e068000 0x0 0x4>`.
- Measured with `0xc`: CPU memset 5.2 → 10.3 GB/s, memcpy 6.8 → 13.6, an empty full-screen GPU render
  2.24 → 1.32 ms (`power-display.md:114-132`).

**A9 equivalent [P register and protocol, I direction]:**

- Same physical address: our PMGR base is `0x20e000000` (`scripts/gpu/read-id.sh` `GPU_PMGR=0x20e080340`), so the
  register is `0x20e068000`.
- iOS's `AppleS8000PMGR` setPerfState (`fffffff005e92094`, `docs/power/evidence/s8000-set-perf.c:60-69`) shows the
  SOC domain (domain 1 of the live ADT's `perf-domains`, named "SOC"):
  - It accepts **only mapped states 12 and 13** (`(s & ~1) == 0xc`).
  - It does a read-modify-write of the low nibble.
  - It optionally polls bit 31 clear, with a 0x2ee00-tick timeout (8 ms).
  - That is the same protocol as T8010 with the same two values. Our `docs/power/README.md:253-254` was right
    that it is "not a GPU perf-state API", but it is the **memory/fabric** state, which feeds the GPU's stores.
- iOS raises it dynamically under GPU load: the live ADT `clpc` node has `dynamic-soc-control = 1`,
  `soc-throughput-gpu-threshold`, and `soc-throughput-gpu-ki-up/-down` (the private live ADT dump (not published)
  lines 640–740) [P]. Linux has nothing that writes it.
- **Voltage:** `AppleS8000PMGR_setVoltageControlMode` (`fffffff005e91b0c`, Ghidra) behaves like this:
  - Mode 0 sets bits `0x1f00` of PMGR+0xa0000.
  - Any other mode clears them and writes explicit voltages. For the SoC it uses byte [15:8] of the current state's
    record word `PMGR + 0x68000 + 0x10*state + 0x18` into +0xa0008.
  - **Corrected 2026-11-03 (§3):** iOS runs with these bits **clear**. Mode 1 is set at init and mode 0 only on
    its power-transition path. The device reads `0xa0000 = 0`, which is iOS's runtime mode, not "software". The
    first version of the tool had the gate the wrong way round; it now checks the iOS runtime configuration.
  - 12 is the fast state [P]: iOS maps perf index *i* to state `13 − i`, and the state-12 record code (48) is
    above state 13's (10).
- **Is Linux on A9 low?** Probably [I]:
  - Our CPU memset is 4.9 GB/s against Henrik's low 5.2 and high 10.3.
  - Henrik's symptom does not fully match, though: our GPU store (1.7 GB/s) is far *below* CPU memset. So the
    GPU stores are clock-bound at 340 MHz today, not memory-bound.
  - Expect a CPU-side doubling now (wl_shm clients, copies). On the GPU, expect some gain on load and store rungs
    now and more after item 2. At 723 MHz the store rate would reach ~3.6 GB/s, which is near what the low
    memory state can feed.

**Runtime test (live release7, no hop):** see §2 for exact commands.

- **DFU risk: low, not zero.** The values and sequence are exactly what iOS does at runtime, and the write is
  refused unless the sequencer is in iOS's runtime configuration (§3). The worst case is a memory-controller
  hang = SoC freeze → DFU.
- Nothing persistent is touched: a reboot restores the boot state.
- **Note for the suspend lane:** if this becomes a driver, restore the state on resume, as Henrik's driver does
  (`:92-111`).

### 4. Empty-tile skip on loaded and don't-care renders (large on partial damage, none on full damage)

- **His rule [P]** (`orchard-mesa.git` `src/imagination/vulkan/pvr_arch_g9p_gfx.c:1707-1720`):
  - ISP_CTL is `0x21000f` (bit 17 off = skip tiles no draw reaches) when the render loads its target **or has a
    don't-care load op**.
  - Otherwise it is `0x23000f`. `G9P_ALL_TILES=1` forces it on.
  - Most of Hyprland's blur passes are full-screen *clears* and keep bit 17 (`performance.md:44-47`). The single
    don't-care pass, which covers the whole screen to draw a small damaged part (`pvr_arch_g9p_gfx.c:1714-1716`),
    is the one that skips.
- **Ours:** the same register word (`w3c0=0021000f`). The kernel side is proven ×6.4 on small damage, and the
  per-pass contract is built (`perf60-fillrate.md` §7, `a9/perf60-empty@06ef780212`).
  - **His addition to copy:** treat don't-care like load. Clear-load renders must keep bit 17.
  - The Mesa side of §7.3 is still unwritten, and this is the rule it should implement.
- **Gain:** about 0 on es2gears (90 % damage). It is large on a real desktop (cursor, typing, a moving window).
- **DFU risk:** none (Mesa + a runtime knob; the failure mode is stale tiles).

### 5. Per-render compile skip (CPU; only matters once the GPU chain is under ~14 ms)

- **His fix [P], two early returns for `apple_g9p`:**
  - `pvr_arch_mrt_load_ops_setup()` (`pvr_arch_mrt.c:500-507`): no load-op programs, shader compile or upload
    per `vkCmdBeginRendering`.
  - The SPM end-of-tile loop in `pvr_arch_render_state_setup()` (`pvr_arch_framebuffer.c:157-165`).
  - This took a third of Hyprland's CPU time; frames went from 18.5 to 16.7 ms.
- **Ours pays it [P]:**
  - `mesa-a9-perf60-src/src/imagination/vulkan/pvr_arch_cmd_buffer.c:5069` calls `pvr_arch_mrt_load_ops_setup()`
    with no g5p guard.
  - `pvr_arch_framebuffer.c:158` runs `pvr_arch_spm_init_eot_state()` per render.
  - Our g5p job path takes its EOT/background programs from Apple's captured programs, so skipping is likely safe
    [I]. The ICD owner should confirm that `g5p_submit.c` reads neither `load_op_state` nor `spm_eot_state`.
- **Gain:** CPU is 85 % idle today (`perf60.md` baseline), so ~0 FPS now. With Zink, CPU time sits in front of the
  GPU chain (`performance.md:29-36`), so it becomes ~2 ms/frame once items 1–3 land.
- **DFU risk:** none.

### 6. Ruled out as the 60 fps difference [P]

- **Job overlap:** his scenes are serialized too (`kernel.md:578-583`). His host hand-offs are 15–17 µs
  (`performance.md:41-43`); ours are ~2 ms of polling edges (`perf60-fillrate.md` §8.1). That is worth a cleanup
  but is not the gap.
- **f16 sample return:**
  - He returns f32: `0xf51a` into four registers (`g9p_isa.h:484-506`, `g9p_compile.c:1392-1440`). `0xf518` (halves
    into the colour output) is documented but unused.
  - Our Hyprland texture sample uses the same `0xf51a` opcode (`1a f5 04 01 08 84`). So the return width is not
    our 0.7 GB/s blit problem.
  - Two differences remain for the ICD owner's offline diff against Apple's A9 LOAD program [I, the ISA differs
    per chip]:
    - His sample is 5 half-words (`f51a, 0100|2·dst, 8100|state<<8|sampler, 0700, 0200`) against our 3.
    - He iterates varyings straight into the sampler (W2 `0x8000`, `g9p_sample_varying`), and lowers `texelFetch`
      to an explicit-LOD sample at the texel centre (`g9p_compile.c:2644-2668`).
- **PBE store settings:** nothing G9P-specific that we lack. His store speed-up came from the memory clock
  (item 3), not from PBE words [I: not diffed word for word].
- **Every job kicked (`0x83<<48` on endpoint 0x21):** the A9 analogue is Apple's unconditional doorbell at TA
  publish, i.e. r81 `p1`, never flown (`83-apple-ta-launch-exact.md` §A). It targets the dispatch plateau, not
  per-frame cost.

## 2. Runner commands: the memory-clock poke (item 3), live release7, no hop

Prereq: the owner's release7 session up and the desktop idle (no gears), and
`scripts/boot/netconsole.sh listen build/omarchy/logs/netconsole-perf60-memclk.log` in another terminal.

*(Device/host command block omitted; it targets the private workspace.)*

- **PASS:**
  - CPU memset climbs well above 4.9 GB/s (Henrik: ×2).
  - The fixture's `clear`/`solid` `td` drop, and the desktop stays responsive.
  - Record `blit` too: unchanged means the sample path is not memory-bound.
- **Stop and report:**
  - Any `refused: …` (hold bits set, routing not `0x1782`, the record codes not 48 > 10, or the SOC live code not
    equal to the current state's record code): do not use `--force`; send the `read` output back for analysis.
  - `REVERTED`: the live code did not follow, and the tool already wrote 13 back. Send both outputs back.
  - `STILL PENDING`: run `set 13` at once.
  - SSH and netconsole silent: SoC freeze → DFU, then cold boot.
- **If it passes:** the proper form is an `apple,s8000-pmgr-misc` variant of Henrik's driver (one table entry,
  plus the DT node at `0x20e068000`), not a boot script.

## 3. SoC voltage before 13 → 12: what iOS does (offline RE, 2026-11-03)

Trigger: device `read` (`build/gpu/perf60/memclk-read1.txt`):

- `0x68000 = 0x00000ddd` (state 13)
- records `0x680d8 = 0x3015` (code 48), `0x680e8 = 0x0a05` (code 10)
- `0xa0000 = 0`

The old tool called that "SOFTWARE" and stopped. Sources: the shared Ghidra on the iOS 16.7.10 j71t kernelcache,
and a raw scan of `__PLK_TEXT_EXEC` for virtual calls through the AppleS8000PMGR vtable (start
`0xfffffff006e0fe30`): setPerfState is slot `+0x768`, setVoltageControlMode `+0x6b0`, the index map `+0x778`.

**Answer: iOS writes no voltage before the raise, nothing over I2C/SPMI and nothing through AOP/SMC. The PMGR's
automatic voltage sequencer moves the SOC rail from the state record itself.** [P for "no host write", I for the
hardware action]

1. **The only writers [P].**
   - In the AppleS8000PMGR kext, `PMGR+0xa00xx` is touched only by `setVoltageControlMode` (`5e91b0c`).
   - `PMGR+0x68000` is touched only by that function and `setPerfState` (`5e92094`).
   - Every 32-bit constant `0xa0000`/`0x6xxxx` in the kext disassembly is at `5e91b24..5e91c0c` or
     `5e920f4..5e92128`.
2. **The runtime caller [P]:** `FUN_fffffff005a39b30` in base ApplePMGR (the device perf-state setter that logs
   `ApplePMGR: %s: %u -> %u`).
   - It calls slot `+0x6c8` first only for domains with flag bit 1. That slot is `5e91ca0`, a CPU cluster
     hand-off that polls `PMGR+0xc8100`/`+0xc8300` bit 1.
   - Then it calls `+0x768` (setPerfState).
   - After that come only reporting calls (`IOStateReporter`, `FUN_5a31440`); there is no voltage call before or
     after.
   - The CPU-cluster path `FUN_5a3ac64` is the same: `+0x768`, then bookkeeping.
3. **The SOC branch of setPerfState [P]** (`s8000-set-perf.c:60-69`):
   - `state = 13 − index` (slot `+0x778` = `5e92380`: domain 1 returns `0xd − w2`; domain 2, the CPU, returns
     `w2 + 2`).
   - It accepts only 12/13, then `w32(0x68000, r32(0x68000) & ~0xf | state)`.
   - If the caller asked to wait, it polls `0x68000` bit 31 clear with a `0x2ee00`-tick timeout (8 ms at 24 MHz).
   - That is the whole sequence: one write, one ack poll.
4. **The voltage mode [P code, I meaning]:**
   - At init, base ApplePMGR `FUN_5a2ca70` calls `+0x6a8(1)` and then `setVoltageControlMode(1)` (`5a2cc30`). That
     clears `0xa0000` bits `0x1f00` and seeds the live codes: `+0xa0018` = CPU PSINFO1[63:56], `+0xa0010` =
     PSINFO2[39:32], and `+0xa0008` = the current SOC state record's byte [15:8].
   - Mode 0 (sets `0x1f00`, no seeds) is called only from `FUN_5a2ab00` (`5a2adf4`), the power-transition path
     that logs `currentPerfState … driver in %s state`. Probably sleep [I].
   - So **`0xa0000` bits clear is iOS's normal running mode.** LLB/iBoot OR in `0x1f00` at boot, and m1n1's
     `cpufreq_init` writes `1` (`overclock-round4.md`). Linux's `0` is the iOS runtime mode, not "software".
   - Our CPU cpufreq already runs 300–1800 MHz in this same mode, with nothing on Linux writing a voltage. The
     sequencer handles the CPU rails there [I; nominal codes, no analog measurement].
5. **The A9 regulator [P]** (`docs/power/overclock-round3.md`, LLB rail table):
   - The SOC is logical rail 2, PMIC buck register `0x12`, base 600 mV, step 3.125 mV.
   - State 13 code 10 = **631 mV**; state 12 code 48 = **750 mV** (nominal DAC targets).
   - The PMIC is the Dialog D2365 on `i2c@20a110000` at `0x3c`, behind PMGR's own DWI interface for DVFS.
6. **Order, delays and acks:**
   - iOS has none of its own; the 8 ms bit-31 poll is the only ack.
   - "Voltage up before frequency up, frequency down before voltage down" happens inside the sequencer while bit 31
     is set [I]. There is no software ordering to copy.

**What it means for us:**

- Doing exactly what iOS does is the single write that is already in the tool.
- **No PMIC access is needed, and none is proposed.** Our kernel has no regulator driver for the D2365 and
  `CONFIG_I2C_CHARDEV` is off. Raw PMIC writes are what `docs/power/README.md` forbids anyway.
- **Userspace `/dev/mem` is enough for the test.** No kernel change is needed for it. The proper form is still an
  `apple,s8000-pmgr-misc` variant.

**Test procedure (`scripts/gpu/perf60-memclk.py`, revised gate):**

1. `read`. **Proceed only if** all of these hold; the tool refuses otherwise:
   - the sequencer reads "auto" (`0xa0000 & 0x1f00 == 0`);
   - the routing word `0xa0004 == 0x1782` (LLB's value, which iOS and iBoot keep);
   - the record codes are 48 > 10;
   - the SOC live code `0xa0008[7:0]` == 10, the current state 13's code. That is iOS's seed, and it shows the
     live register tracks the records.
2. `bench` and the fixture (before).
3. `set 12`:
   - One read-modify-write of `0x68000`, then poll bit 31 (≤ 50 ms).
   - Then watch `0xa0008` for 20 ms. **PASS = it reaches 48**: the sequencer raised the SOC rail target.
   - If it doesn't, the tool writes 13 back at once and prints `REVERTED`.
4. `read`, `bench` and the fixture (after).
5. `set 13` to revert, or reboot. Going down is the safe direction (lower clock first).

**Risk:**

- **Low, but DFU-class:**
  - The register, values and sequence are iOS's own runtime transition, and the sequencer configuration is
    checked against iOS's first.
  - Nothing persistent is written (no PMIC, no NVRAM, no syscfg).
- **Remaining unknown:**
  - If `0xa0008` turns out to be a seed register that the sequencer never rewrites, the tool reverts after 20 ms.
    During those 20 ms the SoC/memory would run the fast clock on whatever voltage the hardware applied.
  - The failure mode is a SoC freeze → DFU.
- **Not proposed:** a manual "voltage first" write of 48 to `0xa0008`. iOS never does that at runtime, and its
  effect in the auto mode is unknown. Consider it only if step 3 reverts cleanly and the owner agrees.

## 4. Proven vs inferred, in one place

- **Proven:**
  - His code paths and numbers, as cited.
  - On A9: the register identity and the 12/13-only protocol (iOS `5e92094`), the voltage-mode function
    (`5e91b0c`), and the `clpc` dynamic-SoC properties.
  - The R1+0x1000 format and its writers.
  - That `6c8 = 0` drops TYPED_V3.
  - The missing compile-skip guards in our ICD.
  - That serialization and f32 return are shared with his stack.
- **Inferred:**
  - That PMGR's sequencer applies the SOC record code on a 13 → 12 change when `0xa0000` bits [12:8] are clear
    (§3; `set` measures it through `0xa0008`). Proven since §3: 12 is the fast state, and iOS writes no voltage
    for the change.
  - That the churn is part of the fixed TA cost.
  - That `ctrl+0x1040` changes are picked up after release (needed for 2b).
  - That skipping load-op/SPM setup is safe for g5p.

## 5. Making it permanent: the `apple,s8000-pmgr-misc` driver (2026-11-03)

**Hardware result that motivates it** (orchestrator, `build/gpu/perf60/memclk/`) [P]:

- `set 12` read back `0xccc` after 710 µs, and the live SOC code reached 48 after 4 µs. No freeze.
- CPU memset 4.56 → 6.99 GB/s; memcpy 3.06 → 4.63 GB/s.
- Fixture: blit 36 → 16 ms, solid 18 → 12, load_small 31 → 18. ALU (62 → 58) and clear (12) barely moved.
- So the sample and load paths were memory-bound, and PBE stores are not (yet).

**Branches** (public fork, unpushed; the orchestrator syncs them):

- `a9/perf60-memclk@2716a6e0f4`: `a9/release7@802a3d4fc4` + one commit, "soc: apple: pmgr-misc: run the A9
  SoC/memory state fast". Five files:
  - `drivers/soc/apple/apple-pmgr-misc.c`
  - `drivers/soc/apple/Kconfig`
  - `arch/arm64/boot/dts/apple/s800-0-3.dtsi`
  - `arch/arm64/boot/dts/apple/s800x-ipad5.dtsi`
  - the `apple,t6000-pmgr-misc.yaml` binding
  - checkpatch is clean on the code; its only messages are about the commit (the trailer form and the binding
    sharing the patch).
- `a9/perf60-clockmem@4b61debe9d` = `a9/perf60-clock@b2881642b8` (never-park + bells + pin ladder) + a `--no-ff`
  merge of `a9/perf60-memclk`.
  - The merge is clean: the clock lane touches only `drivers/gpu/{,drm/}apple-g5p/`.
  - Worktree: `/src/wt/perf60-clockmem`.
  - Build, package and on-device check: `scripts/gpu/perf60-clockmem-build.sh`.
  - `CLOCK_TIP` pins the clock commit. For a newer clock tip, run `CLOCK_TIP=<sha> ... branch` on a fresh
    worktree, then build.

**Driver** (Asahi's pmgr-misc, restructured the way Henrik's T8010 port is: a per-SoC `devices` mask, plus an
S8000 variant):

- **Probe** sets state `s8000_soc_pstate` (module parameter, default 12; 13 = as booted; 0 = left alone). It uses
  exactly the tool's sequence:
  - Refuse a pending change or a state other than 12/13.
  - Gates: hold bits `0xa0000[12:8]` clear, routing `0xa0004 == 0x1782`, record code of 12 > record code of 13,
    and the live code `0xa0008[7:0]` equal to the current state's code.
  - One read-modify-write of `0x68000`, then poll bit 31 (8 ms, iOS's timeout).
  - Poll the live code until it equals the new state's record code (20 ms). On failure, write the old state back
    and return `-EIO`.
  - A refused or failed change keeps the boot state, and the driver stays bound.
- **Boot line, always** (also when a warm hop finds the SoC already in 12):
  `apple-pmgr-misc 20e068000.power-management: soc-perf state=12 code=48 ok`. Any other outcome shows a
  `soc-perf:` warning or error line, and the report line ends in `MISMATCH`.
- **Runtime A/B:** `/sys/bus/platform/devices/20e068000.power-management/soc_pstate` reads the state and takes 12
  or 13 (the same checked sequence, plus a report line). A cold boot can stay slow with the kernel argument
  `apple_pmgr_misc.s8000_soc_pstate=13`.
- **Suspend/resume:** noirq suspend goes to 13 and resume restores the chosen state, through the same checked
  path. Henrik's driver does the same.
- **DT:** `pmgr_misc: power-management@20e068000` in `s800-0-3.dtsi`, `status = "disabled"`.
  - `reg = <0x2 0x0e068000 0x0 0x100>` ("soc-ps": the state register and the records up to state 15) and
    `<0x2 0x0e0a0000 0x0 0x20>` ("volman").
  - Both lie in the ADT pmgr node's `reg[0]` (`0x20e000000`, 1 MiB; `docs/adt/j71t.txt:1727`, `j71s.txt:449`).
  - Enabled in `s800x-ipad5.dtsi`, which j71s/j71t/j72s/j72t include. S8001 and the phones are untouched.
- **Config:** `CONFIG_APPLE_PMGR_MISC=y`, the only change against release7's config (checked by `verify`).

**Package (release7 layout, DEVICE-READY)** — `scripts/gpu/perf60-clockmem-build.sh package` produces it:

- Entry `perf60cm-4b61debe9d`, release `7.3.0-rc1-perf60cm-g4b61debe9d01`.
- Payload `build/boot/m1n1-linux-perf60cm-4b61debe9d.bin`, sha256
  `15519dc395a7…`.
- `build/gpu/perf60-clockmem/{entry,release,cmdline,cmdline-sd,labwc,payload.sha256,entry.sha256,dtbs}`.
- The build has 0 warnings, and the driver object is also W=1 clean. `verify` passed: the tip, a clean tree, only
  the memclk files on top of the clock tip, config = release7's + `APPLE_PMGR_MISC`, and the four DTBs =
  release7's + the node (6 lines each). The Image carries the driver's strings. The worktree is not cleaned yet:
  run `scripts/gpu/perf60-clockmem-build.sh clean` once the package is flown.
- The initramfs and cmdline are release7's (entry renamed).
- The DTBs are release7's packaged DTBs (stock OPPs) plus exactly the built tree's `pmgr_misc` node, copied
  property by property with `fdtput`. `verify` checks that nothing else in the DT changed. The tree's own j71t/j72t
  DTBs carry the overclock OPP table, which release7's do not.

**Runner (orchestrator; DFU risk: the clock lane's for pin ≥ 200; memclk itself is low, proven live):**

*(Device/host command block omitted; it targets the private workspace.)*

- **PASS:** the boot line, `check`'s readback (state 12, live code 48), the desktop up, and `measure`'s
  `bad_lines=0`.
- **Stop:** any `soc-perf:` warning or error, or a `MISMATCH`: the driver kept or restored the safe state, and the
  desktop runs as on the clock package. Send `check`'s output back.

**Follow-up for battery: how iOS ties the state to GPU load** [P ADT properties, I mechanism]:

- iOS doesn't pin 12. The live ADT's `clpc` node (closed-loop performance controller) has
  `dynamic-soc-control = 1`, `soc-throughput-gpu-threshold`, `soc-throughput-gpu-ki-up/-down`,
  `soc-throughput-cpu-*` and `soc-fast-device-index = 4` (the live ADT dump, not published).
- So CLPC raises the SOC domain through ApplePMGR's device perf-state call (`ApplePMGR_setDevicePerfState`,
  `5a39b30` → slot `+0x768`) when GPU (or CPU) throughput crosses a threshold, and lowers it with hysteresis.
- **Linux equivalent, upstream-style:** export a request from pmgr-misc to the G5P driver, either through the
  interconnect framework (a bandwidth vote) or a devfreq passive governor parented to the GPU devfreq.
  - The GPU driver votes "fast" while jobs are in flight and releases after an idle window, e.g. the 20 ms devfreq
    period Henrik uses for the GPU clock.
  - The transition costs ~0.7 ms (measured), so per-frame switching is affordable.
  - Not done here: the desktop wants 12 whenever it renders, and default-on matches tonight's goal.
