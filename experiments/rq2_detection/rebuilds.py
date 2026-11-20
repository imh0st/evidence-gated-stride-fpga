import sys
from pathlib import Path

HERE = Path(__file__).absolute().parent
sys.path.insert(0, str(HERE.parent))
import common as c
from run import DESIGN, RESULTS, RQ1, check

K = 4
RECHECK = "--recheck" in sys.argv


def config_digest(bdir, flow):
    import hashlib
    import re
    f = c.programming_file(bdir)
    data = f.read_bytes()
    if flow in ("vivado", "openxc7"):
        i = data.find(bytes.fromhex("aa995566"))
        return hashlib.sha256(data[i:] if i >= 0 else data).hexdigest()
    if flow == "libero":
        m = re.findall(r"Entire bitstream digest: ([0-9a-f]{64})", Path(f"{bdir}.log").read_text(errors="ignore"))
        return m[-1] if m else None
    if f.suffix == ".jic":
        return hashlib.sha256(data).hexdigest()
    return hashlib.sha256(data[1024:-2]).hexdigest()


def run(board):
    flow = c.BOARDS[board]["flow"]
    out = RESULTS / board
    work = c.BUILD / f"rq2_{board}"
    b0 = c.BUILD / "rq1" / f"{DESIGN}_{board}"
    m0 = c.load_json(RQ1 / board / "manifest.json")
    d0 = c.load_json(RQ1 / board / "deploy.json")
    ref = check(work / "N2", m0, d0, out / "N2.csv")
    cfg0, file0 = config_digest(b0, flow), c.programming_file(b0).read_bytes()
    rows = []
    old_notes = {}
    if RECHECK and (out / "rebuilds.csv").exists():
        import csv
        old_notes = {r["case"]: r["note"] for r in csv.DictReader(open(out / "rebuilds.csv"))}
    for i in range(1, K + 1):
        bdir = work / f"N2r{i}"
        rc, sec = (0, 0.0) if RECHECK else c.build(DESIGN, board, bdir)
        if rc:
            rows.append([board, f"N2r{i}", "", "", "", f"build failed ({rc})"])
            continue
        v = check(bdir, m0, d0, out / f"N2r{i}.csv")
        differ = sorted(r for r in v if v[r] != ref[r])
        rows.append([board, f"N2r{i}", ";".join(differ) or "none",
                     int(c.programming_file(bdir).read_bytes() == file0), int(config_digest(bdir, flow) == cfg0),
                     old_notes.get(f"N2r{i}", "") if RECHECK else f"build_s={sec:.0f}"])
        print(rows[-1], flush=True)
    c.write_csv(out / "rebuilds.csv", ["board", "case", "verdicts_differing_from_N2", "file_identical_to_release",
                                       "configuration_identical_to_release", "note"], rows)


if __name__ == "__main__":
    for b in [a for a in sys.argv[1:] if not a.startswith("--")] or list(c.BOARDS):
        run(b)
