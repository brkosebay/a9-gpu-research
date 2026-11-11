#!/usr/bin/env python3
"""Rebuild the META firmware's memory image from the extractor output, then disassemble it.

usage: disassemble-ldr.py EXTRACTED_DIR OUTDIR [--objdump PATH] [--docker-image IMAGE]

EXTRACTED_DIR is the output of extract-kext-firmware.py (meta-ldr.json plus the
meta-load-*.bin payloads). Every 'load' record is placed at its destination and
'zero' records are zero-filled. Contiguous records are merged into regions
(bases and ends rounded to --align; a new region starts at a gap of more than --gap bytes), so no chip-specific
address map is assumed. For each region this writes <base>.bin and, with a META
objdump (build-metag-binutils.sh), <base>.dis. Regions are listed in regions.json.

The objdump is a Linux binary. On a Linux host pass --objdump; on macOS pass
--docker-image (any Linux image with the binutils prefix mounted at /tools).
Keep OUTDIR out of public repositories: the images are Apple firmware.

Most META firmware code on the A9 is MINIM (16/32-bit compressed encodings),
which GNU objdump decodes as garbage; see minim.py for the expander we used.
"""
import argparse, hashlib, json, pathlib, subprocess


def regions(records, gap, align):
    spans = sorted((r['destination'] & ~(align - 1), -(-(r['destination'] + r['size']) // align) * align)
                   for r in records if r['kind'] in ('load', 'zero'))
    out = []
    for a, b in spans:
        if out and a <= out[-1][1] + gap:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('extracted', type=pathlib.Path)
    ap.add_argument('out', type=pathlib.Path)
    ap.add_argument('--gap', type=lambda x: int(x, 0), default=0x8000)
    ap.add_argument('--align', type=lambda x: int(x, 0), default=0x400)
    ap.add_argument('--objdump', help='path to metag-linux-objdump (Linux host)')
    ap.add_argument('--docker-image', help='run the objdump in this Linux image; --tools-dir is mounted at /tools')
    ap.add_argument('--tools-dir', type=pathlib.Path, help='binutils prefix (contains bin/metag-linux-objdump)')
    a = ap.parse_args()
    j = json.loads((a.extracted / 'meta-ldr.json').read_text())
    a.out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for base, end in regions(j['records'], a.gap, a.align):
        b = bytearray(end - base)
        for r in j['records']:
            if r['kind'] != 'load' or not base <= r['destination'] < end:
                continue
            p = (a.extracted / r['path']).read_bytes()
            assert hashlib.sha256(p).hexdigest() == r['sha256'], r['path']
            o = r['destination'] - base
            b[o:o + len(p)] = p
        name = f'{base:08x}.bin'
        (a.out / name).write_bytes(b)
        manifest.append({'base': hex(base), 'size': len(b), 'sha256': hashlib.sha256(b).hexdigest()})
        args = ['-D', '-b', 'binary', '-m', 'metag', f'--adjust-vma={base:#x}']
        if a.objdump:
            cmd = [a.objdump] + args + [str(a.out / name)]
        elif a.docker_image and a.tools_dir:
            cmd = ['docker', 'run', '--rm', '-v', f'{a.out.resolve()}:/fw', '-v', f'{a.tools_dir.resolve()}:/tools',
                   a.docker_image, '/tools/bin/metag-linux-objdump'] + args + [f'/fw/{name}']
        else:
            continue
        with (a.out / f'{base:08x}.dis').open('w') as f:
            subprocess.run(cmd, stdout=f, check=True)
    (a.out / 'regions.json').write_text(json.dumps(manifest, indent=2) + '\n')
    for m in manifest:
        print(m['base'], m['size'])


if __name__ == '__main__':
    main()
