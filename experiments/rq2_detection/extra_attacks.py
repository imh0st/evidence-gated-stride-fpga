import copy
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).absolute().parent
sys.path.insert(0, str(HERE.parent))
import common as c
from baselines import vendor_flags
from run import BAD, DESIGN, RESULTS, RQ1, check, dump_evidence, released_from

RECHECK = "--recheck" in sys.argv

EXPECTED = {"A10": ["SIP-1"], "A11": ["CFG-3"], "A12": ["TRN-1", "TRN-2", "TRN-3"], "A13": ["REL-2"]}
NOT_DEPLOYED = ("BSD-4", "DEP-1")

IP_EDIT = {
    "zybo": ("clk_wiz.tcl", "    CONFIG.CLKOUT2_REQUESTED_OUT_FREQ {75.000} \\\n",
             "    CONFIG.CLKOUT2_REQUESTED_OUT_FREQ {75.000} \\\n    CONFIG.CLKOUT2_REQUESTED_PHASE {90.000} \\\n"),
    "c10lp": ("clk_gen.v", '.clk1_phase_shift       ("0")', '.clk1_phase_shift       ("3333")'),
    "disco": ("pf_ccc.tcl", '"GL1_0_PLL_PHASE:0"', '"GL1_0_PLL_PHASE:90"'),
}
TIGHT = {
    "zybo": ("set_max_delay -datapath_only -from $clk_a -to $clk_b [get_property PERIOD $clk_a]",
             "set_max_delay -datapath_only -from $clk_a -to $clk_b 0.050"),
    "c10lp": ("set_max_delay -from $clk_a -to $clk_b 10.000", "set_max_delay -from $clk_a -to $clk_b 0.050"),
    "disco": ("set_max_delay 10.000 -from", "set_max_delay 0.050 -from"),
    "zybo_open": ("create_clock -period 10.000 [get_nets { clk_a }]", "create_clock -period 1.000 [get_nets { clk_a }]"),
}


def edited_copy(src, dst, name, old, new):
    text = (Path(src) / name).read_text()
    if text.count(old) != 1:
        raise RuntimeError(f"{name}: expected one occurrence of {old!r}")
    dst.mkdir(parents=True, exist_ok=True)
    (dst / name).write_text(text.replace(old, new))
    return dst / name


def run(board):
    out = RESULTS / board
    work = c.BUILD / f"rq2_{board}"
    b0 = c.BUILD / "rq1" / f"{DESIGN}_{board}"
    m0 = c.load_json(RQ1 / board / "manifest.json")
    d0 = c.load_json(RQ1 / board / "deploy.json")
    ev0 = dump_evidence(b0)
    baseline = check(b0, m0, d0, out / "B0.csv")
    rows = []

    def record(case, verdicts, vendor=None, note="", ignore=()):
        exp = EXPECTED[case]
        worse = sorted(r for r, v in verdicts.items() if r not in ignore and r not in exp
                       and v != baseline[r] and v in BAD | {"PARTIAL", "PROJECT"} and baseline[r] == "SATISFIED")
        rows.append([board, case, ";".join(exp), ";".join(verdicts[r] for r in exp),
                     int(all(verdicts[r] in BAD for r in exp)), ";".join(worse), "" if vendor is None else int(vendor), note])

    if board in IP_EDIT:
        bd = work / "F10board"
        shutil.rmtree(bd, ignore_errors=True)
        shutil.copytree(c.board_dir(board), bd)
        edited_copy(c.board_dir(board), bd, *IP_EDIT[board])
        real_board_dir = c.board_dir
        c.board_dir = lambda b: bd if b == board else real_board_dir(b)
        try:
            rc = 0 if RECHECK else c.build(DESIGN, board, work / "A10")[0]
        finally:
            c.board_dir = real_board_dir
        if rc:
            rows.append([board, "A10", "SIP-1", "", "", "", 1, f"build failed ({rc})"])
        else:
            ev10 = dump_evidence(work / "A10")
            record("A10", check(work / "A10", released_from(m0, work / "A10"), None, out / "A10.csv"),
                   vendor_flags(0, ev10.get("timing_met")), ignore=NOT_DEPLOYED)
    else:
        rows.append([board, "A10", "SIP-1", "", "", "", "", "not applicable: no IP core in the flow"])

    cdc = edited_copy(c.approved_cdc(board).parent, work / "F11cdc", c.BOARDS[board]["cdc"], *TIGHT[board])
    rc = 0 if RECHECK else c.build(DESIGN, board, work / "A11", cdc=cdc)[0]
    if rc:
        rows.append([board, "A11", "CFG-3", "", "", "", 1, f"build failed ({rc})"])
    else:
        ev = dump_evidence(work / "A11")
        record("A11", check(work / "A11", released_from(m0, work / "A11"), None, out / "A11.csv"),
               vendor_flags(0, ev.get("timing_met")), f"timing_met={ev.get('timing_met')}", ignore=NOT_DEPLOYED)

    b12 = work / "A12"
    shutil.rmtree(b12, ignore_errors=True)
    shutil.copytree(b0, b12)
    gone = [p for k in ("netlists", "checkpoints") for p in ev0[k]] + ([ev0["route_report"]] if ev0.get("route_report") else [])
    for p in gone:
        (b12 / p).unlink()
    dump_evidence(b12)
    record("A12", check(b12, m0, d0, out / "A12.csv"), note=f"deleted={len(gone)}")

    m13 = copy.deepcopy(m0)
    m13["release"]["workflow"] = None
    m13["release"]["service_account"] = None
    record("A13", check(b0, m13, d0, out / "A13.csv"))

    c.write_csv(out / "cases_extra.csv", ["board", "case", "expected", "egaudit_verdict", "egaudit_detected",
                                          "other_records_worse", "vendor_flags", "note"], rows)
    for r in rows:
        print(r, flush=True)


if __name__ == "__main__":
    for b in [a for a in sys.argv[1:] if not a.startswith("--")] or list(c.BOARDS):
        run(b)
