import csv
import json
import os
import re
import shutil
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).absolute().parent
sys.path.insert(0, str(HERE.parent))
import common as c
from run import time_check

BUILD_ONLY = {"xcu25": {"flow": "vivado", "part": "xcu25-ffvc1760-2L-e", "cdc": "cdc.xdc", "idcode": None}}
c.BOARDS.update(BUILD_ONLY)

OUT = c.BUILD / "rq5_logic"
RESULTS = HERE / "results" / "logic_scaling.csv"
FIELDS = ["board", "flow", "lanes", "logic_unit", "logic_used", "logic_available", "ff_used",
          "files", "bytes", "vendor_build_s", "exit_code", "egaudit_mean_s", "egaudit_sd_s"]

FILL = """`timescale 1ns / 1ps
// Logic filler for the RQ5 logic-size experiment: N independent lanes, each a 32-bit LFSR and a
// 32-bit accumulator, chained through one register per lane into a single output.
module logic_fill #(parameter N = {n}) (
    input  wire clk,
    input  wire rst,
    output wire out
);
    wire [N:0] chain;
    assign chain[0] = 1'b0;
    genvar i;
    generate
        for (i = 0; i < N; i = i + 1) begin : lane
            reg [31:0] lfsr, acc;
            reg        r;
            always @(posedge clk) begin
                if (rst) begin
                    lfsr <= 32'h00000001 | (i * 32'h9E3779B9);
                    acc  <= i;
                    r    <= 1'b0;
                end else begin
                    lfsr <= {{lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]}};
                    acc  <= acc + (lfsr ^ {{acc[28:0], acc[31:29]}});
                    r    <= chain[i] ^ acc[31];
                end
            end
            assign chain[i + 1] = r;
        end
    endgenerate
    assign out = chain[N];
endmodule
"""

TOP = """`timescale 1ns / 1ps
// Board top of the RQ5 logic-size experiment: the reference design plus logic_fill.
module board_top (
    input  wire       clk,
    output wire [3:0] led
);
    wire clk_a, clk_b, locked, fill;
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

    logic_fill u_fill (
        .clk(clk_a),
        .rst(~locked),
        .out(fill)
    );

    assign led = {led_core[3:1], led_core[0] ^ fill};
endmodule
"""


def make_design(n):
    d = OUT / "designs" / f"scale_n{n}"
    rtl = d / "rtl"
    want = {f.name: f.read_text() for f in (c.ROOT / "designs" / "cdc_ref" / "rtl").glob("*.v") if f.name != "board_top.v"}
    want["board_top.v"] = TOP
    want["logic_fill.v"] = FILL.replace("{n}", str(n)).replace("{{", "{").replace("}}", "}")
    have = {f.name: f.read_text() for f in rtl.glob("*.v")} if rtl.is_dir() else {}
    if have != want:
        shutil.rmtree(d, ignore_errors=True)
        rtl.mkdir(parents=True)
        for name, text in want.items():
            (rtl / name).write_text(text)
    return d


def utilization(bdir, flow):
    bdir = Path(bdir)
    if flow == "vivado":
        rows = {}
        for l in (bdir / "reports" / "utilization.rpt").read_text().splitlines():
            if l.startswith("|"):
                cells = [x.strip() for x in l.strip().strip("|").split("|")]
                rows.setdefault(cells[0], cells)
        lut = rows.get("Slice LUTs") or rows["CLB LUTs"]
        ff = rows.get("Slice Registers") or rows["CLB Registers"]
        return "LUT", int(lut[1]), int(lut[4]), int(ff[1])
    if flow == "quartus":
        t = next(bdir.rglob("*.fit.summary")).read_text()
        le = re.search(r"Total logic elements : ([\d,]+) / ([\d,]+)", t)
        ff = re.search(r"Total registers : ([\d,]+)", t)
        n = lambda s: int(s.replace(",", ""))
        return "LE", n(le.group(1)), n(le.group(2)), n(ff.group(1))
    if flow == "libero":
        t = next(bdir.rglob("*_compile_netlist_resources.rpt")).read_text()
        lut = re.search(r"\|\s*4LUT\s*\|\s*(\d+)\s*\|\s*(\d+)", t)
        ff = re.search(r"\|\s*DFF\s*\|\s*(\d+)", t)
        return "4LUT", int(lut.group(1)), int(lut.group(2)), int(ff.group(1))
    u = json.load(open(bdir / "report.json"))["utilization"]
    return "SLICE_LUTX", u["SLICE_LUTX"]["used"], u["SLICE_LUTX"]["available"], u["SLICE_FFX"]["used"]


def load():
    return list(csv.DictReader(open(RESULTS))) if RESULTS.exists() else []


def save(rows):
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS, "w", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows(rows)


def upsert(row):
    lock = RESULTS.with_suffix(".lock")
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL)
            break
        except FileExistsError:
            time.sleep(0.5)
    try:
        rows = [r for r in load() if not (r["board"] == row["board"] and str(r["lanes"]) == str(row["lanes"]))] + [row]
        save(sorted(rows, key=lambda r: (r["board"], int(r["lanes"]))))
    finally:
        os.close(fd)
        os.remove(lock)
    print(row, flush=True)


def build(board, n):
    flow = c.BOARDS[board]["flow"]
    bdir = OUT / board / f"n{n}"
    rc, sec = c.build(make_design(n), board, bdir)
    row = {"board": board, "flow": flow, "lanes": n, "vendor_build_s": round(sec, 1), "exit_code": rc}
    if rc == 0:
        row.update(zip(["logic_unit", "logic_used", "logic_available", "ff_used"], utilization(bdir, flow)))
    upsert(row)


def time_all(boards=()):
    for row in load():
        if str(row["exit_code"]) != "0" or boards and row["board"] not in boards:
            continue
        bdir = OUT / row["board"] / f"n{row['lanes']}"
        row.update(zip(["logic_unit", "logic_used", "logic_available", "ff_used"], utilization(bdir, row["flow"])))
        _, runs = time_check(bdir)
        files = [p for p in bdir.rglob("*") if p.is_file()]
        row.update(files=len(files), bytes=sum(p.stat().st_size for p in files),
                   egaudit_mean_s=round(statistics.mean(runs), 3), egaudit_sd_s=round(statistics.stdev(runs), 3))
        upsert(row)


if __name__ == "__main__":
    if sys.argv[1] == "time":
        time_all(sys.argv[2:])
    else:
        for n in sys.argv[2:]:
            build(sys.argv[1], int(n))
