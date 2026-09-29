import csv
import sys
from pathlib import Path

HERE = Path(__file__).absolute().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent / "egaudit"))
import common as c
from egaudit.evidence import collect

BUILDS = {
    "cdc_ref/zybo": (c.BUILD / "rq1" / "cdc_ref_zybo", "Vivado"),
    "cdc_ref/c10lp": (c.BUILD / "rq1" / "cdc_ref_c10lp", "Quartus"),
    "cdc_ref/disco": (c.BUILD / "rq1" / "cdc_ref_disco", "Libero"),
    "cdc_ref/zybo_open": (c.BUILD / "rq1" / "cdc_ref_zybo_open", "openXC7"),
    "zybo_hdmi/zybo": (c.BUILD / "public" / "zybo_hdmi", "Vivado"),
    "c10lp_multiproc/c10lp": (c.BUILD / "public" / "c10lp_multiproc", "Quartus"),
    "discovery_ref/disco": (c.BUILD / "public" / "discovery_ref" / "MPFS_DISCOVERY", "Libero"),
    "picosoc_zybo/zybo_open": (c.BUILD / "public" / "picosoc_zybo" / "out", "openXC7"),
}


def extracted(ev, field):
    v = ev.get(field)
    if field in ("constraints", "sources"):
        return sorted(v)
    if field == "ip":
        return sorted({x["vlnv"] for x in v.values() if x["vlnv"]})
    if field == "license":
        return sorted(v)
    return v


def expected(field, text):
    if field in ("constraints", "sources", "ip", "license"):
        return sorted(filter(None, text.split(";")))
    if field == "timing_met":
        return text == "True"
    if field == "wns":
        return float(text)
    return text


def same(field, got, want):
    if field == "wns":
        return got is not None and abs(got - want) < 5e-4
    return got == want


def main():
    res = HERE / "results"
    truth = list(csv.DictReader(open(HERE / "ground_truth.csv", newline="")))
    evs = {b: collect(d) for b, (d, _) in BUILDS.items()}
    rows, tally = [], {}
    for t in truth:
        b, f = t["build"], t["field"]
        if b not in BUILDS:
            continue
        got, want = extracted(evs[b], f), expected(f, t["expected"])
        ok = same(f, got, want)
        missed = sorted(set(want) - set(got)) if isinstance(want, list) else ""
        rows.append([b, BUILDS[b][1], f, int(ok), ";".join(map(str, want)) if isinstance(want, list) else want,
                     ";".join(map(str, got)) if isinstance(got, list) else got,
                     ";".join(missed) if missed else ""])
        k = tally.setdefault(BUILDS[b][1], [0, 0])
        k[0] += ok
        k[1] += 1
    c.write_csv(res / "field_checks.csv",
                ["build", "vendor", "field", "correct", "expected", "extracted", "missed"], rows)
    c.write_csv(res / "accuracy_by_vendor.csv", ["vendor", "correct", "total", "accuracy"],
                [[v, a, n, round(a / n, 3)] for v, (a, n) in tally.items()])
    for v, (a, n) in tally.items():
        print(f"{v}: {a}/{n}")
    for r in rows:
        if not r[3]:
            print("WRONG", r)


if __name__ == "__main__":
    main()
