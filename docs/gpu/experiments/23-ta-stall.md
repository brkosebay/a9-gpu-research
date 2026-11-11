# R23 — TA reaches start23, but its completion chain does not retire

2026-10-23. Kernel **`385568315e6f2fc2e7a606a43e51eebc609f6ac2`** on
`a9/gpu`, parent r22 `09f881cbb09c8535283d96d114cb0662f637120a`.
Patch 0049
applies after0048. Offline investigation and default-off diagnostics. No device access,
integration-tree edits, workspace commit or push. The exact next commands
and decision tree are in `23-device-tests.md` (not published).

**The terminal cause is not proved by r22's capture.** The failure is localized
past notification, channel scanning, slot selection, PM initialization and
most of start23. It is before the normal TA finish/retirement chain completes.
A missing host completion predicate alone cannot explain the observed state.
The next boot captures the missing interpreter records and tests a concrete
scalar substitution in r22. No hardware fix or rendered frame is claimed.

## Evidence and reconstruction

Inputs:

- r22 diagnostic blob,
  SHA256 `20a86d0b6315…`,
  and its same-prefix `mmu_history`, `render_status`, `result`, boot dmesg.
- Late live capture,
  supplied by the orchestrator after failure. Its cached blob is byte-identical
  to r22's. There is one AIC65710 `g5p-meta` IRQ total, accounted for by the
  earlier explicit IRQ test, and no new GPU dmesg after the failed command.
- Firmware round16, particularly its source-backed
  TA start/finish, queues, PM, HWRT, internal waits and retirement recipes;
  r21 design, r22, and
  userspace r16.

`python3 -B scripts/gpu/analyze-render-r23.py` reconstructs the entire root/
shared sparse baseline and subsequent deltas. **Every old value matches**;
no missing delta is silently replaced with a guessed runtime value. The
explicit PM/CH/W/SKU dumps independently provide the following observations:

| Observation | Before launch | TA consumed, 1s, 3s, failure |
|---|---|---|
|TA global notification consumer/producer|0/0|1/1|
|TA control +0/+10/+20/+30/+40|0/0/0/0/0|0/0/2/2/2|
|TA finish / retirement stamp|0/0|0/0|
|G724/G728/G72c/G730|0/0/0/0|0/1/0/c0254000|
|R0+136c; f078|0;0|0808;8|
|R0+430|1|11|
|PM control+4; count/last|0;400/3ff|8;400/3ff|
|PM S serial; runtime words before a0|0; all zero|0; all zero|
|Fault banks e150/e158; event130|zero|zero|

Offsets and values are hex unless stated otherwise. There are 1024 decimal
4KiB free-page entries and 4MiB physical backing. **Stable host count/last
does not prove hardware allocated no pages**: host-visible state need not
reflect each live allocation before PM save.

The TA G+730 value is **CH**, `c0254000`, as start23's actual store shows;
it is not the user-slot number. The earlier round6 prose describing this
word as `ctx` is inaccurate. The byte selectors and W/SKU operands carry8.

`scripts/gpu/firmware-re/round23-evidence.py` checks these five checkpoints,
the identical late dump, IRQ count, captured scalar and nine raw MINIM
instruction anchors. Output is `build/gpu/round23/evidence.json`. It verifies
observations and source bytes, not the proposed cause.

## What this localizes

1. **Queue/kick encoding worked far enough to execute TA start23.** TA's
   `[tag6,tag0]` pointer scan reaches2. The uploaded SKU has23, timestamp,
   801, timestamp,24 and terminal17 at the round16 offsets. MTS10 and the
   type0 notification are the TA-specific recovered values, distinct from
   compute's type2/MTS12. A consumed global entry alone would be weaker
   evidence; here PM/requester/runtime changes provide the additional proof.

2. **Slot8 is selected by the TA-specific source path.** `10017d6c` masks
   the user slot to a byte and writes f078/136c/136d. The observed values
   are exactly8/0808, after both DC3s, generation matches, CBASE matches and
   successful all-level invalidation. No ordinary TA-only restriction to
   slot7 is established. PM requester triples1/2/3 and4/5/6 retain
   f088=30102/f090=60405. They are firmware-managed translation state;
   rebinding them to the user PC is not a supported experiment.

3. **The fresh PM load path has run.** R0+240=01000000,
   +248=01010080 and+2d8=01000080 equal S.a8/S.b0/S.a0 low halves.
   PM load controls290 and258 are clear at every post-consumed snapshot.
   Firmware reaches the G728=1/G724=0/G730=CH stores at
   `800067dc/67e4/67f4`, after its PM setup calls. It then calls the
   hardware launch helper: with the unchanged zero mode operand it uses
   `80009120`, **R0+400=1**, not the alternate software event20 write
   at80009104. r22 did not sample400, so the RAM markers prove the reached
   boundary, not direct observation of the final kick store.

4. **Finish/retirement genuinely has not completed.** G728 remains active,
   ctl+10/+0 never advance, both stamp words remain zero and S lacks PM
   save output. Relaxing the host's PM_saved, selector or channel checks
   cannot make this a completed job. R0+430.bit0 is already set and bit1
   is clear, but that register is the context-store status, not a complete
   TA retirement indication or a current interpreter PC.

5. **No pending host ACK has been observed.** There is no page-request,
   recovery, channel-error or completion entry/IRQ in these captures. An
   invented grow/partial-render ACK is unjustified. This does **not** prove
   that internal hardware event20 never occurred: internal event20 and the
   later host IRQ174/type1 retirement event are different stages, and
   firmware can acknowledge a hardware event before a host sample.

3D is never submitted in the after-TA run. Thus an unsatisfied tag4 in a
submitted 3D job is not the reason this TA stops. The RT/PM constructors,
4MiB budget and full VDM inputs pass their existing byte/oracle checks;
that is construction evidence, not hardware qualification of those objects.

## Missing evidence and ranked causes

The live GbP+110 pointer is **10016510**. Four2e8-byte interpreter records
there fit inside the mapped10000000..10017fff data region, but r22 snapshots
only image+179c0..17b9f globals, not image+1a510 onward. These records hold
pending masks, active slots and saved microsequence cursors. r22 therefore
cannot distinguish wait801 from a synchronous later poll using a saved PC.
GbP+70 points to **8000a2bc**, private META local RAM. Reading the firmware
upload image at a numerically related offset would not read that live word.
The new observer explicitly reports it unavailable and never uses that trick.

The two highest-value next discriminators are:

- **Unproved scalar substitution / full VDM execution.** The measured
  whole userspace record+40 contains **100**, while r22's importer overwrites
  it with the manifest's VDM byte count288. The retained userspace producer
  **207d6a30c, beginRenderPass** writes `whole_record[8]` from
  `*(u64 *)(RenderContext[0xa5] + 0x38)`, a separate object field; it is not
  populated by substituting the exported VDM span length. Its full decompile
  is hash-recorded by the r23 evidence script.
  `6cba8a0` imports that qword as
  D.ab8; `6ca9710` masks it with~f into TA.W88, producing **280**;
  `80007a00` uploads it to **R0+470**. This is an actual difference from
  the captured record. Its precise hardware meaning is unresolved, so
  calling it a proven byte-count field was not warranted. R23 tests100
  independently of stream content; it does not silently change the fixture
  or declare100 universally correct.
- **Common TA/PM completion or geometry execution problem.** A plain
  captured VDM terminate at the first word tests the same TA PM/HWRT,
  context termination helpers, event wait and retirement chain with no
  PPP/triangle/rectangle execution. Success sharply narrows the failure
  to full-stream state, helpers, barriers or workload-dependent PM behavior.
  Failure at the same saved boundary keeps PM/TA clocks/internal-event
  routing in scope. It does not by itself identify an exact missing clock
  write. Compute's observed pass establishes its path, not every geometry
  unit; no guessed power/clock register mutation is added.

A timestamp stall is separately testable with the existing equal-length
zero-mask-wait substitution, **only if the captured cursor supports that
branch**. The genuine801 wait, finish24, backlinks and both stamps remain.
PM pressure/growth remains an open secondary cause; there is no observed
OOM protocol to implement from this run. Slot/CBASE/kick selection and an
overstrict host completion check are demoted by positive evidence above.

## Implementation and containment

Kernel changes are confined to `render-fixed.inc`, `render-probe-r23.h` and
`render-observe-r23.inc`. New `render_probe_variant=0` and
`render_observe=false` are root-only, default off and latched once at prepare.
The existing fixed-render gate must still precede firmware map. Status ABI
revision is23; the r22 fixture binary and its SHA256 are unchanged.

| Probe | VDM | W88 / R0+470 input | Allowed stages |
|---|---|---|---|
|0|Full original r22|280|attach, ta, pair|
|1|First word replaced by c0000000|280|attach, ta|
|2|Full original r22|captured100|attach, ta, pair|
|3|First word replaced by c0000000|captured100|attach, ta|

Only the first VDM dword changes in probes1/3; the remainder stays exact.
Its immutable-input digest is updated to that explicitly selected input.
Pair submission is rejected before any engine publication for those probes.
TA-only requires targeta5, full retirement and PM save, and never reports
numerical/frame success. Probe2 can qualify a frame only through all original
TA+3D retirement, immutable input, guard and4096-pixel checks.

`render_observe=1` adds at every checkpoint:

- All four interpreter records from **owned mapped RAM**, with bounded,
  alignment/overflow-checked reads; saved cursor/TA-or-3D SKU deltas and
  pending masks. A saved cursor is not labelled as a live META PC.
- Explicit five-word CCB watermarks, global TA/3D scheduling objects,
  complete TQ/dependency areas, event-ring indices and uploaded VDM.
- Read-only raw TA start/base/context-store, event, PM, requester and
  clock registers, with a register breadcrumb before every new MMIO read.
  Existing active-wrapper/release gates apply. No selector write or ACK.
- At terminal success/failure: complete undecoded36000 firmware storage,
  b000 stamp storage and2c00 event storage; all five PM auxiliary pages,
  the active RT slice/secondary extent, and nonzero-byte occupancy of all
  256 physical PM pages. Firmware storage may contain logs if firmware
  produced them; no decoded trace format or trace enable is invented.

The old full root/shared sparse snapshot remains. Terminal dumps handle
noncontiguous CPU DMA pages and keep the existing4MiB append-only blob.
Check `blob_dropped`/`history_dropped` and `mmu_reading` after each attempt.
Source-mapped firmware data is distinct from8000 private core RAM throughout.
The blocked FWTRACE candidate is not deployed.

All old publication ordering, real waits/finish/retirement predicates and
quarantine remain. No retry, park, reset, unbind, PM growth response, fake
stamp or CPU pixel write was added. Compute r19d/r20/r21 sources, UAPI,
firmware/power defaults and the old render scaffold stay byte-identical.
Validation and the committed kernel identity are recorded in the device plan.
