import csv
import hashlib
import shutil
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).absolute().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent / "egaudit"))
import common as c
from egaudit.evidence import collect
from egaudit.rules import evaluate

RESULTS = HERE / "results"
REPEATS = 5
RQ1 = HERE.parent / "rq1_end_to_end" / "results"

PUBLIC = HERE.parent / "public_designs" / "results" / "builds.csv"


def real_builds():
    rows = []
    for board in c.BOARDS:
        bdir = c.BUILD / "rq1" / f"cdc_ref_{board}"
        sec = next(csv.DictReader(open(RQ1 / board / "build.csv")))["seconds"]
        rows.append((f"cdc_ref/{board}", bdir, float(sec)))
    public = c.BUILD / "public"
    dirs = {"zybo_hdmi": public / "zybo_hdmi", "c10lp_multiproc": public / "c10lp_multiproc",
            "discovery_ref": public / "discovery_ref" / "MPFS_DISCOVERY", "picosoc_zybo": public / "picosoc_zybo" / "out"}
    for r in csv.DictReader(open(PUBLIC)):
        if r["exit_code"] == "0":
            rows.append((f'{r["design"]}/{r["board"]}', dirs[r["design"]], float(r["seconds"])))
    return rows


def time_check(bdir, manifest=None):
    collect(Path(bdir))
    runs = []
    for _ in range(REPEATS):
        t0 = time.perf_counter()
        ev = collect(Path(bdir))
        evaluate(ev, manifest, None)
        runs.append(time.perf_counter() - t0)
    return ev, runs


def overhead():
    rows = []
    for label, bdir, build_s in real_builds():
        ev, runs = time_check(bdir)
        files = [p for p in Path(bdir).rglob("*") if p.is_file()]
        rows.append([label, len(files), sum(p.stat().st_size for p in files), len(ev["sources"]),
                     len(ev["ip"]), round(build_s, 1), round(statistics.mean(runs), 3),
                     round(statistics.stdev(runs), 3), round(100 * statistics.mean(runs) / build_s, 3)])
        print(label, rows[-1][-3:])
    c.write_csv(RESULTS / "overhead.csv", ["build", "files", "bytes", "hdl_sources", "ip_cores",
                                           "vendor_build_s", "egaudit_mean_s", "egaudit_sd_s", "overhead_pct"], rows)


def scaled_copy(n_ip, bit_mb):
    src = c.BUILD / "rq1" / "cdc_ref_zybo"
    dst = c.BUILD / "rq5_scale" / f"ip{n_ip}_bit{bit_mb}"
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)
    xpr = dst / "cdc_ref.xpr"
    xci = next(dst.rglob("clk_wiz_0.xci"))
    extra = dst / "scale_src"
    extra.mkdir()
    entries = []
    for i in range(n_ip):
        x = extra / f"ip_{i}.xci"
        x.write_bytes(xci.read_bytes() + f"<!-- {i} -->".encode())
        v = extra / f"mod_{i}.v"
        v.write_text(f"module mod_{i}(input a, output b); assign b = a; endmodule\n")
        entries += [f'      <File Path="$PPRDIR/scale_src/ip_{i}.xci"/>', f'      <File Path="$PPRDIR/scale_src/mod_{i}.v"/>']
    text = xpr.read_text()
    xpr.write_text(text.replace("</FileSet>", "\n".join(entries) + "\n    </FileSet>", 1))
    bit = next(dst.glob("*.bit"))
    with open(bit, "ab") as f:
        f.truncate(bit_mb << 20)
    return dst


def scaling():
    rows = []
    for n_ip, bit_mb in [(0, 4), (10, 4), (100, 4), (1000, 4), (0, 64), (0, 256)]:
        d = scaled_copy(n_ip, bit_mb)
        ev, runs = time_check(d)
        rows.append([n_ip, bit_mb, len(ev["ip"]), len(ev["sources"]),
                     round(statistics.mean(runs), 3), round(statistics.stdev(runs), 3)])
        print(rows[-1])
        shutil.rmtree(d, ignore_errors=True)
    c.write_csv(RESULTS / "scaling.csv", ["extra_ip", "bitstream_mib", "ip_seen", "sources_seen",
                                          "egaudit_mean_s", "egaudit_sd_s"], rows)


def _bit_config_digest(path):
    data = Path(path).read_bytes()
    i = data.find(bytes.fromhex("aa995566"))
    return hashlib.sha256(data[i:] if i >= 0 else data).hexdigest()


def _libero_digest(log):
    import re
    m = re.findall(r"Entire bitstream digest: ([0-9a-f]{64})", Path(log).read_text(errors="ignore"))
    return m[-1] if m else None




if __name__ == "__main__":
    RESULTS.mkdir(parents=True, exist_ok=True)
    steps = sys.argv[1:] or ["overhead", "scaling"]
    for s in steps:
        globals()[s]()
