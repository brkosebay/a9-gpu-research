# Hard problems we solved (or pinned down) on the A9 GPU

A symptom-indexed catalogue for people porting Linux GPU support to older Apple PowerVR GPUs (A7, A8/A8X,
A9/A9X, and the A10 work at OrchardLinux). Each entry is something that cost us days. It says what you will
see, why it happens, what fixed it, **how we found it** (the method matters more than the answer if your
chip differs), and whether we expect it on other chips.

The path to the first triangle (power-on to first pixels, including the long TA stall) is in
[FIRST-TRIANGLE.md](FIRST-TRIANGLE.md). This file covers what came after: running real clients on a real
desktop. Per-subsystem porting advice is in [PORTING-OLDER-GENERATIONS.md](PORTING-OLDER-GENERATIONS.md).

**How to read an entry**
- **Labels:** **[P]** proven from code, a decode or captured data. **[V]** verified on our device (a
  flight). **[T]** tested on the host only. **[I]** inferred. "Not flown" means built but never run on
  the device. The source docs use more than one legend; the labels here are normalised to this one.
- **Elsewhere?**
  - **generation-wide**: shared Mesa or Linux code, or the shared kext/firmware design. We expect it on
    any Apple PowerVR chip.
  - **probably**: firmware or Rogue design we expect to carry over, but we haven't checked it on
    another chip.
  - **A9-specific**: tied to A9 values, A9 silicon, or our own driver's choices.

  We never analysed A7 or A8 firmware, so every rating is an inference.
- **Register shorthand:**
  - `R1` is the GPU power wrapper ("Fender") window: `R1+0x1000` is the GPC pstate nibble, `R1+0` holds
    the park flags (bits 29/30), and `R1+0x14 = 7` is the wake write.
  - `R0` is the GPU core window; `R0+0xb00 = 0x10` is the firmware doorbell.
  - `ctrl+`, `policy+` and `meta+` are words in the shared RAM objects that the host and the META firmware
    both see (control object, power-policy record, firmware metadata block).
  - `0x1000xxxx`/`0x8000xxxx` addresses are in the META firmware image. `fffffff00…` addresses are in the
    iOS 16.7.10 J71t kernelcache as named in our Ghidra project.
- **Sources** link to the published doc. "(unpublished)" means the evidence lives in our private workspace;
  the entry states what it established.

## Symptom index

| You see | Entry |
|---|---|
| `DC timeout consumer=0 producer=1 target=1`, then `autoboot stopped at control-wait (-110)` | [F1](#f1) (idle record at map) or [P2](#p2) (pin above the boot pstate): one signature, two causes |
| First ALIVE reads `state=00000000`, `ALIVE submit … ret=-112 … power_abort=1`, or no ALIVE at all | [F2](#f2) |
| First TA consumed but never started; 60 s timeout, DEVICE_LOST | [F3](#f3) |
| Job 1 never runs; a later client's bind times out `ret=-110 consumed_us=-1` | [F4](#f4) |
| After a warm kexec the new kernel never prints a line | [F5](#f5) |
| Warm or hand-run boot refuses every job, `claims=0`, no `latched` lines | [F6](#f6) |
| `RENDER-V3 lost … why=3d-silent`, then the whole SoC locks | [F7](#f7) |
| Whole SoC freezes 0.3–3 s after a client closes and a new one binds | [F8](#f8) |
| RCU stall report during warm-boot GPU bring-up | [F9](#f9) |
| `pstate` never 0 at idle; sleep readiness says `never-park` | [P1](#p1), [P8](#p8) |
| GPU stuck at 340 MHz (boot pstate) whatever you pin | [P2](#p2) |
| After enabling self-park: ~400 µs per doorbell, fps down | [P3](#p3) |
| After enabling self-park: TA wait +0.7 ms per job; fps 543 → 340 | [P4](#p4), [J3](#j3) |
| Whole SoC hangs on a GPU register read near idle, or after a job retired | [P5](#p5) |
| GPU overclock gives nothing; GPU ms/frame flat; CPU memcpy ≈ 8.8 GB/s | [P6](#p6) |
| Above some GPU clock: next submit `-EIO`, `accepted=0`, kernel prints nothing | [P7](#p7) |
| `s2idle` refused exactly 1.0 s after `PM: suspend entry`, GPU parked | [P9](#p9) |
| Warm boots only: `s2idle` returns EBUSY with no line | [P10](#p10) |
| Every job costs ~1 ms more than its GPU work, even an empty pass | [J1](#j1) |
| TA of the next frame never starts under the previous 3D | [J2](#j2), [J6](#j6) |
| GPU 60 % busy, rings empty between frames, firmware parks every frame | [J3](#j3) |
| Fill rate ~1/6 of iOS, clears ~1 GB/s | [J4](#j4) |
| Small damage costs as much as a full-screen redraw | [J5](#j5) |
| After a Mesa rebase: −20 % fps at the same GPU ms/frame | [J7](#j7) |
| Firefox/Aquarium: GPU idle a third of every frame | [J8](#j8) |
| 1M triangles: TA fault, context lost | [J9](#j9) |
| Second client: PM fault at VA 0, or `3d-silent` after a context switch | [J10](#j10) |
| `refuses: a non-linear colour target`, then the app hangs | [Z1](#z1), [Z3](#z3) |
| glGenerateMipmap: level 4 all wrong, or 2 fps with `pthread_once` on top of perf | [Z2](#z2) |
| GL client hangs forever in `drm_syncobj_timeline_wait` after a lost batch; SIGTERM ignored | [Z3](#z3) |
| `zink: couldn't allocate memory`, hundreds of 2 MiB BOs | [Z4](#z4), [M3](#m3) |
| Shader ALU 5× slower than iOS | [Z5](#z5) |
| Vertex registers r8+ read as zero; vkcube/weston wrong | [Z6](#z6) |
| Noise and stale tiles under blended draws | [Z7](#z7) |
| Random ENOENT at GEM lookup during submit (Firefox) | [Z8](#z8) |
| Expecting 2× from fp16 | [Z9](#z9) |
| WebRender shaders refused: `register pressure … 32 of 32` | [Z10](#z10) |
| HW WebRender at 12 fps, a 53–63 ms CPU transfer per frame | [Z11](#z11) |
| MSAA renderbuffer silently incomplete | [Z12](#z12) |
| Dead clients' BOs stay pinned (`handles=0 … vm_pins=1`) | [M1](#m1) |
| GPU RAM per client "doesn't add up" | [M2](#m2) |
| Compositor stops drawing after ~1000 frames | [M4](#m4) |
| Shmem grows all session on a GL desktop | [M5](#m5) |
| ENOSPC from the GPU driver with plenty of RAM free | [M7](#m7) |
| H.264 B-frames wrong only through FFmpeg | [V1](#v1) |
| "Hardware decode works" but it was software | [V2](#v2) |
| Netconsole silent over USB networking | [T2](#t2) |
| A tracer does nothing under `sudo` | [T4](#t4) |

---

## Firmware bring-up and the boot handshake

<a id="f1"></a>
### F1. Bring-up stops at the control command after adding iOS's idle-power record at map

- **Symptom.** ALIVE and the DC boot handoff succeed, and the autoboot phases up to control-submit return 0.
  Then `DC timeout consumer=0 producer=1 target=1` at about 10 s and `autoboot stopped at control-wait
  (-110)`. The SoC stays healthy. [V]
- **Root cause.** The new kernel wrote iOS's whole idle-power record at firmware map: sampler period 16 ms,
  coefficient block, `meta+0x6c4/0x700 = 1`. It also released the GPC at pstate 1 instead of the pinned 4,
  while the park veto `ctrl+0x20` ([P1](#p1)) was still 0. iOS never runs in that state, because it writes
  `ctrl+0x20 = 1` at init. [P]
  - The strongest suspect is `meta+0x6c4`: the per-boot init copies it to `priv+0x230`, which turns on a
    main-loop routine (`0x100044f0`) that no other Linux boot runs. [I]
  - The word that held cmd8 was **not** isolated.
- **Fix.** Map exactly as the last good build: pinned pstate 4 at release, no idle record, sampler off. Write
  the idle record live only after a complete epoch (ALIVE, control complete, nothing failed): the
  coefficients, a barrier, `policy+4 = 16`, a barrier, then `ctrl+0x20 = 1` with a read-back. [V] FLIGHT-H2:
  every expected line in order, including `cmd8-consumed` and `self-park armed … ctl20=1`.
- **How we found it.** *Diff against the last good build first.* The failing kernel was the good one plus two
  patches. Every hunk outside the map was gated on a flag that was still false, so the cause had to be the
  map-time writes. We tabulated good-boot vs failing-boot words from dmesg. Firmware disassembly came only
  afterwards, to explain the words that differed. No device variants were flown.
- **Elsewhere?** probably: the META idle governor and the map-vs-arm ordering are firmware design.
- **Sources.** [lane IP2](docs/release/orchard-0.4/lane-ip2/README.md), [FLIGHT-G](docs/release/orchard-0.4/integration/FLIGHT-G.md), [FLIGHT-H2](docs/release/orchard-0.4/integration/FLIGHT-H2.md).

<a id="f2"></a>
### F2. Allowing the park before bring-up: the first ALIVE reads a parked GPC, or the wake never sends ALIVE

- **Symptom.** With `ctrl+0x20 = 1` before release, the first-ALIVE read gives `state=00000000` and
  `ALIVE submit … ret=-112 … power_abort=1`. With a pinned record, a 16 ms sampler and a stale stamp, there is
  no ALIVE at all and Fender reads 0. [V]
- **Root cause.** [P]
  - The firmware parks as soon as its rings are empty. With the veto clear, it parks before the host's
    first-ALIVE proof.
  - A parked firmware never returns: every wake is a **firmware reboot**. The reboot runs the unpark
    handshake, then the boot sampler (`0x1000aa80`, once per firmware boot), then the scheduler.
  - The sampler divides elapsed time by `policy+4`. With the pinned record (`policy+4 = 0`), a park-then-wake
    divides by zero.
- **Fix.** Arm the park only after a complete epoch ([F1](#f1)). Write `policy+4` nonzero immediately
  before `ctrl+0x20 = 1`, so the sampler-on/park-vetoed pair ([F3](#f3)) exists only between two stores. On
  resume, disarm first and reset `policy+0/+4`. [V] 50/50 park/unpark cycles; warm boots arm and park.
- **How we found it.** We disassembled the park routine (`0x1001cec8`) and the boot sampler, and matched
  them against three earlier failure signatures.
- **Elsewhere?** probably: park-is-a-reboot is firmware behaviour of this META lineage.
- **Sources.** [lane IP](docs/release/orchard-0.4/lane-ip/README.md), [lane IP2](docs/release/orchard-0.4/lane-ip2/README.md), [FLIGHT-H2](docs/release/orchard-0.4/integration/FLIGHT-H2.md).

<a id="f3"></a>
### F3. First TA consumed, never started, while the sampler runs with the park vetoed

- **Symptom.** The firmware consumes the first TA, which never starts. After a 60 s timeout comes
  DEVICE_LOST, in 2 of 3 boots. A warm kexec out of that state was not safe. [V]
- **Root cause.** The pair `policy+4 = 16` (sampler on) and `ctrl+0x20 = 0` (park vetoed). [P]
  - With the veto set, the job-start functions take an extra path (`0x100130a0` plus an activity record)
    that iOS never runs. [I]
- **Fix.** Never let that pair exist outside two adjacent stores ([F2](#f2)). Never turn `ctrl+0x20` off live
  in a park epoch: our debugfs refuses it with `-EBUSY`. [V]
- **How we found it.** We flew one firmware power word per flight. Then the decode of what `ctrl+0x20`
  changes inside the firmware explained why the older evidence did not transfer.
- **Elsewhere?** probably.
- **Sources.** [lane IP §1.4–1.5](docs/release/orchard-0.4/lane-ip/README.md), [apple-idle-power-design §3](docs/gpu/apple-idle-power-design-20261109.md), [STATUS](docs/gpu/STATUS.md).

<a id="f4"></a>
### F4. Once the firmware stops polling, it sleeps through RAM-only publications

- **Symptom.** With the pstate pinned, a DC attach is consumed in about 1 ms, but job 1's TA, published with
  no doorbell, never runs (`events=1` for the whole boot). With doorbells for jobs, a second client's bind
  (published with no bell) times out `bind … ret=-110 consumed_us=-1`. [V]
- **Root cause.** In the old unpinned mode the firmware looped, posted about 31 ALIVEs/s and drained its rings
  by itself, so our host relied on polling. Pinned, it waits on a doorbell and ignores ring producers that
  nobody rang. [P]
- **Fix.** Ring for **every** publication: DC, TA, 3D, bind, close, kexec quiesce. [V] TA median 2 ms and 3D
  4 ms (against 8–10 and 32 ms polled); the second bind is consumed in 1 ms.
- **How we found it.** We counted events per boot from the log, then made a census of every RAM-only producer
  store in the submit path.
- **Elsewhere?** generation-wide: the iOS kext rings on every submit.
- **Sources.** [perf60-clock](docs/gpu/experiments/perf60-clock.md), [apple-idle-power-design §3](docs/gpu/apple-idle-power-design-20261109.md).

<a id="f5"></a>
### F5. Warm kexec: the next kernel never prints a line

- **Symptom.** A warm kexec out of a boot with GPU state (several bound clients, or a wedged firmware)
  produces no console line, and a cold boot is needed. Single-client kexecs worked. [V]
- **Root cause.** The GPU firmware kept running from the old kernel's RAM across the kexec, so a live firmware
  with live bindings was still writing the incoming kernel's memory. [P]
- **Fix.** Both sides of the kexec need work.
  - **Outgoing:** a quiesce unbinds every slot RAM-only, with no register access. It then power-cycles the
    GPU through PMGR (`unbind why=kexec slots=12 verified=12 ret=0`). A wedged device skips the detach and
    only cycles.
  - **Incoming:** a bounded "dirty start" validates the inherited state and, in the repairing mode, does one
    bounded PMGR power cycle before booting firmware. [V] Boots come up `origin=warm-cycled failed=0` after
    multi-client and wedged boots.
- **How we found it.** We ran warm hops out of progressively dirtier states, each with netconsole. "No line at
  all" pointed at memory corrupted before the console came up.
- **Elsewhere?** generation-wide: any firmware that keeps DMA-ing into shared RAM does this unless it is stopped
  and power-cycled.
- **Sources.** [STATUS](docs/gpu/STATUS.md) (warm kexec; rules learned), status 2026-11-02 (unpublished).

<a id="f6"></a>
### F6. A warm or hand-run boot refuses every job: the firmware-facing setup is consumed only at map

- **Symptom.** Every typed submit returns `-EOPNOTSUPP` ("refused: boot tuple … no hardware touched"). The
  bring-up summary shows `events=1 irqs=0` and no `latched` lines; a cold boot shows thousands of events and
  all the lines. [V]
- **Root cause.** The submit path's configuration is latched at firmware map. That boot was bootstrapped without
  it, and the bootstrap marker is one-shot, so nothing after the map can change it. [P] The firmware has the
  same shape: the boot sampler, the only place it applies a pstate, runs once per firmware boot. So what must
  be right at map is the pin and the power-on pstate, and the idle record must **not** be there ([F1](#f1)).
- **Fix.** Write the map-time configuration before the bootstrap. On a warm boot, check the latch lines before
  flying anything. [V]
- **How we found it.** We diffed the failing boot's bring-up summary against a sealed cold one.
- **Elsewhere?** probably: map-time-only consumption is a firmware design pattern.
- **Sources.** [lane IP2](docs/release/orchard-0.4/lane-ip2/README.md), [perf60-clock](docs/gpu/experiments/perf60-clock.md).

<a id="f7"></a>
### F7. Silent GPU loss, then a whole-SoC lock: the recovery window let an old epoch ring

- **Symptom.** A long Aquarium run ends at `RENDER-V3 lost … why=3d-silent: context lost, device recovers`,
  then the SoC locks. There is no fault packet and no recovery stage after it. [V]
- **Root cause.** A source-level unsafe path, **not proven** to be the one hit. [P]
  - A silent loss (a host timeout) set only `lost`/`recovering`. It left the epoch's failed/alive flags and
    the register licence untouched.
  - The scheduler ran the deferred close before it checked `recovering`.
  - So an old owner's close could ring (`R1` wake, `R0+0xb00`) into a dead firmware. A fault packet blocked
    this path, but a silent loss did not.
  - Separately, our recovery cut PMGR power without first stopping the firmware. iOS always stops first.
- **Fix.** At loss detection, under the event lock, revoke the register licence and mark the epoch
  failed/stopped before returning to the scheduler. Keep deferred closes behind recovery. Recovery order:
  Fender core 0, then GPC 0, a bounded poll for stable-off, and never a PMGR cycle on an unproven stop. [V]
  in-boot recovery from a real wedge (firmware restarted in ~20 ms, a new client rendered exactly). Recovery
  after a real *silent* loss is not yet proven.
- **How we found it.** We replayed the scheduler body on the host with mocked GPU actions (old order `J C R J C`,
  fixed `J R J C`) and inventoried every post-loss register path. Ghidra on iOS's
  `AGXFirmware_forcePowerCycleAndReboot` (`fffffff006c9e070`) gave Apple's order.
- **Elsewhere?** generation-wide: host ordering around a firmware that can die silently.
- **Sources.** [r39-silent-recovery](docs/gpu/r39-silent-recovery.md), [freeze-root-cause](docs/gpu/freeze-root-cause-20261109.md).

<a id="f8"></a>
### F8. Whole-SoC freeze on GPU client churn (characterised, not closed)

- **Symptom.** On repeated Firefox launches, about 4 locks in 48. The last line is a DC park that was
  consumed and verified, and userspace lived for seconds after it. Every freeze lands 0.3–3 s after a
  PM-involved close, followed by a fresh bind. [V]
- **Root cause (characterised).**
  - One-factor flights ruled out freed page-table pages, freed render memory and post-loss code. [V]
  - What differs from iOS: iOS's firmware parks between bursts (~97 % of idle samples in an iOS-side capture).
    The park does a full cache and MMU flush (SLC all-context, MMU invalidate of all contexts) and completes
    the PM write-back before any host release. Our never-park stack never ran that flush. [P]
  - The DC handler issues only a PC-level MMU invalidate. [P]
  - The freeze is GPU-side state outliving a teardown; the exact access is not observed. [I]
- **Direction.** Turn on the firmware's own park ([P1](#p1)). Then replace our invented close machinery with
  iOS's refcounted detach. Not yet re-run with self-park.
- **How we found it.** Three live module parameters, default 0, flipped one per flight on a deterministic
  48-launch script. Breadcrumbs were flushed **before** each register access, to tell a stalled access from
  a later fault.
- **Elsewhere?** probably: any port that runs never-park will meet the flush dependency.
- **Sources.** [freeze-root-cause](docs/gpu/freeze-root-cause-20261109.md), [apple-idle-power-design](docs/gpu/apple-idle-power-design-20261109.md).

<a id="f9"></a>
### F9. A warm-boot RCU stall during GPU bring-up was a printk, not a GPU wait

- **Symptom.** An expedited RCU stall on CPU0 during GPU autoboot. The NMI backtrace runs
  `console_flush_all ← _dev_emerg ← …perf_readback`. It was reported as 85 ms but was 21 ms: `s: 85` is a
  sequence number. [V]
- **Root cause.** A 320-character `KERN_EMERG` record on a 115200-baud serial console. Emergency records flush
  with preemption disabled, at ~87 µs per character. [P]
- **Fix.** Print it at info level, in short records. [P]
- **How we found it.** We read the backtrace instead of auditing the GPU waits, which were already sleepable.
- **Elsewhere?** generation-wide.
- **Sources.** [lane GS4 §1](docs/release/orchard-0.4/lane-gs4/README.md).

---

## Power, park and sleep

<a id="p1"></a>
### P1. The firmware never parks: one host word, `ctrl+0x20`, vetoes it

- **Symptom.** No Linux epoch ever parked. About 9.7 M GPC samples in 1,496 boot logs all read state 4,
  never 0, so Apple's sleep certificate ([P8](#p8)) could never be met. We had wrongly blamed the pin and the
  sampler. [P]
- **Root cause.** [P]
  - The firmware's idle tail (`0x10009bd8`) reaches its try-park only if all of these hold, in order:
    `priv+0x188 ≠ 0`, `policy+0x34 ≠ 0`, engines idle, every root ring empty, two more flags clear.
  - `priv+0x188` is a per-tick copy of `ctrl+0x20`, so a host write takes effect without a reboot.
  - The iOS kext writes `ctrl+0x20` from bit 0 of a platform word, and on this board that bit is set. Linux
    never wrote it.
  - The same bit selects the submit branch in `submitDeviceControl`.
- **Fix.** Arm `ctrl+0x20 = 1` live after a complete epoch ([F1](#f1), [F2](#f2)). Refuse every `R0` access
  in a park epoch ([P5](#p5)). Carry the PM record on every TA in park epochs, because a parked GPC loses
  power between two jobs. [V] Idle pstate 0 in 80/80 samples, `ready` 5/5, 50/50 park cycles.
- **How we found it.** Ghidra on the AGX kext: the `ctrl+0x20` store sits in an **undefined code region**
  just after `AGXMetaFirmware_initializeSharedRootsAndControl` (`fffffff006c97888`). We had to disassemble
  it from raw bytes. Then the META firmware image, which we extracted ([tools/](tools/README.md)), gave the
  idle tail's vetoes in order.
- **Elsewhere?** probably: the veto lives in the shared kext/firmware design. The platform-word bit is per
  board, so another board may ship with it clear and take the other submit branch.
- **Sources.** [lane IP §1.1–1.2](docs/release/orchard-0.4/lane-ip/README.md), [lane GS4 §2](docs/release/orchard-0.4/lane-gs4/README.md), [FLIGHT-H2](docs/release/orchard-0.4/integration/FLIGHT-H2.md).

<a id="p2"></a>
### P2. The GPU is stuck at the boot pstate (340 MHz), and pinning higher stalls bring-up

- **Symptom.** Three different symptoms. [V]
  - A pin written into the policy record doesn't hold.
  - A pin via control-object words holds at 100, but the GPU stays at pstate 1.
  - Pin 200 gives `DC timeout consumer=0 producer=1` at control-wait.
- **Root cause.** [P]
  - The firmware owns its override words and reloads them every pass from the control object
    (`policy+0x6f4 = ctrl+0x1040`, `policy+0x68c = ctrl+0x1038`).
  - In governor state 0 the firmware never changes pstate while powered. The setter runs only from the boot
    sampler and from fractional-pin dither arms.
  - An iOS capture of `policy+0x34` under load shows only 4→0 and 0→4: iOS changes clock **only across
    park → wake**. Never-park removes that route.
  - Where exactly pin 200 stalls stays [I]. An earlier "SLC drain never acknowledges" reading was withdrawn.
- **Fix.** Write the firmware's own override inputs (`ctrl+0x1038 = 400`, `ctrl+0x1040 = pin`). Have the host
  power the GPC on directly at the pinned pstate (`R1+0x1000 = 0x10 | q`) with matching policy words, so the
  boot sampler sees no change. [V] Pins 200/300/400 pass (474/550/723 MHz). Note: 340 → 723 MHz cut the median
  job by only ~21 %; see [P6](#p6).
- **How we found it.** We decoded the firmware's limit writer (a `min()` over three words) and counted its
  store sites. An iOS capture of pstate transitions then showed that iOS never changes clock while powered.
- **Elsewhere?** probably: boot-sampler-only DVFS is firmware design; the pstate table is per chip.
- **Sources.** [perf60-clock](docs/gpu/experiments/perf60-clock.md), [STATUS](docs/gpu/STATUS.md).

<a id="p3"></a>
### P3. Self-park: every doorbell waited up to 2 ms for a GPC that powers on only after the bell

- **Symptom.** After arming self-park, the doorbell took 394–410 µs per job (1–2 µs without park). The log had
  hundreds of `dc-kick … did=rang-parked … settle=185`: the full 2 ms of reads, with the GPC still 0. [V]
- **Root cause.** Our never-park doorbell kept a settle loop that re-read `R1+0x1000` every 10 µs, for up to
  2 ms, until the GPC read powered. A parked GPC powers on only **after** the bell, so the wait always ran to
  its end, inside the TA-wait window. [P] Apple's `AGXMetaFirmware_submitDeviceControl`
  (`fffffff006ca05d4`) does: barrier, `R1+0x14 = 7` with a read-back, one nibble read, then `R0+0xb00 = 0x10`
  at any nibble, with no wait loop.
- **Fix.** In park epochs, read once and ring. Refuse only `R1+0 == 0`, a dead wrapper; a parked wrapper reads
  bits 30:29 = 11. [V] 2–3 µs per bell; glmark2 build 340–365 → 431–438 fps (+22 %).
- **How we found it.** Per-job µs counters (TA/3D work, bell, TA wait, queue) A/B against a no-park kernel at
  the same SoC state ([tools/census](tools/README.md)). We counted the `settle=` field in the log and re-read
  Apple's order in Ghidra.
- **Elsewhere?** generation-wide: the ring-at-any-nibble order is in the shared kext submit path.
- **Sources.** [lane BELL](docs/release/orchard-0.4/lane-bell/README.md), [FLIGHT-H3](docs/release/orchard-0.4/integration/FLIGHT-H3.md).

<a id="p4"></a>
### P4. Self-park costs a firmware wake per frame

- **Symptom.** Per-frame GPU work is unchanged, but fps went 543 (no park) → 340–365 (park), then 431–438
  after [P3](#p3). The remaining ~0.4 ms per job is the real wake: GPC power-on alone is ~550 µs, plus the
  firmware restart. [V]
- **Root cause.** The idle tail parks as soon as the engines are idle and the rings empty, with no
  hold-off. [P] Our GL stack kept one frame in flight ([J3](#j3)). On iOS, an IOReport sample of Safari WebGL at
  60 Hz also shows about one park per frame. An older figure, "iOS parks between every command buffer", came
  from our own probe app waiting on each command buffer. [P]
- **Fix.** Keep the next frame queued ([J3](#j3)); not flown. Don't "fix" this by turning `ctrl+0x20` off live
  ([F3](#f3)).
- **How we found it.** A serialization map from per-job counters: what stops job N+1 being queued before N
  completes, ranked by how often each cause empties the queue.
- **Elsewhere?** generation-wide.
- **Sources.** [FLIGHT-H2](docs/release/orchard-0.4/integration/FLIGHT-H2.md), [FLIGHT-H3](docs/release/orchard-0.4/integration/FLIGHT-H3.md), [frames-in-flight](docs/gpu/frames-in-flight-20261111.md).

<a id="p5"></a>
### P5. A GPU register read toward a parked or power-gated GPU hangs the whole SoC

- **Symptom.** A whole-SoC freeze (cold boot needed) on a register access after a job retired, or in park
  mode with register reads allowed. [V]
- **Root cause.** The core register window is safe to touch only if three conditions hold. [P]
  - PMGR graphics power is on.
  - The GPC pstate is in range.
  - The park flag (`R1+0` bit 29) is clear.

  Apple's equivalent is `isGPURegisterAccessible`, and Apple reads the fault banks only with the firmware
  stopped. A stalled device-memory access takes the other CPU core down within milliseconds.
- **Fix.** A per-epoch register licence, checked before every `R0` access. Park epochs refuse all of them,
  fault banks included. Never read GPU registers after a job retires; measure with firmware-written RAM
  stamps. [V] 758 reads, 0 stale, 254 refused at bit 29.
- **How we found it.** We counted park-flag hits at every register completion, then checked Apple's
  accessibility test in Ghidra.
- **Elsewhere?** generation-wide.
- **Sources.** [STATUS](docs/gpu/STATUS.md) ("rules learned the hard way"), [lane IP §2](docs/release/orchard-0.4/lane-ip/README.md), [perf60-fillrate](docs/gpu/experiments/perf60-fillrate.md).

<a id="p6"></a>
### P6. GPU benchmarks are memory-bound because the SoC stays in its low memory state (13)

- **Symptom.** A GPU overclock from 723 to 948 MHz gives +30 % ALU but +0–7 % on scenes, with GPU ms/frame
  nearly flat. CPU memcpy read is 8.8 GB/s, and `PMGR+0x68000` reads `0xddd`. [V]
- **Root cause.** The boot leaves the SoC/memory performance domain in state 13 (DRAM 800 MHz). [P]
  - iOS's state 12 (DRAM 1200 MHz) is raised at runtime by CLPC, a closed loop on DRAM bandwidth counters and
    CPU memory stall.
  - Nothing on Linux raised it.
  - iOS writes nothing else around the switch: the PMGR sequencer moves the rail, and a bit-31 poll
    (≤ 8 ms) acknowledges it.
- **Fix.** An S8000 variant of the `apple-pmgr-misc` pattern from the T8010 driver: state 12 at probe, 13
  across suspend. [V] CPU read bandwidth 8.8 → 15.1 GB/s, and **+24–43 % fps on every real glmark2 scene** on
  the same boot. State 12 at the stock clock beats 948 MHz in state 13. An idle-power cost and a load-driven
  governor are still open.
- **How we found it.** A read-only census of the running state, then a runtime A/B/A on one boot. Ghidra on
  CLPC and PMGR gave iOS's policy; the CLPC update sits at a vtable slot where Ghidra had defined no
  function.
- **Elsewhere?** probably: the T8010 (A10) has the same register and states, and A7/A8 were not analysed. **Always
  state the SoC memory state next to a GPU number.**
- **Sources.** [memclk-orchard §11](docs/power/memclk-orchard-20261110.md), [lane SOC](docs/release/orchard-0.4/lane-soc/README.md), [FLIGHT-H2](docs/release/orchard-0.4/integration/FLIGHT-H2.md), [CLPC](docs/power/clpc-20261111.md), [lane AMC](docs/release/orchard-0.4/lane-amc/README.md).

<a id="p7"></a>
### P7. Above the GPU's clock limit: a silent `-EIO` on the next submit

- **Symptom.** At 996 MHz, every attempt stops about 25 s after boot: one run passes, then the next submit
  fails `Input/output error … accepted=0`, and the kernel prints nothing. +50 mV turned it into a recovered
  3D fault. 804–948 MHz pass at stock voltage. [V]
- **Root cause.** The driver's epoch "failed" latch was set from many paths with no log line. Set while no job
  ran, it made the next submit fail silently. [P] Voltage changed the failure mode, not the outcome, so 996
  is a clock-path limit. 948 is this unit's ceiling, and the trip site was not identified. [I]
- **Fix.** Logging only: one line at the first latch with its site, and one per refusal. [P]
- **How we found it.** We read every `-EIO`/`-EBUSY` return on the submit path in full, and ran a voltage
  A/B at the same clock.
- **Elsewhere?** probably: the silent-latch bug is ours and portable, but the clock limit is per chip and unit.
  Background [P]: the GPU clock is a per-pstate PMGR record, f = 24 MHz × mult / prediv / postdiv, and the kext
  supports up to 16 states.
- **Sources.** [oc-opt1 §2, §9, §11–12](docs/power/oc-opt1-20261110.md).

<a id="p8"></a>
### P8. Sleep refused on every boot: Apple's certificate needs the firmware's own park

- **Symptom.** Sleep readiness reports `not-ready … -16` on warm boots and `ready` on cold boots. Both were
  later named `never-park/gpc=04`. [V]
- **Root cause.** Apple's quiescence test (`AGXMetaFender_isQuiescent`, `fffffff006ca66e4`) requires
  `R1+0[30:29] = 11`, GPC nibble 0 and `R1+8 = 0`: exactly the state the firmware's park leaves. iOS
  waits for the park and never forces one. [P]
  - The cold `ready` came from an unsampled branch of our readiness query, i.e. sampling luck.
  - An iOS-side trace of a real system sleep showed iOS has **no separate GPU system-sleep path**. The GPU
    is already idle-gated (firmware stopped, power off) ~40 ms after the last frame, and wake is the ordinary
    power-on plus firmware boot. [P]
- **Fix.** Name every refusal in the readiness query, and make the park reachable ([P1](#p1)). [V] Idle
  certifies 5/5. A host-forced park was rejected, because Apple has no such path.
- **How we found it.** Ghidra on the kext's power-off gate and quiescence check, a census of archived boot
  logs, and the iOS sleep trace with wall-clock heartbeat frames.
- **Elsewhere?** generation-wide: the certificate and idle-gate model are in the shared kext.
- **Sources.** [lane GS](docs/release/orchard-0.4/lane-gs/README.md), [lane GS4 §2](docs/release/orchard-0.4/lane-gs4/README.md), [FLIGHT-H2](docs/release/orchard-0.4/integration/FLIGHT-H2.md).

<a id="p9"></a>
### P9. `s2idle` refused exactly 1.0 s after suspend entry, with the GPU parked and readiness `ready`

- **Symptom.** `PM: suspend entry (s2idle)` → +1.00 s `GPU-PM sleep refused: busy or no quiescent
  certificate`. Earlier in the log there is `close-defer … pm=last pending=1`, and no matching release after
  it. On the next build, a second refusal reads `busy=accepted`. [V]
- **Root cause.** [P]
  - The sleep-idle predicate counted a pending deferred close as busy.
  - A deferred close releases only when the context is neither the PM's last nor its previous *distinct*
    context.
  - A boot-time client exited while it was "last". After that only the compositor rendered, so the close
    never released, and the 1 s drain always timed out.
  - The second refusal (`busy=accepted`): the busy predicate read the boot-long render claim `accepted`, a
    set-once flag rather than an in-flight count, so every sleep after the first GPU job was refused.
- **Fix.** The deferred close is no longer a busy state, and suspend detaches every held slot. The `accepted`
  term is dropped from the predicate. Every refusal names its stage and lists all held reasons. **Not flown. No build has yet admitted G5P system sleep on hardware.**
- **How we found it.** Timing arithmetic (1.0026 s = the 1000 ms stage-1 drain), then reading the release
  rule, then making every silent `-EBUSY` log.
- **Elsewhere?** A9-specific: the deferred close is our own substitute for the firmware park ([F8](#f8)).
- **Sources.** [lane SLEEP](docs/release/orchard-0.4/lane-sleep/README.md), [FLIGHT-RC2](docs/release/orchard-0.4/integration/FLIGHT-RC2.md).

<a id="p10"></a>
### P10. Warm boots only: sleep returns EBUSY with no line, and power domains never turn off

- **Symptom.** On a kexec boot, `s2idle` returned EBUSY with no `PM: suspend entry` line and no refusal line.
  The same bundle cold-booted got further. [V]
- **Root cause.** Two causes. [P]
  - Several `-EBUSY` paths in the PM core and in drivers were silent. Because the entry line is printed
    unconditionally, its absence meant the capture had lost lines.
  - A real warm-only difference: on a kexec boot, the PMGR power-state driver held `keep_on` for every
    domain for the whole boot. `power_off` returned `-EBUSY` (ignored by genpd), so a "successful" sleep
    would have kept graphics powered and resumed into a dirty start.
- **Fix.** Log every refusal path. In the interim, refuse GPU sleep on kexec boots by name. Then end the hold at
  each provider's `sync_state`. Not flown.
- **How we found it.** The rule that **cold and warm boots must behave identically**: we tabulated every
  cold/warm difference in the admission path, each marked fixed or not, instead of chasing the one symptom.
- **Elsewhere?** probably: the shared Apple PMGR driver has the same kexec hold.
- **Sources.** [lane SLEEP](docs/release/orchard-0.4/lane-sleep/README.md), [FLIGHT-RC2](docs/release/orchard-0.4/integration/FLIGHT-RC2.md).

---

## Job submission and performance

<a id="j1"></a>
### J1. Every job costs ~1 ms more than its GPU work, even an empty pass

- **Symptom.** On the microbenchmarks, an empty 64×64 pass took 1.34 ms on Linux against 0.156 ms on iOS. Every
  full-screen single pass took 2.6–2.9 ms, against ~1.0 ms on iOS. [V]
- **Root cause (after a correction).**
  - The first comparison set our fence-wall time against iOS GPU timestamps. With our own timestamps, GPU work
    is within ~1.3× of iOS everywhere. [V]
  - The biggest fixed cost is the firmware's doorbell → TA-start delay (~0.55 ms), the same for empty and
    full jobs. On iOS a *serial* empty pass costs the same (~0.83 ms). [V]
  - The real difference: with two command buffers in flight, iOS starts the next TA 0.5–0.75 ms before the
    previous 3D ends. We ran strictly serial.
- **Fix.**
  - Publish the 3D right after its TA instead of after the TA retires: −0.5 ms on an empty job. [V]
  - Pipeline depth 2: publish N+1 once N's TA completes.
  - The PM-record change in [J2](#j2).

  The host paths (ioctl 12–70 µs, bell 1–2 µs, IRQ 7–11 µs) are not the floor.
- **How we found it.** We ran the same microbenchmark on both sides, with Metal GPU timestamps on iOS. On
  Linux we used a per-phase timer the firmware **already writes** into the TA and 3D work records (24 ticks/µs)
  that nobody had read. Absolute stamps split each phase into segments. In Ghidra,
  `AGXChannelQueue_submitBlockInvoke` (`fffffff006cbb948`) kicks the TA and 3D per submission without waiting
  for retirement. [P]
- **Elsewhere?** probably: the A10 side measured about 1 ms per render too.
- **Sources.** [microbench-gap](docs/gpu/microbench-gap-20261109.md), [perf60-hendrik](docs/gpu/experiments/perf60-hendrik.md); TA-done latency spec (unpublished).

<a id="j2"></a>
### J2. A parameter-buffer rebuild on every TA: TA N+1 can't start under 3D N

- **Symptom.** 64 tiny passes cost 1.14 ms each for 36 µs of GPU work. The gap from the previous 3D end to the
  next TA start was 707 µs, against 153 µs on iOS. At depth 2, TA N+1 started 89 µs *after* 3D N, not under
  it. [V]
- **Root cause.** Our kernel put a PM record ("tag6") in every TA command. On every tag6 the firmware rewrites
  the free list, a pool-sized, job-independent cost: 3,136 entries at 1536×2048. Apple emits the record only
  when the PM changed (first use, new backing, grow or shrink). [P]
- **Fix.** Send tag6 only when a per-PM dirty flag is set; otherwise send a satisfied-dependency object of
  Apple's shape. [V] Small passes −34 %, fill −21 % at depth 2, the TA(N+1)−3D(N) gap +89 → −462 µs (iOS: −506
  to −745), glmark2 +8–35 % per scene, no free-list drift.
- **How we found it.** Ghidra: `AGXTACommandDescriptor_preparePMAndWork` reads a pending record mode that
  clears after one use, and the TA builder emits tag6 only for some modes. We diffed that against our
  unconditional tag6. Then a one-parameter A/B on one boot, with the stop rule written down in advance: "if
  the delay does not move, tag6 is not the cost".
- **Elsewhere?** generation-wide: the Rogue parameter-buffer model and the kext logic.
- **Sources.** [heavy-census](docs/gpu/heavy-census-20261109.md), [opt1-o04-flight](docs/gpu/opt1-o04-flight-20261110.md); the Ghidra reading of the record mode (unpublished).

<a id="j3"></a>
### J3. The firmware parks between frames because GL keeps only one frame in flight

- **Symptom.** glmark2 build ran at 431–438 fps with the GPU 60–61 % busy. 69–70 % of jobs finish their TA
  with no successor queued. [V]
- **Root cause.** Mesa's `dri_flush()` and `kopper_flush_frontbuffer()` wait for the previous frame's fence on
  every SwapBuffers (`pipe_caps.throttle`). So the CPU starts frame N+2 only after N retires, the rings empty,
  and the firmware parks ([P4](#p4)). [P] Secondary causes:
  - a cap on the kernel's chain of queued-ahead jobs;
  - winsys backpressure that drains the whole context;
  - render-target creation, which also drains it.
- **Fix (built, not flown).** A ring of throttle fences, with Zink on G5P keeping two frames in flight. Kopper
  asks for `frames + 2` swapchain images, and the winsys waits for the job 8 back instead of draining. The
  prediction is about 520–550 fps on build. There should be no change at a 60 Hz desktop, where one park per
  vsync is the Apple way.
- **How we found it.** Per-job "why not ahead" reason counters in the kernel, over three runs, plus Ghidra: iOS
  kicks at once and defers only on a non-empty pending list.
- **Elsewhere?** generation-wide: driver-independent Mesa code plus Apple's park.
- **Sources.** [FLIGHT-H3](docs/release/orchard-0.4/integration/FLIGHT-H3.md), [frames-in-flight](docs/gpu/frames-in-flight-20261111.md).

<a id="j4"></a>
### J4. Fill rate looked like 1/6 of iOS: it was park/re-wake churn

- **Symptom.** Full-panel 3D ran at about 70–100 Mpx/s. Clear took 12 ms, solid fill 18, blit 36, ALU16 62. [V]
- **Root cause.** None of cluster count, occupancy, PBE form, tiles in flight or memory attributes; a page
  attribute A/B moved nothing. The firmware was parking and re-waking the GPC around every job. On a
  never-park kernel the same rungs took 2/2/4/8 ms. [V]
- **Fix.** Keep the GPC powered while work is queued: now a fast bell ([P3](#p3)) and a non-empty queue
  ([J3](#j3)).
- **How we found it.** A one-factor fixture ladder (clear, solid, blit, small load, scissored load, ALU) with
  one knob per hypothesis. **Rule learned on the way:** a measurement knob that read GPU registers just
  after a job retired froze the SoC ([P5](#p5)).
- **Elsewhere?** probably: any port running Apple's firmware with self-park.
- **Sources.** [perf60-fillrate §8–10](docs/gpu/experiments/perf60-fillrate.md).

<a id="j5"></a>
### J5. Every LOAD pass touched all 3,072 tiles: PROCESS_EMPTY_TILES was forced on

- **Symptom.** A small damaged area cost as much as a full-screen redraw: 30 ms of 3D for a small load. [V]
- **Root cause.** Bit 17 of the 3D template's ISP control word (PROCESS_EMPTY_TILES) was set on every pass. We
  had forced it on so that CLEAR passes write tiles that have no geometry. Apple sets it only for a 4× resolve,
  and upstream pvr only when a colour attachment clears. [P]
- **Fix.** A per-pass "may skip empty tiles" flag, which Mesa sets for LOAD or DONT_CARE backgrounds with no
  clear-and-store and no resolve. [V] 30.2 → 4.7 ms (6.4×). The tiler bins by scissor, so no render-rect
  pruning is needed.
- **How we found it.** A word-by-word diff of our 3D register image against Apple's (only this bit differed),
  then upstream's rule, then a fixture A/B.
- **Elsewhere?** generation-wide: Rogue ISP semantics.
- **Sources.** [perf60-fillrate §0.1, §7, §8.1](docs/gpu/experiments/perf60-fillrate.md).

<a id="j6"></a>
### J6. Depth-2 pipelining never fires: every job waits on the previous job's fence

- **Symptom.** With pipelining on, Aquarium started 16 of 12,119 jobs early. Firefox's Zink flush thread spent
  51 % of its samples in `vkQueueSubmit`. [V]
- **Root cause.** Three layers. [P]
  - `pvr_clear_last_submits_syncs()` CPU-waited for all of the previous submission at every submit.
  - Three over-broad Zink constructs turned into waits on the previous fence that gate the TA: the
    reordered-command-buffer ALL→ALL barrier, the end-of-batch dma-buf release barrier, and the
    implicit-sync semaphores.
  - Our winsys passed fragment-stage waits to the kernel as whole-job waits.
- **Fix.**
  - Zink "precise sync" narrows each construct to its real stages.
  - pvr marks fragment-stage waits as 3D-only.
  - The kernel drops a context's own fences in that case.

  Early jobs went 0.1 % → 22 % [V], **but Aquarium's fps did not move**: 57 % of decision points had no
  next job at all ([J8](#j8)).
- **How we found it.** Ghidra showed that iOS attaches dependency waits only to the TA record. Per-decision
  reason counters, and a log attributing every barrier wait by stage.
- **Elsewhere?** generation-wide: Mesa pvr and Zink code.
- **Sources.** [henrik-g9p-port-study §0](docs/gpu/henrik-g9p-port-study.md), [aquarium-idle-gpu-critical-path](docs/gpu/aquarium-idle-gpu-critical-path.md); dependency spec and device tables (unpublished).

<a id="j7"></a>
### J7. After a Mesa rebase, glmark2 drops 17–23 % at the same GPU ms/frame

- **Symptom.** build went 384 → 302 fps and jellyfish 248 → 191, with GPU ms/frame unchanged. Per submit, strace
  showed syncobj transfers 16 → 28 and syncobj waits 2 → 4, including zero-timeout polls. [V]
- **Root cause.** An **auto-merged** upstream hunk, not a conflict. "GPU blits by default" for G9P changed
  `pvr_stage_mask()` so that transfer stages map to TRANSFER|GEOM|FRAG on every device. Zink's end-of-batch
  barrier therefore gained geometry and fragment sources, and the next render's geometry waited on the
  previous render's fragments. [P]
- **Fix.** Keep G5P transfer stages out of geometry and fragment, and build a submission's signal fences
  once. [P]
- **How we found it.** A same-boot A/B (old vs rebased stack, bare environment), strace syscall counts per
  submit, then a read of the auto-merged hunks.
- **Elsewhere?** generation-wide: any Mesa-pvr Apple port rebased past that commit. **Check
  `pvr_stage_mask()` after every rebase.**
- **Sources.** [opt1-o04-flight](docs/gpu/opt1-o04-flight-20261110.md), [FLIGHT-RC2](docs/release/orchard-0.4/integration/FLIGHT-RC2.md); lane M3 report (unpublished).

<a id="j8"></a>
### J8. Aquarium (Firefox hardware WebRender) leaves the GPU idle 38 % of every frame

- **Symptom.** 23–26 fps at 43.8 ms per frame, with 16 ms of each frame having no job outstanding, while only
  ~1.1 of the 2 cores are busy in those gaps. [V]
- **Root cause, ranked.**
  - `vkCmdCopyBuffer` ran as a CPU memcpy on the single Zink flush thread, after a host wait on every earlier
    job. Zink's one queue carried both of Firefox's GL contexts, so WebRender copies waited on WebGL jobs:
    ≈4.7 ms per frame. [P]
  - Per-draw recording costs ≈4 ms per frame. The A9 has no LSE atomics, so LL/SC loops are expensive. [P]
  - The load-op shader was compiled on every begin-rendering, and G5P never reads it. [P]
- **Fix.** A BO-precise host wait and skipping the dead compile: 26 → 29 fps, GPU idle 15.8 → 12.6 ms per frame
  [V]. Moving the copies to the GPU **lost** 3 fps: each became its own TA+3D job paying 0.7–1 ms of fixed
  latency ([J1](#j1)).
- **How we found it.** We joined the `dma_fence` trace 1:1 with the driver's submit log, so every fence had a
  job identity. Then we classified each GPU-idle gap by the job that ended it, the job that started next, and
  who ran in the gap.
- **Elsewhere?** probably.
- **Sources.** [aquarium-idle-gpu-critical-path](docs/gpu/aquarium-idle-gpu-critical-path.md), [aquarium-cpu-profile](docs/gpu/aquarium-cpu-profile-20261109.md).

<a id="j9"></a>
### J9. 1M triangles fault the TA (context lost)

- **Symptom.** One draw of 3 M vertices at 1536×2048 gave `SUBMIT_RENDER_TYPED: Input/output error`. At 64×64
  the failure began at 1 M triangles, while 262 k passed. iOS runs it in 19.6 ms. [V]
- **Root cause.** The serial "3D after TA retires" publish. With TA and 3D published together it **passes**,
  at 14.7 ms GPU time, faster than iOS. [V]
  - Still open: frames that overflow the parameter buffer.
  - iOS splits such scenes itself with partial renders: an iOS run showed 1,231 re-entries, and its
    ParamBuffer is bounded. [P]
- **Fix.** The joint publish. Partial render and pool growth are not built.
- **How we found it.** We ruled out VDM count truncation, vertex-fetch faults and PM write-back into closed
  slots. Apple's limits came from `AGXParameterManagement_initHostAndFirmwareState` and an iOS PM-state
  capture.
- **Elsewhere?** generation-wide: Rogue parameter-buffer exhaustion.
- **Sources.** [microbench-gap](docs/gpu/microbench-gap-20261109.md); 1M-triangle fault spec (unpublished).

<a id="j10"></a>
### J10. Several clients: PM faults from one parameter-buffer state shared across contexts

- **Symptom.** A deterministic PM fault at a second client's first 3D: a read, page invalid, requester PM,
  VA 0. A save/restore attempt then gave a silent 3D loss. [V]
- **Root cause.** One PM served every VM. Its control words and pool advance with every context's job, so
  restoring a per-context state against a pool that another context has advanced is inconsistent. Four
  faults on the way all had this root. [P]
- **Fix.** iOS's model: a PM set (control, state, list, free list), a pool and aux pages per context, each
  with its own PM ID. Defer a close while the write-back still targets the closing context. [V] Multi-client
  Hyprland, 16 min, 0 faults.
- **How we found it.** We decoded the fault (requester, level, context), kept a ring of per-job snapshots of
  the PM words at start, TA done and end, and read in Ghidra how iOS takes a ParamBuffer ID per prepare from a
  127-entry pool.
- **Elsewhere?** generation-wide.
- **Sources.** [perf60-clock](docs/gpu/experiments/perf60-clock.md) ("the fault named"), [STATUS](docs/gpu/STATUS.md).

---

## Mesa and Zink

<a id="z1"></a>
### Z1. Render-to-texture refused ("a non-linear colour target"), then the app hangs

- **Symptom.** glmark2 terrain and refract log `G5P refuses: a non-linear colour target`. Zink drops the batch
  and the app blocks ([Z3](#z3)). [V]
- **Root cause.** A gate, not missing hardware. The twiddled PBE store was already written and matched to iOS,
  but it sat behind a probe switch that the release didn't set. iOS's form for a 2D twiddled target is a
  twiddle bit in PBE word 0 and **no row pitch** in word 1. The layout is the same twiddle the texture unit
  already samples. [P]
- **Fix.** On by default. Together with [Z2](#z2): terrain 2 → **17 fps**, refract 2 → **30 fps**, and all 16
  scenes run. [V] Still refused by name: 3D depth-plane stores, layered rendering, and mip tails that aren't
  64-byte aligned.
- **How we found it.** 28 native iOS render captures. Our `g5p_pbe_2d()` reproduces all 28 PBE rows bit for bit
  in a host unit test. The Metal driver builds PBE words in userspace, so on this question the captures are
  the Apple source, not the kext.
- **Elsewhere?** probably: the twiddle layout is Rogue-wide, but we captured the PBE word layout only on A9.
- **Sources.** [pbe-twiddled](docs/gpu/pbe-twiddled-20261111.md), [FLIGHT-RC2](docs/release/orchard-0.4/integration/FLIGHT-RC2.md).

<a id="z2"></a>
### Z2. glGenerateMipmap: point-sampled levels, then 2 fps from a per-texel CPU blit

- **Symptom.**
  - dEQP mipmap-generate cases: every pixel of level 4 wrong (the first level whose 2×2 footprints mix
    colours).
  - Once [Z1](#z1) let terrain render, it ran at 2 fps, with perf showing `pthread_once` at 51 %. [V]
- **Root cause.**
  - Zink has no generate-mipmap hook, so `util_gen_mipmap` issues one linear blit per level.
  - Our meta blit only took single-level images, so every level fell to the CPU transfer path.
  - That path ignored the filter (it took the top-left texel) and looked up the format description per
    texel through `pthread_once`. [P]
- **Fix.**
  - A bilinear CPU blit by Vulkan's rules.
  - GPU mip generation through the twiddled PBE, one level per pass.
  - Format lookups once per copy.

  Small or unaligned tails stay on the CPU. [V] in rc2.
- **How we found it.** We read the CTS results per level, reproduced on the host with an ES client whose
  transfers take the CPU path, and followed the call chain from glmark2's source down to the copy.
- **Elsewhere?** generation-wide: the Zink path is shared.
- **Sources.** [pbe-twiddled §PBE2](docs/gpu/pbe-twiddled-20261111.md), [FLIGHT-RC2](docs/release/orchard-0.4/integration/FLIGHT-RC2.md); mipmap-generate analysis (unpublished).

<a id="z3"></a>
### Z3. A refused or lost batch hangs the GL client forever (black window, SIGTERM ignored)

- **Symptom.** After `batch … dropped … the context is lost`, the main thread sits in
  `drm_syncobj_timeline_wait`. SIGTERM does nothing, because the ioctl restarts. [V]
- **Root cause.** The waiter was the Wayland WSI's explicit-sync acquire, an untimed wait. [P]
  - After the loss, `zink_end_batch` created the present semaphore and returned before submitting, so nothing
    signalled it.
  - The kernel refused the transfer from a fence-less syncobj, so the WSI skipped the present and the
    compositor never released the old buffer.
- **Fix.**
  - Zink keeps submitting a lost screen's batches, empty, so every promised signal fires.
  - Each flush gets a new batch state.
  - pvr does **not** mark the device lost on a refusal: only that command buffer is invalid, and a lost device
    would kill every GL context in the process.
  - The pvr side must also signal a failed submission's signals. [V] The apps exited cleanly.
- **How we found it.** We ruled out waiters by ioctl number, which left the WSI acquire, then traced the
  semaphore's lifecycle down to the kernel's EINVAL.
- **Elsewhere?** generation-wide: generic Zink and WSI.
- **Sources.** [opt1-o04-flight](docs/gpu/opt1-o04-flight-20261110.md), [henrik-g9p-port-study](docs/gpu/henrik-g9p-port-study.md); lane M2 report (unpublished).

<a id="z4"></a>
### Z4. Games run out of GPU memory: decompressed S3TC, not slab BOs (corrected)

- **Symptom.** `zink: couldn't allocate memory` in refract and SuperTuxKart, with hundreds of 2 MiB kernel
  BOs. [V]
- **Root cause.** Our first model blamed BO count and dead upload staging; a device flight overturned it. [V]
  - **Textures dominate:** 321 MiB at 256 px and 584 MiB at 512 px, because S3TC was decompressed to RGBA8.
  - The A9 samples ETC2/EAC, ASTC LDR and PVRTC, and **no BC formats**. [P]
- **Fix.** Re-encode S3TC uploads to the same-size ETC2 format in Mesa's state tracker. [V] SuperTuxKart's
  pinned data dropped by 48 %, and the allocation failures at 512 px are gone. It is lossy (37 dB), so ASTC 4×4
  is next.
- **How we found it.** We read Apple's per-format table in the userspace Metal driver:
  `AGX::G5::TextureFormatTable::chooseTextureFormatOBJC` is a jump table with one row per pixel format, and
  every BC format resolves to the `Unsupported` row. We checked that against format codes from iOS captures.
  Then we split SuperTuxKart's memory per category from the arena's stats lines.
- **Elsewhere?** probably: only the A9 table was read.
- **Sources.** [tex1](docs/gpu/tex1-compressed-textures-20261110.md), [mem1](docs/gpu/mem1-gpu-memory-20261109.md).

<a id="z5"></a>
### Z5. Shader ALU 5× slower than iOS: Apple's loop-unroll budget

- **Symptom.** 64 dependent vec4 FMAs per pixel took 49 ms on Linux and 9.2 ms on iOS. [V]
- **Root cause.** Instruction count, not ALU speed: both stacks issue about one instruction per slot. NIR's
  default `max_unroll_iterations = 16` kept the 64-trip loop as a loop. That gave 1,562 dynamic instructions
  against Apple's 261, and the same shader hand-unrolled compiled to 269. [P]
- **Fix.** Apple's measured unroll budget: cost = trips × (scalar ALU ops per iteration + 1), with a·b+c counted
  as 2. Apple unrolls at cost ≤ 480 and keeps the loop at ≥ 500, which fits all six probed boundaries. Also
  turn on multiply-add fusion (`fuse_ffma`). [V] 49 → 11.9 ms, within 14 % of iOS.
- **How we found it.** We compiled with **Apple's compiler offline** (`metal-tt -arch applegpu_g5p`,
  [tools/metal](tools/README.md)), ran a ladder of loops (trip counts × body sizes) to find the first loop it
  kept, and counted dynamic instructions on both sides. No iOS session was needed.
- **Elsewhere?** probably: the method carries over, but the budget was measured only for g5p.
- **Sources.** [microbench-gap](docs/gpu/microbench-gap-20261109.md), ALU codegen spec (unpublished).

<a id="z6"></a>
### Z6. Vertex shaders read registers r8+ as zero (3D clients draw wrong or nothing)

- **Symptom.** vkcube and weston-simple-egl were wrong in real windows, with registers r8 and up reading 0. A
  program with more than 32 common-store dwords wedged the TA. [V]
- **Root cause.** The vertex unified-store size was a captured constant 4, which covers r0..r7. Apple's
  `VertexProgramVariantPDSState` sizes it from the program. Two siblings: [P]
  - the common store is `2·ceil(dwords/16)`;
  - Apple sets the LAST bit on the final attribute DMA too. Without it, a shader that fetches an attribute and
    reads the vertex index wedges.
- **Fix.** Size from the program, as `max(4·ceil(inputs/8), 2·ceil(max(temps, inputs+2)/4))` above 8 temps or 8
  input dwords, else 4. [V] vkcube matches a CPU reference, and weston-simple-egl draws (2026-11-02).
- **How we found it.** From Apple's PDS-state builder and iOS instancing captures, not from Rogue defaults.
- **Elsewhere?** probably: the PDS/VDM state is Rogue-wide, but the formula comes from the A9 driver.
- **Sources.** [STATUS](docs/gpu/STATUS.md) ("GPU apps in real windows"); status report 2026-11-02 (unpublished).

<a id="z7"></a>
### Z7. Frame-varying noise and stale tiles under blended draws

- **Symptom.** Blend-over-LOAD fixtures failed exactly in the tiles a second pass drew, with first-pass pixels
  from other positions. Qt Quick windows showed noise and stale tiles. [V]
- **Root cause.** Every non-discarding draw was recorded with ISP pass type OPAQUE. An opaque object that covers
  a tile replaces the background's tag, so the LOAD never runs, and a blend's tile read returns stale on-chip
  memory. The first fix missed the depth/stencil path and colour-mask-0 draws. [P]
- **Fix.** TRANSLUCENT for any destination read and punch-through for discard, on both paths. Mask-none draws
  get tag writes disabled. Partial write masks are refused by name. [V] Blend ladder 59/59.
- **How we found it.** A fixture pixel map (the bad rows held other positions' first-pass pattern), then a diff
  of our ISP words against Apple's pass type per program.
- **Elsewhere?** generation-wide: PowerVR hidden-surface tag semantics.
- **Sources.** [STATUS](docs/gpu/STATUS.md) ("Hyprland on the GPU"); Hyprland GPU notebook (unpublished).

<a id="z8"></a>
### Z8. Random ENOENT in Firefox: the submit used a resource list after the lock dropped

- **Symptom.** Render submits failed at the kernel's GEM handle lookup with errno 2. [V]
- **Root cause.** The winsys built the job's resource list under its lock, then released the lock before submit.
  Meanwhile another thread could legally free memory the job didn't use but that conservative tracking still
  listed, which closed the handle. [P]
- **Fix.** Keep the snapshot alive through submit, and rebuild it on retry. [T] 18/18 reproductions before the
  fix, 18/18 passes after.
- **How we found it.** A host reproduction with the unmodified ICD against a fake kernel node, with logging
  knobs that made the interleaving repeatable.
- **Elsewhere?** generation-wide: a winsys concurrency pattern.
- **Sources.** [vdm-zink-lifetime-fix](docs/gpu/vdm-zink-lifetime-fix.md).

<a id="z9"></a>
### Z9. fp16, mediump and co-issue gave no gain on A9

- **Symptom.** We expected a 2× FP16 lever.
- **Root cause.** [P]
  - Apple's own A9 half code has the same instruction count and size as fp32: one scalar per instruction, no
    packed 2×f16.
  - Every probe shows one operation per instruction, so a co-issue scheduler has nothing to pair.
  - Half saves registers only.
  - Safari's WebGL path emits `float` for every precision. [I]
- **Verdict.** 0 % on our benchmarks. The only lever is occupancy on register-bound shaders.
- **How we found it.** Matched float/half Metal probes compiled offline by Apple's compiler, counted by
  instruction class.
- **Elsewhere?** A9-specific: the encoding was probed only for g5p. Other generations' FP16 ALUs may well differ [I], so re-probe your chip.
- **Sources.** [lane-b2-beyond-apple](docs/gpu/lane-b2-beyond-apple.md).

<a id="z10"></a>
### Z10. Firefox WebRender shaders refused: W-only varyings and vertex register pressure

- **Symptom.** A W-only varying probe had every channel wrong. One WebRender shader pair was refused with
  `register pressure: … 32 of 32 in use in each vertex bank`. [V]
- **Root cause.** [P]
  - **W:** varying planning ran before liveness, so its use counter was still zero, and no W setup was
    emitted.
  - **Pressure:** all 64 vertex dwords really were live:
    - 13 booleans held a dword each, because combined compares can't fuse into their selects;
    - several values were computed ~900 instructions before their use.
- **Fix.**
  - W: plan the varyings after liveness.
  - Pressure: rewrite `bcsel(iand(a,b),x,y)` as `bcsel(a,bcsel(b,x,y),y)`, so every condition takes the fused
    compare+select, plus a min-pressure order.
  - Don't guess a spill ABI: Apple's A9 vertex shaders spill only at 192 live values, and their spill
    ABI was not captured. [T]
- **How we found it.** Real Firefox shader corpora admitted through Mesa GL → Zink → our backend on a fake node,
  counting refusals rather than exit codes.
- **Elsewhere?** probably: the bug class is in shared Mesa code (varying planning, boolean pressure). The register budget and spill rules depend on each generation's ISA, which we haven't compared [I].
- **Sources.** [firefox-wr3](docs/gpu/firefox-wr3-20261108.md); quad-blend pressure note (unpublished).

<a id="z11"></a>
### Z11. Hardware WebRender at 12 fps: a 53–63 ms CPU format conversion per frame

- **Symptom.** After every 1024² WebGL pass came one CPU transfer of 53–63 ms, about 57 of the ~83 ms per
  frame. [V]
- **Root cause.** The RGBA8 → BGRA8 copy into the compositor texture took the CPU path, which resolved formats
  and bounds per texel. [P]
- **Fix.** Resolve once per rectangle and byte-permute: 15.2 → 0.88 ms [T]. The real fix is a GPU blit, which
  was done later ([Z2](#z2)).
- **How we found it.** perf symbolized against build-ID-matched libraries, and the driver's own transfer log.
- **Elsewhere?** generation-wide.
- **Sources.** [webgl-perf-r39-9](docs/gpu/webgl-perf-r39-9.md).

<a id="z12"></a>
### Z12. GL MSAA framebuffers silently incomplete

- **Symptom.** `glRenderbufferStorageMultisample(4, GL_RGBA8)` raises no error but reports
  `RENDERBUFFER_SAMPLES = 0` and `INCOMPLETE_ATTACHMENT`. [T]
- **Root cause.** Inside Zink, the capability query uses the color-attachment usage, but image creation adds
  SAMPLED. Our driver allows only 1 sample for SAMPLED, because sampling a 4× image isn't built. [P]
- **Status.** Open. We won't advertise an unbuilt limit. The 4× hardware path works through Vulkan.
- **Elsewhere?** generation-wide: any Zink driver whose sampled MSAA count is below its attachment count.
- **Sources.** [mem1](docs/gpu/mem1-gpu-memory-20261109.md), MSAA note (unpublished).

---

## Memory

<a id="m1"></a>
### M1. Closed clients keep their memory pinned ("handle-less BOs" after quiesce)

- **Symptom.** After every client exits, the BO list still shows big BOs owned by dead PIDs, with
  `handles=0 … vm_pins=1`, and `Unevictable` equals the device pin count. One quiesce held 176 MiB.
  MemAvailable never comes back after a nested compositor exits. [V]
- **Root cause.** We defer a context close while the parameter manager may still write back into that context's
  PM set ([P9](#p9)). Deferring the whole context also kept its VM and every user mapping pinned. The late
  write needs only the PM set, its pool and the page tables. [I]
- **Fix.** On a deferred close, trim every ordinary user mapping of that VM, and keep the PM pools, aux pages,
  render-target memory and firmware tables. Never free on a timer, on an error fence or "N jobs later". [V]
  Dead processes no longer keep arenas pinned (+75 MiB available).
- **How we found it.** Per-BO debugfs snapshots (owner, size, handles, pins) before and after teardown and after
  the next clients' jobs, compared with Unevictable/Shmem from the same moment. Owner turnover between
  snapshots showed bounded retention rather than a leak.
- **Elsewhere?** probably: any port that keeps a context alive for the PM write-back.
- **Sources.** [GPU RAM](docs/ram/gpu-ram-20261111.md), [STATUS](docs/gpu/STATUS.md); close-trim handoff and RAM accounting notes (unpublished).

<a id="m2"></a>
### M2. GPU RAM per client "doesn't add up"

- **Symptom.** Close logs read 105–182 MB pinned, and the totals look like a per-client cost that grows with the
  number of clients. [V]
- **Root cause.** The close log prints **device-wide** counters, so multiplying them by clients is wrong. The
  device pin count covers user GEM only, not firmware, page tables or PM pools. Imported scanouts alias display
  BOs. A diagnostic log redirected into tmpfs `/tmp` is shmem that outlives the client. [P]
- **Rules we now use.**
  - CMA is inside MemTotal; Shmem is inside Cached; GEM pins overlap Shmem, Unevictable and mapped PSS.
  - Use PSS, not RSS.
  - Never sum `/proc/iomem` ranges.
  - zram saving = `orig_data_size − mem_used_total`.
  - Attribute per client from per-BO rows taken at the same moment.
  - Send logs to disk, not tmpfs.

  The [RAM census tool](tools/README.md) prints these rules.
- **Elsewhere?** generation-wide.
- **Sources.** [GPU RAM](docs/ram/gpu-ram-20261111.md).

<a id="m3"></a>
### M3. Hundreds of 2 MiB kernel BOs (Zink slab parents): BO count is not the memory problem

- **Symptom.** SuperTuxKart shows 281 kernel BOs of exactly 2 MiB. [V]
- **Root cause.** Zink sub-allocates from 2 MiB slab parents, and our ICD made every allocation of 2 MiB or more
  its own kernel BO. Zink's `heap=3` is its internal enum, not a Vulkan heap. [P]
- **Fix.** Data chunks of 8 MiB and a 1 MiB own-BO threshold. BOs dropped 291 → 83, **but pinned MiB did not
  move**. Memory was textures ([Z4](#z4)). [V] Our BOs are write-combined, so don't advertise HOST_CACHED.
- **How we found it.** We matched the 2 MiB size to Zink's slab code instead of guessing, then flew one env
  switch per change.
- **Elsewhere?** generation-wide.
- **Sources.** [mem1](docs/gpu/mem1-gpu-memory-20261109.md).

<a id="m4"></a>
### M4. The compositor stops drawing after ~1000 frames: the driver arena fills up

- **Symptom.** labwc ran fine until the ICD's 64 MiB arena filled at frame 1262 (~53 KB per frame). Then
  allocations were refused and labwc stopped drawing. [V]
- **Root cause.** Four, verified on the host. [T]
  - Freed descriptor sets never returned their GPU words: a bump allocator, and Zink never resets its pools.
  - The arena could not grow after the first job.
  - Released and imported BOs stayed VM-mapped, and importing a buffer twice returns the same GEM handle, so
    closes need a per-handle refcount.
  - A job's fixed 16 KiB VDM stream filled at ~123 draws.
- **Fix.**
  - A VMA heap per descriptor pool, as RADV does.
  - Arena growth while the context is idle.
  - Proper unmaps.
  - Split jobs at the stream limit.

  Soaks of 10–20 k frames pass against a kernel model on the host. [T] The current arena grows on demand.
- **How we found it.** We read the pool allocation sizes in the device log, traced the free path, and built long
  soaks against a fake node that enforces the kernel's per-VM limits.
- **Elsewhere?** generation-wide: shared Mesa winsys and descriptor code.
- **Sources.** [STATUS](docs/gpu/STATUS.md); arena-fix notebook (unpublished).

<a id="m5"></a>
### M5. Shmem grows all session on a GL desktop: the loader sends the render node through kmsro

- **Symptom.** Shmem grows for the whole session on the desktop. [V]
- **Root cause.** Our DRM driver's name had no Gallium descriptor, so Mesa's loader gave its render node the
  kmsro fallback. Zink then imported every client dma-buf a second time and released it with a call the
  render node refuses. kmsro also duplicated the fd without close-on-exec. [P]
- **Fix.** Map the driver name straight to Zink in `pipe_loader_drm.c`, and use `os_dupfd_cloexec()`. If you
  rename your DRM driver, check for this fallback. [V] Shmem stays flat.
- **Elsewhere?** generation-wide.
- **Sources.** [a9-update](docs/gpu/hendrik/a9-update-20261103.md), [STATUS](docs/gpu/STATUS.md).

<a id="m6"></a>
### M6. Every Vulkan instance pins memory it never uses

- **Symptom.** Each client and each probe instance holds a 2 MiB pinned chunk before it creates a device. Every
  device holds two default tables of more than half a MiB. [T]
- **Root cause.** The winsys committed its first arena chunk at enumeration, and the default tables used the full
  65536-entry sizes, although only entry 0 is read. The arena is executable and can only be trimmed from the
  tail. [P]
- **Fix.** Commit lazily on the first slice, with a 512 KiB floor, and use one-page default tables. [V] −4.5 to
  −5.5 MiB per session on hardware.
- **Elsewhere?** generation-wide.
- **Sources.** [STATUS](docs/gpu/STATUS.md), [GPU RAM](docs/ram/gpu-ram-20261111.md).

<a id="m7"></a>
### M7. ENOSPC from the GPU driver with plenty of RAM free

- **Symptom.** VM_BIND, CREATE_BO or CREATE_RENDER_TARGET fails with ENOSPC or EINVAL, while MemAvailable is fine. [V]
- **Root cause.** Several independent caps in our kernel driver, none of them a RAM quota. [P]
  - 64 MiB per BO.
  - 768 MiB of unique pinned GEM per VM.
  - 1 GiB of summed mappings per VM.
  - 1 GiB per device.
  - 4096 mappings per VM.
  - 8 VMs per file.
  - 32 render targets per context.
- **Fix.** Find which guard fired before you touch any cap; add rejection-site diagnostics.
- **How we found it.** An audit that tabulated every ENOSPC/EINVAL site with its unit and aliasing rule.
- **Elsewhere?** probably: these are our driver's limits, so a driver reusing it inherits them.
- **Sources.** [STATUS](docs/gpu/STATUS.md); ENOSPC audit (unpublished).

<a id="m8"></a>
### M8. The parameter pool: don't shrink or free it on a timer; Apple grows it from firmware feedback

- **Symptom.** Each PM-holding context keeps a large private pool (~12 MiB at 16 KiB pages). [V]
- **Root cause.** The PM may write its free list back after the context's last job. Apple's kext never frees the
  free list at retirement; it re-initialises it only on fault restart or a forced power cycle. Its grow
  routine is feedback-driven:
  - it consumes PM feedback;
  - it rate-limits;
  - it computes a floor from the render-target size;
  - it applies 128-job hysteresis before lowering that floor;
  - it links memory in 128 KiB blocks.

  Some of the feedback is in 4 KiB units. [P]
- **Status.** No pool-sizing change has landed. The rule: port Apple's protocol before reducing the pool.
- **Elsewhere?** probably: the parameter buffer is Rogue-wide, but the specifics come from the A9 kext.
- **Sources.** [GPU RAM](docs/ram/gpu-ram-20261111.md).

---

## Video decode (VXD)

<a id="v1"></a>
### V1. H.264 B-frames with temporal direct are wrong only through FFmpeg: DPB slot identity

- **Symptom.** Comparing FFmpeg `v4l2request` against software decode, 15 of 16 streams are bit-exact. One High
  profile stream with B temporal-direct has all four of its B-frames different. Our own test client is
  bit-exact on the same boot. [V]
- **Root cause.** The driver relied on **stable userspace DPB indices**. The co-located picture's stored motion
  was written with that picture's earlier hardware slots, but the inverse L0 map used the *current* slots.
  FFmpeg compacts its DPB afresh for each picture, and the V4L2 stateless uAPI doesn't require stable indices, so
  this was a kernel bug. [P]
- **Fix.** Store a slot → `reference_ts` snapshot in each CAPTURE buffer, and map the co-located buffer's saved
  slots to the current L0 by timestamp. [V] H.264 16/16 and HEVC 12/12 bit-exact.
- **How we found it.** Same-boot runs with the known-good client ruled out a regression. An LD_PRELOAD ioctl
  tracer captured both clients' requests. We paired them in decode order by frame_num/POC (each client numbers
  its own timestamps) and looked for a reference that changed index between a P and its B pictures.
- **Elsewhere?** probably: the A10 has the same VXD, and any stateless driver that keys hardware state by DPB
  index has this bug.
- **Sources.** [FLIGHT-G](docs/release/orchard-0.4/integration/FLIGHT-G.md), [FLIGHT-RC2](docs/release/orchard-0.4/integration/FLIGHT-RC2.md), temporal-direct note (unpublished).

<a id="v2"></a>
### V2. "Hardware decode works" when it silently fell back to software

- **Symptom.** A Main10 HEVC clip plays, but hardware setup was refused and VXD interrupts rose by 0. In the other
  direction, a comparator reported FAIL for bit-exact streams. [V]
- **Root cause.** FFmpeg falls back to CPU decode without failing. The comparator counted framemd5 header lines as
  frames.
- **Fix.** Count a hardware result only when all three hold:
  - the log names the driver;
  - VXD interrupts rise by the frame count;
  - the driver's decode counter rises.

  Compare only the hash field.
- **Elsewhere?** generation-wide.
- **Sources.** [FLIGHT-G](docs/release/orchard-0.4/integration/FLIGHT-G.md).

<a id="v3"></a>
### V3. VXD probe: the core ID is not what you expect

- **Symptom.** The first read-only probe printed a core ID that the test plan's guess called "unsupported", and
  no video nodes appeared. [V]
- **Root cause.** The expected ID was a guess. In Apple's driver, the low nibbles are the entropy and pixel pipe
  counts, `coreId >> 16 > 6` is the gate, and the revision is only printed. The same pass found more
  misnamed registers. The firmware also needs its boot/init message before it schedules anything. [P]
- **Fix.** Derive ID gates and register meanings from the vendor driver. Bring up in steps (read-only probe,
  then firmware boot), with a log path that survives a panic.
- **Elsewhere?** probably: the A10 has a VXD of the same family, but its values must be re-read.
- **Sources.** VXD bring-up notes (unpublished).

---

## Platform and tooling pitfalls

<a id="t1"></a>
### T1. Days of reverse engineering on a regression that a diff would have found

- **Symptom.** A new build fails at a step that passed on every earlier boot.
- **Fix.** Start from what changed: the new patches, the dmesg diff against the last good cold boot, and the
  words written differently. Revert to the known-good values, and use RE only to explain that one difference.
  [F1](#f1) is the worked example. [V]
- **Elsewhere?** generation-wide.
- **Sources.** internal notes (unpublished); the worked example is [F1](#f1).

<a id="t2"></a>
### T2. Netconsole silent over USB networking

- **Symptom.** No netconsole lines reach the host, so a freeze leaves no log. [V]
- **Root cause.** Several, any of which is enough:
  - a **broadcast** `remote_mac` never arrived over the USB network link;
  - the initramfs target died when the USB gadget re-created `usb0`;
  - the enable step ran on the wrong side.
- **Fix.** Set `remote_mac` to the host's USB interface **unicast** MAC through configfs. Re-arm after every boot,
  kexec boots included. Write a boot-id marker and check that it arrived. [V] FLIGHT-H2/H3.
- **Elsewhere?** generation-wide.
- **Sources.** [FLIGHT-H2](docs/release/orchard-0.4/integration/FLIGHT-H2.md), [FLIGHT-H3](docs/release/orchard-0.4/integration/FLIGHT-H3.md).

<a id="t3"></a>
### T3. Shipped scripts lose their executable bit

- **Symptom.** After an install, helper scripts were mode 0644: rotation was dead and the scale stuck at 1. A
  test ladder failed with rc 126. [V]
- **Fix.** Commit scripts as git mode 100755, have the packager force modes for `bin/` and autostart, and add a
  pre-flight check. When copying to a device, run scripts as `bash script.sh`.
- **Elsewhere?** generation-wide.
- **Sources.** packaging history (unpublished).

<a id="t4"></a>
### T4. An `LD_PRELOAD` tracer does nothing under `sudo`

- **Symptom.** An ioctl tracer produced no capture for a tool run under `sudo`. [V]
- **Root cause.** sudo resets the environment and strips `LD_PRELOAD` and `LD_LIBRARY_PATH`. A GPU client
  started under sudo also silently loads a different Mesa.
- **Fix.** Use `sudo env LD_PRELOAD=… cmd`, or run only the debugfs reads under sudo.
- **Elsewhere?** generation-wide.
- **Sources.** [FLIGHT-H3](docs/release/orchard-0.4/integration/FLIGHT-H3.md).

<a id="t5"></a>
### T5. Measure the stack the desktop really loads

- **Symptom.** glmark2 refused scenes, lost the context and ran at half the shipped stack's fps. [V]
- **Root cause.** It was run with an old private Mesa stack instead of the compositor's environment.
- **Fix.** Copy the GPU-relevant environment from the running compositor's `/proc/<pid>/environ` (the
  [census tool](tools/README.md) does this).
- **Elsewhere?** generation-wide.
- **Sources.** [lane IP2](docs/release/orchard-0.4/lane-ip2/README.md).

<a id="t6"></a>
### T6. Agent-driven device runs: foreground waits, stale chains, silent monitors

- **Symptom.**
  - An interrupted `launch; sleep; ssh …` chain left a half-booted device.
  - A stale "wait for SSH" loop from a failed run launched a second runner when a later boot came up.
  - A log monitor ending in `| cut` never fired.
  - A `/proc/*/cmdline` busy-check inside `sh -c` matched itself. [V]
- **Fix.**
  - Launch alone, then wait for SSH in a background `until` loop.
  - Stop every earlier chain before starting a new one.
  - End monitor pipelines with `grep --line-buffered` or `awk … fflush()`.
  - Match `/proc/*/comm`, or skip your own PID.
- **Elsewhere?** generation-wide.
- **Sources.** internal notes (unpublished).

<a id="t7"></a>
### T7. Docker on a macOS host: stale virtiofs dentries and mtimes, a case-insensitive filesystem, little disk

- **Symptom.**
  - After a host-side `rm`, an `fopen(…, "w")` of the same path in the container fails with ENOENT, and only
    sometimes.
  - A host edit wasn't recompiled: ninja skipped it, and the build silently lacked the fix. [V]
- **Fix.**
  - Truncate (`: >file`) instead of deleting.
  - `touch` edited files inside the container, or gate on object hashes.
  - Keep the kernel tree in a Docker volume: APFS is case-insensitive.
  - Check free disk before kernel builds.
- **Elsewhere?** probably: any port built in Docker on macOS.
- **Sources.** internal notes (unpublished).

<a id="t8"></a>
### T8. zsh does not word-split

- **Symptom.** A bash idiom (`set -- $p`) run by a zsh tool shell left `$2` empty, and `rm -rf $E/$2` deleted the
  parent directory. [V]
- **Fix.** Run anything that relies on splitting inside `bash -c`, and guard `rm -rf` paths with `${var:?}`.
- **Elsewhere?** generation-wide, for agent tooling whose shell is zsh.
- **Sources.** internal notes (unpublished).

<a id="t9"></a>
### T9. Byte-exact Mesa rebuilds: strip mode, and gates against moving references

- **Symptom.** A control rebuild of an installed library didn't match its bytes. A reference gate died on a
  missing SHA hours after its base passed. [V]
- **Root cause.** meson's install-time strip is a plain `strip`, not `strip -S`. And reference build directories
  were shared state that other work rebuilt in place.
- **Fix.** Use plain `strip`, and check that the control reproduces the installed SHA first. Gate a new build
  differentially against its base (the same shader corpus through both compilers) instead of against other
  builds' directories.
- **Elsewhere?** generation-wide.
- **Sources.** internal notes (unpublished).

<a id="t10"></a>
### T10. A test fixture wrote through a symlink and destroyed the real kernel payload

- **Symptom.** A rehearsal test replaced a 15 MB kernel payload with 26 bytes. [V]
- **Root cause.** The test tree symlinked real artifacts, and a fixture took a real artifact's name, so its write
  followed the symlink.
- **Fix.** Never give a fixture a real artifact's name. Assert that the payload is not a symlink, and hash real
  payloads before and after tests.
- **Elsewhere?** generation-wide.
- **Sources.** internal notes (unpublished).

<a id="t11"></a>
### T11. Warm kexec refused after a cold boot: the CPUs came up without PSCI

- **Symptom.** Every warm hop was refused ("SMP kexec needs PSCI"), and the CPUs reported
  `enable-method=spin-table`. [V]
- **Root cause.** The m1n1 build used for that cold boot didn't provide PSCI. A7–A11 have no EL2, so PSCI comes
  from the loader.
- **Fix.** After every cold boot, check that `/proc/device-tree/cpus/cpu@0/enable-method` reads `psci` before
  relying on warm hops.
- **Elsewhere?** generation-wide on A7–A11.
- **Sources.** internal notes (unpublished).

<a id="t12"></a>
### T12. Cold and warm boots must behave identically

- **Symptom.** Problems that appear only on kexec boots ([F5](#f5), [F6](#f6), [F9](#f9), [P10](#p10)).
- **Fix.** Treat every cold/warm difference as a bug. Test both kinds of boot, and keep a table of differences,
  each marked fixed or not. This rule found [P10](#p10)'s domain hold. [V]
- **Elsewhere?** generation-wide.
- **Sources.** [lane SLEEP](docs/release/orchard-0.4/lane-sleep/README.md); internal notes (unpublished).
