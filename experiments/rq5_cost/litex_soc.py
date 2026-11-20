import csv
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).absolute().parent
sys.path.insert(0, str(HERE))
from logic_scaling import c, time_check, utilization

TOP, PART = "xilinx_alveo_u250", "xcu250-figd2104-2L-e"
OUT = c.BUILD / "rq5_litex"
RESULTS = HERE / "results" / "litex_soc.csv"
FIELDS = ["cores", "logic_unit", "logic_used", "logic_available", "ff_used", "files", "bytes",
          "vendor_build_s", "exit_code", "egaudit_mean_s", "egaudit_sd_s"]
REPORTS = ["utilization", "timing_summary", "clock_interaction", "cdc -details", "bus_skew", "drc"]


def generate(cores, gen):
    from litex.soc.cores.cpu.rocket.core import Rocket
    from litex.soc.integration.soc import SoC
    from litex_boards.targets import xilinx_alveo_u250 as target
    add_ram = SoC.add_ram
    SoC.add_ram = lambda self, name, *a, **k: None if name == "firmware_ram" else add_ram(self, name, *a, **k)
    args_read = Rocket.args_read

    def read(args):
        args_read(args)
        Rocket.cpu_num_cores = cores
    Rocket.args_read = staticmethod(read)
    argv = sys.argv
    sys.argv = [TOP, "--cpu-type", "rocket", "--cpu-variant", "full", "--with-pcie",
                "--output-dir", str(gen), "--build", "--no-compile-gateware"]
    try:
        target.main()
    finally:
        sys.argv, SoC.add_ram, Rocket.args_read = argv, add_ram, staticmethod(args_read)


def build(cores):
    gen, out = OUT / "gen" / f"rocket{cores}", OUT / f"rocket{cores}"
    generate(cores, gen)
    gw = gen / "gateware"
    script = (gw / f"{TOP}.tcl").read_text()
    files = re.findall(r"^read_verilog \{(.+)\}$", script, re.M) + [str(f) for f in sorted(gw.glob("*.init"))]
    tcl = [f"create_project -force -part {PART} litex_rocket{cores} {{{out.as_posix()}}}",
           "add_files " + " ".join("{" + Path(f).as_posix() + "}" for f in files),
           f"set_property top {TOP} [current_fileset]",
           "add_files -fileset constrs_1 {" + (gw / f"{TOP}.xdc").as_posix() + "}",
           f"set_property PROCESSING_ORDER EARLY [get_files {TOP}.xdc]",
           script[script.index("create_ip"):script.index("synth_ip")],
           "launch_runs -jobs 8 synth_1", "wait_on_run synth_1",
           'if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} { error "synth_1 failed" }',
           "launch_runs -jobs 8 impl_1 -to_step write_bitstream", "wait_on_run impl_1",
           'if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} { error "impl_1 failed" }',
           "open_run impl_1", "file mkdir {" + (out / "reports").as_posix() + "}"]
    tcl += [f"report_{r} -file {{{(out / 'reports' / (r.split()[0] + '.rpt')).as_posix()}}}" for r in REPORTS]
    (gen / "project.tcl").write_text("\n".join(tcl + ["close_project"]) + "\n")
    t0 = time.monotonic()
    rc = subprocess.run([c.VIVADO, "-mode", "batch", "-nojournal", "-log", f"{out}.log", "-source", str(gen / "project.tcl")],
                        cwd=OUT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
    row = {"cores": cores, "vendor_build_s": round(time.monotonic() - t0, 1), "exit_code": rc}
    if rc == 0:
        row.update(zip(FIELDS[1:5], utilization(out, "vivado")))
    upsert(row)


def load():
    return list(csv.DictReader(open(RESULTS))) if RESULTS.exists() else []


def upsert(row):
    rows = [r for r in load() if int(r["cores"]) != int(row["cores"])] + [row]
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS, "w", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: int(r["cores"])))
    print(row, flush=True)


def time_all():
    for row in load():
        if str(row["exit_code"]) != "0":
            continue
        out = OUT / f"rocket{row['cores']}"
        _, runs = time_check(out)
        files = [p for p in out.rglob("*") if p.is_file()]
        row.update(files=len(files), bytes=sum(p.stat().st_size for p in files),
                   egaudit_mean_s=round(statistics.mean(runs), 3), egaudit_sd_s=round(statistics.stdev(runs), 3))
        upsert(row)


if __name__ == "__main__":
    if sys.argv[1] == "time":
        time_all()
    else:
        for n in sys.argv[1:]:
            build(int(n))
