import argparse
import struct
import sys

SYNC = b'\xaa\x99\x55\x66'
FRAME_WORDS = 101
FDRI = 2


def fdri_words(path):
    data = open(path, 'rb').read()
    i = data.find(SYNC)
    if i < 0:
        raise ValueError(f'{path}: no sync word')
    words = struct.unpack(f'>{(len(data) - i - 4) // 4}I', data[i + 4:i + 4 + ((len(data) - i - 4) // 4) * 4])
    out, k, reg = [], 0, None
    while k < len(words):
        w = words[k]
        kind = w >> 29
        if kind == 1:
            reg = (w >> 13) & 0x3FFF
            n = w & 0x7FF
            if reg == FDRI and n:
                out.extend(words[k + 1:k + 1 + n])
            k += 1 + n
        elif kind == 2:
            n = w & 0x7FFFFFF
            if reg == FDRI:
                out.extend(words[k + 1:k + 1 + n])
            k += 1 + n
        else:
            k += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('bit'); ap.add_argument('readback'); ap.add_argument('--mask-words'); ap.add_argument('--log')
    a = ap.parse_args()
    expected = fdri_words(a.bit)
    rb = open(a.readback, 'rb').read()
    rbw = struct.unpack(f'>{len(rb) // 4}I', rb[:len(rb) // 4 * 4])
    got = rbw[FRAME_WORDS:FRAME_WORDS + len(expected)]
    if a.mask_words:
        mw = open(a.mask_words, 'rb').read()
        mask = list(struct.unpack(f'>{len(mw) // 4}I', mw))
    else:
        mask = [0] * len(expected)
    if len(mask) != len(expected):
        raise ValueError(f'mask FDRI length {len(mask)} != bit FDRI length {len(expected)}')
    short = len(got) < len(expected)
    mism = masked = 0
    first = []
    for idx, (e, g, m) in enumerate(zip(expected, got, mask)):
        masked += bin(m).count('1')
        d = (e ^ g) & ~m & 0xFFFFFFFF
        if d:
            mism += bin(d).count('1')
            if len(first) < 10:
                first.append(f'word {idx} (frame {idx // FRAME_WORDS}, offset {idx % FRAME_WORDS}): expected {e:08x} read {g:08x}')
    ok = mism == 0 and not short
    line = (f"READBACK_COMPARE {'PASS' if ok else 'FAIL'} words={len(expected)} readback_words={len(rbw)} "
            f"masked_bits={masked} mismatched_bits={mism} mask={'placement' if a.mask_words else 'none'} method=UG470-6-method2")
    print(line)
    for f in first:
        print('  ' + f)
    if a.log:
        with open(a.log, 'w', encoding='utf-8') as fh:
            fh.write(line + '\n' + ''.join('  ' + f + '\n' for f in first))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
