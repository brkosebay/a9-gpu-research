# R19 — context1 catalogue-base repair and complete job page walks

Head `3ab2d63e58da7608ceaa2e9fa4fb6b50b188749c` on `a9/gpu`.
Apply patch0040 on parent `9e54857fd20cd6eab95c91ca58a881f60effbca2`.
The implementation agent made no device calls or workspace commits.

## Fault decode and scope

The round11 same-image decoder gives `e150=010005c0:00100139`:
valid1, type0 **Page Invalid**, read1, level3 **Cat Base**, requester4
**CDM**, sideband0, context1, address `0x10005c000` (16-byte precision).
The requester table entry is `6ff5ed8+4*16`: pointer `594613f` (`CDM`),
classification8. `e158=0` has no valid META-bank fault. This is a context1
catalogue-base failure, before the catalogue/directory/table walk, rather
than evidence that the stream's leaf PTE is invalid.

Field positions and name/type tables are from iOS `6ca5c14` as documented in
firmware RE rounds11/12. The level3 name also
matches IMG's [public debug decoder](https://android.googlesource.com/kernel/mediatek/+/android-mtk-3.18/drivers/staging/imgtec/rogue/rgxdebug.c).

The r18c log records the new
fault at line422, then **firmware event4/word1=200 at424..430**. Event130=0
therefore does not establish absence of the MMU event. The recovered callback
ACK at `80009ff0..8000a000` followed by recovery dispatch is consistent with
this observation; host sampling did not capture the ACK instruction itself.

The reset-release PBE fault and failed1720 maintenance are absent in this
run. They stay controlled by the VA0 sink and cache3 preamble. No new ACK,
event-mask change or fake completion is part of r19.

## Software mappings and hardware context are separate

The existing constructor installs catalogue[4] for data and catalogue[12]
for code, directory[0] in both, and these leaves:

- B=`300000000`: ti0; helper `300014000`: ti5; USC `300028000`: ti10;
  user PDS `300030000`: ti12.
- Output `100000200`: ti0+200; scratch `100044000`: ti17;
  `100048000`: ti18; scratch tail `10004a020`: ti18+2020;
  arguments `10004a068`: ti18+2068; CDM `10005c000`: ti23.
- Packed PDS offsets420/430/400/740 are **byte offsets from B**, not
  values to multiply by16. They are all in code page0. User USC22c0,
  PDS2400/2480 and argument data30040 are walked separately too.

Recovered entry encoders remain unchanged: catalogue=`PA>>8|1`,
directory=`PA|3` (16KiB leaf size), PTE=`PA|d` for current code/data0c.
PTE valid bit0 is1, read-only bit1 is0, CC bit2 and SLC-bypass bit3 are1,
META-protect bit62 is0. Firmware mappings keep their recovered protection.
There is no evidence in this fault that changing code permissions fixes it.
The offline test executes the actual prepare constructor and verifies all
8 complete paths, offsets, neighboring holes and fixture hashes.

DC3 publication remains `{3,1,0,0,0}` with the unshifted catalogue PA in
host slot86/index1, aliased to GPU slot89/control+1048. Tag/version stays0
in host84/GPU87/control+1044. The context remains W+8=1. No context0
substitution or invented nonzero generation is used.

Firmware `1000218c..10002218` reads the indexed catalogue and calls
`10019b84`, which writes e140=context and e148=PA>>12, then invokes the
context-maintenance helper. A consumed DC3 is insufficient proof of the
installed base: r18c had no banked context1 readback. Whether the missing
base comes from a stale META-visible array, a firmware control-flow issue,
or another cause is still unresolved. The r19 repair is a gated host
experiment at a quiescent pre-submit boundary, not a complete production
firmware/context synchronization protocol.

## R19 behavior

`mmu_setup_variant` now defaults to1 in the kernel. R19 wrappers also default
the VA0 sink on. Explicit0 remains available for historical comparisons.
The current constructor copies the boot catalogue including the sink into
the compute catalogue; this corrects r18c's documentation claim that only
the firmware mapping is inherited. The sink backing remains separate from
all job data and neither context's sink is rewritten by the CBASE repair.

`compute_mmu_variant` is latched during prepare, accepts0..3, and defaults0:

- **0:** observe the installed bases, retain the firmware-only attachment.
- **1:** install context1's retained catalogue base, then invalidate PT/PD/PC.
- **2:** install the base only.
- **3:** invalidate only, retain the firmware-installed base.

Before the first CL publication, all variants require attached/context-complete,
released, active GPC, empty rings and no latched failure. They read both
hardware context bases using iOS `6ca5cd8..6ca5d04`'s SLC-clock-ON requirement,
and restore the exact original clock and selector. Thus variant0 adds a
transient clock/selector observation sequence, not a literally read-only
baseline. MMIO breadcrumbs are retained before each stage.

Variants1/2 issue e140=1 then e148=`compute_catalogue_dma>>12`, with coherent
RAM publication preceding it. Readback must equal that exact encoded base;
a mismatch returns-EIO and prevents CL publication. Context0 is never rebound.
Variants1/3 first reject an outstanding e138 request, issue **e138=f**
(context1<<3 plus PT/PD/PC bits1/2/4), and poll the three invalidate bits clear
for100ms. The request targets context1, not all contexts. Firmware80009030
supplies the context<<3 encoding; the public IMG MMU definitions identify
the three invalidate levels. A busy register or timeout leaves CL hidden.
The operation is never retried after an attempted failure. Existing
wrapper park, one-shot failure latch, event preservation and DMA retention
remain in effect. Repeated successful fixed work reuses the installed VM.

Prepare always dumps19 named job VAs through **both** retained catalogues:
catalogue DMA/index/entry, directory DMA/index/entry, leaf DMA/index/PTE,
valid/read-only/cache/protection bits and translated PA+offset. A missing or
foreign parent prints the stopping level and is never dereferenced as a PA.
An invalid target leaf is identified explicitly. Dumps go to diagnostic_blob;
compact CBASE/invalidate records also appear in mmu_history and dmesg.
CPU walks do not establish TLB contents or the installed base.

## Ranked device commands

Each command requires its own freshly booted integrated r19 kernel. Only
the orchestrator runs these. `build/kernel-gpu` is the GPU-only verification
build, not a replacement for the integrated NVMe boot kernel.

*(Device/host command block omitted; it targets the private workspace.)*

Defaults are sink1, ACK0, policy7, full fixture1, dependency1, profile0,
code-PTE0 and cache3. `GPU_COMPUTE_MMU` is deliberately explicit above.
Observer revision190 is mandatory; older integrated kernels fail before
parameter writes. The default explicit fault-walk VA is `0x10005c000`;
`GPU_MMU_FAULT_VA=0` inspects VA0 and an empty value disables that additional
stage walk. Prepare's full job walks always remain enabled. The r19 scripts
use a separate remote directory and log names including the MMU selector;
all earlier versioned scripts remain unchanged.

Require the `MMU CBASE before` comparison first. A zero/incorrect context1
base followed by `after ... match=1` discriminates the proposed fix. If it
was already correct, the combined variant also tests missing invalidation;
variants2/3 separate those effects. Check `request=0000000f ... result=0`,
continued clean release, and any new e150 address/context/level. A changed
fault level is progress through translation, not shader completion.

Success still requires firmware stamp1, output12345678, all63 other sentinels
intact, no firmware fault and verified park. Neither matching CBASE readback
nor a completed invalidate alone establishes GPU acceleration.

## Offline validation

Run `scripts/gpu/check-round19.sh`. It executes production prepare, page-walk,
CBASE and submit functions with ASan/UBSan, real fixture SHA256 verification,
all4 variants for both fixtures, all13 DMA-allocation failures, each broken
hierarchy level, unchanged context0, restored bank/clock state, ignored base
writes, busy/timeout invalidate, inactive/stopped/unattached gates and rejection
of resubmission after an MMU failure. It verifies CL producer/ring/stamp stay
unpublished on failure. The new wrapper has27 fake-sysfs cases, plus the49-case
r19 experiment runner and inherited r18c sink/release/cache/policy/diagnostic
and runner suites. Both kernel frontends build with W=1; strict checkpatch
and diff checks must pass.

Logs: `build/gpu/round19-targeted.log`, `build/gpu/round19-build.log`.

Validation completed: targeted script exits0; both W=1 frontends and all
offline suites pass. The exported patch also passes strict checkpatch with
zero errors/warnings/checks. Full Image.gz +104 DTBs exits0; build/kernel-gpu
COMMIT matches the head above and DIRTY/kernel worktree status are empty.
No numerical GPU completion is claimed before the orchestrator runs r19.
