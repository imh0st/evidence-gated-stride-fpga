import copy
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).absolute().parent
sys.path.insert(0, str(HERE.parent))
import common as c
from baselines import vendor_flags

RESULTS = HERE / "results"
RQ1 = HERE.parent / "rq1_end_to_end" / "results"
DESIGN = "cdc_ref"
BAD = {"VIOLATED", "MISSING"}

EXPECTED = {"A1": ["CFG-1"], "A2": ["CFG-2"], "A3": ["SIP-2"], "A4": ["RPT-1"], "A5": ["TENV-3"],
            "A6": ["BSD-1"], "A7": ["BSD-4"], "A8": ["DEP-1"], "A9": ["REL-1", "BSD-3"]}

OPTIONS = {
    "vivado": "set_property STEPS.PLACE_DESIGN.ARGS.DIRECTIVE ExtraNetDelay_high [get_runs impl_1]\n",
    "quartus": "set_global_assignment -name SEED 7\n",
    "libero": "configure_tool -name {PLACEROUTE} -params {EFFORT_LEVEL:true}\n",
    "openxc7": "--seed 7\n",
}
FALSE_PATH = {
    "zybo": "set_false_path -from $clk_a -to $clk_b\n",
    "c10lp": "set_false_path -from $clk_a -to $clk_b\n",
    "disco": "set_false_path -from [get_clocks {u_clk/u_ccc/PF_CCC_C0_0/pll_inst_0/OUT0}]"
             " -to [get_clocks {u_clk/u_ccc/PF_CCC_C0_0/pll_inst_0/OUT1}]\n",
    "zybo_open": "set_false_path -from [get_clocks clk_a] -to [get_clocks clk_b]\n",
}
OTHER_TARGET = {"zybo": "020F30DD", "c10lp": "0f8181cf", "disco": "23727093", "zybo_open": "020F30DD"}
OLD_VERSION = {"vivado": "v2024.1", "quartus": "24.1std.0 Build 1077", "libero": "2024.1.0.3",
               "openxc7": "Yosys 0.55; nextpnr-xilinx 0.8.2"}


def check(build, manifest, deploy, out):
    args = [build]
    work = out.parent
    if manifest is not None:
        (work / f"{out.stem}.manifest.json").write_text(json.dumps(manifest, indent=2))
        args += ["--manifest", work / f"{out.stem}.manifest.json"]
    if deploy is not None:
        (work / f"{out.stem}.deploy.json").write_text(json.dumps(deploy, indent=2))
        args += ["--deploy", work / f"{out.stem}.deploy.json"]
    c.egaudit("check", *args, "--out", out)
    return {r: v for r, (v, _) in c.read_verdicts(out).items()}


def released_from(manifest, build_dir):
    ev = c.load_json(build_dir / "_ev.json")
    m = copy.deepcopy(manifest)
    m["bitstream"] = {"file": ev["bitstream"], "sha256": ev["bitstream_sha256"]}
    m["reports"] = {"timing": ev.get("timing_report_sha256")}
    return m


def dump_evidence(build_dir):
    sys.path.insert(0, str(c.ROOT / "egaudit"))
    from egaudit.evidence import collect
    ev = collect(build_dir)
    (build_dir / "_ev.json").write_text(json.dumps(ev, indent=2))
    return ev


def edit_timing_report(build_dir):
    ev = c.load_json(build_dir / "_ev.json")
    rpt = build_dir / ev["timing_report"]
    text = rpt.read_text(encoding="utf-8", errors="ignore")
    if rpt.suffix == ".json":
        m = re.search(r'"achieved": ([\d.]+)', text)
        rpt.write_text(text.replace(m.group(0), f'"achieved": {float(m.group(1)) + 10:.2f}', 1))
        return
    old = f"{ev['wns']:.3f}"
    new = f"{ev['wns'] + 1:.3f}"
    if old not in text:
        raise RuntimeError(f"slack {old} not found in {rpt}")
    rpt.write_text(text.replace(old, new, 1), encoding="utf-8")


def regenerate_timing_report(build_dir, flow):
    work = build_dir.parent
    if flow == "openxc7":
        return False
    if flow == "vivado":
        dcp = next(build_dir.rglob("*_routed.dcp"))
        tcl = work / "regen.tcl"
        tcl.write_text(f"open_checkpoint {{{dcp.as_posix()}}}\n"
                       f"report_timing_summary -file {{{(build_dir / 'reports' / 'timing_summary.rpt').as_posix()}}}\n")
        subprocess.run([c.VIVADO, "-mode", "batch", "-nojournal", "-nolog", "-source", str(tcl)],
                       cwd=work, stdout=subprocess.DEVNULL, check=True)
    elif flow == "quartus":
        sta = Path(c.QUARTUS_SH).with_name("quartus_sta.exe")
        subprocess.run([str(sta), DESIGN], cwd=build_dir, stdout=subprocess.DEVNULL, check=True)
    else:
        tcl = work / "regen.tcl"
        tcl.write_text(f"open_project -file {{{next(build_dir.glob('*.prjx')).as_posix()}}}\n"
                       "run_tool -name {VERIFYTIMING}\nsave_project\nclose_project\n")
        subprocess.run([c.LIBERO, f"SCRIPT:{tcl.as_posix()}", f"LOGFILE:{(work / 'regen.log').as_posix()}"],
                       cwd=work, stdout=subprocess.DEVNULL, check=True)
    return True


def constraint_files(build_dir, flow):
    if flow == "libero":
        return sorted(p for p in build_dir.glob("constraint/*.sdc") if "derived" not in p.name) + \
               sorted(build_dir.glob("constraint/io/*.pdc"))
    if flow == "openxc7":
        args = (build_dir / "pnr.args").read_text().split()
        return [(build_dir / args[i + 1]).resolve() for i, a in enumerate(args[:-1]) if a == "--xdc"]
    text = "".join(p.read_text(errors="ignore") for p in build_dir.glob("*.xpr")) + \
           "".join(p.read_text(errors="ignore") for p in build_dir.glob("*.qsf"))
    paths = re.findall(r'<File Path="([^"]+\.xdc)"', text) + re.findall(r'-name SDC_FILE "?([^"\n]+)"?', text)
    resolved = []
    for p in paths:
        p = p.replace("$PPRDIR", build_dir.as_posix())
        q = Path(p) if Path(p).is_absolute() else build_dir / p
        resolved.append(q.resolve())
    return [p for p in resolved if p.exists()]


def run(board, do_program=True, recheck=False):
    t = c.BOARDS[board]
    flow = t["flow"]
    out = RESULTS / board
    work = c.BUILD / f"rq2_{board}"
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)

    b0 = c.BUILD / "rq1" / f"{DESIGN}_{board}"
    m0 = c.load_json(RQ1 / board / "manifest.json")
    d0 = c.load_json(RQ1 / board / "deploy.json")
    ev0 = dump_evidence(b0)
    baseline = check(b0, m0, d0, out / "B0.csv")
    rows = []

    def record(case, verdicts, vendor, note="", ignore=()):
        exp = EXPECTED.get(case, [])
        worse = sorted(r for r, v in verdicts.items() if r not in ignore
                       and v != baseline[r] and v in BAD | {"PARTIAL", "PROJECT"} and baseline[r] == "SATISFIED")
        detected = all(verdicts[r] in BAD for r in exp) if exp else None
        rows.append([board, case, ";".join(exp), ";".join(verdicts[r] for r in exp),
                     "" if detected is None else int(detected),
                     ";".join(r for r in worse if r not in exp),
                     "" if vendor is None else int(vendor), note])

    f1_cdc = work / "F1cdc" / t["cdc"]
    f1_cdc.parent.mkdir(parents=True, exist_ok=True)
    f1_cdc.write_text(c.approved_cdc(board).read_text() + FALSE_PATH[board])
    f2_opts = work / "f2_options.tcl"
    f2_opts.write_text(OPTIONS[flow])
    f3_design = work / "F3src" / DESIGN
    if f3_design.exists():
        shutil.rmtree(f3_design)
    shutil.copytree(c.ROOT / "designs" / DESIGN, f3_design)
    core = f3_design / "rtl" / "cdc_ref_core.v"
    src = core.read_text()
    core.write_text(src.replace("if (rdata != expected) error <= 1'b1;", "// sequence check removed"))

    builds = {"A1": dict(cdc=f1_cdc), "A2": dict(opts=f2_opts), "A3": dict(design=f3_design), "N2": {}}
    info = {}
    for case, kw in builds.items():
        bdir = work / case
        if recheck:
            rc, sec = 0, None
        else:
            rc, sec = c.build(kw.get("design", DESIGN), board, bdir, cdc=kw.get("cdc"), opts=kw.get("opts"))
        ev = dump_evidence(bdir) if rc == 0 else {}
        info[case] = (bdir, rc, sec, ev)

    not_deployed = ("BSD-4", "DEP-1")
    for case in ("A1", "A2", "A3"):
        bdir, rc, sec, ev = info[case]
        if rc:
            rows.append([board, case, ";".join(EXPECTED[case]), "", "", "", 1, f"build failed ({rc})"])
            continue
        m = released_from(m0, bdir)
        v = check(bdir, m, None, out / f"{case}.csv")
        record(case, v, vendor_flags(rc, ev.get("timing_met")),
               f"timing_met={ev.get('timing_met')} bitstream_changed={ev.get('bitstream_sha256') != ev0['bitstream_sha256']}",
               ignore=not_deployed)

    b4 = work / "A4"
    shutil.rmtree(b4, ignore_errors=True)
    shutil.copytree(b0, b4)
    dump_evidence(b4)
    edit_timing_report(b4)
    record("A4", check(b4, m0, d0, out / "A4.csv"), None)

    m5 = copy.deepcopy(m0)
    m5["tool"]["version"] = OLD_VERSION[flow]
    record("A5", check(b0, m5, d0, out / "A5.csv"), None)

    b6 = work / "A6"
    shutil.rmtree(b6, ignore_errors=True)
    shutil.copytree(b0, b6)
    other = info["A3"][0] / info["A3"][3]["bitstream"]
    shutil.copy2(other, b6 / ev0["bitstream"])
    v6 = check(b6, m0, d0, out / "A6.csv")
    dump_evidence(b6)
    record("A6", v6, None)

    m7 = copy.deepcopy(m0)
    m7["target"]["idcode"] = OTHER_TARGET[board]
    m7["target"]["serial"] = None
    record("A7", check(b0, m7, d0, out / "A7.csv"), None)

    if do_program:
        f1_file = c.programming_file(info["A3"][0])
        if recheck:
            logs = sorted(p for p in (work / "A8_program").glob("*.log"))
        else:
            logs = c.program(board, f1_file, work / "A8_program")
        c.egaudit("deploy", "--vendor", flow, *sum((["--log", l] for l in logs), []),
                  "--file", f1_file, "--operator", "board-operator", "--out", work / "A8_deploy.json")
        d8 = c.load_json(work / "A8_deploy.json")
        record("A8", check(b0, m0, d8, out / "A8.csv"), vendor_flags(verify=d8["verify"]),
               f"verify={d8['verify']}")

    m9 = copy.deepcopy(m0)
    m9["release"]["approver"] = None
    m9["signature"] = {}
    record("A9", check(b0, m9, d0, out / "A9.csv"), None)

    n1 = c.BUILD / "rq1_moved" / f"{DESIGN}_{board}"
    shutil.rmtree(n1, ignore_errors=True)
    shutil.copytree(b0, n1)
    record("N1", check(n1, m0, d0, out / "N1.csv"), False)

    bdir, rc, sec, ev = info["N2"]
    record("N2", check(bdir, m0, d0, out / "N2.csv"), vendor_flags(rc, ev.get("timing_met")),
           f"bitstream_file_identical={ev.get('bitstream_sha256') == ev0['bitstream_sha256']}")

    m_n2 = released_from(m0, bdir)
    if (flow != "openxc7") if recheck else regenerate_timing_report(bdir, flow):
        record("N3", check(bdir, m_n2, None, out / "N3.csv"), False, ignore=not_deployed)
    else:
        rows.append([board, "N3", "", "", "", "", "", "not applicable: no standalone timing analysis"])

    files = constraint_files(b0, flow)
    saved = {p: p.read_bytes() for p in files}
    try:
        for p, data in saved.items():
            p.write_bytes(data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        record("N4", check(b0, m0, d0, out / "N4.csv"), False, f"files={len(files)}")
    finally:
        for p, data in saved.items():
            p.write_bytes(data)

    c.write_csv(out / "cases.csv", ["board", "case", "expected", "egaudit_verdict", "egaudit_detected",
                                    "other_records_worse", "vendor_flags", "note"], rows)


def summarize():
    rows = []
    for board in c.BOARDS:
        for name in ("cases.csv", "cases_extra.csv", "cases_inputs.csv", "cases_rebuild.csv", "cases_sim.csv"):
            f = RESULTS / board / name
            if f.exists():
                rows += list(csv_rows(f))
    cols = ["board", "case", "expected", "egaudit_verdict", "egaudit_detected", "other_records_worse",
            "vendor_flags", "note"]
    c.write_csv(RESULTS / "rq2_detection.csv", cols, [[r.get(k, "") for k in cols] for r in rows])


def csv_rows(path):
    import csv
    with open(path, newline="") as f:
        yield from csv.DictReader(f)


if __name__ == "__main__":
    RESULTS.mkdir(parents=True, exist_ok=True)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for b in args or list(c.BOARDS):
        run(b, do_program="--no-program" not in sys.argv, recheck="--recheck" in sys.argv)
    summarize()
