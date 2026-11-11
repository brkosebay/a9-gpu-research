# G1 / experiment 01 — power gfx and capture Rogue ID candidates

**Status: run 1 wedged on the first R0 read; see the results below.**
Do not repeat the unmodified script. Use [experiment 02](02-fender-meta.md)
for the recovered Fender startup prerequisite. Research agent has not accessed the iPad.
Human/orchestrator owns execution and appends the actual results below.

## Evidence and hypothesis

**Verified offline:** j71t ADT provides GPU windows
`0x201000000/0x100000` and `0x201e00000/0x100000`; its compatible is
`gpu,s8003`. Hoolock commit `6831bc701a6ce059e71e5aaa9488c9195bea6927`
has the `gfx` PMGR provider at `0x20e080340`. Its
`apple_pmgr_ps_set` implementation defines target bits3:0, actual bits7:4,
ACTIVE=15, auto-enable bit28, and write-one-to-clear history bits8:9.
See [bring-up evidence](../agx-g5p-bringup.md).

**Verified offline:** `build/kernel/config` has `CONFIG_DEVMEM=y`,
`CONFIG_STRICT_DEVMEM` unset, `CONFIG_APPLE_PMGR_PWRSTATE=y` and generic
power domains enabled. **Inferred prerequisite:** the currently running
HoolockRD must use that kernel/config and expose BusyBox `devmem` and
`/dev/mem`; the script checks availability before writing anything.

**Inferred hypothesis under test:** forcing the known gfx domain ACTIVE
is sufficient for the Rogue ID words to become accessible in one of the
ADT windows. The script reads both because range identity has not yet been
proven. It makes **one kind of write only: the named gfx PMGR control word**,
then restores it. It never writes either GPU window or boots META.

**Inferred operational limit:** if GPU MMIO needs additional clocks,
Fender sequencing or reset release, a read can abort or hang despite the
PMGR state being ACTIVE. Neither devmem nor a simple kernel ioread guarantees
recovery from a bus SError. Capture the existing console; if it faults,
stop and retain that output rather than broadening the address scan.

## Exact human procedure

1. Use the project's existing human-operated procedure to reach the
   HoolockRD root BusyBox shell on **this j71t/S8003**. This experiment does
   not change the boot chain or device storage. Run before adding any GPU
   driver; ensure no other GPU experiment is running.
2. Paste the following block into that shell. It creates a script in RAM.
   It is identical to repository `scripts/gpu/read-id.sh`.

<!-- READ_ID_SCRIPT_BEGIN -->
*(Device/host command block omitted; it targets the private workspace.)*
<!-- READ_ID_SCRIPT_END -->

3. Execute once, preserving the exit code and complete output:

*(Device/host command block omitted; it targets the private workspace.)*

4. Save the output with the existing human console/logging method. Verify
   the `Restoring PMGR` / `PMGR gfx after` lines appeared. A bus fault or
   killed process can prevent the EXIT trap; restore the clean boot state
   using the existing human reboot procedure in that case, and record it.
5. Append raw words and outcome below. If the script stops on missing
   devmem, permissions, RESET/DEV_DISABLE/PARENT_OFF or PMGR timeout, do not
   bypass that condition. The next probe should use a kernel runtime-PM
   consumer of `ps_gfx`, or a corrected prerequisite identified statically.
   It should retain these same bounded ID reads and log each operation.

## Interpretation

**Verified public decode:** legacy core ID is `+0x18`, revision is `+0x20`.
B=`revision[23:16]`, V=`revision[15:8]`, N=`id[15:8]`, C=`id[7:0]`.
Designer=`revision[31:24]`, maintenance=`revision[7:0]`. New PBVNC uses
u64 `+0x20`: B/V in high32, N/C in low32, each 16 bits. These formulas
come from Linux `pvr_gpuid_decode_reg` and `pvr_rogue_cr_defs.h`.

**Inferred acceptance:** choose a layout only when raw words are stable
and sensible for the identified register window. The script prints both
decodes as candidates and does not select one. All zeros, all ones, a
numerically familiar tuple in the other window, or a nonzero high word are
insufficient evidence. A positive result should be repeated once from a
fresh human-controlled boot and compared with open hardware definitions.

**Proposed fallback if devmem is unavailable:** make the next experiment a
small diagnostic platform driver under `/src/wt/gpu` with DT
`power-domains = <&ps_gfx>`, call `pm_runtime_resume_and_get`, then map and
read these three words in each window, logging before every read. Build
with `scripts/build-kernel.sh --tree gpu`; let the human run it. No kernel
patch is required for the verified current config, and none has been
installed or built as part of experiment 01.

## Results (human/orchestrator to append)

**Verified result status:** none yet; do not fill this from inferred values.

```text
Date / kernel commit:
PMGR before / requested / ACTIVE observed / after restore:
R0 +18 / +20 / +24:
R1 +18 / +20 / +24:
Exit code / bus fault / dmesg:
Fresh-boot repeat:
Chosen layout and evidence, or still unresolved:
```

## Results: run 1 (2026-10-22 12:25, orchestrator)

Setup: kernel `744636325f11` (a9/periph round 1, HoolockRD initramfs).
HoolockRD BusyBox has **no `devmem`**, so a static BusyBox-compatible
replacement (`tools/devmem/devmem.c`, mmap + volatile 32-bit access,
runtime page size) was pushed to `/tmp/bin` via wget over USB networking.
Log: `docs/test-logs/2026-10-22-gpu-exp01.txt`.

- **Verified:** before the run, `pm_genpd` showed `gfx off-0`, and PMGR gfx
  `0x20e080340` read `0x00000300` (no RESET/DEV_DISABLE/PARENT_OFF bits).
- **Verified:** writing `0xf` brought the domain up: the poll saw
  `0x000003FF` (actual state 15 = ACTIVE).
- **Verified:** the **first GPU window read, `devmem 0x201000018 32`, never
  returned.** No output after "ACTIVE observed". There was no immediate panic
  and no SError on the console. The kernel still answered ICMP on usb0, but a
  second shell (telnet) couldn't be served and the system degraded. The core
  is presumably stuck in an unterminated bus read. The restore trap didn't
  run (gfx left ACTIVE). Hard reboot needed.
- **Window 2 (`0x201e00000`) was never reached** because the script reads
  window 1 first.
- **Inferred:** PMGR power alone isn't enough for the window-1 registers to
  respond. Something else has to come first: a clock gate, reset release, or
  the "Fender" sequencing hinted at by `agfPollFenderReg`. Or window 1 isn't
  the RGX register bank. Round 2 should find what AGXG5P does between
  power-on and its first RGX register access. Consider reading window 2
  first next time, and make any future on-device read run under a
  watchdog/timeout or from a kernel module with a known-good sequence.
- **Verified (photo of the framebuffer console, 2026-10-22):** at t=222 s,
  `rcu: rcu_preempt detected stalls on CPUs/tasks: 1-...0`, then
  `Sending NMI from CPU 0 to CPUs 1` and `After 10 seconds, these CPUS still
  haven't responded to the NMI: 1`. CPU1 is wedged inside the window-1 load
  and doesn't even take the NMI, which is consistent with a bus transaction
  that never completes (the target isn't clocked or is held in reset). No
  SError was reported.
