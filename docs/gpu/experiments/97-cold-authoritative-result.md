# r97 cold-direct (authoritative): triangle-exact, TA 7.070 s, 3D 3.880 s

Sealed folder `build/gpu/round97/raw/20261030T231025Z/stage01-attempt1` (CLOSED, campaign `exit_code` 0, `stop_reason` none, one stage, one attempt). Never touched; every number below is read from it.
Reader outputs are outside the sealed tree: `build/gpu/round97/cold-outcome-20261030T231025Z/` (`r97-outcome.json`, `result.json`).

**Verdict: `triangle-exact`.** The natural TA with the executed app draw g0 completed, the natural 3D then rendered the exact oracle triangle into the 64x64 target page, and the pinned reader and the kernel's own `R97 target when=end` row agree.

## Identity

- Route `cold-direct`, `kexec=0`, `boot_changed=false`, one boot `776199aa-c5c4-459b-9118-e85c9bb935e9` from source to end. Health gate: 2 clean probes, uptime 41 s.
- Entry `tri97-dadd3e38dc` (kernel `7.3.0-rc1-gdadd3e38dcbb`, `R97 latched cfg=1` in the console), payload sha256 `acf1fcc4a588…`, payload-manifest `272122ce...`, device-manifest `85f92dd5...` (all equal to DEVICE-READY and `campaign-start.json`); staged image `a30c260e...` equals `tri97-entry/Image.gz`.
- Seal: `SHA256SUMS` 60/60 OK, `CLOSED` pins its sha256 (`d573bcbf...`) and 60 files.
- Pinned scripts equal `device-manifest.json`: `r97-outcome.py` a614b692, `r96-outcome.py` c94b72a9, `r97-spec.py` 15bff920.
- Flags: submitted, consumed, completed; no timeout, refusal or freeze; `runner/render/export/prepare/attach/job rc` all 0.

## Target page (authoritative: `r96-target-end.bin`, 16384 B, sha256 `01b1cd7183da…`)

| | count |
|---|---|
| red (`ffff0000`) | 1152 (all inside the oracle triangle; oracle red = 1152; red outside = 0) |
| blue (`ff0000ff`) | 2944 (all outside the triangle; blue inside = 0) |
| other / untouched | 0 / 0 |
| oracle match | 4096 / 4096 |
| witness pixels | 8 / 8 (4 inside red, 4 outside blue) |

- `r96-target-end.bin` is byte-identical to `r96-target-exp.bin` (same sha256), i.e. the page at the end equals the expected export.
- Before the 3D job (`R97 target when=ta-complete`): 4096/4096 untouched (`a5a5a5a5`). The TA alone wrote nothing to the target; the 3D job produced the whole frame.
- Kernel row `R97 target when=end cls=3 match=4096 red_in=1152/1152 blue_out=2944 red_out=0 guard=1` and the reader's class and sha agree (`kernel_agrees`).
- `legacy_counters` (render_status pixels/red/blue) read 0 on this path; they are not the verdict.
- The r96 end code is 5 (complete), `failed=0/0`, no freeze.

## Timing (target kernel clock, ktime ns; n = 1)

Sources: TA publish / consume = `R80 times pub_ns / consume_ns`; TA complete = `R97 budget start_ns + complete_ns` (the observation, what the reader prints as `elapsed_ms` 7068, rounded and counted from the wait start); 3D = `R96 publish_ns` plus `times.consumed / fw`. The G2 drain events and R74 milestones cross-check them.

| interval | ns | ms | s |
|---|---:|---:|---:|
| TA publish -> consume | 818,917 | 0.819 | 0.000819 |
| **TA publish -> complete** | 7,069,891,401 | 7069.891 | **7.069891** |
| 3D publish -> consume | 2,458,066 | 2.458 | 0.002458 |
| **3D publish -> complete** | 3,880,498,609 | 3880.499 | **3.880499** |
| **Total, TA publish -> 3D complete** | 10,961,917,260 | 10961.917 | **10.961917** |

Supporting: TA consume -> complete 7.069072 s; TA completion event drained at +7.068501 s (1.391 ms before the observation); 3D stamp first seen at +3.879457 s; 3D completion event drained at +3.880326 s (0.173 ms before); 3D window end +3.901493 s (= complete + 20 ms settle); TA complete -> 3D publish 11.527 ms (capture plus the 53-line console dump; `ta_to_publish_ns` 4,928,674 as printed); TA publish -> report-end 10.988883 s.

Context (n = 1 each, no interpretation): the warm diagnostic boot of the same payload took TA 5.011 s, 3D 0.565 s (total 5.583 s). Earlier g1-only TA boots: 0.103 s (r96 success), 11.02 s (r95b), 12.006 s twice (the r96 budget misses). This TA completed at 7.07 s: after the 5.0 s warm run, well inside the 20 s budget, and not watchdog-like (`late_vs_r96_cap` false, final pass not fired). The 3D time is 6.9x the warm run's.

## Established / not established

- Established: on the cold-direct route the r97 kernel flies the g0 edit through the natural TA, the TA completes inside the 20 s budget, the natural 3D renders the exact oracle triangle (4096/4096), and the SoC stays alive to the end of the capture. This is the first cold-direct triangle-exact.
- Not established: any completion rate or latency spread (cold n = 1, warm n = 1; TA 5.0 s vs 7.1 s and 3D 0.56 s vs 3.88 s differ per boot). The A10 USC padding hang class (about 1 in 12) is not retired by one run.
- Display is a separate step (`scripts/gpu/r97-frame-export.py`, `chvt 6` before `a9present`); not part of this result.

## Reproduce

```
python3 -B -I scripts/gpu/r97-outcome.py build/gpu/round97/raw/20261030T231025Z/stage01-attempt1
python3 -B -I scripts/gpu/r97-cold-result.py build/gpu/round97/raw/20261030T231025Z build/gpu/round97/cold-outcome-20261030T231025Z   # 31 checks, rc 0
python3 -B -I scripts/gpu/test-r97-cold-result.py                                                                                      # 6 tests, ALL PASS
```
