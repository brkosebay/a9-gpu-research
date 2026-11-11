# Experiment 02 — Fender startup, ID, and META baseline

**Status: orchestrator Run 1 passed all phases; see results below.** No
device access by the research agent. **Verified limitation:** this build stages firmware but does not
start it. The requested complete G2 firmware-boot attempt remains gated on
the page tables and shared init fields listed below. Do not interpret this
experiment as a completed firmware boot implementation.

## Why experiment 01 hung, and what changes

**Verified on device:** PMGR gfx reached ACTIVE, then R0 `+0x18` did not
return. R1 was never accessed. See [experiment 01](01-read-id.md).

**Verified in Ghidra + the actual 20H350 IOKit tables:** R0 `0x201000000`
is RGX; R1 `0x201e00000` is Fender. The S8003 host startup at
`0xfffffff006c93a9c` enables clock gate 0 and power gate 0 (ADT ID 124),
then, for C0 with no `has-kf` property, performs these **32-bit** accesses:

1. **Write** Fender `+0x10000 = 0xffff0000` (end of init FIFO).
2. **Write** Fender `+0x0 = 0x40000000`.
3. **Write** Fender `+0x1000 = 0x11`.
4. **Read/poll** Fender `+0x1000` until bit4 clears; then wait at least 10 µs.
5. Apple reads **RGX `+0x20` first, then `+0x18`**, in
   `0xfffffff006ca644c`. The diagnostic follows this exact order and does
   not read R1 as a Rogue bank or add the previously unverified `+0x24` read.

**Inferred:** this is the missing prerequisite for the failed bare R0 read.
It is the verified Apple sequence, not yet a successful Linux measurement.
**Verified software limit:** a poll timeout bounds repeated completed reads;
it cannot interrupt an individual MMIO transaction that never completes.
There is no honest guarantee against another hardware hang. The build avoids
the known bad first read, logs each Fender setup step and both ID reads
before access, and separates
wrapper startup from every RGX/META access. Do not substitute a shell
`timeout` for the wrapper sequence or claim it can recover a stalled bus.

## Offline build and firmware staging

**Verified implementation:** branch `a9/gpu`, kernel tree `/src/wt/gpu`.
Driver `drivers/gpu/apple-g5p/a9-gpu-diag.c`, `CONFIG_APPLE_G5P_DIAG=y`.
Default `a9_gpu_diag.enable=0` skips driver registration entirely.
Only j71t is accepted when enabling it. This is a plain platform diagnostic;
there is no DRM node or rendering support.

From the host repository root, these steps are offline:

*(Device/host command block omitted; it targets the private workspace.)*

Use `build/prebuilt/initramfs/initramfs.gz` as the argument if the combined
peripheral initramfs is unavailable. `build-diag.sh` builds Image.gz/DTBs in
`build/kernel-gpu/` and appends only the exact local GPU firmware to the
supplied initramfs, producing `build/gpu/initramfs-gpu.gz`. Apple firmware
remains under build/ and is never part of the patch series.

The orchestrator can assemble the tethered RAM payload:

*(Device/host command block omitted; it targets the private workspace.)*

Then use the existing human-operated boot procedure. Do not run experiment
01, a raw GPU devmem probe, another GPU driver, or another GPU experiment on
this boot. If integrating other kernel workstreams, cherry-pick the GPU
series into the orchestrator's integration tree and rebuild there; do not
reset another workstream or assume the GPU tree includes its changes.

**Inferred prerequisite:** Linux reaches the existing HoolockRD USB shell.
Keep the existing console available. A fresh boot is required after an
unterminated access; this diagnostic retains its gfx runtime-PM reference
until removal/reboot instead of guessing a power-off protocol.

## Exact orchestrator device commands

These are **not** commands for the research agent to execute. The source
uploaded by `-f` is diagnostic.sh, a
BusyBox shell script. It checks j71t/S8003 and the diagnostic sysfs node.

First validate the firmware hash and stage its LDR into DMA RAM. This stage
issues no GPU register reads/writes; driver registration itself attaches the
gfx power-domain consumer.

*(Device/host command block omitted; it targets the private workspace.)*

**Expected:** the exact SHA256 and 94 records validate; `prepare` reports
`30000` DMA bytes, T1 PC `20000000`, SP `8000b3c8`, and explicitly says the
image is not executable. Result `loaded=1` means **packed in DMA RAM only**;
it does not mean GPU-mapped, running, or firmware-alive.

Run the **Fender-only** stage, then inspect its complete log before doing
anything else:

*(Device/host command block omitted; it targets the private workspace.)*

**Expected:** logged writes R1 `+10000`, `+00000`, `+01000`, then bit4 clear
and result `last=0 powered=1 fender=1`. **No R0 read occurs in this stage.**
If the poll returns `-ETIMEDOUT`, retain the raw status and stop. If a single
access hangs, retain the last logged operation, use the human reboot
procedure, and do not proceed to ID/META or broaden the scan.

Only after a successful wrapper stage, request the same two ID reads Apple
uses:

*(Device/host command block omitted; it targets the private workspace.)*

**Expected:** R0 `+0x20`, then `+0x18`, each logged before and after the read.
All-zero/all-one candidates and revisions outside Apple's C0 check cause failure. **Verified host constraint:**
Apple's `readChipInfo` accepts branch byte 9 and version bytes 7, 10, 13 or
15; this is a host check, not a measured BVNC. Preserve the raw words and
only then decode B/V from revision and N/C from ID as in experiment 01.

Optionally capture the META slave-port baseline after ID succeeds:

*(Device/host command block omitted; it targets the private workspace.)*

**Verified implementation:** this reads RGX CTRL1 `+0xa18`, IRQSTATUS
`+0xac8`, then reads T0/T1 ENABLE and STATUS through the slave port. Slave
reads write CTRL0 `+0xa10`; they do not copy firmware or enable a thread.
Each ready poll is bounded at 100 ms. A not-ready port is a useful result;
do not bypass it by writing guessed reset values.

## G2 boot gate and the decisive alive test

**Verified RE:** Apple stages the LDR in mapped GPU RAM, appends segment-MMU
configuration and two firmware init pointers, then performs META master
boot. It does not replay LoadMem addresses directly through the slave port.
The implementation therefore stages the proven RAM layout and retains the
bounded slave-port primitives; `load` returns `-EOPNOTSUPP` instead of
executing an upload against absent mappings. See the
[bring-up sequence and structures](../agx-g5p-bringup.md).

**Still required before a firmware-start command can be enabled:** verify
GPU catalogue/PDE/PTE encoding and the firmware GPU-VA allocation, construct
both init objects and their ring pointers, fill the `+0x200` boot config and
two init arguments, reproduce the Fender FIFO plus META reset release, and
connect IRQ 174 / the firmware event ring. The present build intentionally
has no command that pretends these prerequisites are satisfied.

**Verified strongest current alive signal:** a firmware event-ring entry
with type u32 `0` causes `AGXMetaFirmware_handleFirmwareControllerEvent`
`0xfffffff006ca263c` to set the alive flag and wake the boot waiter. The
ring has 256 slots of 44 bytes, control consumer `+0`, producer `+0x10`.
The ADT `meta-sw-interrupt` describes AIC set/ack addresses
`0x20e104014` / `0x20e104094`, mask `0x4000`, corresponding to IRQ 174.
A later complete G2 build should report the raw first event, index change,
and IRQ count before consuming/acknowledging it. An enabled thread, a static
PC, successful LDR copy, or the greeting string found offline does not pass.

## Results (orchestrator to append)

**Verified result status:** Run 1 passed all phases, as appended below by
the orchestrator. The following template is retained for future repeats.

```text
Date / kernel commit / initramfs SHA256:
Preflight validation / DMA pack result:
Wake: last logged operation / Fender status / result:
R0 +20 / +18 (only after successful wake):
META CTRL1 / IRQSTATUS / T0 ENABLE,STATUS / T1 ENABLE,STATUS:
Exit codes / full log paths / fresh-boot repeat:
Full firmware boot: NOT IMPLEMENTED in this build; do not infer success.
```

### Run 1 (2026-10-22 ~13:50, orchestrator): ALL PHASES PASSED, system stayed alive

Kernel: integration `a9/integ` = periph 681cceb6e8 + pcie 4f70c40735 + gpu
f0a73d521f (`7.3.0-rc1-g230f5ccd5c27`), stock m1n1, bootargs
`panic=0 a9_gpu_diag.enable=1`, initramfs `build/gpu/initramfs-gpu.gz`
(repacked as one gzip stream by mkpayload.sh). Logs: `docs/test-logs/exp02-*.log`.

```text
preflight: firmware SHA256 and all 94 LDR records validated
           LDR packed into 30000 DMA bytes at 0x000000080ac80000; T1 PC=20000000 SP=8000b3c8
           not executable: GPU PTEs, boot config and shared init not installed
wake:      request gfx power domain / gfx runtime PM active
           W R1+10000=ffff0000, W R1+00000=40000000, W R1+01000=00000011
           poll R1+01000 bit4 clear -> Fender wake status=00000001 result=0
id:        R0+00020=00090f00
           R0+00018=011b0602
meta:      RGX CTRL1=07000040 IRQSTATUS=00000000
           META T0 ENABLE=0201c032 STATUS=00020000
           META T1 ENABLE=0201c132 STATUS=00000000
```

Notes: with the Fender wake, the RGX window reads that wedged CPU1 in
experiment 01 now return immediately. The ID words pass Apple's
`readChipInfo` constraint (branch byte 9, version byte 15 = 0x0f).
Decoding is left to the GPU agent. The experiment-01 "legacy" layout would
give B.V.N.C = 9.15.6.2 (inferred, unverified). The CMA regression from the
PCIe dma-ranges window was present in this kernel (`cma: Failed to reserve
16 MiB`), but the 30000-byte DMA allocation still succeeded.
