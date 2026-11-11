# R24 — discriminate TA workload, PM progress and firmware event/finish stalls

2026-10-23. Based on r23 kernel `385568315e6f2fc2e7a606a43e51eebc609f6ac2`,
device integration `b7e52e2624`, workspace log commit `dda03e8`. No device
access, integration edits, workspace commit or push. Kernel identity and the
ordered owner plan are in `24-device-tests.md` (not published).

**W88=100 does not resolve this stall. TA start and some GPU-side PM memory
activity are observed; no completed TA, event-wait boundary or frame is proved.**
The new default-off observer samples the missing TA/context/cache registers,
compares direct uploads with W, and records bounded parameter-page contents.
First boot changes only the full VDM's first word to the already supported
terminate opcode, retaining the captured scalar, real waits and retirement.

## Apply the r23 decision table to the actual capture

Source prefix:
`logs/r23-pair-probe2-obs1-cache3-mmu1-ts0-after1-20261023T085837Z-`.
The diagnostic blob SHA256 is
`73306a002c43…`.
The five sparse checkpoints reconstruct without an old-value mismatch.
`blob_dropped=0`, `history_dropped=0`, `mmu_reading=0` rule out an obviously
truncated observer or an MMIO read still stuck in this capture.

This follows the r23 **no yielded TA slot / inspect runtime and MMIO** branch,
not its `SKU_delta=058, pending_mask=20` branch. All four image records have
`pending=0,current=16,active=0` even after TA starts. There is no saved TA
cursor in those records. Separately, the **uncached root TA global object**
has pointers at offsets1c/4c equal to the SKU **base**, `c0254a00`.
Those words are not a live META PC, nor an observed wait801 cursor.

Two address corrections are essential:

- Decimal3223666688 is **c0254000**, the **CH** pointer in G730, as proved by
  start23's store at800067f4. It is not c0254a00. G730=CH and the saved
  root pointers=SKU are different fields.
- **R0+408/40c = W98 =100040000**, the fixture's VDM BO.
  **R0+418/41c = W90 =100080000**, its scratch BO. The r23 device plan's
  “f060 VDM base” attribution was wrong. Same-image uploads80007a70 and
  80007a40 establish the register/operand pairs; fixture roles establish
  which address is VDM. An address still being programmed is not a fetch PC.

The five CCB words0/10/20/30/40 become **0,0,2,2,2**: the notification and
scan reached the two pointer entries; execute/read retirement did not.
Slot8 appears in f078/136c, the TA A/B registers are uploaded, PM control+4
becomes8, and G728=1/G724=0/G730=CH are stores in start23 after its PM setup
and cache-handshake helper. Thus notification, dispatch, user-slot selection
and a substantial portion of TA start worked. A host completion predicate
cannot explain both missing stamps and the unretired CCB.

**The raw terminal PM occupancy is not zero:**

| Physical16KiB page | Nonzero bytes | First offset |
|---|---:|---:|
|1|79|3000|
|2|5|0000|
|6|92|1000|

`g5p_boot_alloc_page` zeroes every page, and the retained CPU constructor
does not populate these physical PM payload pages. This is positive evidence
of GPU-side writes after construction, plausibly PM/TA parameter activity.
The old observer recorded only terminal occupancy, so the timing, writer and
payload remain unknown. It **demotes an entirely inactive GPU/PM path**;
it does not establish successful geometry, vertex-PDS/USC fetch, VDM END or
correct parameter data. Stable host count1024/last1023 and absent PM-save
outputs do not negate live hardware allocations.

## What the cursor and MMIO do, and do not, localize

G728 is set at800067dc, then the zero mode operand takes
80006808→80009120→**R0+400=1** at8000912c. There is no newly identified host
geometry kick to add. A sampled400=0 cannot prove that this transient store
never happened. The initial helper80009138 writes/polls **cb8.bit0**, then
writes **c68=1** before returning to the G728 stores. Persistent busy cb8
with G728 already1 would need a later/repeated transaction explanation;
it cannot simply be assigned to that first pre-G728 invocation.

After the launch call, start23 can also enter an instrumentation path via
80006874→8000a434→10017688 when control+170.bit0 selects it. The timestamp
packets have their own control-dependent path. A synchronous start tail,
timestamp helper, finish24 poll or cleanup can retain an older cursor.
Conversely, opcode801 yields at800066c0 by storing a pending mask and cursor.
No such **CPU-visible** yield is observed here. The four cached image records
being unchanged does not prove that the interpreter never reached801:
META-cache visibility or another saved runtime representation remains an
unresolved observation limit. R24 continues to report private8000a2bc
unavailable; it does not substitute packed upload-image bytes for live RAM.

430 changes1→11, but bit0 was already1 before launch. Same-image finish24
uses bit0 for readiness and bit1 for a branch; this is not a whole-job done
register. Do not infer finish24 ran from430 alone. Event130=0 is also not a
proof that internal20 never occurred: firmware can acknowledge it before
the host reads it. Internal20 and the later host type1/IRQ174 differ.
No new host IRQ or fault is observed, and after-TA mode never notifies3D.

The workload/retirement RAM state is stable, but not every hardware word is:
clock-status R0+8 changes from200 at TA-consumed to100300 at1s. Its exact
Apple fields are unproved. This further cautions against calling the entire
GPU frozen from the first consumed snapshot.

Ranked remaining hypotheses:

1. **Full VDM/PPP/VS/helper/barrier execution, or workload-dependent PM state.**
   Terminate-only retains common PM/TA/context helpers but avoids the original
   triangle, trailing rectangle and vertex shading. A complete empty TA
   retirement sharply separates these from a shared startup/finish issue.
2. **Internal event handling, synchronous finish/PM save/cleanup or META
   observation visibility.** No complete TA stamp chain or saved PM state
   exists. Programmed input/dirty PM pages plus43011 keep a post-kick issue
   at least as plausible as a missing host initializer.
3. **Geometry/TA island, context load/cache handshake or common PDS context
   task execution.** Compute qualifies its own path, not geometry. The raw
   clocks, reset words, cb8/c68/cd8/ce0, store/resume task words438..464, PDS/USC
   execution bases and PM requester state are the next observations. A plain
   terminate still exercises common termination/context machinery, so its
   failure would not uniquely prove a power defect.
4. **Host programming expected outside W, or a missing/incorrect PM/RT
   operand.** Positive uploads demote a wholly absent register upload;
   38 direct dword comparisons expose which operands actually reached MMIO.
   Fresh constructor and offline oracle agreement remain construction
   evidence, not hardware qualification. No new host ISP/TA write is proved.

Changing W88 alone, repeating slot/CBASE experiments, a longer frozen wait,
an invented grow ACK or relaxing completion tests has low discriminating value.
No evidence-backed Apple clock/island write was recovered in this round, so
there is no clock-force, reset, firmware-patch or PM-catalogue-rebind variant.

## Default-off, latched r24 observer

`render_hw_variant` is root-only0600, default0, read once and validated at
prepare, and retained with the job. `render_status revision=24` reports
`hw` and `hw_samples`. Existing probe/cache/MMU/timestamp selections and the
hash-pinned fixture are retained. New kernel code is `render-observe-r24.inc`
plus its calls from `render-fixed.inc`; compute/UAPI remain unchanged.

| Profile | Additional observation |
|---|---|
|0|No r24 MMIO or parameter scan; original r23 observers remain independently selectable.|
|1|Fixed TA/PM/start/context/PDS/USC register allowlist;38 direct W comparisons; raw root SKU-pointer matches; bounded PM payload samples.|
|2|Profile1 plus seven public Rogue BIF/PM status **candidates**12d0/1320/1328/1330/1338/1350/1358. Apple fields unverified; optional later discriminator.|

The [primary IMG-authored Linux header](https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/imagination/pvr_rogue_cr_defs.h)
and retained DDK header corroborate status names/offsets, not A9 clock masks
or full Apple portability. Profile1 is preferred for the first boot because
it adds source-referenced registers without the candidate status bank.

Samples occur at attachment, after cache/MMU preparation but before TA
publication, immediately after each notification, consumed/completed stages,
two early wait opportunities with20/100ms minimum thresholds,1s/3s, and
terminal retention. `ticks` records actual sampling time; scheduling and the
large inherited snapshots can delay the early opportunities. This is not a
cycle trace. Early opportunities do not run a second job or publish a producer.

Each MMIO read has a prior cached breadcrumb and uses the existing released,
not-stopped, active-wrapper gates. No MMIO selector, ACK, counter setup,
slave request, halt, clock or reset is written by the new observer. Fixed
reads can still expose a nonresponding register: the runner retains the
breadcrumb and requires another cold boot instead of retrying or killing it.

PM scans count all nonzero dwords in4MiB and save at most256 per sample,
at most32 per page, with explicit `dropped_words`. They show a prelaunch
baseline and subsequent payload writes. This truncation is separate from
append-buffer `blob_dropped`; nonzero counts are not shader-fetch counters.
Output is bounded even when every PM dword is dirty. All original real waits,
stamps, PM-save/pixel checks and terminal quarantine remain mandatory.

The r24 host runner reserves a boot marker before bootstrap and captures all
five attributes, dmesg/IRQ/boot identity even on bootstrap or stage failure.
The on-device runner rejects stale revision/epoch and terminate-only `pair`.
The offline decoder retains unavailable-vs-zero distinctions and labels
global saved pointers independently of image execution records.

## Reproduction

`scripts/gpu/firmware-re/round24-evidence.py` verifies the exact r23 log,
CH/SKU arithmetic, all five states, dirty PM pages,21 raw MINIM anchors and
88 already captured direct-upload dword comparisons. It never contacts the
device or claims a terminal cause. Output: `build/gpu/round24/evidence.json`.

`scripts/gpu/check-render-r24.sh` runs the pinned round16 ISA/RT/wait oracles,
r23/r24 evidence, inherited constructors and369 allocation-failure paths,
ASan/UBSan on actual r24 observer/retirement code, exact read allowlists and
breadcrumbs, inactive/default gates, latching, worst-case dirty-page bounds,
fake host/sysfs runner failures and decoder tests. Compute regression uses
`scripts/gpu/check-compute-r23.sh`; full build uses
`scripts/build-kernel.sh --tree gpu`. Device execution remains untested.
