import re

BUS_TYPE = {'CLB_IO_CLK': 0, 'BLOCK_RAM': 1, 'CFG_CLB': 2}


def parse_part(path):
    cols, half, row, bus = {}, None, None, None
    for line in open(path, encoding='utf-8'):
        s = line.rstrip()
        m = re.match(r'^  (top|bottom): ', s)
        if m:
            half = m.group(1); continue
        m = re.match(r'^      (\d+): ', s)
        if m:
            row = int(m.group(1)); continue
        m = re.match(r'^          (CLB_IO_CLK|BLOCK_RAM|CFG_CLB): ', s)
        if m:
            bus = m.group(1); continue
        m = re.match(r'^ +frame_count: (\d+)', s)
        if m:
            cols.setdefault((bus, half, row), []).append(int(m.group(1)))
    return cols


def frame_sequence(path):
    cols = parse_part(path)
    seq = []
    for bus in ('CLB_IO_CLK', 'BLOCK_RAM', 'CFG_CLB'):
        for half in ('top', 'bottom'):
            rows = sorted(r for (b, h, r) in cols if b == bus and h == half)
            for row in rows:
                for c, n in enumerate(cols[(bus, half, row)]):
                    for minor in range(n):
                        seq.append((bus, half, row, c, minor))
                seq.extend([('PAD', half, row, None, None)] * 2)
    return seq


def far(bus, half, row, col, minor):
    return (BUS_TYPE[bus] << 23) | ((1 if half == 'bottom' else 0) << 22) | (row << 17) | (col << 7) | minor
