# R18c — dedicated pre-release context0 VA0 sink

Head `9e54857fd20cd6eab95c91ca58a881f60effbca2` on `a9/gpu`.
Apply patch0039 on r18b `98bec623190117c834744f983fb40118c449c97d`.
The implementation agent made no device calls or workspace commits.

Ranked commands, each on its own fresh integrated r18c boot:

*(Device/host command block omitted; it targets the private workspace.)*

The first uses default policy7 (META+6c8=0), the second policy10
(META+6c8=1 and its existing coefficient/timing changes), and the third is
ACK-only with no sink, default policy7. Do not interpret policy7→10 as a
single-bit comparison. Policy9 is also selectable by setting
`GPU_DIAG_DC_VARIANT=9`. Sink and ACK default to0; no implicit ACK is enabled
by a sink run. The prior cache3 preamble is held fixed for these commands.

## Exact mapping and lifetime

`GPU_MMU_VA0_SINK=1` selects `mmu_setup_variant=1`, latched at initial map.
The helper runs before maps_ready, arm and release. It allocates **three
separate zeroed16KiB coherent DMA pages** for the sink directory, leaf table
and backing. It publishes only boot catalogue[0]→directory[0]→leaf[0].
Leaf flags0 produce valid writable `PA|1`, matching the recovered optional
iOS dummy-tree flags; directory/catalogue use the existing recovered encoders.
Only VA `[0,4000)` is mapped; all neighboring holes remain absent. The
firmware catalogue slot387 and its directory/leaves are preserved. This is
not an all-address fallback or a claim that normal iOS boot maps VA0.

The backing is distinct from R0+e160's scratch page, firmware/root/shared
memory and all compute resources. Catalogue publication follows a DMA
barrier after filling the new tables. No live page-table patching occurs.
Allocation failure does not publish cat[0]; outer map failure is terminal.
Resources remain retained with the existing boot DMA lifetime until reboot.
Selectors2/3 (unverified PBE/ISP and fault-control deltas) stay unsupported.

The context0 boot catalogue receives this mapping. A subsequently attached
context1 compute catalogue retains its original mappings and shares only
the reserved firmware directory. It does not inherit catalogue[0] or alias
the sink. The PTE inspector recognizes the new owned directory/leaf pages.

## Evidence to collect

Observer revision182 is required. The r18c scripts are new; r18b/r18 scripts
are unchanged. The runner explicitly sets sink0/1, ACK0/1, and defaults the
fault-inspection VA to0 based on round11/12's decoded address. Setting
`GPU_MMU_FAULT_VA` still selects another explicit address. Host log names
include sink and ACK selectors. Cached mmu_history, diagnostic_status and
diagnostic_blob are copied separately exactly as in r18b; bulky dumps stay
out of dmesg. Both frontends preserve all release-boundary observations.

First require `MMU sink-installed VA=0 bytes=4000 context=0 leaf_flags=0`
and the full parent/PTE mapping in diagnostic_blob before release. The desired
fault-prevention sample is:

`MMU reset-released event130=00000000 pending=0 ...`

Check the earlier new release-boundary samples too; a clean later sample
alone cannot exclude a transient firmware-handled fault. If the fault moves
from level2 to a lower-level fault, inspect the exact parent/PTE entries;
that is not prevention. A different address/context is also not success.

Each stage also records `MMU sink <stage> nonzero_bytes=... first=...` in
retained history and compact dmesg. The initial backing is all zero. A
nonzero CPU-visible byte is captured by one full first-change blob dump;
subsequent stages retain nonzero counts/first offsets. Zero writes are
invisible to this check, and CPU RAM snapshots do not establish GPU cache
contents. A missing change does not prove no PBE transaction occurred.

After a clean release, still require 1728.bit0 to clear, actual dispatch,
firmware stamp1, output12345678 and intact sentinels. A clean fault sample
or an ACK-only cleared event is not GPU acceleration. The bounded one-shot
ACK variant, quarantine, failure park and no-retry behavior are preserved.

## Offline validation

`scripts/gpu/check-round18c.sh` exercises production sink construction with
all three allocation failures, pre-release/reuse guards, exact cat0/dir0/
leaf0 encodings, absent neighboring entries, separate zero backing and
observed mutation; production owned-table walking with the dedicated tables;
the inherited exact ACK/release-boundary, cache, policy, buffer-retention and
runner suites; both W=1 frontends; strict checkpatch and diff checks.
`tools/gpu/test_sink_runner_r18c.py` checks12 wrapper combinations against
fake sysfs, including sink+policy7/9/10, independent ACK, invalid inputs and
old revision rejection. No device or network action is performed by tests.
Logs: `build/gpu/round18c-targeted.log`, `build/gpu/round18c-build.log`.

Validation completed: targeted script exits0 (53 runner cases and12 wrapper
combinations plus sanitizer/driver checks); full Image.gz +104 DTBs exits0.
`build/kernel-gpu/COMMIT` matches the head above; DIRTY and kernel worktree
status are empty. GPU fault prevention and completion await the orchestrator.
