# Whole-SoC freeze on Firefox context churn: root cause and fix spec (2026-11-09, rev 2)

Freeze lane, static RE only, no device runs. Rev 2 folds in the 11:25 repro: identity step only, on
vdm-warmport with Mesa r39-9.1 (`build/gpu/r39-11-kernel/device/netconsole.log`). Tree read:
`build/orchard-pr2/cs/skiptiles-kwork/kernel/source` (0030/0031 included; the lifecycle code is the
same as vdm-long). [V] = code/Ghidra, [P] = logs, [I] = inference.

## 1. What the repro settles

- **Mesa is out.** So are the recovery path and silent-loss detection. The lock needs no `lost`.
  The last line is `park slots=12/11 parks=12` at 238.213 [P]. That park DC3 was consumed and verified,
  so the firmware and the MMU invalidate were still alive after the close.
- **Userspace lived for seconds after it.** So the CPU did not stall on the close/park host MMIO
  (`g5p_rv3_dc_kick`: R1+0x14, R1+0x1000, R0+0xb00). A CPU stalled on a Device-nGnRnE access takes
  the other core down within milliseconds (mmio-access §1.2).
- The SoC died during the jobs that followed: the new Firefox (8/7) plus labwc (10/9). With err+ consoles
  those jobs print nothing.
- **The lifecycle is deterministic.** Every launch unparks the pair the launch before last
  parked and binds an identical VM to it. The tag is the packed descriptor-change count
  (`g5p_vm_generation`, `vm-mutation.h`), and it is identical per mode: 0140622f on 8/7 (software WebRender, the frozen launch 12), 0143cd32 on 12/11 (hardware). Then the
  previous process's deferred close runs (`unbind why=close` → CBASE 0, then `park`). The VM's
  tables, BOs and PM pool pages are freed right after.
- One observation so far: a lock at launch 12 after 11 clean launches. That suggests a timing or cache-residency race on
  a deterministic sequence.

## 2. Mechanism (re-ranked)

**M-A, most likely (≈55 %): a GPU-originated fabric stall from MMU or memory state outliving a
teardown.** A GPU walk or write resolves through freed memory to a non-DRAM physical address,
and the access never completes. So there is no MMU fault and no event. The firmware stalls, and the
host dies at its next GPU register access: the next bell, which during the identity step's 3 s about:support
sleep may come seconds later. That is why the frozen screen is always about:support. This fits "no lost line,
userspace alive briefly".

Why our stack, and not iOS:
- **Invalidation is PC-level only.** The firmware DC3 handler `1000218c` and the per-kick tag compare `10017ac4`
  issue only `e138=(S<<3)|4` (PC level). They never issue PD/PT (`render-user-mmu.h`, `boot-r74g.inc`) [V].
  Our render path adds nothing: `render_user_mmu_inval` is compiled `(0)`, and the compute `|7` invalidate is not in
  this tree [V]. PD/PT cache lines for the reused context ID can therefore point into the
  previous owner's **freed** table pages. Every Firefox process has the same VA layout, so the new owner hits exactly
  those lines. The pages are back in the kernel allocator (`g5p_vm_release` → `dma_free_coherent`), and their
  contents become arbitrary PTEs [I].
- **PM state.** The PM pool list holds **physical** PA>>12 entries, not VAs (firmware-re README §PM). The PM
  also writes a released context's F back "two switches later" (`render-user-pmset.h`, release8
  quiet2 seq 858/893) [V]. Late PM work for a released set can therefore address freed pool pages [I].
- **The iOS difference is the power cycle, not the protocol.** `AGXGart_detachSlotsAndDestroyAddressSpace`
  `6caef14` does what our close does: publish PA/tag 0 per slot, DC3, wait for
  `AGXFirmware_waitDeviceControlConsumed` [V], then release the `param_1[0x3e+i]` objects at once,
  which are most likely the table levels [I]. iOS gets away with it because its GPU parks
  between bursts: GPC 0 on 96.6 % of idle samples (mmio-access §1.2). That completes PM write-back and drops
  GPU-side state before a release (perf60-clock.md:874). Linux runs **never-park**, so
  nothing ever empties those caches [I].

**M-B (≈20 %):** late work of the closed context walks its slot in the ~14 ms between
`unbind why=close` (the DC3 handler installs **CBASE 0**, i.e. a catalogue read at PA 0) and `park`. This is weakened by the
park consuming normally afterwards.

**M-C (≈15 %):** an R0 bell at a bad GPC moment in the new context's first submits (the perf60c class).
Weak: release8 holds the GPC at pstate 4 (`gpc=00000004` on every kick) and Apple writes b00 at any nibble.

**M-D:** the rev-1 recovery-path power cut. It is real, but it is not this repro. Its fix stays, as patch 0033.
Post-loss access inventory (Q1a, 0030 kernel):
- `g5p_rv3_lose_recover`: RAM plus `mmio_gate`, under `event_lock`.
- Job `out:` path: RAM. The l123 PMGR read is compiled out.
- Scheduler: `close_deferred` is skipped.
- IRQ thread `g5p_r74f_ring` (R1, R0+0xb00): gated by `b->failed` under `event_lock`.
- `dc_kick` and legacy unbind: gated by `mmio_off` and by `failed‖stopped`.
- `fault_read` (R0 e150..): runs before the `lost` line.
- `g5p_recover`: AIC ack (always-on), then **PMGR gfx off with no Fender stop**, then Fender wake, then the boot stages.

iOS's restart tail (`reportFaultAndRestartChannels` `6c81dac` → `stopForRecoveryOptionalPowerCycle` `6ca1e40`) always stops
first. Its `setPlatformPower(0)` panics unless the Fender is stable-off.

## 3. Discriminating flights (identity-churn.sh, 48 launches each, ≈16 min; base rate ≈4 locks)

One kernel, three live 0600 params, default 0. Flip one per flight and use no other change. This is not variant
guessing: each flight answers one yes/no question.
- **F1 `render_pt_pool=1`:** page-table pages never return to the kernel (§4.1). Clean at 48 launches means a
  stale walk through freed tables (M-A, MMU half).
- **F2 `render_close_hold_ms=2000`:** a closed context's BO, pool and aux pages are kept for 2 s **and** ≥2
  distinct-context jobs after its park (§4.2). Clean means late GPU writes to freed data (M-A, PM half).
- **F3 `render_pair_fresh=1`:** `g5p_ru_slot_pair` hands out pairs monotonically and never reuses one within the boot.
  The firmware arrays are 256 wide and the selectors take any 8-bit slot (multi-client-design R2), which gives about 120 pairs.
  Clean with F1/F2 off means per-context-ID state (stale PD/PT for that ID). A lock means memory reuse.
- If all three still lock: M-B/M-C.
- Every flight carries patch 0033 and the §4.3 crumbs. F1 turns a stale walk into an MMU fault, and that fault must
  not then hit the M-D power cut.

## 4. File-level fix spec (patch 0032, Codex: build and stop, no tests)

**4.1 `drivers/gpu/drm/apple-g5p/drm-vm.inc`, table-page pool (also the containment fix if F1 is clean).**
- Add `struct g5p_pt_pool {spinlock; list; count}` in `struct g5p_drm`. `g5p_vm_alloc_page()` takes from the pool first.
- `g5p_vm_release()` and `g5p_vm_prune()` push table pages and the VM root into the pool
  **after `memset(0)` plus `g5p_table_clean_page()`** instead of `dma_free_coherent`.
- Freed only at driver remove. Gate it with `render_pt_pool` (0600, the param read at release time).
- A stale PD/PT line then always lands on a zeroed or valid GPU table page (a fault at worst), never on a wild PA.
- emerg line once per 64 pushes: `G5P pt-pool pages=`.

**4.2 `drm-render-unbind.inc` / `drm-render-v3.inc`, close hold.**
- In the close item after a verified `g5p_rv3_park`, move the context's last references (BO pins, pool and aux pages,
  `ctx->ref`) onto `rd->close_hold[]` with `park_ns` and `rd->switches` at park.
- `g5p_render_close_deferred()` drops entries once `ktime >= park_ns + hold` and
  `rd->switches - at >= 2`. Count `rd->switches` where `pm_prev/pm_last` advance.
- Bounded to 8 entries. When full, drop the oldest that meets its condition, otherwise hold the next bind (the job is requeued).
- Recovery drops the hold only after a verified cycle, as with bindings today.

**4.3 Breadcrumbs (always on, low volume).** `dev_emerg` + `pr_flush(50,false)`. netconsole is NBCON with
a printer thread (`netconsole.c:2699`), so unflushed lines die with the SoC.
- Gated jobs: for 10 s after any bind or close, i.e. every job of the new context and of labwc in that window.
- In each gated job, bracket every GPU register access: R1 wake, R0+0xb00 (in `g5p_wk_ring`, `g5p_rv3_dc_kick`
  and `g5p_r74f_ring`).
  - `RENDER-V3 crumb pre seq= slots= what=` followed by `pr_flush` goes **before** the access.
  - A plain `crumb post` goes **after** it.
- Also emit crumbs at TA/3D completion, carrying `pmset= pm_last= pm_prev=`.
- Reading: "pre arrives, post doesn't" means the register access stalled the core, i.e. the GPU was already wedged
  (M-A or M-C). "Post arrives, then silence" means something else.
- Add `set=` to the `bind` and `park` lines.

**4.4 Patch 0033 (containment, from rev 1, unchanged).** In `recover.inc` `g5p_recover()`, insert
Apple's `stopFirmwareForPowerDown` (`6c9fa10`: `AGXMetaFender_setGPUCorePower(0)` `6ca6544`, then
`setGPCPerformanceState(0)` `6ca4ccc`) via `g5p_fender_idle()` with a 1 s recovery `g5p_fender_io`.
Then poll stable-off as `AGXMetaFender_isStableOff` `6ca6684` does: R1+0[31:30]==1 and GPC nibble 0, for up to 200 ms.
**Never** run `g5p_kq_cycle` on an unproven stop: mark the boot failed and return `-ETIMEDOUT`, the same rule as
`g5p_idle_work`. Apple's `setPlatformPower` `6ca0f78` panics in that state.
Markers, each followed by `pr_flush`: `fender-pre`, `fw-stop`, `stable-off`, `cycle-begin/done`.
After wake, refuse the boot stages unless (R1+0x1000&0x1f)==1 (also add this check to `g5p_fender_wake_once`, `core.inc`).
Every early `-EPERM` predicate and every `g5p_rv3_recover` trylock timeout gets its own emerg line.

**Apple-way end state (after F1–F3 answer).** If M-A is confirmed, the faithful fix is iOS's ordering:
a GPU park (GPC 0 → stable-off, Fender path) between the last job referencing a closed context
and the free of its memory. 4.1 and 4.2 are the RAM-only equivalent we can run without reopening park-mode R0 risks.

## 5. iOS probe requests (read-only, orchestrator runs them)

1. ios-mmio-reader at 10 kHz on R1+0 and R1+0x1000 while an app is killed and another
   GPU app is launched straight after. Does iOS reach GPC 0 / R1+0[31:30]==1 between the old process's last submit
   and the new one's first? (This tests the "free power cycle" in M-A.)
2. Same loop: log `GPURestart*` and kdebug `0x85930c10/0c0c`. iOS should show no restart on churn.
*(Passage removed: boot-chain or iOS-side tooling detail, out of scope for this repository.)*
