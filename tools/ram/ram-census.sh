#!/bin/sh
# Read-only, stdout only. Run as root for all-process PSS/debugfs/dmesg.
# Does not mount debugfs, scan GPU registers, change policy or stop the desktop.
exec python3 - "$@" <<'PY'
import datetime, glob, gzip, os, pathlib, re, subprocess, sys
P = pathlib.Path

def read(path):
    try: return P(path).read_text(errors='replace')
    except OSError as e: return 'UNAVAILABLE: %s\n' % e

def section(title, body):
    print('\n== ' + title + '\n' + body.rstrip())

print('RAM-CENSUS v1', datetime.datetime.now(datetime.timezone.utc).isoformat(),
      'label=' + (sys.argv[1] if len(sys.argv)>1 else 'snapshot'))
section('identity', read('/proc/sys/kernel/random/boot_id') + read('/proc/cmdline') + str(os.uname()))
m = {}
raw = read('/proc/meminfo')
for key, value in re.findall(r'^(\w+):\s+(\d+) kB', raw, re.M): m[key] = int(value)
section('meminfo (KiB; overlapping views)', raw)
section('cache estimates (KiB)', 'file_cache_excluding_shmem=%d\nfile_cache_plus_buffers=%d\nCMA_in_use=%d' %
        (max(0,m.get('Cached',0)-m.get('Shmem',0)),
         max(0,m.get('Cached',0)-m.get('Shmem',0))+m.get('Buffers',0),
         m.get('CmaTotal',0)-m.get('CmaFree',0)))
section('physical ranges (nested iomem: do not sum)', read('/proc/iomem'))
for path in ('/sys/kernel/debug/memblock/memory','/sys/kernel/debug/memblock/reserved',
             '/sys/kernel/kexec_crash_size','/sys/kernel/kexec_crash_loaded'):
    section(path, read(path))
try:
    config = gzip.decompress(P('/proc/config.gz').read_bytes()).decode()
    section('running config', '\n'.join(l for l in config.splitlines() if re.search(
        'LOG_BUF|LOG_CPU|PRINTK_EXECUTION|CMA_SIZE|LRU_GEN|ZRAM|ZSWAP', l)))
except (OSError, EOFError): print('running config unavailable; supply matching packaged config')
try:
    r = subprocess.run(['dmesg'], capture_output=True, text=True, timeout=5)
    section('boot/driver accounting receipts (historical; NOT current totals)', '\n'.join(
        l for l in r.stdout.splitlines() if re.search(
        r'Memory:|reserved mem|Reserved memory|log_buf_len|printk:|crashkernel|cma:|SWIOTLB|swiotlb|G5P.*(pool|pages|bytes|pinned)|RENDER-V3.*(pool|pages|trim)|firmware.*(size|bytes)',l,re.I))
        if r.returncode == 0 else r.stderr)
except (OSError, subprocess.TimeoutExpired) as e: print('dmesg unavailable:',e)
for kind in ('g5p_bos', 'adbe_bos'):
    paths = sorted(glob.glob('/sys/kernel/debug/dri/*/' + kind))
    section(kind + ' (one alias only)', read(paths[0]) if paths else 'UNAVAILABLE (not zero)')
print('GPU arena/firmware: BO inventory above; arena committed/live requires winsys log, '
      'private coherent firmware/PM/page-table bytes lack a complete rc2 counter. UNKNOWN, not zero.')
rows=[]; missed=0
for proc in P('/proc').iterdir():
    if not proc.name.isdigit(): continue
    try:
        sm = (proc/'smaps_rollup').read_text()
        v = {k:int(n) for k,n in re.findall(r'^(\w+):\s+(\d+) kB',sm,re.M)}
        name = (proc/'comm').read_text().strip().replace('\t',' ')
        rows.append((v.get('Pss',0),int(proc.name),name,v))
    except (OSError,ValueError): missed+=1
section('process PSS (KiB; includes mapped GEM, do not add to GPU)',
        'pid\tcomm\tPSS\tRSS\tPSS_anon\tPSS_file\tPSS_shmem\tSwapPSS')
for pss,pid,name,v in sorted(rows, reverse=True):
    print('\t'.join(map(str,[pid,name]+[v.get(k,0) for k in
        ('Pss','Rss','Pss_Anon','Pss_File','Pss_Shmem','SwapPss')])))
print('SUM_PSS_KiB=%d SUM_SwapPSS_KiB=%d unreadable_or_raced=%d (includes kernel threads)' %
      (sum(r[0] for r in rows),sum(r[3].get('SwapPss',0) for r in rows),missed))
section('swaps', read('/proc/swaps'))
for dev in sorted(glob.glob('/sys/block/zram*')):
    raw=read(dev+'/mm_stat'); section(dev+'/mm_stat (bytes)',raw)
    try:
        orig,comp,used=map(int,raw.split()[:3])
        print('payload_ratio=%.3f effective_ratio=%.3f net_payload_saved_MiB=%.3f' %
              (orig/comp if comp else 0,orig/used if used else 0,(orig-used)/1048576))
    except ValueError: pass
    section(dev+'/comp_algorithm',read(dev+'/comp_algorithm'))
for path in ('/proc/pressure/memory','/proc/pressure/cpu','/proc/pressure/io',
             '/proc/stat','/sys/module/zswap/parameters/enabled',
             '/sys/kernel/mm/lru_gen/enabled','/sys/kernel/mm/transparent_hugepage/enabled'):
    section(path,read(path))
section('reclaim counters (take differences between snapshots)', '\n'.join(
    l for l in read('/proc/vmstat').splitlines() if re.match(r'(pswp|pgscan|pgsteal|allocstall|oom_kill|compact)',l)))
print('\nNOT A BALANCE: MemAvailable is an estimate; CMA is in MemTotal; slab includes '
      'SReclaimable/SUnreclaim; Cached includes Shmem; GPU BO/import/PSS overlap. '
      'Firmware/boot exclusions require early receipts. Snapshot is sequential, not atomic.')
PY
