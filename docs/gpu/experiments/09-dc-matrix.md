# Experiment 09 — one hypothesis per fresh boot

Round-10 kernel head `4e7805c3e88f1c6c9c91854ca75a960a580b9bbc` (`a9/gpu`).
Apply patches 0021–0023 after `befac93b38`, integrate and build the complete
Omarchy payload. The GPU-only Image is not the integrated boot payload.
Only the orchestrator runs these commands. No experiment is run automatically.
Default `dc_variant=0 dc_observe=0` leaves the round-9 firmware bytes, MMIO
sequence, one-shot behavior and inert-by-default registration unchanged.

Exp08, reported and logged by the orchestrator, still timed out with DC
consumer=0/producer=1 after full barriers, valid boot handoff, drained ALIVE,
Fender W7/readback0 and kick0x10. Park succeeded. This rules out the tested
ordering correction as a sufficient fix; it does not distinguish scheduling,
initialization policy and firmware cache visibility. New partial MINIM
decoding by the firmware-RE agent shows the consumer advances **after cmd8
returns**, so consumer0 is also consistent with blocking inside cmd8.
ALIVE trailing words remain opaque and must not be echoed.

## Preparation and exact commands

Once on the host, upload both scripts (these commands copy files only):

*(Device/host command block omitted; it targets the private workspace.)*

The following is the ranked run list. Execute **one line per fresh boot**;
do not run this as a batch. Reupload after reboot if `/tmp` is lost.
Each helper sets `dc_observe=1`, selects the variant, enables all six original
parameters and runs CONTROL/IRQ/WORK/PARK with the original runner lock.

*(Device/host command block omitted; it targets the private workspace.)*

After each run, replace `N` with its variant number and collect the complete
logs before reboot (also retain the command output above):

*(Device/host command block omitted; it targets the private workspace.)*

The runner lock is removed on success, so the second collection is only for
failed runs. Do not clear a failed lock, run another variant on that boot,
reset the GPU, kill the root server, or free firmware memory. A stuck writer
still requires collection/reboot; no cleanup command is sent behind it.

## Evidence and ranking

- **0 — control.** Same submission as exp08, with observation enabled.
  If this succeeds while exp08 failed, logging delays or boot variability
  become confounders. Repeat the control before attributing a variant fix.
- **7 — recovered pre-MTS policy gate.** MINIM scheduler8000a120 calls
  10001ac8 before reading TXSTAT or fetching MTS. The helper calls the large
  policy routine1000c0d8 when private+228 and+22c are both nonzero. Firmware
  init10003ca4 loads these from META init+6c0/+6c8; Linux sets both to1 while
  leaving dynamic power policy incomplete. Variant7 sets **META init+6c8=0
  before release**, leaving6c0=1 and every ring/kick unchanged. This bypasses
  a concrete recovered gate; it is not a normal iOS policy or a verified fix.
  Check `DC fw ... policy meta6c0=1 meta6c8=0`, then compare cache_epoch and
  consumer progress with control0. Success does not authorize rendering
  under a policy bypass. No root length, busy byte or counter is seeded.
- **6 / 1 — visibility.** Host `ca0744` distinguishes normal shared-memory
  META `c0` aliases from the root's `40` cache-bypass alias. The variants
  clear bit31 in init+0x1c (6), or init+0x18 and +0x1c (1), **before boot**.
  These are hypotheses about using an existing alias mechanism for DC;
  neither is the recovered ordinary DC host sequence. Data-only separates
  stale slot data from a stale control/producer view. Existing GART leaves
  and all other pointers stay unchanged. There is no claim these aliases
  bypass GPU SLC or flush an already cached firmware copy of a pointer.
- **5 — initialization policy.** Fresh decompilation of `c96be8` confirms
  control+0x30 = `((host+0x1af8 & 3) == 0)`. Both 0 and 1 are real host
  choices. Linux currently uses 1; this variant uses 0 before boot. The
  firmware meaning is unknown: this is not a verified "ready" bit. No
  other init-policy field is guessed or written after ALIVE.
- **2 — interrupt state.** Reuses the known ADT AIC ack at +0x94=0x4000,
  after Fender, before the kick. The normal IRQ handler already acks it,
  making this a weaker hypothesis. No unknown GPU interrupt register is
  accessed, and none of ALIVE's trailing payload words is echoed.
- **3 — missed notification.** Original kick0x10 followed by one Fender
  W7/active-state-checked kick0x10 at one second if still unconsumed.
  Producer and slot are never republished, and the original three-second
  deadline is not extended. A fault or failed active-state check blocks
  the re-kick. Park/quarantine rules remain unchanged. Success supports
  a notification/timing issue, not permission to retry work generally.
- **4 — queue routing.** `ca0358` uses CL0x12; `ca05d4` and TA `ca00a0`
  use0x10. Thus 0x12 for DC is deliberately ranked last and contradicts
  the normal recovered DC path. It changes only the kick value, not the
  register. No evidence justifies probing an arbitrary new MMIO address.

All selectors are latched in `map`, before arm/release; later sysfs parameter
changes do not change an existing boot's variant. Values outside0..7 fail
map and latch failure. The original separate boot/control gates remain.
The DRM frontend has equivalent parameters under `a9_gpu_drm`; the supplied
helper intentionally targets the existing diagnostic workflow.

## Reading the memory snapshots

`DC matrix latched variant=N observe=1` identifies the actual chosen mode.
The snapshot stages are `before-publish`, `before-kick`, `after-kick`,
`100ms`, optional `re-kick`, and `consumed` or `timeout`.

Each stage explicitly logs consumer/producer for submission slots60/64/68/6c,
event70, four stamp controls in71, and controls72/73, with shared offsets.
The first sample then emits every nonzero word in **all** root0x8000 and
shared0x60000 bytes; omitted words are zero. Each later sample emits every
changed word, including changes to zero. This covers the complete boot
control block, channel states, event/stamp records, and unknown trace/fault
buffers without inventing heartbeat semantics. The shadow costs416KiB and
is allocated only when observation is explicitly enabled. The additional
480-byte T0 global-variable shadow is part of the boot structure.

Translate root/shared offsets with `g5p_plan_layout` in `boot-layout.h`.
Known control locations include host control slot5e, payload-size+0x1020,
cmd8 completion counter+0x1024,
tail pointers+0x1044/+0x1048, initialized+0x104c and trailing+0x2054; the
meaning/ownership of all other words is deliberately not assigned here.
The baseline includes pointer/host values too; a delta is not automatically
a firmware write if it coincides with our producer/slot/event-consumer stores.

Every sample also prints `DC fw ... payload_units=... root_copy_units=...`
`cache_epoch=... root_busy=... host_request=...` and a separate policy line
with META init6c0/6c8, T1 PC/SP and control30. `root_busy` is specifically
byte+498, not an inferred full-word flag. Root copy units+1480 is a live
length field; **no sentinel is written**. Zero is the legitimate cmd8 size,
so unchanged zero cannot show whether the handler was entered. A cache_epoch
increment supports reaching the cache-maintenance tail (or another caller
of that helper); pair it with the baseline and absence of other traffic.
The firmware's internal wait uses private+0x160/+0x16c and META internal
0480fff8/0480fff0 with request0x11047. These internal addresses are **not**
added to the ARM MMIO allowlist. The image's80000000 region contains MINIM
code: ALIVE word1=8000a120 is the scheduler PC, per the new decoder evidence.
Its local-memory image is staged at image+0x24000 then copied into META
core memory. Reading that CPU staging buffer would not reveal the live
private/thread state. Live core-memory readback still needs a safe recovered
path; no slave-port access is attempted while firmware is running.

These are **CPU-visible coherent RAM** samples, not a direct read of META's
cached view. IRQ/event drain and firmware may run concurrently; samples are
not atomic. A transient value can appear between samples. Logging changes
timing and large trace changes may fill the kernel log; preserve netconsole
and the complete dmesg as usual. No extra GPU readback is issued after boot. Mapped T0 global-variable RAM
(META100139c0..10013ba0, packed image+179c0..17ba0) is also sampled as
`image+...` words; only this declared range of the image is captured. The
remaining image words are outside the snapshot, not implied to be zero.
This mapped T0 region differs from the8000 local core-memory staging source.

No CPU streaming DMA sync or raw CPU cache invalidation is applied to
coherent DMA allocations. That would not establish META/SLC cache behavior
and can violate DMA API ownership. The cache experiments instead change
verified address-alias bits at boot. A firmware-side clean/invalidate command
needs a recovered protocol before implementation.

Success still means `control_complete=1` then the original IRQ/CL checks and
park. Consumer advance proves transport only, never shader completion. Same
timeout retains consumer0/producer1 and the classified failure-park path.
New ALIVE failure under an init/alias variant rejects that variant for this
boot; it is not a DC result. No outcome enables Mesa compute automatically.
