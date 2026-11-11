# Experiment 10 — CL visibility after working DC transport

Round11 kernel patches0024–0025 (head recorded in round11-report.md). Fresh boot only.
Exp09 v7 proved zero-payload cmd8 completion (`cache_epoch=1`, consumer1)
and AIC IRQ delivery, then consumed the global CL notification without advancing
the private channel consumer. No shader was dispatched. Exp09 v0 had no RAM
changes/cache epoch. Remaining DC variants are deferred.

All following experiment helpers use `dc_variant=7`, which sets meta+6c8=0
before release. This is an experimental power-policy bypass, not a recovered
normal iOS policy. Kernel parameter defaults and default boot remain unchanged.
The old run-dc-variant.sh remains available only for explicit historical controls.

Next run: **CL variant2** (original aliases, notification word2=1). Firmware
10004e94 copies word2 into ctl+30; the dependency callback scans ctl+20 toward
ctl+30, independently of host producer ctl+40. Sending0 is a concrete mismatch
with our published pointer count1. Success requires global CL consumer1,
scan1/endpoint1/host producer1, unchanged stamp1 and no observed fault. It logs
ctl0 retirement separately; tag4 scan is transport, not GPU completion. This
variant changes the notified endpoint and the diagnostic success predicate;
it never fabricates a stamp or forces a firmware consumer. New cl-scanned
RAM sample preserves the actual evidence. T1 is started on demand by T0 for
real work; no host T1 start is added.

**CL variant1**, deferred until endpoint/readiness evidence warrants it: Cache-bypass aliases for the private channel-state
notification pointer and the channel control/pointer ring/dependency/stamp.
Addresses become40254xxx instead ofc0254xxx. Every byte other than these
32-bit pointers and added observations matches variant0; context/identity
remain zero. It is a visibility hypothesis, not proof that those zero fields
are valid. Global CL ring aliases and kick0x12 are unchanged.

Upload the new runner and helper, after integrating patches0024–0025 and building
an integrated payload (the GPU-only Image is not an integrated payload):

*(Device/host command block omitted; it targets the private workspace.)*

If variant2 scans successfully, repeat it before changing aliases or policy.
If endpoint1 is observed but scan0, inspect the full channel/global-CL readiness
and resource scheduler fields from the new snapshots. Do not submit cmd3 or
GPU work as a guessed fix for a dependency-only path. Do not batch runs, clear
a failed lock or retry on the same boot.

New RAM samples:cl-prepared,cl-before-kick,cl-after-kick,cl-timeout. They extend
the DC baseline and use the existing strict decoder. Snapshot root slot49
(the firmware CL scheduler object), the private area shared+54000..543ff,
and queue controls. `T1_entry_pc`/`T1_initial_sp` are configured init fields,
not live thread registers. In v7, cmd8 returned despite entry20000000, so that
value alone is not evidence of a stalled T1.

Returned, kernel-classified CL timeout (`work_timed_out=1`) now allows explicit
wrapper park even with an abandoned private channel. The global CL ring must
be empty or contain only our single published slot; all other submission
rings and the event ring must be empty, indices/targets valid, and no event
fault recorded. It freezes further commands, retains DMA and IRQ handling,
and preserves original -110. No DMA quiescence/reset/recovery is claimed.
The runner attempts this only after its writer returned, never behind a
stuck writer, unclassified error or event fault. Failed lock/logs remain.

Firmware telemetry: slot73 controls256 records of36bytes at slot77
(shared+489c0); hostc98bdc..c98c38 ->cb8c6c reports statistics. The four
pending v0 records are types1,2,0,4; these are not unconsumed GPU jobs or four
faults. Unknown fields remain opaque. Do not advance this consumer merely to
make the queue look empty; it is deliberately outside the park submission set.
