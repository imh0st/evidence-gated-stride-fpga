import shutil
import sys
from pathlib import Path

HERE = Path(__file__).absolute().parent
sys.path.insert(0, str(HERE.parent))
import common as c
from baselines import vendor_flags
from run import BAD, DESIGN, RESULTS, check, dump_evidence, released_from

RECHECK = "--recheck" in sys.argv

EXPECTED = {"A14": ["SIP-2"], "A15": ["SIP-2"]}
NOT_DEPLOYED = ("BSD-4", "DEP-1")
MEM = "\n".join(f"{v:02x}" for v in range(16)) + "\n"
HDR = "localparam WIDTH = 8;\nlocalparam DEPTH = 16;\n"
EDIT = {"A14": ("rom_init.mem", MEM.replace("00", "5a", 1)), "A15": ("rom_params.vh", HDR.replace("DEPTH = 16", "DEPTH = 15"))}

ROM = """`timescale 1ns / 1ps
module rom (
    input  wire clk,
    input  wire rst,
    output wire out
);
`include "{hdr}"
    parameter INIT_FILE = "{mem}";
    reg [WIDTH-1:0] mem [0:DEPTH-1];
    initial $readmemh(INIT_FILE, mem);
    reg [3:0] a;
    reg [WIDTH-1:0] q;
    always @(posedge clk) begin
        if (rst) a <= 4'd0; else a <= a + 4'd1;
        q <= mem[a];
    end
    assign out = ^q;
endmodule
"""

TOP = """`timescale 1ns / 1ps
module board_top (
    input  wire       clk,
    output wire [3:0] led
);
    wire clk_a, clk_b, locked, rom_bit;
    wire [3:0] led_core;
    clk_gen u_clk (.clk_in(clk), .clk_a(clk_a), .clk_b(clk_b), .locked(locked));
    cdc_ref_core u_core (.clk_a(clk_a), .clk_b(clk_b), .locked(locked), .led(led_core));
    rom u_rom (.clk(clk_a), .rst(~locked), .out(rom_bit));
    assign led = {led_core[3:1], led_core[0] ^ rom_bit};
endmodule
"""


def variant(work):
    data, design = work / "F14data", work / "F14src" / DESIGN
    if not RECHECK:
        shutil.rmtree(design, ignore_errors=True)
        shutil.copytree(c.ROOT / "designs" / DESIGN, design)
        data.mkdir(parents=True, exist_ok=True)
        (data / "rom_init.mem").write_text(MEM)
        (data / "rom_params.vh").write_text(HDR)
        (design / "rtl" / "board_top.v").write_text(TOP)
        (design / "rtl" / "rom.v").write_text(ROM.format(hdr=(data / "rom_params.vh").absolute().as_posix(),
                                                         mem=(data / "rom_init.mem").absolute().as_posix()))
    return design, data


def run(board):
    t = c.BOARDS[board]
    out = RESULTS / board
    work = c.BUILD / f"rq2_{board}"
    out.mkdir(parents=True, exist_ok=True)
    design, data = variant(work)
    r14 = work / "R14"
    approved = {n: (data / n).read_text() for n, _ in EDIT.values()}
    rows = []
    try:
        if not RECHECK and c.build(design, board, r14)[0]:
            raise SystemExit(f"{board}: R14 build failed, see {r14}.log")
        ev0 = dump_evidence(r14)
        target = ["--target-idcode", t["idcode"]] + (["--target-serial", t["serial"]] if "serial" in t else [])
        c.egaudit("manifest", r14, "--out", out / "R14.manifest.json", "--release-id", f"{DESIGN}_rom_{board}",
                  *c.ROLES, *target)
        m14 = c.load_json(out / "R14.manifest.json")
        baseline = check(r14, m14, None, out / "R14.csv")
        for case, (name, text) in EDIT.items():
            for n, a in approved.items():
                (data / n).write_text(a)
            (data / name).write_text(text)
            bdir = work / case
            rc = 0 if RECHECK else c.build(design, board, bdir)[0]
            if rc:
                rows.append([board, case, "SIP-2", "", "", "", 1, f"build failed ({rc})"])
                continue
            ev = dump_evidence(bdir)
            v = check(bdir, released_from(m14, bdir), None, out / f"{case}.csv")
            worse = sorted(r for r, x in v.items() if r not in NOT_DEPLOYED + tuple(EXPECTED[case])
                           and x != baseline[r] and x in BAD | {"PARTIAL", "PROJECT"} and baseline[r] == "SATISFIED")
            rows.append([board, case, ";".join(EXPECTED[case]), ";".join(v[r] for r in EXPECTED[case]),
                         int(all(v[r] in BAD for r in EXPECTED[case])), ";".join(worse), int(vendor_flags(0, ev.get("timing_met"))),
                         f"timing_met={ev.get('timing_met')} configuration_changed={ev.get('config_sha256') != ev0.get('config_sha256')}"])
    finally:
        for n, a in approved.items():
            (data / n).write_text(a)
    c.write_csv(out / "cases_inputs.csv", ["board", "case", "expected", "egaudit_verdict", "egaudit_detected",
                                           "other_records_worse", "vendor_flags", "note"], rows)


if __name__ == "__main__":
    for b in [a for a in sys.argv[1:] if not a.startswith("--")] or list(c.BOARDS):
        run(b)
