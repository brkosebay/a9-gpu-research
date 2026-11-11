#!/usr/bin/env python3
"""Parse a g5p_gpu_stats snapshot (our kernel driver's debugfs counters) into GPU ms/frame and GPU busy %.

usage: gpu-stats.py STATS_FILE [--frames N] [--window-ms MS] [--json]
       gpu-stats.py - < STATS_FILE

The file is one line of key=value pairs, reset by writing 0 to it. The keys our
driver prints (2026-11): now_ns since_ns jobs failed ta_ticks td_ticks ioctl_ns
queue_ns prep_ns ta_wait_ns gap_ns td_wait_ns tail_ns touch_ns bell_ns samples
ta_irq_ns td_irq_ns ta_decide_ns td_decide_ns joint ovh_ns ahead ... .

ta_ticks / td_ticks are firmware timestamps of geometry (TA) and fragment (3D)
work, in ticks of the 24 MHz reference clock. GPU busy time is their sum; it
over-counts wall-clock busy time when the TA of one job runs under the 3D of the
previous one (our pipelined kernels do that), so treat busy % as an upper bound
there. since_ns..now_ns is the window since the last reset; pass
--window-ms to use your own wall-clock window instead. Without --frames, only
per-job figures are printed.

Port to your driver: keep the idea, not the names. Count GPU-side time from the
firmware's own start/end stamps per job, accumulate per engine, and expose a
resettable snapshot; then GPU ms/frame = busy / frames, which is the number that
tells you whether the GPU or the CPU/kernel path is the bottleneck.
"""
import argparse, json, re, sys

TICK_HZ = 24_000_000


def parse(text):
    out = {}
    for k, v in re.findall(r'(\w+)=([0-9,]+)', text):
        out[k] = [int(x) for x in v.split(',')] if ',' in v else int(v)
    return out


def summarise(s, frames=None, window_ms=None):
    g = lambda k: s.get(k, 0) if isinstance(s.get(k, 0), int) else 0
    ta_ms, td_ms = g('ta_ticks') / TICK_HZ * 1e3, g('td_ticks') / TICK_HZ * 1e3
    gpu_ms = ta_ms + td_ms
    win = window_ms if window_ms else (g('now_ns') - g('since_ns')) / 1e6
    jobs = g('jobs')
    r = dict(jobs=jobs, failed=g('failed'), window_ms=round(win, 3), gpu_ms=round(gpu_ms, 3),
             ta_ms=round(ta_ms, 3), td_ms=round(td_ms, 3),
             gpu_busy_pct=round(gpu_ms / win * 100, 2) if win > 0 else None)
    if jobs:
        r.update(gpu_ms_per_job=round(gpu_ms / jobs, 4),
                 ta_wait_ms_per_job=round(g('ta_wait_ns') / jobs / 1e6, 4),
                 td_wait_ms_per_job=round(g('td_wait_ns') / jobs / 1e6, 4),
                 host_overhead_ms_per_job=round(g('ovh_ns') / jobs / 1e6, 4),
                 bell_us_per_job=round(g('bell_ns') / jobs / 1e3, 3))
    if frames:
        r.update(frames=frames, gpu_ms_per_frame=round(gpu_ms / frames, 3),
                 jobs_per_frame=round(jobs / frames, 3))
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('stats')
    ap.add_argument('--frames', type=float)
    ap.add_argument('--window-ms', type=float)
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    text = sys.stdin.read() if a.stats == '-' else open(a.stats).read()
    r = summarise(parse(text), a.frames, a.window_ms)
    print(json.dumps(r) if a.json else ' '.join(f'{k}={v}' for k, v in r.items()))


if __name__ == '__main__':
    main()
