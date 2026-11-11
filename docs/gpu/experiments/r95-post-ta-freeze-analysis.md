# r95: the first natural TA-complete run, and what stopped it

Research note (no device access, no code edited, no commit). Raw evidence only: nothing below is an analyzer verdict, and no gate in the proposed r95b run reads an analysis.

Tags: **[O]** observed in a file or in the source, **[D]** derived from [O] by arithmetic or reading code, **[U]** unknown.

Sources read: `build/gpu/round95/raw/20261030T152707Z/` (campaign root and `stage01-attempt1/`), `build/gpu/round95/r95-netconsole-tail.log`, the live `build/omarchy/logs/netconsole-boot8-nvme.log` (from the stage offset 195890884 on), the r95 runner scripts in `scripts/gpu/`, the r94 raw folder (`round94/raw/20261030T145952Z`), the older rounds' `diagnostic_blob` files, and the kernel tree `a9/tri95` @ `29134a97b7` (extracted read-only from the `linux-a9-src` volume with `git archive`; line numbers below are that tree's). To re-read a file:
`docker run --rm -v linux-a9-src:/src:ro linux-a9-kbuild git -c safe.directory='*' -C /src/linux show a9/tri95:drivers/gpu/apple-g5p/<file>`.

## 0. Summary

1. **The task's framing needs one correction.** The device did not freeze "immediately" after `render-fixed-ta result=0`. It answered a brand-new SSH session about 0.77 s later [O/D, section 1]. It stopped on the very next host action: `echo r73b-export | sudo tee $D/command`. Everything the host and the kernel did between `result=0` and that write is cached-RAM work and was observed to complete.
2. **The first and only MMIO on the post-TA path is `g5p_r82_endbank()`** (`boot-r80.inc:602`), called from `g5p_r73b_export()` (`boot-r73b.inc:1214`): one `readl` of `R1+0x1000`, 28 `readl` of RGX bank registers, 6 `readl` of the BIF fault latch, 13 more extras for the r85 end slot. Its first output line (`R82C fault-bank`, `boot-r80.inc:634`) and the command's `result=` line never appeared. [O/D]
3. **Why this export, why now [D]:** every earlier `r73b-export` that completed (r85 to r88, r93, r94; r94's blob shows the end bank `done=1`) ran with the GPU stalled or faulted but powered. r95 is the first run where the firmware retired the TA, saved PM, and went idle for ~0.8 s before the host read ~47 GPU registers. The `R1+0x1000 & 0x1f == 1` gate checks the wrapper, not the TA/TE/PM blocks behind the 28 + 13 offsets. This is the leading candidate, not a proof ([U], section 2).
4. **No TA output can be reconstructed from what is on the host.** The END-checkpoint digests, `r82c` end rows, PM-payload compare and `R94 end` state existed in kernel RAM when it stopped and were never exported. Even a successful r95 export would have produced digests only, not raw TA bytes (the raw page dumper is gated on seeding, which r95 turns off) [O/D, section 3].
5. **r95b minimum:** make the post-TA path MMIO-free (two early returns), dump the TA output objects as raw hex from RAM at TA end, inside the kernel, before the host does anything, and keep the host order "RAM-only reads first, `r73b-export` second, nothing else". The end bank moves to a later run. Details and line numbers in sections 4 and 5.

## 1. Evidence, timeline, and what the files can and cannot say

### 1.1 Clock mapping [D]

The Mac stamps each netconsole line with its receive time (1 s resolution) and also stamps file mtimes. Intersecting all 448 stamped lines of `netconsole-closed.txt` bounds the offset to `wall = kernel + 59207.339 s` (±1 ms, i.e. 16:26:47.339 + kernel). The mapping assumes the Mac's receive latency is far below 1 ms and the device clock does not drift over 15 s; both are consistent with the 448-line fit. File mtimes and birth times (sub-second, from `stat`) share the Mac clock, so they place host-side events on the kernel axis.

### 1.2 Timeline

| wall (16:28:..) | kernel s | source | event |
|---|---|---|---|
| 00.7 | 73.365 | netconsole | `RENDER publish engine=0 slot=8 ... sequence=1`; TA consumed |
| 01.377 | 74.038 | netconsole | `G2 event index=33 type=1 word1=00000001`, raw event words (omitted) (the only non-type-0 event in the log) |
| 01.381 | 74.043 | netconsole | `ta-ram-complete`, `R74B TA RAM complete stamp=00000001 pm_saved=1 consumer=1 producer=1`, `wait-exit ret=0`, `report-end ret=0` |
| 01.382 | 74.043294 | netconsole | `command render-fixed-ta result=0` (**last kernel line from this boot**) |
| 01.736 | ≈74.40 | mtime `render-runner.txt` | device-side `run-render-r76.sh` finished; its last output line reached the Mac |
| 01.768 | ≈74.43 | birth `export.txt` | host launched the export ssh (`run-control-host-r95-stage.sh:222-224`) |
| 02.153 | ≈74.81 | mtime `export.txt` | the 45-byte file `boot_id=df2052bd-...` was written: a fresh sshd session ran `cat /proc/sys/kernel/random/boot_id` |
| (derived) ~29:01.8 | | `bounded 60` | the 60 s ssh bound would have fired (`bounded()`/`ssh()` at `run-control-host-r95-stage.sh:108-109`, `R80_SSH_LIMIT=60`) |
| 29:16.51 | | mtime `wrapper.log` | `close engine_rc=-1`; `stage01-wrapper.out` = `Terminated: 15` |
| 30:07 | 3.67 (new boot) | live netconsole | first line after the stage: a different boot (AOP kernel, no `apple-g5p-drm` lines) |

[O] There is no line of any kind from this boot after 74.043294. [O] `export.txt` has `boot_id=` but no `r73b-export-rc=`; the kernel never printed `command r73b-export result=` or `R82C fault-bank`.

### 1.3 What this does and does not show

- **[D] The kernel was alive and scheduling at ≈74.81 s**, 0.77 s after TA completion, with sshd, a shell and `cat` running. So the stop is not "at TA completion" and not inside any of the ~20 `render_status` reads.
- **[O] The stop is in the window between that `boot_id` print and the first line the export would have printed.** In r94 the same command took 1.7 ms (`73.992587` R82C line, `73.994296` command line).
- **[U] Whole-SoC freeze versus a stuck export thread.** The folder cannot tell them apart. The 60 s bound expired (~16:29:01.8), the recovery loop (`run-control-host-r95-stage.sh:236-246`) started its 10 s sleep + 15 s ssh polls, and the campaign was SIGTERM'd at 16:29:16.5 (`Terminated: 15`, `engine_rc=-1`; header: `reachable=None`, `freeze=None`, `export_rc=None`; `campaign-end.json`: `stages_captured=[]`). No `collect-hang-evidence.sh` run happened (no `-hang/` dir). No reply to a post-export ssh poll is on record. The task states the SoC froze; the data in the folder neither confirms nor refutes "only the export thread is stuck in an uninterruptible `readl`". Section 4 makes r95b never be killed during recovery.
- **[U] Spontaneous versus export-induced.** No r95 variant without the export exists. The firmware's own idle handling at about +0.8 s could stop the SoC with no host action at all; the evidence is equally consistent with that (rank 3 below).

## 2. Q1: every action after the final `command render-fixed-ta result=0`, in order

Notation: **W** = sysfs write, **R** = sysfs read, **M** = MMIO. Line numbers: `run-render-r76.sh` (RR), `run-control-host-r95-stage.sh` (CH), kernel files as named.

| # | actor | trigger | code | MMIO? | observed |
|---|---|---|---|---|---|
| 1 | kernel (command thread) | return of the `g5p_r22_command` `render-fixed-ta` branch (`render-fixed.inc:3565-3679`); `g5p_r52b_stall` runs, `r32_second` and `r52g_terminal` are skipped (`g5p_r74b_ram_only`); `g->last_result = 0`; `dev_info("command ... result=0")` | `core.inc:600-604` | no | [O] result=0 line |
| 2 | device shell, backgrounded subshell | `printf render-fixed-ta > $D/command` returns, writes `$out.rc` | RR:152 (`run_stage`, `.rc` write) | no | [D] rc=0 |
| 3 | device shell | `run_stage` polls `.rc` once per second (RR:154-157), then `cat "$out.log"` (empty) and `cat "$D/render_status"` (**R** #1, third `revision=52` line: `TA_submitted=1 TA_consumed=1 TA_complete=1 ... terminal=1 PM_saved=1`) | RR:162-163; `render_status_show` `render-fixed.inc:3705` ("Cached status only: never MMIO") | no | [O] third line of `render-runner.txt` |
| 4 | device shell | 14 `grep -Eq "(^\| )rNN_case=0" "$D/render_status"` for r53..r70, then `r72_case=1`, `r71_case=2`, `r59_case=2`, `r52h_case=0`, `3D_submitted=0` (**R** #2-#20) | RR:173-180 | no | [D] all passed (script reached the next line) |
| 5 | device shell | `echo "r76 observation ... retained resources, no subsequent command on this boot"`, script exits 0 | RR:181 | no | [O] 4th line of `render-runner.txt`; file closed 16:28:01.736 |
| 6 | host (engine) | `tee` ends, `rrc=${PIPESTATUS[0]}` = 0 | CH:218 | no | [D] |
| 7 | host → device | new ssh: `b=$(cat boot_id); echo boot_id=$b; [ "$b" = $boot_before ] \|\| exit 3` (**R**) | CH:222 | no | [O] `export.txt` = `boot_id=df2052bd-...` |
| 8 | device shell | `echo r73b-export \| sudo tee $D/command` (**W**): `sudo` startup, then `command_store` | CH:223 | | **[O] no further output: stop point** |
| 9 | kernel | `command_store`: `capable(CAP_SYS_RAWIO)`; `sysfs_streq(buf, "r73b-export")` is handled **before** the command mutex (a wedged stage cannot block it) | `core.inc:551-554` | no | |
| 10 | kernel | `g5p_r73b_export()`: `atomic_xchg(&r->exported, 1)`; `g5p_r73b_disarm()` (hrtimer cancel only if `watchdog_state==1`; `r73b_watchdog=0` in the receipt) | `boot-r73b.inc:1195-1211` | no | |
| 11 | kernel | `g5p_r84b_export()` returns immediately: `r84b_seeded == 0` (r95 has `r84b_seed=0`) | `boot-r73b.inc:1213`; `render-r84b.inc:199-205` | no | [O] seed=0 in the receipt; [D] no-op, so the `g5p_table_clean_page()` cache maintenance in that function is dormant |
| 12 | kernel | **`g5p_r82_endbank()`** | `boot-r73b.inc:1214`; `boot-r80.inc:602-647` | **yes** | see below |
| 13 | kernel | `g5p_r80_final()`: `mutex_lock(&x->lock)`, final drain of ring 5, `g5p_r80_freeze()` | `boot-r73b.inc:1215`; `boot-r80.inc:296-318` | no (RAM; the drain's only store is the ring consumer word / `ctrl0` guard, as in every round) | not reached |
| 14 | kernel | blob prints, `g5p_r74f/g/h_export`, `g5p_r80_export` (`g5p_r82c_export`, `g5p_r85_export`, `g5p_r94_export` → `g5p_r94_export_end`: SHA-256 over W and code BO), `R73B` rows | `boot-r73b.inc:1216-1330`; `boot-r80.inc:739-744` | no | not reached |
| 15 | kernel | `dev_info("command r73b-export result=%d")`, return `count` | `core.inc:553` | no | **never printed** |
| 16 | host | `echo r73b-export-rc=$?`, then (only if rc 0 and `boot_id` matches) `cat` of `result render_status diagnostic_status diagnostic_blob mmu_history`, `fw_trace`, `dmesg` | CH:223-234 | no | none of these files exist in the folder; the `else` branch (CH:235-246) runs instead |

Row 12, in order [O: source]:

1. `bank_attempts++`, `bank_arm_ns`
2. `state = readl(R1 + 0x1000)` (`:612`); if `(state & 0x1f) != 1` → refused, return (no further MMIO, no R82C print)
3. 28 × `readl(g->rgx + g5p_r80_bank_offsets[i])` (`:619`): `0x130 0xb20 0x400 0x408 0x410 0x428 0x430 0x438 0x43c 0x470 0x6020 0x6038 0x60c0 0x8328 0xc18 0xc28 0xc38 0xc68 0xc78 0xc80 0xc88 0xc90 0xcb8 0xcc0 0x240 0x248 0x2d8 0x3d0`
4. `r82c_armed` is 1 (set by `g5p_r95_latch`, `boot-r80.inc:567-575`): 6 × `readl` of (bytes omitted) (`:626-631`), then `dev_info "R82C fault-bank ..."` (`:634`)
5. `r84b_seed` is 0: skipped
6. `r85_obs` is 1: `g5p_r85_endbank()` (`:579-598`): 13 extra `readl` (`0x414 0x420 0x5020 0x5028 0x5110 0x5118 0x5120 0x5030 0xe008 0xe028 0xe048 0xc30 0xc34`); riders are 0

Nothing else on the post-TA path touches the GPU:
- [O] `g5p_r74h_end(g, 0)` (`render-fixed.inc:3150`; `render-r74h.inc:408-419`) ran **before** the `ta-ram-complete` milestone. It sampled the R80 timeline, took the END checkpoint (digests of 18 RAM objects against the before-TA baseline, `r74h_cp`), `g5p_r82c_end` (PTE rows), and `g5p_r74h_phys(g, true)` (FNV compare of up to 256 PM payload pages). All RAM, all completed (the milestone and `R74B TA RAM complete` printed after them). Their results are in kernel RAM only.
- [O] The IRQ thread (`g5p_r73b_irq`, `boot-r73b.inc:770-807`) writes only the AIC SW-IRQ ack (`b->swirq + 0x94`) except via `g5p_r85_irq_bank()` (`boot-r80.inc:439-477`), which reads 41 GPU registers at the first IRQ ≥ `first_g728_ns` + 100 ms (slot 0) and ≥ slot-0 read + 1 s (slot 1), and stops once `exported` is set (`:447`).
- [O] The r80 drain thread (`g5p_r80_thread`, `boot-r80.inc:205`), `g5p_r80_alive` (ladder=0) and `g5p_r80_irq_bank` (bank=0) are inert in this tuple.

## 3. Q2: the first potentially unsafe step, and a ranking

Classes asked about, with their status on this path:

| class | present after `result=0`? | evidence |
|---|---|---|
| MMIO read of GPU registers | **yes**: `g5p_r82_endbank` (47 reads) and, if armed, IRQ slot 1 | section 2 |
| cache flush/clean | dormant: only in `g5p_r84b_export` (`seed=0`) | row 11 |
| RAM alias / hash | already done before `result=0` (`r74h_phys`, END digests); `g5p_r94_export_end` SHA-256 over W/code BO runs in the export (same code as r94, 2 ms there) | `render-r74h.inc:408-419`, `boot-r80.inc:739-744` |
| bank snapshot | the end bank itself (slot 2) | row 12 |
| exporter | RAM-only formatting into a 4 MB blob (`G5P_BLOB_SIZE`, `diagnostics.inc:5`); r94's blob was 285 KB, so no overflow risk | |
| firmware interaction | no doorbell, no ring write beyond the standing drain; `g5p_r73b_export` rings nothing | |

**Ranking** (most to least likely):

1. **`g5p_r82_endbank` reading a block the firmware has gated after retirement.** [D] Same code and same register list succeeded in r94 (`R85 bank slot=2 ... last_state=00000001 ... done=1`, export 1.7 ms) with the GPU in a fault state, and the IRQ banks succeeded in r85-r88, r93 with the GPU stalled. [O] In r94, `first_g728_ns=0`; in r95 the TA genuinely completed (idle words 0, `pm_saved=1`) and the host read ~47 registers ≈0.75 s later. [D] Only the R1 wrapper state is checked before the reads; registers at `0x6020/0x6038/0x60c0/0x8328/0xc18..0xcc0/0x5020..0x5120` belong to blocks that may not stay clocked once the TA retires. [O] Ordering fits: the first MMIO of the whole post-TA sequence; nothing was printed after it. [U] Never demonstrated: no `R82C fault-bank` line means the freeze is before that print, not that the gate read ran.
2. **`g5p_r85_irq_bank()` slot 1** (41 reads in the IRQ thread, due ≥ slot-0 read + 1 s). [U] Needs `first_g728_ns != 0` in r95 (it was 0 in r94; r95's R80 timeline was never exported). Slot 0 fires at the first IRQ ≥ `first_g728_ns` + 100 ms, so if `first_g728_ns` was set anywhere in the 673 ms TA window slot 0 fell at ≈73.5 to 74.1 s and slot 1 was due at ≈74.5 to 75.1 s. That interval straddles the 74.81 s `boot_id` print and the 50 to 200 ms of `sudo` startup before `exported` is set (`boot-r73b.inc:1209`, which disables it). This is a real overlap with rank 1, not a tail case: **r95 data cannot separate the two**, and r95b guards both (section 6.1).
3. **A spontaneous stop with no host MMIO at all** (firmware idle handling; fabric/DRAM-side effect of the completed TA; GPU wrapper power transition). [U] Consistent with every observation; only a run whose post-TA path is MMIO-free and also stops would show it. If r95b stops anyway, this is the answer.
4. **RAM-only export steps** (blob formatting, `g5p_r80_final`, SHA-256 of W/code BO, `r82c` rows). Low: identical code ran 1.7 ms in r94. If `(state & 0x1f) != 1` the R82C line would not print even on success, so this rank is only reachable via a refused gate followed by a hang in RAM code. A `mutex_lock(&x->lock)` deadlock in `g5p_r80_final` would stall only the export thread, not the SoC (see [U] in section 1.3); it needs the r80 kthread to hold the lock indefinitely, which nothing suggests.

The cheapest discriminator is what r95b does: take the MMIO off the post-TA path and see whether the stop persists.

### 3.1 Comparison with the neighbouring flows

| run | TA ends how | GPU state at export | export | raw object bytes |
|---|---|---|---|---|
| r94 (`round94/raw/20261030T145952Z`) | fault event=4 at 73.759, `ta-ram-timeout` 73.7708 | stuck, powered (`R1+0x1000 = 1`) | OK, 1.7 ms; end bank done at 74268077133 ns | no (digests only) |
| r84b (`round84b/raw/20261029T213008Z/stage01`) | stalled, 12 s timeout | stuck, powered | OK | yes: 4 snaps (before-ta, end, late, post-op incl. `dcache_clean_poc`), 801 `R84B` lines, 317 KB blob; **requires seeding the pages pre-TA** (`g5p_r84b_dump`, `render-r84b.inc:173`) |
| **r95** | natural completion, `stamp=1`, `pm_saved=1` | idle after retire, ≥0.77 s later | **never completed** | none (seed=0, so the r84b dumper is gated off; r74h gives FNV/nz/delta/first only) |

## 4. Q3: artifacts that exist, and whether any TA output is recoverable

### 4.1 Exists on the Mac [O]

`build/gpu/round95/raw/20261030T152707Z/` (campaign root): `campaign-start.json`, `campaign-end.json` (`stages_captured=[]`), `health-stage01.log`, `netconsole-enable-stage01.log`, `source-identity-stage01.{txt,err}`, `stage01-wrapper.out` (`Terminated: 15`).

`stage01-attempt1/` (sealed, `CLOSED`, SHA256SUMS over 13 files): `netconsole-closed.txt` (448 lines, 50 101 B, ends at `result=0`), `campaign-...-stage01-render-runner.txt` (4 lines: three `render_status` snapshots, the last with `TA_complete=1 PM_saved=1`, plus the closing echo), `-host.log` and `engine.log` (bootstrap summary through `control-wait`; `numerical: NOT_CONFIRMED`), `-params.txt` (22 readbacks), `-receipt.txt`, `-export.txt` (45 B), `-phase.txt` (`experiment`), `-staging.txt`, `-fixture.txt`, `wrapper.log`, `header.json` (all result fields `None`).

Elsewhere: `build/gpu/round95/r95-netconsole-tail.log` (540 lines, same last line); the live `build/omarchy/logs/netconsole-boot8-nvme.log` (the same bytes plus the next boot); the pre-TA bootstrap capture `build/gpu/exp12-r19d-...-20261030T152742Z-{boot,diagnostic_blob (1916 B: latches only),diagnostic_status,dmesg (494 KB, pre-TA),mmu_history,ram.json (0 B),runner}.txt`.

Not on the Mac (never pulled): `diagnostic_blob`, `fw_trace`, `result`, final `dmesg`, `/run/g5p-render-r76-used/*.rc,*.log` (tmpfs, reboot-volatile), and all kernel RAM.

### 4.2 What is reconstructible from the host [O/D]

- `stamp=00000001`, `pm_saved=1`, `consumer=1 producer=1` (`R74B TA RAM complete`); `TA_submitted/consumed/complete=1`, `terminal=1`, `3D_*=0`, `numerical=0 pixels=0`.
- Timing: publish 73.365 → completion event 74.038 (673 ms); `irqs` 5811 → 6213, `events` 2906 → 3107; `ta-grace-end` 73.3648 with `cancel=consumed-before-bell`.
- The type-1 completion event's 11 raw words (table above).
- The mapping receipt `R82C prepared ... ok=1 ... rt0_leaf=000000080d24c00d tpc_leaf=000000084b0c800d aux0_leaf=000000080ec3000d` [O], so [D] RT0 at PA 0x80d24c000, TPC at 0x84b0c8000, AUX0 at 0x80ec30000 (low 12 bits are PTE attributes); every page is mapped, which is r95's one change from r94.

### 4.3 What is lost [D]

Everything the kernel computed at TA end: the 18-object END digests, the `r82c` end PTE rows, the PM payload compare (`phys_changed`, first delta), the R80 timeline (`first_g728_ns`, g724/g728/g72c), the R85 bank slots 0/1, the ring-5 firmware trace, `R94 end` W/code state. The RT0/TPC/PM/AUX contents themselves (the TA "output") existed only in coherent DRAM allocations of that boot.

**Not recoverable.** The device rebooted (next-boot lines from 16:30:07, kernel t=3.67 s, a different kernel with no `apple-g5p-drm` output), the kernel has no `pstore/ramoops` path here (`boot_r73b_watchdog_ms=0`; the watchdog that would have panicked into ramoops was disabled), and no tool in the tree dumps pre-reset DRAM. [U] whether DRAM contents physically survived the reset is not knowable from the repo; the following boot has since allocated over it.

## 5. Q4: the minimum safe r95b capture sequence

Design rules: (a) the TA's own end state is captured in-kernel before the command returns, because that is the place already proven survivable (its RAM passes completed) and it does not depend on host reaction time (≥0.77 s here); (b) after that, the host only reads RAM-backed sysfs files, one file per ssh, saving and sealing before any command write; (c) no GPU register is read after the TA retires; (d) the optional end bank is a later run, never in the same boot as an unsealed folder.

### 5.1 Tier A: in-kernel, automatic, RAM-only (new, `boot_r95_cfg == 2` only)

Called from `g5p_r74h_end()` right after `g5p_r74h_phys(g, true)` (`render-r74h.inc:418`), so it runs on both completion and timeout. After a `dma_rmb()`, plain loads only (no `readl`, no cache maintenance, no `dsb`):

1. For each of the 18 objects of `g5p_r74h_obj()` (`render-r74h.inc:29`): one header line `R95B obj name=<rt0|tpc|pm-control|pm-list|pm-free|aux0..4|ta-w|store|...> len fnv nz sha256` to the blob, then `g5p_blob_hex()` (`diagnostics.inc:66`) of the **full current bytes** (RT0..RT3, TPC, AUX0..4 are 0x4000 each; PM control 0x140, PM list 0x500, PM free 0x1000, W 0x560, store 0x400). About 170 KB of data (10 pages of 16 KB plus ~8 KB of small objects; `REGION` is a prefix of RT0 and can be skipped), ~11 k hex lines, ~0.6 MB of text; with r94's 285 KB the blob stays far under the 4 MB cap. Call `cond_resched()` every 16 hex lines, as `render-r84b.inc:149-150` does.
2. **Netconsole copy of the highest-value subset** (`dev_emerg`, as the existing `R74B TA RAM complete` line), so the bytes survive even if the SoC stops before any host read: the 18 header lines; TPC and RT0 changed 64-byte lines versus the before-TA baseline (`h->base` already holds it, `base_off[]`), each line `R95B raw obj=<n> off=<hex> b=%64phN`, capped at 128 lines per object; PM control (5 lines). Roughly 300 lines, the same scale as the existing 100-line bursts in this log.
3. PM payload frames (256 pages = 4 MB): record only the existing `phys_changed/first/was/now` and per-page changed counts in the blob. The 4 MB raw read is r95c work (a RAM bin attribute, section 5.5).
4. `R95B cap-end id=1 lines=<n> blob_bytes=<n> chain_fnv=<hex> t_ns=<ktime> irqs=<n> mmio_since_ta_end=0` on netconsole and in the blob, then `smp_store_release(&x->r95b_cap_done, 1)`. A line count and a running FNV let the reader see a dropped UDP line.
5. A 1 Hz `delayed_work` printing `R95B alive n=<k> t_ns=<ns> irqs=<n>` for 120 s (RAM only). It timestamps the moment the kernel stops, independent of ssh.

### 5.2 Tier B: host reads, RAM-backed sysfs only, one ssh per file, saved before the next

Order: `render_status`, `result`, `diagnostic_status`, `diagnostic_blob`, `mmu_history`. All are cached-RAM readers (`diagnostics.inc:108-127` takes only the diag spinlock; `render_status_show` and `result_show` are READ_ONCE formatting). Each file is written to its own path, then `sha256`, then a zero-byte `<file>.done`. Then copy the netconsole bytes seen so far to `netconsole-at-tierB.txt` and write `phase.txt = tierB-sealed`. **No `command` write has happened.** This tier succeeds or fails without any export.

### 5.3 Tier C: `r73b-export`, now RAM-only (`cfg95 == 2` skips the end bank)

Same command, same position as today (`CH:222-223`), but `g5p_r82_endbank` returns early. Then `diagnostic_blob` again (`diagnostic_blob-after-export.txt`), `fw_trace` (binary, raw redirect), `dmesg`. These add the R74H/R80/R94 export lines and the ring-5 trace. If the SoC stops here with **zero** GPU MMIO since the TA retired, the stop is not the end bank (rank 3), and Tiers A and B are already sealed on the Mac.

### 5.4 Stop cleanly, and tell capture success from a later freeze

- No GPU stop command exists in this driver and none should be added: `run-render-r76.sh:181` already says "retained resources, no subsequent command on this boot". After Tier C the runner does a **liveness window only**: `ssh 'cat /proc/uptime'` every 2 s for 60 s, each result appended to `liveness.log` with the Mac timestamp. Then it seals the folder (existing `close_folder`, `run-raw-stage-r95.sh`) and leaves the boot as it is for the owner's next DFU. It never reboots the device.
- **Never SIGTERM the campaign while it is in the recovery path.** The r95 recovery code (`R80_RECOVER_LIMIT=300`, then `collect-hang-evidence.sh --seconds 300`, with its serial fallback) is exactly what could have answered the whole-SoC-versus-thread question and it was cut off at 75 s. [O] `engine_rc` stayed at its initial `-1` and the folder was closed by the wrapper's `EXIT` trap, so the wrapper itself was terminated while the engine was still running; [D] nothing in `run-raw-stage-r95.sh` or `run-raw-campaign-r95.sh` has a timer that could do that, so the kill was external. This is a procedural rule for the orchestrator (put it in `DEVICE-READY.md`), not a script change.
- **Capture success** is a mechanical, human-read check on raw markers (no analyzer): `R95B cap-end id=1` present in `netconsole-closed.txt` with a line count and chain FNV matching the `R95B raw` lines, **and** `diagnostic_blob.txt` containing the same `cap-end` line and all 18 `R95B obj` headers, **and** `diagnostic_blob.txt.done`. Any later loss is a separate fact.
- **Freeze localisation** comes from three independent clocks: the last `R95B alive n=` line (kernel), the last `liveness.log` reply (host), and `phase.txt` / which `.done` files exist (host). A stop after `tierB-sealed` and before `tierC` completes, with zero MMIO, is the spontaneous-stop answer; a stop after Tier C only is a different question again.

### 5.5 Omit or defer

- Omit: `g5p_r82_endbank` and the slot-1/late `g5p_r85_irq_bank` read after TA end (kernel change below); any `render-fixed-*` command or `snapshot`/`fifo` after the TA; any cache maintenance (`g5p_table_clean_page`, `dsb(sy)` cache ops; the r84b visibility step stays dormant); the 19 post-TA `render_status` greps may stay (cached RAM, cheap).
- Defer to r95c: the optional end bank as a **separate** command `r95b-endbank` (default off in the runner, only after `tierC` and a sealed folder), printing `dev_emerg "R95B endbank reg i off"` before **each** `readl` so the last netconsole line names the register; and a RAM bin attribute `ta_phys` streaming the 4 MB of PM payload frames straight from `r->physical[i].cpu` (read-only, no copy into the blob).

## 6. Q5: what the builder changes

Create new `r95b` copies following the per-round pattern (r94 → r95). The r95 host files are hash-pinned; do not edit them in place. Kernel: a new branch `a9/tri95b` from `a9/tri95 @ 29134a97b7`, one commit, one patch beside `patches/gpu/0155-...`.

### 6.1 Kernel (`drivers/gpu/apple-g5p/`, line numbers of tri95)

| file:line | change |
|---|---|
| `r95-gate.h:16` | `#define G5P_R95_CFG_MAX 1U` → `2U` (update the header comment). `g5p_r95_cfg_valid` (`:27-35`) stays as is: cfg 2 has the same prerequisites. `g5p_r95_vcanary` (`:18`) is truthy for 2: **no gate-recipe change**. |
| `boot-r73b.inc:127-129` | `boot_r95_cfg` description: add "2 = cfg 1 plus a MMIO-free post-TA path and the R95B RAM capture" |
| `boot-r80.inc:94` (`struct g5p_r80`, the line with the `r84b_*` fields; add after it) | add `u32 r95_cfg, r95b_cap_done;` |
| `boot-r80.inc:567-575` `g5p_r95_latch` | `r->r80->r95_cfg = cfg;` keep `r82c_armed = 1`; add `ramonly=%u` to the `R95 latched` line |
| `boot-r80.inc:606` `g5p_r82_endbank` | extend the first guard: `if (!x \|\| !x->r82_endbank \|\| READ_ONCE(x->bank_done) \|\| x->r95_cfg == 2) return;` (the only call site is `boot-r73b.inc:1214`). The export then prints `R85 bank slot=2 name=end done=0 attempts=0` and `R82C fault done=0`, which is itself a raw marker. |
| `boot-r80.inc:447` `g5p_r85_irq_bank` | after the existing `exported` guard add `if (x->r95_cfg == 2 && READ_ONCE(x->end_ns)) return;` (`end_ns` is set by `g5p_r80_note_end`, the first statement of `g5p_r74h_end`, `boot-r80.inc:333`). Slot 0 and the pre-TA-end flight stay byte-for-byte as r95 so the TA still completes. |
| `render-r74h.inc:418` | after `g5p_r74h_phys(g, true);` add `g5p_r95b_capture(g);` |
| `render-fixed.inc:607` | forward declaration `static void g5p_r95b_capture(struct g5p_diag *g);` next to the `g5p_r74h_end` one |
| new `render-r95b.inc`, included at `render-fixed.inc:3496` after `#include "render-r94.inc"` | `g5p_r95b_capture()` as in 5.1, using `g5p_r74h_obj()`, `g5p_r33_fnv32()`, `sha256()`, `g5p_blob_hex()`, `g5p_blob_printf()`; the heartbeat `delayed_work` and a `devm_add_action_or_reset` to cancel it at unbind. **This file must contain no `readl/writel/dsb/dma_sync/clean_page`.** |
| `core.inc:551-554`, `boot-r73b.inc:1195-1215` | no change in r95b (export keeps its order; the end bank is already gone via the guard above). Fix the comment at `:1212`. |

### 6.2 Host/spec (new r95b copies)

| file | change |
|---|---|
| `scripts/gpu/r95b-spec.py` (from `r95-spec.py`) | `:42` `cfg95=1` → 2; `stage_params` `p['boot_r95_cfg'] = 1` → 2; `config_valid` (`:58-62`) accept `(0, 1, 2)`; `self_check` last assertion currently requires `config_valid(2, p)` to be **False**; flip it to True and require `config_valid(3, p)` False; keep the 22-key shape (`ENV_KEYS` unchanged: only a value changes) |
| `scripts/gpu/run-control-host-r95b-stage.sh` (from `run-control-host-r95-stage.sh`) | `:42` `"$s_cfg95" =~ ^1$` → `^[12]$`; `:45` `[ "$s_cfg95" = 1 ]` → `= 2`; every other `cfg95` comparison in `:38-59` follows the spec value; replace `:222-234` (the export-then-pull block) with a call to `capture_post_ta` from a new sourced `scripts/gpu/r95b-capture.sh` implementing 5.2-5.4; keep the `reachable=0` recovery branch (`:235-246`) unchanged |
| `scripts/gpu/write-ready-r95.py:124` pattern | extend the source check for the two `r95_cfg == 2` guards, the `g5p_r95b_capture(g)` call after `g5p_r74h_phys(g, true)`, and "no MMIO token in `render-r95b.inc`" |
| `scripts/gpu/check-r95-raw-fast.sh`, `payload-manifest`, `device-manifest` | re-pin (orchestrator) |
| `DEVICE-READY.md` | state: no SIGTERM during recovery; Tier D (end bank) is off |

### 6.3 Tiny preflight (no device, stubs only)

The campaign runner has no dry-run and kexecs the real iPad with a listener up (`campaign-dry-run-hits-device`); test only the new helper and the source tree.

1. `scripts/gpu/test-r95b-capture-order.sh`: put a stub `ssh`, `sha256_file` and a temp "folder" on `PATH`; `source r95b-capture.sh`; call `capture_post_ta`; assert from the stub's recorded argv: (a) the first `command` write is `r73b-export`, and it comes after five `cat` reads each followed by `<file>.done`; (b) no `r95b-endbank` string appears unless `GPU_R95B_ENDBANK=1`; (c) a stub failure on read k leaves reads 1..k-1 intact and `phase.txt` names step k; (d) no `reboot`/`kill`. About 40 lines.
2. `scripts/gpu/r95b-source-gates.sh <tree>`: (a) `grep -n 'x->r95_cfg == 2' boot-r80.inc` shows the guard inside both `g5p_r82_endbank` and `g5p_r85_irq_bank`; (b) `G5P_R95_CFG_MAX 2U`; (c) `grep -nE 'readl|writel|dsb|dma_sync|clean_page' render-r95b.inc` is empty; (d) `g5p_r95b_capture(g)` is called exactly once, right after `g5p_r74h_phys(g, true)`.
3. After the build: `python3 -B -I scripts/gpu/r95b-spec.py --check`, and `strings Image | grep -c 'R95B cap-end'` ≥ 1.
4. Free on-device check (no GPU command): the existing param readback loop (`CH:168-172`) already requires `boot_r95_cfg=2` to read back as 2.

## 7. What stays open

- [U] Whether the stop was the end bank (rank 1), IRQ slot 1 (rank 2), or independent of the host (rank 3). r95b is built so a repeat either returns the TA output bytes and shows which, or returns them and shows it was neither.
- [U] Whether the SoC or only one thread stopped. The freeze premise comes from the task, not from the folder. The cheapest discriminator needs no device: ask the orchestrator what was seen between 16:29:16 and the 16:30:03 reboot (ssh refused versus hung, display state, whether the reboot was a deliberate DFU). That answer separates "SoC stopped" from "export thread stuck or `sudo` hung" better than anything r95b can add; r95b's recovery path (never killed) then confirms it with `collect-hang-evidence.sh`.
- [U] Whether `first_g728_ns` was set in r95 (the timeline was never exported); Tier A does not add it, and `R80 times` will appear in the Tier C blob if the export completes.
- [U] How long after retirement the firmware gates the GPU; the heartbeat timestamps give a lower bound if a stop recurs without MMIO.
