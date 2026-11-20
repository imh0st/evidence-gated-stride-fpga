import sys
from pathlib import Path

HERE = Path(__file__).absolute().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "rq5_cost"))
import common as c
import run as rq5

DESIGN = "cdc_ref"


def same_configuration(flow, a, b):
    fa, fb = c.programming_file(a), c.programming_file(b)
    if flow in ("vivado", "openxc7"):
        return rq5._bit_config_digest(fa) == rq5._bit_config_digest(fb)
    if flow == "libero":
        ga, gb = rq5._libero_digest(f"{a}.log"), rq5._libero_digest(f"{b}.log")
        return ga is not None and ga == gb
    da, db = fa.read_bytes(), fb.read_bytes()
    if fa.suffix == ".jic":
        return da == db
    diff = [i for i in range(min(len(da), len(db))) if da[i] != db[i]]
    return len(da) == len(db) and all(i < 1024 or i >= len(da) - 2 for i in diff)


rows = []
for board, t in c.BOARDS.items():
    b0 = c.BUILD / "rq1" / f"{DESIGN}_{board}"
    for case in ("A1", "A2", "A3", "N2"):
        bdir = c.BUILD / f"rq2_{board}" / case
        if bdir.exists():
            rows.append([board, case, int(not same_configuration(t["flow"], b0, bdir))])
c.write_csv(HERE / "results" / "config_changed.csv", ["board", "case", "configuration_changed"], rows)
for r in rows:
    print(r)
