# Render resource snapshot lifetime fix — 2026-11-08

Generated-by: LLM. **Host-reproduced bug fixed; attribution to the device's
Aquarium rejection awaits the r39-3.1 diagnostic flight.** No device access.

Implementation branch: `g5p-r39-6-stream-fix`, currently
`21da747f24e8a5313f6307df53e0cebe9ac5ae6a` on approved W safety
commit `90cbc11e46566c27cf13f2a45c5635647e8871d7`, itself on r39-5 `9a6e338ad86`.
Only `src/imagination/vulkan/winsys/apple_g5p/pvr_g5p_winsys.c` changed.
r39-6 is sealed at `build/gpu/r39-6/runner.tar.gz`; source/package identities
and all final host gates are recorded in adjacent `SHIPMENT.json`. Only the
PowerVR split upgrades; the packet rolls back to r39-3, since r39-4/5 were withdrawn.

## Evidence and cause

The list of render resources was built under `ws->lock`, but the lock was
released before sync setup, optional stream logging and SUBMIT_RENDER_TYPED.
An application may legally free memory that this job does not use on another
thread. Conservative read tracking can nonetheless include that allocation
in the resource list. Its final BO reference removes it from `own_bos` under
the same lock, then unmaps/closes its GEM handle. Submission of the older
snapshot fails the kernel's **GEM handle lookup**, with ENOENT. Resource-range
coverage can remain completely valid.

The same exposure exists for an unused tail arena chunk trimmed after the
snapshot, and on EBUSY retry when the lock is released but the old list retained.
A command-count threshold or VDM size-limit change cannot fix that lifetime gap.

Host reproductions use the unmodified installed r39-3.1 diagnostic ICD and the
production range validator linked into the timeline fake. No fake range or
handle corruption is enabled. The supported `PVR_G5P_PERF_READS=0` mode exercises
conservative listing; `PVR_G5P_WS_LOG=1` widens the existing scheduling interval.
These knobs make the interleaving repeatable; the exact default Firefox path
still needs the device diagnostic. The fake renders no pixels.

- `scripts/gpu/orchard/test-vdm-lifetime.py`: a native render races with
  `vkFreeMemory()` of an unrelated 4 MiB allocation. At 100 µs the baseline
  fails with `g5p_render_resolve drm_gem_object_lookup`, errno 2. The report
  shows stream `0x3002bc000 + 442444` (442380 commands + 64 guard), program and
  all six task references covered; sync lookup succeeds; listed BO handle
  **104** has `lookup=-2`. Baseline receipts:
  `build/gpu/vdm-zink-fix/lifetime/free-100.{fake,log.gz}`.
- `scripts/gpu/orchard/test-vdm-zink-lifetime.py`: real EGL/GLES → installed
  Zink → G5P. A shared EGL context repeatedly creates/deletes unrelated,
  dedicated ~4 MiB textures while the main context draws. At **500, 1000 and
  4096 draws**, **64 KiB and 1 MiB** limits, three repetitions per cell:
  **18/18 baseline cases reproduce ENOENT at GEM lookup**. Receipts:
  `build/gpu/vdm-zink-fix/zink-lifetime/`.
- The identical GL/Zink matrix with the fixed winsys: **18/18 PASS**,
  no missing GEM handle or device-lost error. Receipts:
  `build/gpu/vdm-zink-fix/zink-lifetime-fixed/`.
- Native teardown at 100, 500, 1000, 2000, 5000, 10000 and 20000 µs:
  **7/7 fixed PASS**. Another **7/7 PASS** with a deliberately injected,
  pre-acceptance EBUSY; the resource list is rebuilt and the freed BO omitted.
  Receipts: `lifetime-fixed/` and `lifetime-retry/` under the same root.

The fixed A/B library is r39-3 plus the stream lane's changed winsys file,
compiled in the private container. It is not yet a qualification of the final
r39-6 compiler/source combination. Final package gates must run again after
rebasing and building the complete committed archive.

## Fix

Keep `ws->lock` held from resource-list construction through the submit ioctl.
This synchronizes against own-BO removal and arena trimming. Once accepted,
the kernel owns GEM references for the job; BO destruction already follows
its existing idle-wait path. On EBUSY, wait without the winsys lock, reacquire
it, and **rebuild the list before retrying**. A fixed array capacity check now
precedes filling it. No kernel change, UAPI change, stream relocation or new
environment switch is introduced.

The once-per-context rejection diagnostic reports dataset and shared key IDs,
context, VDM+guard, TA program, six task intervals and coverage indexes, listed
BO handles/ranges, sync handles/points/flags and safe follow-up object lookups.
The r39-3.1 diagnostic packet contains only those reports, without the fix,
so its device reproduction remains useful and comparable.

## Release status

The approved safety commit restores the W-without-smooth named refusal; it
contains no r39-7 coefficient implementation. The combined **r39-6 installed
package** passed the lifetime GL/Zink repro 18/18, step6 15/15, both step7
28/28, corpus270/default288 identity, 19 compiler fixtures, 19 bank-constraint
sanitizer checks, 74 real WR compiler pairs (29/31 GLES, 39/43 optimized,
all r39-5 admissions retained), 16 CPU numeric references, 30 fake-readback
negative controls, two W refusal controls, 12 native VDM cases and package
transaction/ABI checks. Full source was streamed and 13,154 files rehashed.

Packet: `build/gpu/r39-6/runner.tar.gz` (3,458,800 bytes), SHA256
`5a50c550671f…`.
See the final device plan: all numeric cases
first, native 2048, the 14-sample Aquarium gate, full sweep and separate HW
shader capture. No A9 pixels or device workload in this plan have been run
by this lane. The device's original Aquarium ENOENT still needs attribution
through its diagnostic evidence or successful final-package device tests.
