# integration-g flight (2026-11-11, orchestrator)

Bundle `orchard-04-integration-g.tar.gz` (sha256 `7408a869…4228`, Orchard integration `b7ed084`, release
`7.3.0-rc1-orchard-apple-16k-topic-integration04g`). It was installed from `orchard-opt1-20261110` into a fresh staging dir,
`/var/tmp/orchard04g`, because the old dir's overlay backup refuses a second install. The overlay backup is at
`/var/tmp/orchard04g/overlay-backup`. The device was cold-booted from DFU with the PSCI launcher
(`build/orchard-release/hw/bin/orchard launch --entry orchard-04-integration-g`). Raw results:
`build/orchard-0.4/integration/flight-g/{ip,hevc,h264}/`.

SoC state during the flight: 13 (not changed).

## IP block: STOP at IP0 (S1), no freeze

- Firmware ALIVE at 7.02 s and the DC boot handoff were verified. Autoboot phases release, events, control-prepare and
  control-submit all returned 0.
- **cmd8 was never consumed:** `DC timeout consumer=0 producer=1 target=1` at 10.06 s, then
  `autoboot stopped at control-wait (-110)`. There was no "autoboot complete: GPU up" and no
  "G5P self-park armed".
- Policy record at the stop: `+0=1 +4=0x10 +c=0 +34=1`. debugfs: `self_park=1 armed=0 park_epoch=0 ctl20=0`,
  `policy0=1 sample_ms=16 target=2 pstate=1`. suspend_ready: `not-ready 201000000.gpu:ring3=0/1 -16`.
- The SoC stayed healthy (SSH, NVMe and USB all fine). IP1–IP8 were not run.
- Handed to lane IP2 (Opus): `docs/release/orchard-0.4/lane-ip2/`. Lead [I]: iOS's record runs the boot sampler from
  release (`policy+0=1`, 16 ms) while ctrl+0x20 stays 0 until after bring-up. That is near the latency123 T2/T3
  configuration, but this time it stalls the control queue itself.

## Not run on this boot

- The DP3 session check, Firefox H.264/HEVC playback, and the GPU set: the GPU is not up.
- Warm hops out of this boot: the GPU state is a stopped autoboot, so no kexec.
