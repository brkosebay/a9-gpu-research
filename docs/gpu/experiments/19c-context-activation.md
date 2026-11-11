# R19c — selected user slot, cache0/preinstall, and boot-VM CDM

Parent: `38c2d02dd8de680806205ee528bae98ea53ada1d` (`a9/gpu`).
Head: `fa850de794e6dc17f5cb723d6bffe4e6591a4f85` (`a9/gpu`).
Apply patch0043
after the parent.
`build/kernel-gpu/` contains the matching `Image.gz` and105 DTBs; COMMIT
matches this head, DIRTY is empty, and debug info is disabled.
No device access or workspace commit by the implementation agent.

This implements the three diagnostic comparisons from
firmware RE Round 14. Slot7 is the default because
the reference context allocator starts its user pool there; its hardware
significance remains unproved. The fixture, stream VA, table encoding and
completion criteria remain those of r19b.

`compute_context_slot` accepts7 (default) or1 (legacy comparison), latched at
map. That slot reaches the shared unshifted PA array, host generation array,
DC3, W+8, start32+14, finish33+0c, banked CBASE selection, MMU invalidation
and optional SLC operation. Retained repeats rebuild W/SKU with the same slot;
no hardware slot is inferred from the DRM userspace context handle.
For7, all-level MMU invalidation is `e138=3f` and optional SLC is `e230=81f`.
The old `compute_slc_context1` parameter name is retained for compatibility,
but its operation now follows the selected slot.

Aligned `readl(f078)` and `readl(136c)` are captured in the hardware dump and
in short MMU-history records at pre-producer and returned failure, before
bulk RAM diagnostics. The latter records also decode e150's context,
requester, level, type, read bit and VA, retaining the split raw halves.
Pre-producer values precede firmware start32 and need not yet select the
new slot. Fault-time7 should give CDM=7, CDM_copies=0707 and, if the same
fault follows the slot, `e150=010005c0:00700139`. These samples never write
requester selectors, ACK a fault or claim a numeric completion.

`GPU_COMPUTE_CACHE=0` survives both runner layers unchanged. Combining it
with `GPU_MMU_PREINSTALL=1 GPU_COMPUTE_MMU=0` retains firmware boot binding
and DC3 while omitting host11f00/688/1720, CBASE writes and invalidation
after attach. The observer still temporarily selects CBASE banks and
restores the exact original clock/selector. A preinstalled CBASE mismatch
returns-EIO before CL publication; it is never repaired in MMU0 mode.

`compute_boot_vm` / `GPU_COMPUTE_BOOT_VM=1` is a separate, default-off gate.
It forces effective slot0 and pre-release fixture construction, independent
of the requested user slot. Before release, PC[4] and PC[12] are installed
into the existing boot catalogue; nonzero entries there are refused. The
VA0 sink and boot firmware entries are preserved. The catalogue is borrowed
from the boot allocation, with no separate free/replacement. Optional table
aliases borrow that same page and do not add the user-catalogue cookie.
Slot0 retains its existing PA and host tag, skips DC3 entirely and marks
only attachment bookkeeping complete. It requires cache0/MMU0, baseline
profile/code PTE, SLC0 and generation changes0. Changing these knobs after
preinstall does not change the latched fixture. The staging prepare-recovery
path explicitly refuses boot VM/preinstalled allocations so it cannot zero
the live firmware catalogue. Normal completed-job retirement and numerical
failure abandonment still apply; timeout/MMU/event faults require reboot.

All frontend/boot/compute/render/repeat/recovery activation gates remain
explicit. This is the fixed-fixture ABI, with no general COMPUTE or live
user-VM capability added. R19c runners require observer revision193 and use
`/tmp/g5p-round19c`; use them instead of the revision192 r19b wrappers.

## Ranked orchestrator commands

Each line requires a **fresh integrated r19c boot**, using the stock DTB.
Defaults hold policy7, sink1, ACK0, full fixture, dependency1, profile0,
code-PTE0, after-cache1, SLC0, generations0, table-clean0 and readback0.
Run in an environment without unrelated GPU overrides.

*(Device/host command block omitted; it targets the private workspace.)*

The first holds the r19b v1 maintenance settings while changing the slot.
The second removes the post-attach boot-maintenance subset using the
firmware-preinstalled user slot. The third compares the working boot slot0
with that second mode. For a same-build legacy control, use
`GPU_COMPUTE_SLOT=1 scripts/gpu/run-compute-host-r19c.sh` on another fresh boot.

Save each command's runner, dmesg, MMU-history, diagnostic-status and blob
files under the printed `build/gpu/exp12-r19c-*` prefix. Effective slot0 is
included in the filename for the boot-VM mode. Compare failure-time selector
copies, fault context/VA/level, CBASE match and channel/stamp progression.
A context0 repeat of the fault would be `010005c0:00000139`; success requires
the firmware stamp, output12345678 and63 untouched sentinels, rather than
consumed DC3 or matching CBASE alone.

For the r19b retained render-node workflow, repeat the successful variant
on a fresh boot with UAPI/repeat/recovery enabled. Example for the first mode:

*(Device/host command block omitted; it targets the private workspace.)*

Only after numerical success, continue on that same boot:

*(Device/host command block omitted; it targets the private workspace.)*

`GPU_COMPUTE_SERVER=1 GPU_COMPUTE_UAPI=1 GPU_COMPUTE_LIMIT=1048576` also keeps
the prior no-submit server mode. It warms boot/control/IRQ and enables
render/repeat; it does not establish numerical success. A returned MMU fault
is still contained, never reset or replayed by recovery.

## Offline validation

Run `scripts/gpu/check-round19c.sh`, then `scripts/build-kernel.sh --tree gpu`.
The offline runner invokes no SSH/device commands: host forwarding uses a
fake SSH executable and fake builder; device flow tests use fake sysfs.
Production-helper ASan/UBSan tests cover both user slots, PA/tag/DC3/packet
agreement, generations, CBASE/clock restoration, MMU/SLC masks, repeats,
numerical-failure recovery, preinstalled mismatch suppression, boot-VM map
preservation/no-rebind, and both independent/borrowed table-readback pages.
The inherited cache-observer test expects the six new register reads.
The check also runs W=1, stock/coherent DTB comparison, UAPI client compile,
checkpatch and the r18c regression suites. Logs remain in `build/gpu/`.

Validation passed:56 fake-sysfs wrapper cases,8 fake-SSH host cases,55 r19c
flow cases, the complete sanitizer/W=1/DTB/client/checkpatch suite and r18c
regressions. A final prepare-after-attach refusal was also checked under
ASan/UBSan and W=1. The exported patch passes strict checkpatch with zero
errors/warnings and reverse-apply verification against HEAD. See
`build/gpu/check-round19c.log`, `check-r19c-final.log`,
`test-mmu-r19c.log` and `build-round19c.log`.
