import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from frame_map import far, frame_sequence
from readback_compare import FRAME_WORDS

SEGBIT = re.compile(r'^(CLBLM_[LR])\.SLICEM_X0\.([A-D])LUT\.INIT\[(\d+)\]$')


def lutram_bels(placement):
    top = [m for m in json.load(open(placement))['modules'].values() if m.get('attributes', {}).get('top')][0]
    out = set()
    for c in top['cells'].values():
        a = c.get('attributes', {})
        kind = str(a.get('X_ORIG_TYPE', ''))
        if kind.startswith(('RAM', 'SRL')) and not kind.startswith('RAMB'):  # block RAM frames are masked whole
            out.add(a['NEXTPNR_BEL'])
    return sorted(out)


def main():
    part, tilegrid, db, placement, out = sys.argv[1:6]
    seq = frame_sequence(part)
    index = {}
    for i, (bus, half, row, col, minor) in enumerate(seq):
        if bus != 'PAD':
            index[far(bus, half, row, col, minor)] = i
    mask = [0] * (len(seq) * FRAME_WORDS)
    bram = 0
    for i, s in enumerate(seq):
        if s[0] == 'BLOCK_RAM':
            for w in range(FRAME_WORDS):
                mask[i * FRAME_WORDS + w] = 0xFFFFFFFF
            bram += 1
    grid = json.load(open(tilegrid))
    site_tile = {site: name for name, t in grid.items() for site in t.get('sites', {})}
    init = {}
    for ttype in ('clblm_l', 'clblm_r'):
        for line in open(os.path.join(db, f'segbits_{ttype}.db')):
            p = line.split()
            m = SEGBIT.match(p[0])
            if m:
                for b in p[1:]:
                    mi, bi = b.lstrip('!').split('_')
                    init.setdefault((m.group(1), m.group(2)), []).append((int(mi), int(bi)))
    bels = lutram_bels(placement)
    luts = {(b.split('/')[0], b.split('/')[1][0]) for b in bels}
    nbits = 0
    for site, letter in sorted(luts):
        tile = site_tile[site]
        t = grid[tile]
        b = t['bits']['CLB_IO_CLK']
        base = int(b['baseaddr'], 16) if isinstance(b['baseaddr'], str) else b['baseaddr']
        for minor, pos in init[(t['type'], letter)]:
            fi = index[base + minor]
            w = fi * FRAME_WORDS + b['offset'] + pos // 32
            mask[w] |= 1 << (pos % 32)
            nbits += 1
    with open(out, 'wb') as fh:
        fh.write(struct.pack(f'>{len(mask)}I', *mask))
    print(f'mask: {bram} BLOCK_RAM frames, {len(luts)} distributed-RAM LUTs ({nbits} INIT bits): {sorted(luts)}')


if __name__ == '__main__':
    main()
