import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).absolute().parent
sys.path.insert(0, str(HERE.parent))
import common as c
from input_attacks import EDIT, variant
from run import BAD, DESIGN, RESULTS, RQ1, dump_evidence, released_from

RECHECK = "--recheck" in sys.argv
EXPECTED = {"A16": ["BSD-1"], "A17": ["BSD-1"]}
NOT_DEPLOYED = ("BSD-4", "DEP-1")

VIVADO_A17 = """open_checkpoint {SYNTH}
set c [lindex [lsort [get_cells -hierarchical -filter {REF_NAME =~ LUT*}]] 0]
set init [get_property INIT $c]
regexp {^(\\d+)'h([0-9A-Fa-f]+)$} $init -> w hex
scan $hex %llx v
set_property INIT [format "%d'h%0*llX" $w [expr {($w + 3) / 4}] [expr {$v ^ 1}]] $c
puts "A17: $c INIT $init -> [get_property INIT $c]"
write_checkpoint -force {SYNTH}
close_design
open_project {XPR}
reset_run impl_1
launch_runs impl_1 -to_step route_design -jobs 4
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} { error "impl_1 failed" }
open_run impl_1
report_utilization       -file {RPT}/utilization.rpt
report_timing_summary    -file {RPT}/timing_summary.rpt
report_clock_interaction -file {RPT}/clock_interaction.rpt
report_cdc -details      -file {RPT}/cdc.rpt
report_bus_skew          -file {RPT}/bus_skew.rpt
report_drc               -file {RPT}/drc.rpt
write_bitstream -force -mask_file {BIT}
close_project
"""

LIBERO_A17 = """set out {OUT}
new_project -location $out -name cdc_ref -hdl VERILOG -family {PolarFireSoC} \\
    -die {MPFS095T} -package {FCSG325} -speed {-1} -die_voltage {1.0} -part_range {EXT} \\
    -adv_options {IO_DEFT_STD:LVCMOS 1.8V}
import_files -hdl_source {NETLIST}
build_design_hierarchy
set_root -module {board_top::work}
set_option -synth 0 -module {board_top::work}
import_files -io_pdc {PDC}
import_files -sdc {DSDC}
import_files -sdc {CSDC}
set cons "$out/constraint"
set sdcs [list -file "$cons/board_top_derived_constraints.sdc" -file "$cons/cdc.sdc"]
organize_tool_files -tool {PLACEROUTE}   -module {board_top::work} -input_type {constraint} -file "$cons/io/pins.pdc" {*}$sdcs
organize_tool_files -tool {VERIFYTIMING} -module {board_top::work} -input_type {constraint} {*}$sdcs
run_tool -name {COMPILE}
run_tool -name {PLACEROUTE}
run_tool -name {VERIFYTIMING}
run_tool -name {GENERATEPROGRAMMINGDATA}
run_tool -name {GENERATEPROGRAMMINGFILE}
file mkdir "$out/export"
export_prog_job -job_file_name cdc_ref -export_dir "$out/export" -bitstream_file_type {TRUSTED_FACILITY} -bitstream_file_components {FABRIC}
save_project
close_project
"""


def tamper(board, bdir, log):
    flow = c.BOARDS[board]["flow"]
    if flow == "vivado":
        tcl = bdir.parent / "a17.tcl"
        tcl.write_text(VIVADO_A17.replace("{SYNTH}", "{" + next(bdir.glob("*.runs/synth_1/board_top.dcp")).as_posix() + "}")
                       .replace("{XPR}", "{" + next(bdir.glob("*.xpr")).as_posix() + "}")
                       .replace("{RPT}", (bdir / "reports").as_posix()).replace("{BIT}", "{" + (bdir / "cdc_ref.bit").as_posix() + "}"))
        return subprocess.run([c.VIVADO, "-mode", "batch", "-nojournal", "-log", str(log), "-source", str(tcl)],
                              cwd=bdir.parent, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
    if flow == "openxc7":
        spec = importlib.util.spec_from_file_location("x7build", c.ROOT / "flows" / "openxc7" / "build.py")
        x7 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(x7)
        design = json.loads((bdir / "design.json").read_text())
        cells = design["modules"]["board_top"]["cells"]
        name = next(n for n in sorted(cells) if cells[n]["type"].startswith("LUT") and "1" in cells[n]["parameters"]["INIT"])
        init = cells[name]["parameters"]["INIT"]
        cells[name]["parameters"]["INIT"] = init[:-1] + ("1" if init[-1] == "0" else "0")
        (bdir / "design.json").write_text(json.dumps(design, indent=2))
        log.write_text(f"A17: {name} INIT {init} -> {cells[name]['parameters']['INIT']}\n")
        part = c.BOARDS[board]["part"]
        args = (bdir / "pnr.args").read_text().split()
        try:
            x7.run([x7.X7 / "bin" / "nextpnr-xilinx.exe", "--log", "nextpnr.log", *args], log, bdir)
            with open(bdir / "design.frames", "w") as frames:
                x7.run([x7.X7 / "bin" / "fasm2frames.cmd", "--part", part, "--db-root", x7.DB, "design.fasm"],
                       log, bdir, stdout=frames)
            x7.run([x7.X7 / "bin" / "xc7frames2bit.exe", "--part_file", x7.DB / part / "part.yaml", "--part_name", part,
                    "--frm_file", "design.frames", "--output_file", "cdc_ref.bit"], log, bdir)
        except SystemExit:
            return 1
        return 0
    if flow == "libero":
        vm = bdir / "synthesis" / "board_top.vm"
        v = vm.read_text(encoding="utf-8")
        luts = sorted(re.finditer(r"defparam (\S+(?: )?)\.INIT=(\d+)'h([0-9A-Fa-f]+);", v), key=lambda m: m.group(1))
        m = next(x for x in luts if int(x.group(2)) == 16)
        new = f"defparam {m.group(1)}.INIT={m.group(2)}'h{int(m.group(3), 16) ^ 1:0{len(m.group(3))}X};"
        vm.write_text(v.replace(m.group(0), new, 1), encoding="utf-8")
        net = bdir.parent / "A17_netlist"
        shutil.rmtree(net, ignore_errors=True)
        tcl = bdir.parent / "a17.tcl"
        cons = bdir / "constraint"
        tcl.write_text(LIBERO_A17.replace("{OUT}", "{" + net.as_posix() + "}").replace("{NETLIST}", "{" + vm.as_posix() + "}")
                       .replace("{PDC}", "{" + (cons / "io" / "pins.pdc").as_posix() + "}")
                       .replace("{DSDC}", "{" + (cons / "board_top_derived_constraints.sdc").as_posix() + "}")
                       .replace("{CSDC}", "{" + (cons / "cdc.sdc").as_posix() + "}"))
        rc = subprocess.run([c.LIBERO, f"SCRIPT:{tcl.as_posix()}", f"LOGFILE:{log.as_posix()}"], cwd=bdir.parent,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
        if rc:
            return rc
        with open(log, "a") as f:
            f.write(f"A17: {m.group(0)} -> {new}\n")
        for d in ("designer", "export"):
            shutil.rmtree(bdir / d, ignore_errors=True)
            shutil.copytree(net / d, bdir / d)
        return 0
    raise ValueError(flow)


def check(build, manifest, out, rebuild=None):
    mpath = out.parent / f"{out.stem}.manifest.json"
    mpath.write_text(json.dumps(manifest, indent=2))
    c.egaudit("check", build, "--manifest", mpath, *(["--rebuild", rebuild] if rebuild else []), "--out", out)
    return {r: v for r, (v, _) in c.read_verdicts(out).items()}


def run(board):
    out = RESULTS / board
    work = c.BUILD / f"rq2_{board}"
    design, data = variant(work)
    r14, r14r = work / "R14", work / "R14r"
    m14 = c.load_json(out / "R14.manifest.json")
    baseline = {r: v for r, (v, _) in c.read_verdicts(out / "R14.csv").items()}
    rows = []

    def record(case, v, v_plain, note, ignore=NOT_DEPLOYED):
        exp = EXPECTED.get(case, [])
        worse = sorted(r for r, x in v.items() if r not in ignore and r not in exp
                       and x != baseline[r] and x in BAD | {"PARTIAL", "PROJECT"} and baseline[r] == "SATISFIED")
        plain = sorted(r for r, x in v_plain.items() if r not in ignore
                       and x != baseline[r] and x in BAD | {"PARTIAL", "PROJECT"} and baseline[r] == "SATISFIED")
        rows.append([board, case, ";".join(exp), ";".join(v[r] for r in exp),
                     int(all(v[r] in BAD for r in exp)) if exp else "", ";".join(worse),
                     ";".join(plain) or "none", note])

    if not RECHECK and c.build(design, board, r14r)[0]:
        raise SystemExit(f"{board}: R14r build failed, see {r14r}.log")
    dump_evidence(r14r)

    record("N5", check(r14, m14, out / "N5.csv", r14r), check(r14, m14, out / "N5_plain.csv"), "rebuild=R14r")
    b0, m0 = c.BUILD / "rq1" / f"{DESIGN}_{board}", c.load_json(RQ1 / board / "manifest.json")
    bsd1 = [check(b0, m0, out / f"N5_{n}.csv", work / n)["BSD-1"] for n in ("N2", "N2r1", "N2r2", "N2r3", "N2r4")]
    rows[-1][-1] += f"; RQ1 release against N2, N2r1-N2r4: BSD-1 {';'.join(bsd1)}"

    name = EDIT["A14"][0]
    assert (data / name).read_text() != EDIT["A14"][1], "the memory-initialization file must be the approved one"
    a16 = work / "A14"
    dump_evidence(a16)
    m16 = released_from(m14, a16)
    record("A16", check(a16, m16, out / "A16.csv", r14r), check(a16, m16, out / "A16_plain.csv"),
           f"restored={name}")

    a17 = work / "A17"
    rc = None if c.BOARDS[board]["flow"] == "quartus" else 0
    if not RECHECK and rc == 0:
        shutil.rmtree(a17, ignore_errors=True)
        shutil.copytree(r14, a17)
        rc = tamper(board, a17, work / "A17.log")
    if rc is None:
        rows.append([board, "A17", "BSD-1", "", "", "", "", "not run under Quartus"])
    elif rc:
        rows.append([board, "A17", "BSD-1", "", "", "", "", f"flow failed ({rc})"])
    else:
        ev = dump_evidence(a17)
        m17 = released_from(m14, a17)
        ev0 = dump_evidence(r14)
        record("A17", check(a17, m17, out / "A17.csv", r14r), check(a17, m17, out / "A17_plain.csv"),
               f"configuration_changed={ev.get('config_sha256') != ev0.get('config_sha256')}")

    c.write_csv(out / "cases_rebuild.csv", ["board", "case", "expected", "egaudit_verdict", "egaudit_detected",
                                            "other_records_worse", "flagged_without_rebuild", "note"], rows)


if __name__ == "__main__":
    for b in [a for a in sys.argv[1:] if not a.startswith("--")] or list(c.BOARDS):
        run(b)
