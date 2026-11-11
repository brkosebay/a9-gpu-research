# From power-on to the first triangle on the A9 GPU

This is the bring-up path we took on the iPad 5 (Apple A9, "G5P", a PowerVR Rogue running Apple's own firmware
on a META core). It runs from the first register read on 2026-10-22 to the first Mesa-driven triangle on
2026-10-31, in order. Each step says what it needs, what went wrong, how we knew, and how far we expect it
to carry to other Apple PowerVR chips (A7, A8/A8X, A9X; the A10 is OrchardLinux's work).

It is written for people, and their AI agents, bringing up the same kind of GPU. What came after the first
triangle (power, performance, Mesa, memory) is in [HARD-PROBLEMS.md](HARD-PROBLEMS.md). The per-subsystem
porting map is in [PORTING-OLDER-GENERATIONS.md](PORTING-OLDER-GENERATIONS.md).

**Conventions**
- **Labels:** **[P]** proven from code, a decode or captured data. **[V]** verified on our device. **[I]**
  inferred.
- **Elsewhere?**
  - **generation-wide**: public Rogue behaviour, or the shared kext/firmware design. We expect it on every
    Apple PowerVR chip of this lineage.
  - **probably**: we expect it to carry over, but haven't checked another chip.
  - **A9-specific**: tied to A9 values or our own choices.

  We have never analysed A7/A8 firmware, so every rating is inference.
- **Register windows:** `R0` is the GPU core window (`0x201000000` on the A9) and `R1` is the "Fender" power
  wrapper window (`0x201e00000`).
- **Addresses:** `fffffff00…` addresses are in the iOS 16.7.10 J71t kernelcache. The names next to them are
  the names we gave those functions in Ghidra. `0x8000xxxx`/`0x1000xxxx` addresses are META firmware PCs.
- **"(unpublished)"** marks evidence in our private workspace; the sentence states what it established.

## If we did it again: the short path

1. Power the PMGR graphics domain, then **wake the Fender** before you touch `R0` ([step 1](#step-1)).
2. Replay Apple's whole reset FIFO through the Fender, and don't read `R0` while reset is held. Load the
   firmware through mapped RAM, not the META slave port ([steps 2–3](#step-2)).
3. Build the shared init objects exactly as the kext packs them, and wire the rings and the doorbell
   ([steps 3–4](#step-3)).
4. For the first control command, disable the firmware's power-policy path (`meta+0x6c8 = 0`). Turn it on
   later, once the GPC is up before ALIVE ([step 5](#step-5)).
5. Map a zero "VA 0 sink" page in context 0, and put user work in **catalogue slot 7 or above**
   ([step 6](#step-6)).
6. Get a compute job to retire first ([step 7](#step-7)). Then **check every byte you copied from a capture
   for truncation**. Both of our longest stalls were capture-truncation bugs.
7. For the TA, `W+0x88` (copied into `R0+0x470`) is a **PDS code-heap offset to a small program**, not a
   length. Point it at that program, with the program's bytes present ([step 8](#step-8)).
8. Never touch GPU registers after a job retires. Publish the 3D RAM-only ([step 10](#step-10)).

## Timeline

| Date | Milestone |
|---|---|
| 2026-10-22 | exp01: the PMGR domain is ACTIVE, but the first bare `R0` read never returns; CPU1 wedged |
| 2026-10-22 | exp02: Fender wake first, then the ID reads return; SoC alive |
| 2026-10-22 | exp03: the reset FIFO was stored but not executed; after the fix, a read during reset hard-locks the SoC |
| 2026-10-22 | exp06: **firmware ALIVE on Linux**; the first control command (`cmd8`) times out |
| 2026-10-22 | exp09: `cmd8` consumed with the policy gate bypassed (`meta+0x6c8 = 0`) |
| 2026-10-22 | exp10: **first job end to end** (a CL no-op) |
| 2026-10-23 | exp18c: the VA 0 sink removes the reset-release MMU fault |
| 2026-10-23 | exp19c: user context in slot 7: shader output written, but the job doesn't retire |
| 2026-10-23 | r19d: **first compute job retires** after restoring one byte the fixture had truncated |
| 2026-10-23 | r22: first render attempt: the TA is consumed by the firmware, **never completes (-110)** |
| 2026-10-23 | **First GPU-drawn triangle, by a compute shader**: pixel-exact, every foreground and background pixel |
| 2026-10-24 | iOS-side read-only captures of Apple's TA/3D work records and PM state |
| 2026-10-25 | many candidates tried and closed (policy, fabric bridges, stride, saved-context word, TE1 lane) |
| 2026-10-28 | `cmd8` consumed **with the policy on**: GPC up before ALIVE |
| 2026-10-30 | r94: `W+0x88` pointed at Apple's program: the VDM and PM move for the first time |
| 2026-10-30 | r95: plus the TPC page mapped: **first natural TA completion** |
| 2026-10-30 | r96: **first natural TA→3D render** (a 64×64 clear), shown on the panel |
| 2026-10-31 | r97: the app's triangle linked in: **triangle-exact**, cold boot |
| 2026-10-31 | Mesa102: **first Mesa-driven triangle** (EGL → Zink → our Vulkan driver), 10/10 frames |
| 2026-11-02 | vertex unified-store sizing fixed: vkcube and **weston-simple-egl** draw |

---

<a id="step-1"></a>
## 1. Power and the first register access (PMGR, Fender)

**What's needed** [P] (from the kext's `AGXG5P_mapPowerAndStartFender`, `fffffff006c93a9c`):
1. Turn on the PMGR graphics power domain. Linux's `ps_gfx` genpd does this, and covers the provider's
   separate clock-enable and power-enable calls.
2. Wake the Fender, all 32-bit writes on `R1`:
   - `+0x10000 = 0xffff0000` (the init FIFO terminator);
   - `+0 = 0x40000000`;
   - `+0x1000 = 0x11`;
   - poll until `+0x1000` bit 4 is clear;
   - wait 10 µs.
3. Only then read `R0`: `+0x20`, then `+0x18`. The kext's `readChipInfo` (`fffffff006ca644c`) accepts revision
   `& 0xff0000 == 0x90000` and a few version bytes. [V] Our reads returned revision `0x00090f00`.
4. The kext picks the register banks with a two-range switch on the device's memory count: index 0 is RGX, index
   1 is the Fender.

**What went wrong.** In exp01, the PMGR domain reached ACTIVE, and then the first `R0` read never returned. CPU1
wedged and didn't even take the NMI (`rcu_preempt detected stalls … haven't responded to the NMI`). There was
no SError, and the device needed a hard reboot. [V]

**How we knew.** Ghidra on the AGX kext's IOService paths and the two-range branch, checked against the ADT power
gates. One device run per stage.

**The general rule, found later** [P]: `R0` has no bus response while the Fender holds the GPC at pstate 0, or is
on its way there. iOS gates every runtime `R0` read on `AGXMetaFirmware_isGPURegisterAccessible`
(`fffffff006ca10ec`). That check requires three things:
- the Fender powered;
- `1 ≤ (R1+0x1000 & 0xf) ≤ max pstate`;
- `R1+0` bit 29 clear (the firmware sets it before it drops the GPC).

When the check fails, iOS **skips** the read. `R1` is safe whenever PMGR graphics is on. See
[mmio-access](docs/gpu/experiments/mmio-access.md) and [HARD-PROBLEMS P5](HARD-PROBLEMS.md#p5).

**Elsewhere?** probably: any Apple GPU with host-loaded META firmware behind a Fender wrapper. The A10 differs
(ARM firmware on an IOP behind RTKit). The kext class names `AGXMetaFender`/`AGXMetaFirmware` suggest a family. [I]

**Read:** [agx-g5p-bringup §Power](docs/gpu/agx-g5p-bringup.md), [exp01](docs/gpu/experiments/01-read-id.md),
[exp02](docs/gpu/experiments/02-fender-meta.md).

<a id="step-2"></a>
## 2. Reset, SLC, MMU and the META boot

**What's needed** [P] (Apple's `programResetStream`, `fffffff006c9feb4`, and `bootFirmwareAndWait`,
`fffffff006c9f954`):
1. Mode reset: `R1+0x10 = 0`. Then `R1+0 = 0x40000000`, and reset the Fender FIFO cursor to `0x10000`.
2. Append to the **Fender init FIFO**. Its entries are register/value pairs, with a flags byte in bits 23:16, and
   64-bit values are written high half first. In order:
   - a three-step `SOFT_RESET` (`+0x100`) sequence, which holds META while the rest is programmed;
   - `META_BOOT` (`+0xbf8`) = 1;
   - the MMU catalogue base for context 0: `+0xe140` = 0, then `+0xe148` = catalogue PA >> 12;
   - SLC3 control and scramble (`+0xe200`, `+0xe208`, `+0xe210`);
   - two Fender words;
   - `R0+0xe160`, which iOS points at a zero page;
   - `R0+0xbb8` = 0;
   - `SOFT_RESET` = 0;
   - the terminator.
3. Power the core: `R1+0x20000 = 0x20`, and poll bit 5. Set the GPC to pstate 1 (`R1+0x1000 = 0x11`) and wait for
   bit 4 to clear. Then wait for the firmware's alive flag.

Apple runs this once per power-up. A second "arm" pass of ours turned out harmless and unnecessary.

**What went wrong.**
- Our first wake left the GPC at pstate 1 and never made the pre-boot core request, so the FIFO was **stored but
  not executed**: reset, catalogue and SLC all read 0. [V]
- With that fixed, a read of `R0+0xa18` right after the reset-held arm hard-locked the SoC. [V]
- Lesson: "Fender active" does not mean the META slave port is readable.

**How we knew.** Ghidra on the `AGXMetaFirmware_*`/`AGXMetaFender_*` methods. Register names come from the
public Linux `pvr_rogue_cr_defs.h`: the MMU and SLC3 names, and `JONES_IDLE` at `+0x8328`. We compared the
FIFO word by word on the device. A census of every SLC write in the kext showed that iOS's whole SLC programming
equals ours.

**Fix** (round 6): no `R0` reads after arm except the reset halves; no slave-port loading (firmware goes through
mapped RAM); replay Apple's complete FIFO, ending with reset = 0; then watch RAM events. That gave ALIVE in exp06.

**Axes we later closed, so you don't have to** [V]:
- `R1+0x10 |= 4` is **void**. A corrected decode showed that Apple writes 0 there, as we do.
- The PMGR fabric bridges differ from iOS on Linux. A full replay of Apple's bridge settings latched and survived
  ALIVE, but changed nothing for the TA.
- A warm kexec is **not** a full GPU reset: some VDM state survives it (step 8).

**Elsewhere?**
- generation-wide: the RGX reset, MMU and SLC3 register names are public Rogue.
- A9-specific: the Fender FIFO's mode, values and delivery come from per-SKU tables and ADT flags. [I]

**Read:** [agx-g5p-bringup §Reset](docs/gpu/agx-g5p-bringup.md), [round6-readback](docs/gpu/round6-readback.md),
[exp03](docs/gpu/experiments/03-boot-meta.md).

<a id="step-3"></a>
## 3. Firmware (LDR) load and the init objects

**What's needed** [P] (Apple's `layoutAndLoadLDR`, `fffffff006c9f1bc`):
- **Not a slave-port upload.** The loader works out four segment extents plus a local-memory staging area,
  copies the load records into GPU-mapped RAM, and zeroes the ordinary segments.
- It then appends register/value "config" pairs to the boot config at image `+0x200`:
  - the segment MMU pairs;
  - the LDR's own config pairs;
  - a terminator.
- Two converted init pointers go at image `+0x3ff8`/`+0x3ffc` (the first init block, and the shared control).
- The A9 firmware has 94 LDR records, and its GPU base is `0xe1c0000000`.
- **The init objects** are packed at 64-byte boundaries, in two groups. They include the shared control
  object, the queue controls, the event data and the performance storage.
- META init fields we had to fill:
  - the PIO table (`+0x630` + 0x10·i: RGX, Fender, AIC timer, SW-IRQ);
  - the Fender-enabled and policy flags (`+0x6c0`/`+0x6c8`);
  - the SW-IRQ set offset and mask;
  - the config words from the measured version.
- META address aliasing: normally `(low32 + 0x40000000) | 0xc0000000`, with an uncached window for the
  init-root range.

**What went wrong.** At first we didn't know which init fields ALIVE needs. In the event, ALIVE arrived with the
dynamic policy fields still zero. [V]

**How we knew.** Ghidra on the loader and the packer, with our packer checked independently against every LDR
record. Our [extractor](tools/README.md) pulls the LDR out of the kernelcache and decodes its records.

**Elsewhere?** probably: the META LDR format and the method transfer, but the offsets are specific to the
firmware build. [I]

**Read:** [agx-g5p-bringup §LDR](docs/gpu/agx-g5p-bringup.md).

<a id="step-4"></a>
## 4. The host↔firmware rings, the kick and the IRQ

**What's needed** [P]:
- **Device-control (DC) ring:**
  - control and entries pointed at by the host object (`+0x360`, `+0x368`);
  - consumer u32 at `+0`, producer u32 at `+0x10`;
  - 256 slots × 20 bytes, one kept free;
  - a `dmb ish` before the producer store.
- **The kick**, in `AGXMetaFirmware_submitDeviceControl` (`fffffff006ca05d4`):
  1. fill the entry;
  2. barrier;
  3. Fender pre-kick `R1+0x14 = 7`;
  4. doorbell `R0+0xb00 = 0x10`.

  Nothing goes in between.
- **Doorbell values:** `0x10` for DC and TA, `0x11` for 3D. The global CL notification is type 2 with kick
  `0x12`.
- **Firmware→host event ring:** 256 × 44-byte entries, with the same index layout as the DC ring. A type-0
  event carries the scheduler's address, and its handler sets the host-side alive flag.
- **Auxiliary rings** in shared RAM: event, log, statistics, trace. Apple acks the AIC interrupt first, then
  drains log, event and trace/statistics.
- **IRQ:** the ADT `meta-sw-interrupt` gives the set and ack registers and mask `0x4000`, which is AIC IRQ 174
  on the A9.

**What went wrong.**
- exp06 got ALIVE, then `cmd8` "timed out at consumer=0/producer=1".
- Adding the Fender pre-kick (exp07) and full barriers (exp08) changed nothing. [V]

  The transport was right; the blocker was the policy gate in step 5.
- Later, with the policy on, the trace ring filled with repeating setup cycles. A post-run correction showed
  that this was **backpressure from a loop, not the cause**. [V]
- The TA and 3D rings were consumed without a doorbell. A late TA doorbell fired once and changed nothing. [V]

**How we knew.** Ghidra on the submit, drain and IRQ methods. We rebuilt the event ring from iOS captures, which
showed our drain and ack were already correct.

**Elsewhere?** probably: these are the firmware ABI's ring layouts ("not a stock IMG KCCB"). Expect the same
family on META-firmware chips, but re-derive it for each firmware build. [I]

**Read:** [agx-g5p-bringup §Rings](docs/gpu/agx-g5p-bringup.md), [submission-g5p](docs/gpu/submission-g5p.md),
[exp04](docs/gpu/experiments/04-cl-queue.md).

<a id="step-5"></a>
## 5. ALIVE, and the first control command (`cmd8`)

**What's needed** [P]:
- The scheduler (`0x8000a120`, the address an ALIVE event carries) runs a readiness helper (`0x10001ac8`)
  before fetching work.
- That helper runs the large power-policy routine (`0x1000c0d8`) when two private words are non-zero.
- The firmware's boot copy (`0x10003ca4`) loads those words from META init `+0x6c0`/`+0x6c8`. The copy is not
  linear: `meta+0x6c4` lands in `priv+0x230`.
- There are two ways through it:
  1. **Bypass, the way we first got through:** set `meta+0x6c8 = 0` before release. [V] `cmd8` completes and AIC
     delivery is confirmed. Then the CL notification needs word 2 = 1, not 0: the firmware copies it into the
     queue's end index. With that, the first job ran end to end.
  2. **Policy on (`meta+0x6c8 = 1`), the way iOS runs.** The gate is `0x1000d044`, which returns 0 when
     `policy+8`/`+0xc` read 2/2. The predicate is [P]; that the firmware's own policy code wrote those values is
     [I], since the host had written 0/4. [V] The fix was a bounded
     power-up that gets GPC1 active about 0.55 ms *before* ALIVE, plus DC/TA doorbells only inside the
     firmware's active window. With those, `cmd8` was consumed with the policy on and render prepare passed.

     The earlier confound was warm-kexec GPU cycling.

**What went wrong.**
- `DC timeout consumer=0 producer=1` again and again.
- Freezes at the `cmd8` kick with the policy on.
- One run had one ALIVE and a firmware cycling its trace every ~0.85 ms without consuming anything. That retired
  host timing and the doorbell as causes. [V]
- Two weeks later the same signature came back, from a different cause: iOS's idle-power record written at map
  ([HARD-PROBLEMS F1](HARD-PROBLEMS.md#f1)).

**How we knew.** We disassembled and replayed the MINIM/META firmware, and ran one variant per fresh boot. We
recorded the trace ring in flight. A decode of the whole policy subsystem showed its hardware reach: a few
Fender registers and two PIO words, and **never** `R0`. [P]

**Elsewhere?** probably: the specific words belong to this firmware build, but the *pattern* (a power-policy
readiness gate in front of the first control command) probably exists on other META firmware. [I]

**Read:** [exp06](docs/gpu/experiments/06-post-alive.md), [exp09](docs/gpu/experiments/09-dc-matrix.md),
[exp10](docs/gpu/experiments/10-cl-visibility.md), [73e](docs/gpu/experiments/73e-device-result.md),
[74e](docs/gpu/experiments/74e-build-report.md), [lane IP2](docs/release/orchard-0.4/lane-ip2/README.md).

<a id="step-6"></a>
## 6. GART and the GPU VM

**What's needed** [P] (class `AGXSharedGartTableBackingG3ThruG9`). 16 KiB GPU pages, three levels:
- **catalogue:** 1024 u32 entries indexed by `(VA >> 30) & 1023`, each `(dir_PA >> 12) << 4 | 1`;
- **directory:** 512 u64 entries indexed by `(VA >> 21) & 511`, each `leaf_PA | 3`;
- **leaf:** 128 u64 entries indexed by `(VA >> 14) & 127`.

PTE flag bits (public meanings): bit 62 PM/META protect, bit 3 SLC bypass, bit 2 cache-coherent, bit 1
read-only, bit 0 valid.

Leaf flags come from a per-range **attribute table**, so "all firmware RAM as `PA|7`" is wrong:
- the image is mapped with protect + valid;
- shared memory and the uncached init roots add the coherency bit;
- PIO adds the SLC-bypass bit;
- Apple's own host buffers are `PA|0xd`.

**Contexts:**
- Boot context 0 uses catalogue slot 0.
- **iOS user contexts start at slot 7. Slots 1–6 belong to the parameter manager's requesters.**
- Attach is a DC3 entry `{3, slot, 0, 0, 0}`.

**What went wrong.**
1. An MMU fault event at the exact moment of reset release: a PBE write to VA 0. [V]
2. With a sink in place, the compute job faulted at level 3 "Cat Base", context 1. The CPU-side tables, the
   catalogue base and a META read-back of the page tables all matched. So it was not a table-content
   problem. [V]

**How we knew.** We recovered the MMU fault decoder from the kext (`fffffff006ca5c14`); its field positions match
IMG's public `rgxdebug.c`. We kept a retained MMU history at every boot stage, and read the page tables back
through META.

**Fix.**
1. A **VA 0 sink**: three zeroed 16 KiB pages mapping only `[0, 0x4000)` in context 0 before release. This
   removed the reset-release fault, and cache maintenance completed.
2. The user context in **slot 7**: no fault, and the output was written. [V]

**Elsewhere?** generation-wide: a three-level PC/PD/PT MMU with 16 KiB leaves and 40-bit VAs appears in both
the A9 and A10 trees, and the class name "G3ThruG9" suggests one GART format across generations. The
user-slot assignment belongs to the firmware. [I]

**Read:** [agx-g5p-bringup §Round 3](docs/gpu/agx-g5p-bringup.md), [18c](docs/gpu/experiments/18c-va0-sink.md),
[19](docs/gpu/experiments/19-context1-cbase.md), [19c](docs/gpu/experiments/19c-context-activation.md),
[11](docs/gpu/experiments/11-context-attach.md).

<a id="step-7"></a>
## 7. The first compute job, and a triangle drawn by compute

**What's needed** [V]:
- A fixed compute job modelled on an iOS capture: a CDM stream, PDS/USC code in the code heap at
  `0x3_0000_0000`, and a channel with a tag-4 dependency, notified through the global CL ring.
- An attached user context in slot 7.
- A cache preamble that worked:
  1. `R0+0x11f00 = 1`, then a fence;
  2. `R0+0x688 = 7`, then a poll;
  3. request `R0+0x1720 |= 0x1f`, then poll `R0+0x1728` bit 0.

  Its semantics are unknown.
- Completion means the firmware stamp words, the numerical store and 63 intact sentinels. A host-side
  classification isn't enough.

**What went wrong.**
- "Scanned but not started": stamp 0, output untouched, no fault.
- Then the MMU faults from step 6.
- Then the shader output was written correctly, but the job never retired (`-110`). [V]

**How we knew.** A byte diff of our fixture against the successful iOS capture. The USC helper had been copied
for only `0x40` bytes, and it branches to `+0x40`, where iOS has a USC END. **Exactly one byte changed.** [P]

**Fix (2026-10-23).** We restored that byte, and the first compute job retired: numerical PASS, 63/63 sentinels.
User-BO compute through GEM from userspace followed. The same evening, a **compute-shader rasteriser drew the first
GPU triangle**, pixel-exact on every foreground and background pixel, with the guards intact. [V] The run record is
unpublished; the timeline above dates it.

This was our first **capture-truncation** bug, and the TA root cause in step 8 turned out to be the same class.

**Elsewhere?** probably: the job model and the method transfer. The USC/PDS ISA is generation-specific.

**Read:** [19d](docs/gpu/experiments/19d-completion-retirement.md), [20](docs/gpu/experiments/20-user-compute.md).

<a id="step-8"></a>
## 8. The TA is consumed but never finishes: the path to the cause

This took from 2026-10-23 to 2026-10-30. It is the step most likely to cost another porter weeks.

**The symptom** [V]:
- The TA notification is consumed.
- The firmware's TA start routine (`start23`, `0x8000672c`) runs its 63 register stores, ending with
  `R0+0x400 = 1`.
- Release is set; there is no MMU fault.
- `TA_complete = 0`, `PM_saved = 0`, and `-110` after 12 s.

A microsecond flight recorder caught one short burst about 422 µs after the doorbell, then nothing:
- the VDM runs its cursor to the stream terminate;
- the parameter manager is busy for a few µs;
- everything reads idle (`JONES_IDLE`);
- `EVENT_STATUS` never latches `TA_FINISHED` (bit 5) or `TA_TERMINATE` (bit 6).

The firmware's TA finish routine waits on `TA_FINISHED`. Skipping that wait gives a diagnostic "complete" with no
output. Our 2026-10-29 synthesis put it as: "there is no missing kick; everything reads idle with the TA still
open and nothing produced".

**The cause, at the confidence the evidence gives.** One factor flipped on its own (r94) was the first change
that made the stalled TA move. [V] Adding back a page our own diagnostics had unmapped (r95) then gave the first
**natural** TA completion. [V]
- The flipped factor is `W+0x88`, a word of the TA work record that `start23` copies into `R0+0x470` as its
  last store. It is a **code-heap offset to a small PDS program** written by userspace, **not a length**. [P]
  - A census of 15 iOS captures shows the word moving with the program block between two heap layouts.
- Every value we had flown pointed at zeros or at a different program. The fixture had also **zero-filled
  exactly the 24 non-zero dwords** of Apple's low code-heap block that the offset points into, because our
  capture range started at `+0x180`.
- Apple's kext only mask-copies this word from the userspace record. Our own layers had rewritten it from a
  stream size. So "Apple's value with Apple's bytes" had never flown.
- **r94**, Apple's offset plus Apple's block, one factor: for the first time the VDM cursor and the PM moved, and
  the PM served pages. The tiling engine then wrote the tail pointer cache (TPC) and faulted, because an
  earlier write-canary diagnostic of ours had unmapped the TPC page. [V]
- **r95**, the same with the TPC page mapped: the first natural TA completion. Stamp 1, `PM_saved=1`,
  consumer = producer, a type-1 completion event. [V]

Caveats:
- No document proves the mechanism. Whether the hardware *executes* that program or only latches its address is
  unknown.
- Completion was not deterministic: 2 of 3 cold boots, at 0.1 to 12 s.
- The runs that completed also kept other settings (policy on, a self-draining attach), which were present
  but not proven necessary.
- The first TA that completed carried no application draw, only the driver's end-of-stream strip. The app
  draw came in r97.

The A10 side (OrchardLinux) reported four causes that had each stalled their TA. One of them was "`R0+0x470` is
a PDS program pointer". Our W-record census confirmed that one independently on the A9. On the A9, each of the
others was either refuted, already matched ours, or (the free list above 2^38) changed nothing.

**What we tried first, and why each one wasn't it** (so your agent doesn't retry them):

| Candidate | What it turned out to be | Moved the stall? |
|---|---|---|
| The firmware's TA wait | Waits on `TA_FINISHED`; skipping it gives a fake completion | no |
| Stale VDM index state on warm boots | A real warm-boot fault: set `INDEX_LIST0.start_present` and `INDEX_LIST5.start_index = 0` | fixed the warm fault, not the stall |
| TE terminate and region headers | The TE must write headers, terminate the lists and invalidate the TPC; our RT scalars matched Mesa | no |
| "The firmware overwrites `pm+0x18`" | A misreading: the word is the high half of our own 64-bit VA ([38](docs/gpu/experiments/38-pm-state-review.md)) | no |
| Fabric bridges, power mode, reset | A full replay of Apple's PMGR bridge state; `R1+0x10 \|= 4` was a misdecode | no |
| `meta+0x6c8` power policy | The stall reproduced with the policy on | no |
| Our stream edit zeroed the vertex stride | A real bug: every triangle was zero-area | no |
| TE1 lane / "Cat Base" fault at VA 0 | An artefact of the *forced* finish; a natural TA installs the lanes itself | no |
| `W+0x464` as "kick flags" | **Corrected**: it enables a saved-context *restore* and must be 0 | changed the VDM path, never completion |
| `STATE_STREAM_OUT1` packing | A real G5P vs modern-Mesa difference (enable bit 14, sync bit 11), in a diagnostic path | no |
| A late TA doorbell | It fired once | no |
| VDM→PPP back-pressure, "consumer gate", PPP credits | It measured the **symptom**: a finite output buffer that never drained. The model fitted to it was later falsified, and no credit register exists | quantified it |
| Parameter-manager free list above 2^38 (reported for A10) | Moving it below 2^38 left the stall unchanged | no |
| "PM clients never set up" (our r83 ranking, ~35 %) | Superseded by `W+0x88` | — |
| **`W+0x88` → `R0+0x470`** | **A PDS code-heap offset; Apple's offset plus Apple's bytes** | **yes** |

**How we knew, in general.** Each of these methods closed at least one row:
- a firmware replay/emulator of the TA start and finish routines;
- ~2 µs flight sampling of the GPU's own status registers;
- one factor per cold boot;
- iOS-side read-only captures of Apple's records (step 9);
- adversary reviews of each candidate before flying it;
- public PowerVR sources (Mesa pvr, the Linux `pvr_rogue_cr_defs.h`, DDK headers) to name registers;
- the cross-project report from the A10 side.

**What went wrong around the success.** About 0.8 s after r95's TA completed, the SoC froze in our export-time
register read-back (one Fender read, then ~47 `R0` reads after the firmware had gone idle). This is the leading
candidate, not a proof. The fix became a standing rule: **never access GPU registers after a job retires**. r96's
first "timeout" was a real completion at 12.006 s, just past the 12 s budget.

**Elsewhere?** probably: the `R0+0x470` program contract. The A10's pre-fix stall (VDM past the stream, no
region/PM/event) matched our plateau, and A9/A10 captures agree on the program's shape. The free-list 2^38 rule
was seen on the A10 and not reproduced on the A9. The INDEX_LIST and `W+0x464` lessons are generic Rogue. [I]

**Read:**
- [23](docs/gpu/experiments/23-ta-stall.md), [24](docs/gpu/experiments/24-ta-hardware.md),
  [33](docs/gpu/experiments/33-ta-finished.md), [34](docs/gpu/experiments/34-ta-end-path.md);
- [83-powervr-ta-contract](docs/gpu/experiments/83-powervr-ta-contract.md),
  [83-ta-launch-root-cause](docs/gpu/experiments/83-ta-launch-root-cause.md) (its ranking was later superseded);
- [85](docs/gpu/experiments/85-ppp-backpressure-re.md), [87](docs/gpu/experiments/87-bridge9-consumer-gate-re.md);
- [91](docs/gpu/experiments/91-build-report.md) (how our layers broke `W+0x88`);
- [r95b](docs/gpu/experiments/r95b-natural-ta-output-analysis.md) (what a natural TA writes);
- [r95-post-ta-freeze](docs/gpu/experiments/r95-post-ta-freeze-analysis.md).

The W-record census, the consumer-gate model and the ranking that led to r94 live in dense firmware-trace docs
we did not publish (r90, r92, 86, 83-apple-ta-launch-exact). Their conclusions are stated above.

<a id="step-9"></a>
## 9. Apple's PM state, captured from iOS at TA kick

**What was captured** (2026-10-24, an iOS-side read-only probe, on two working Metal jobs: one triangle at 64×64,
and 1 M triangles at 1536×2048):
- the TA work record W, then the 3D work record;
- the parameter-manager (PM) control block, the selected PM record and the channel header;
- the free list, the page list and the aux pages, at TA kick and after retirement.

One early run crashed iOS by reading a freed PM buffer. Gating the reads on liveness fixed that.

**What was learned** [P]:
- Apple's PM state is three allocations: a shared control, a record array, and a page list. Ours merged two.
- The TA start reads only three qwords of the selected record.
- Compared live, **every field the firmware consumes matched ours in form**. The control block is not on the
  kick path.
- Our earlier "the firmware writes `pm+0x18`" was a misreading.

**Was it decisive?** No. The PM captures closed the family of "our PM inputs are wrong" hypotheses. The decisive
Apple-side evidence came from the same campaign, but from other objects:
- the **TA-record census**, showing `W+0x88` following the code offset;
- the **userspace code-heap pages**, with the low block our fixture had zeroed.

One of our docs had the `W+0x88` word on 2026-10-24 and read it as a stream end. **Lesson:** when you diff
records against the working OS, classify every differing word, and don't let a plausible name stand in for a
census.

**Elsewhere?** probably: the record shapes belong to the firmware and kext, but the method ("capture the working
OS's records at kick and diff by field class") transfers. [I]

**Read:** [38](docs/gpu/experiments/38-pm-state-review.md). The live diff (ds-r40) is unpublished.

<a id="step-10"></a>
## 10. The first TA+3D render, and the first Mesa triangle

**What's needed** [V]:
- After the natural TA completes, publish the 3D **once, RAM-only, with no register access**:
  - the record, then the work-control word, then the producer last (the TA publish order);
  - the 3D is consumed without a doorbell;
  - its dependency is on the TA's stamp.
- The 3D work record already matched Apple's for every word the firmware consumes. [P]
- Our typed submit UAPI carries the `W+0x88` program reference explicitly (`ta_program_va`/`_size`), and the
  kernel copies it into the record unmodified.

**Results** [V]:
- **r96, 2026-10-30:** the first natural TA→3D render. A 64×64 target was fully cleared, 4096/4096 pixels, and
  shown on the panel. This is the clear-only class: it proves the fragment, PBE and end-of-tile path.
- **r97, 2026-10-30/31:** we linked the app's draw back in by editing 3 VDM dwords and raised the TA budget to
  20 s. On a cold boot it was **triangle-exact**: 1152 red pixels inside the triangle, 2944 blue outside, 4096/4096
  matching the oracle, with TA 7.07 s and 3D 3.88 s.
- **First userspace submit through the typed UAPI:** match.
- **Mesa102, 2026-10-31:** EGL → Zink → our Vulkan driver → the typed submit, **10/10 distinct frames matching**.
  The oracle accepted either colour within ¾ px of an edge. Its blocker was in Mesa: the driver's wait cap
  had to exceed the kernel's job bound.
- **2026-11-02:** the vertex shader's unified store is now sized from the program, as Apple does. The hard-coded 4
  had left registers r8 and up reading zero. vkcube matches a CPU reference, and **weston-simple-egl draws**
  ([HARD-PROBLEMS Z6](HARD-PROBLEMS.md#z6)).

**What went wrong.** Completion latency was bimodal: under 1 s, or 12–33 s. The cause was proven on hardware
later: the firmware polls its own shared pages and doesn't see host updates until the SLC line is evicted. An
interim read of those pages while a phase is in flight gives a median of 0.07 s from key press to frame. The
Apple-way fix (the full pstate table and policy words) was still open in [STATUS](docs/gpu/STATUS.md) (2026-11-06).
The later power work is in [HARD-PROBLEMS P1–P3](HARD-PROBLEMS.md#p1).

**How we knew.** Sealed raw captures were compared against a pinned oracle, and the kernel's row had to agree with
the reader's. We took RAM-only digests of every object before and after the 3D publish.

**Elsewhere?** probably: the 3D record and dispatch are firmware-specific. The unified-store sizing rule is for
the G5P USC, and the A10's G9P differs. [I]

**Read:** [96-natural-3d-brief](docs/gpu/experiments/96-natural-3d-brief.md),
[r96-device-result](docs/gpu/experiments/r96-device-result.md), [97-triangle-brief](docs/gpu/experiments/97-triangle-brief.md),
[97-cold-authoritative-result](docs/gpu/experiments/97-cold-authoritative-result.md),
[a9-first-pixels-real-submit](docs/gpu/experiments/a9-first-pixels-real-submit.md), [STATUS](docs/gpu/STATUS.md).

---

## Names worth searching for in your own kernelcache and firmware

These are our Ghidra names and addresses for the A9 iOS 16.7.10 build. Search your own kernelcache for the class
names and strings; the addresses won't match.

- **Classes and strings:**
  - `AGXMetaFender`, `AGXMetaFirmware`, `AGXSharedGartTableBackingG3ThruG9`, `AGXParameterManagementMeta`,
    `AGXFirmware`;
  - the kext table `AGXPMContextNames` (`Firmware`, `PM_TE0`, `PM_VCE0`, `PM_ALIST0`, `PM_TE1`, …);
  - the hardware block name table (`VDMM`, `IPF`, `ISP`, `TPF`, `USCS`, `PPP_…`, `VCE`, `FBCDC`);
  - the string `META FW started!` inside the firmware LDR;
  - the kext's `!!! Unimplemented` message.
- **Kext functions:**

  | Area | Functions |
  |---|---|
  | power | `AGXG5P_mapPowerAndStartFender` `fffffff006c93a9c`, `readChipInfo` `fffffff006ca644c` |
  | boot | `programResetStream` `fffffff006c9feb4`, `bootFirmwareAndWait` `fffffff006c9f954`, `prepareHardwareForBoot` `fffffff006c9fc10` |
  | loader | `layoutAndLoadLDR` `fffffff006c9f1bc` |
  | submit and IRQ | `submitDeviceControl` `fffffff006ca05d4`, `handleInterrupt` `fffffff006c98ab4` |
  | register access | `isGPURegisterAccessible` `fffffff006ca10ec` |
  | MMU faults | fault decoder `fffffff006ca5c14` |
  | TA record | importer `fffffff006cba8a0` (plain copy of the userspace word that becomes `W+0x88`) |

- **Firmware (META):**

  | Routine | PC |
  |---|---|
  | scheduler | `0x8000a120` |
  | TA start (`start23`) | `0x8000672c`, with its last store `R0+0x470 ← W+0x88` at `0x80007a00` |
  | the TA_FINISHED route | `0x8000a2bc` |
  | policy readiness gate | `0x1000d044` |
  | boot copy of the META init words | `0x10003ca4` |
- **Public register names** (Linux `pvr_rogue_cr_defs.h`, Mesa pvr):
  - `EVENT_STATUS` (bit 5 `TA_FINISHED`, bit 6 `TA_TERMINATE`);
  - `JONES_IDLE` `0x8328`;
  - VDM context store status `0x430`, VDM cursor `0x410`;
  - MMU fault status `0xe150`;
  - `INDEX_LIST0/5`;
  - the TE block at `0xc00`–`0xc98`.

The [tools](tools/README.md) extract the AGX kexts and the firmware from a kernelcache, so you can do the same on
your chip.
