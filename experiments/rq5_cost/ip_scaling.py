import csv
import os
import re
import shutil
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).absolute().parent
sys.path.insert(0, str(HERE))
import logic_scaling as ls
from logic_scaling import c, time_check, utilization

OUT = c.BUILD / "rq5_ip"
RESULTS = HERE / "results" / "ip_scaling.csv"
FIELDS = ["board", "units", "ip_instances", "egaudit_ip", "hier_levels", "logic_unit", "logic_used",
          "logic_available", "files", "bytes", "vendor_build_s", "exit_code", "egaudit_mean_s", "egaudit_sd_s"]

TOP = """`timescale 1ns / 1ps
// Board top of the RQ5 IP-count experiment: the reference design, the IP block design, and logic_fill.
module board_top (
    input  wire       clk,
    output wire [3:0] led
);
    wire clk_a, clk_b, locked, fill, ipq;
    wire [3:0] led_core;

    clk_gen u_clk (
        .clk_in(clk),
        .clk_a(clk_a),
        .clk_b(clk_b),
        .locked(locked)
    );

    cdc_ref_core u_core (
        .clk_a(clk_a),
        .clk_b(clk_b),
        .locked(locked),
        .led(led_core)
    );

    ipnet_wrapper u_ip (
        .clk(clk_a),
        .q(ipq)
    );

    logic_fill u_fill (
        .clk(clk_a),
        .rst(~locked),
        .out(fill)
    );

    assign led = {led_core[3:1], led_core[0] ^ fill ^ ipq};
endmodule
"""


def make_design(units):
    d = OUT / "designs" / f"ip_u{units}_n0"
    rtl = d / "rtl"
    want = {f.name: f.read_text() for f in (c.ROOT / "designs" / "cdc_ref" / "rtl").glob("*.v") if f.name != "board_top.v"}
    want["board_top.v"] = TOP
    want["logic_fill.v"] = ls.FILL.replace("{n}", "0").replace("{{", "{").replace("}}", "}")
    shutil.rmtree(d, ignore_errors=True)
    rtl.mkdir(parents=True)
    for name, text in want.items():
        (rtl / name).write_text(text)
    return d


def load():
    return list(csv.DictReader(open(RESULTS))) if RESULTS.exists() else []


def upsert(row):
    key = lambda r: (r["board"], int(r["units"]))
    lock = RESULTS.with_suffix(".lock")
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL)
            break
        except FileExistsError:
            time.sleep(0.5)
    try:
        rows = [r for r in load() if key(r) != key(row)] + [row]
        RESULTS.parent.mkdir(parents=True, exist_ok=True)
        with open(RESULTS, "w", newline="") as f:
            w = csv.DictWriter(f, FIELDS)
            w.writeheader()
            w.writerows(sorted(rows, key=key))
    finally:
        os.close(fd)
        os.remove(lock)
    print(row, flush=True)


def build(board, units):
    bdir = OUT / board / f"u{units}_n0"
    os.environ["IPNET_UNITS"] = str(units)
    rc, sec = c.build(make_design(units), board, bdir, opts=HERE / "ip_net.tcl")
    log = Path(f"{bdir}.log").read_text(errors="ignore")
    cells = re.findall(r"^IPNET cells (\d+)", log, re.M)
    row = {"board": board, "units": units, "ip_instances": cells[-1] if cells else "",
           "vendor_build_s": round(sec, 1), "exit_code": rc}
    if rc == 0:
        row.update(zip(["logic_unit", "logic_used", "logic_available"], utilization(bdir, "vivado")[:3]))
    upsert(row)


def time_all(boards=()):
    for row in load():
        if str(row["exit_code"]) != "0" or boards and row["board"] not in boards:
            continue
        bdir = OUT / row["board"] / f"u{row['units']}_n0"
        ev, runs = time_check(bdir)
        files = [p for p in bdir.rglob("*") if p.is_file()]
        bd_ip = [k for k in ev["ip"] if k.startswith("ipnet/")]
        row.update(egaudit_ip=len(bd_ip), hier_levels=max(k.count("/") - 1 for k in bd_ip) if bd_ip else 0,
                   files=len(files), bytes=sum(p.stat().st_size for p in files),
                   egaudit_mean_s=round(statistics.mean(runs), 3), egaudit_sd_s=round(statistics.stdev(runs), 3))
        upsert(row)


if __name__ == "__main__":
    if sys.argv[1] == "time":
        time_all(sys.argv[2:] or ["zybo"])  # the other flows: ip_qsys.py, ip_sd.py, ip_rtl.py
    else:
        build(sys.argv[1], int(sys.argv[2]))
