# r73e device result: first-ALIVE cmd8 crosses the host timing boundary

Date: 2026-10-28. Device run: `tri73e-97c24b45c1`, case 01,
GPU-clean epoch (DFU -> cold Linux -> one warm kexec). Artifacts are under
`build/gpu/round73c/runs/case01-20261028T142700Z-*` and the boot
`fc15edc6` section of `build/omarchy/logs/netconsole-boot8-nvme.log`.

## Observed

- The command slot was constructed before firmware release with target producer
  `1`.
- The first and only ALIVE arrived 1,643,042 ns after release.
- The threaded IRQ path observed `R1+0x1000 = 1` before and after the Fender
  handshake.
- `R0+0xb00 = 0x10` was written; both the before and after breadcrumbs printed,
  so the doorbell write returned.
- The host DC producer remained `1`; firmware consumer remained `0` through the
  timeout. No MMU fault was recorded.
- The old repeated-ALIVE symptom disappeared: one ALIVE, 145 IRQs, 26,305
  trace records. The retained trace changes after its initial records to a
  repeating type `1/0/4` family rather than the earlier `1/2/4/3` cycle.
- The retained `1/0/4` cycle repeats with a median 20,438-tick interval between
  timestamped type-1 rows (about 0.85 ms at 24 MHz). This is continued firmware
  execution, not a sleeping or wedged META core. The former type-2/type-3 wait
  phases appear only at the beginning and then disappear.
- At 100 ms the policy state was still `+8/+c = 2/2`, `+34 = 1`, companion
  state `0`, and policy sample period `+4 = 0`.

## Conclusion

r73e retires the host-timing and MMIO-doorbell hypotheses for this run. The
command is visible in the host-owned queue and the notification write returns,
but firmware does not reach or accept the DC consumer path. This is new progress
from r73b/r73c: the failure boundary is now inside firmware scheduling/readiness,
not before publication.

The fast, stable trace cycle makes a repeatedly failing scheduler/readiness
predicate more likely than a blocked pre-MTS timing wait. It does not by itself
identify which predicate; the independent firmware factors below remain needed.

Static closure identifies a candidate that evaluates false under the retained
100-ms and timeout snapshots. `1000d044(policy)` reads `policy+8/+c`.  For
`2/2`, with Linux's cached `meta+0x6e0 = 1`, `policy+0x34 = 1`, and
`companion+0 = 0`, the correct path passes the companion check, calls the nested
`1000c0d8` governor, and returns zero if that call returns.  The governor can
wait or mutate the record, so this is not an unconditional completed-return
proof.

A zero from `1000d044` also does not by itself prevent `10003bb4` from trying
its source-1/source-2 fallbacks.  Those fallback state/request words were zero
in the same retained snapshots, making the complete sampled tuple predict no
service.  This remains a sampled CPU-visible state, not proof that the live
scheduler loaded the tuple or even reached this call.  r73f case 01 tests the
whole behavior removed by replacing this helper at entry with `return 1`; a
positive result therefore implicates this helper and its nested governor path,
not only its final Boolean arithmetic.

The static chain to discriminate is:

```
8000a120 -> 10001ac8 -> 1000c0d8       pre-MTS policy
8000a240 -> 10003bb4 -> 1000d044       post-MTS policy readiness
                              -> 1000d504 companion readiness
8000a36c                                  service/DC dispatch
```

## Required matched control

Run r73e case 02 from a separate GPU-clean epoch. It must use the same prebuilt
slot and first-ALIVE IRQ publication path with only `meta+0x6c8 = 0` changed.
A consumed cmd8 proves the queue, barrier, Fender handshake and doorbell are
valid and isolates the pending consumer to firmware state enabled by `6c8 = 1`.

## Next discriminators

Each factor starts from its own GPU-clean epoch and retains r73e publication:

1. Force `1000d044` to return true at entry. Consumption localizes the blocker
   to behavior removed by that bypass, including its nested governor call; it
   does not isolate only the final readiness Boolean. No consumption leaves
   pre-MTS policy, companion, or service scheduling open.
2. Independently skip only the scheduler's pre-MTS call to `1000c0d8`.
   Consumption localizes the blocker to that call; no consumption with factor 1
   passing distinguishes the post-MTS gate.
3. If both fail independently, instrument/force `1000d504` before modifying
   policy data. Do not combine bypasses until the independent branches score.

These are diagnostic firmware-image factors, not proposed production fixes. A
real fix must reconstruct the Apple policy/readiness contract after the blocking
gate is localized.

## Cold-source runner contract

On a genuinely GPU-untouched cold Linux source, the G5P driver is normally
unbound and `/sys/bus/platform/devices/201000000.gpu/result` does not exist.
Runners must accept that state only when the device has no `driver` symlink. If
`result` exists, they must retain the stricter all-zero field check. Future
single-case GPU runners should use this two-branch predicate rather than reading
`result` unconditionally under `set -e`.
