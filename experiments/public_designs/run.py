"""Public designs, one per design flow, built with the flow's tool and programmed on the evaluation board.

    python run.py build [design ...]     fetch the design, port it where needed, build it, record the time
    python run.py check [design ...]     release manifest, programming and device verification, EGAudit
                                         (--recheck: from the existing builds and programming logs)
    python run.py ip zybo_hdmi c10lp_multiproc   IP instances the tool lists against those EGAudit extracted

designs/public.csv names each design's source, version, and license:
  zybo_hdmi        Digilent Zybo Z7-20 HDMI demo                          Vivado    Zybo Z7-20
  c10lp_multiproc  Intel Cyclone 10 LP multiprocessor Nios II design,
                   ported to Nios V (flows/quartus/niosv_port.py)         Quartus   Cyclone 10 LP kit
  discovery_ref    Microchip PolarFire SoC Discovery Kit reference design Libero    Discovery Kit
  picosoc_zybo     PicoSoC ported to the Zybo Z7-20 (designs/picosoc_zybo) openXC7  Zybo Z7-20
The Intel design is distributed under Intel's license and is not included here: download top.par from
its page and set INTEL_PAR to the file. After the Discovery reference design, the board is programmed
back with Microchip's released image (DISCO_RESTORE_JOB).
"""
import csv
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

HERE = Path(__file__).absolute().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent / "egaudit"))
import common as c

OUT = Path(os.environ.get("PUBLIC_BUILD", c.BUILD / "public"))  # a short path avoids Windows path limits
REPOS = c.BUILD / "_repos"
RESULTS = HERE / "results"
DESIGNS = {r["design"]: r for r in csv.DictReader(open(c.ROOT / "designs" / "public.csv"))}
DYNCLK = "zybo-20-hw.ipdefs/repo/vivado-library/ip/axi_dynclk_v1_1/drivers/ddynclk_v1_0"
DYNCLK_FILES = {"src/Makefile": "src/Makefile", "src/ddynclk.c": "src/ddynclk.c", "src/ddynclk.h": "src/ddynclk.h",
                "src/ddynclk_g.c": "src/ddynclk_g.c", "src/ddynclk_selftest.c": "src/ddynclk_selftest.c",
                "src/ddynclk_sinit.c": "src/ddynclk_sinit.c", "data/dynclk.mdd": "data/ddynclk.mdd",
                "data/dynclk.tcl": "data/ddynclk.tcl"}
QSYS = ["philosopher_zero", "philosopher_one", "philosopher_two", "multiprocessor_tutorial_main_system"]


def build_dir(name):
    return {"discovery_ref": OUT / name / "MPFS_DISCOVERY", "picosoc_zybo": OUT / name / "out"}.get(name, OUT / name)


def programming_file(name):
    b = build_dir(name)
    return {"zybo_hdmi": b / "zybo-20-hw.runs" / "impl_1" / "design_1_wrapper.bit",
            "c10lp_multiproc": b / "top_level.jic",
            "discovery_ref": b / "export" / "MPFS_DISCOVERY.job",
            "picosoc_zybo": b / "picosoc_zybo.bit"}[name]


def git_checkout(name, url, commit):
    repo = REPOS / name
    if not repo.exists():
        subprocess.run(["git", "clone", "-q", url, str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", commit], check=True)
    return repo


def zybo_hdmi(out, log):
    """Release 20/HDMI/2025.1-1 of Digilent/Zybo-Z7. Its archive lacks the driver files of the
    axi_dynclk IP, without which Vivado stops; they are taken from Digilent/vivado-library."""
    d = DESIGNS["zybo_hdmi"]
    archive = REPOS / Path(d["source"]).name
    if not archive.exists():
        REPOS.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(d["source"], archive)
    with zipfile.ZipFile(archive) as z:
        z.extractall(REPOS / "zybo_hdmi")
    shutil.copytree(REPOS / "zybo_hdmi" / "zybo-20-hw", out)
    lib = DESIGNS["vivado_library"]
    for src, dst in DYNCLK_FILES.items():
        target = out / DYNCLK / dst
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            urllib.request.urlretrieve(f"{lib['source']}/{lib['version']}/ip/axi_dynclk/drivers/dynclk/{src}", target)
    return subprocess.run([c.VIVADO, "-mode", "batch", "-nojournal", "-log", str(log), "-source",
                           str(HERE / "zybo_hdmi.tcl"), "-tclargs", (out / "zybo-20-hw.xpr").as_posix()],
                          cwd=OUT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode


def c10lp_multiproc(out, log):
    """Intel's design (top.par, Quartus 17.0) restored in Quartus 25.1, which no longer offers Nios II:
    the four processors are ported to Nios V/m, the system is generated, and the project is compiled."""
    par = os.environ.get("INTEL_PAR")
    if not par:
        raise SystemExit("set INTEL_PAR to top.par, downloaded from the page in designs/public.csv")
    tmp = REPOS / "c10lp_par"
    with tarfile.open(par) as t:
        t.extractall(tmp)
    out.mkdir(parents=True)
    qsys_bin = Path(shutil.which(c.QUARTUS_SH) or c.QUARTUS_SH).parent.parent / "sopc_builder" / "bin"
    with open(log, "w") as f:
        run = lambda cmd: subprocess.run(cmd, cwd=out, stdout=f, stderr=subprocess.STDOUT).returncode
        rc = run([c.QUARTUS_SH, "--restore", str(next(tmp.rglob("top.qar")))])
        rc = rc or run([sys.executable, str(c.ROOT / "flows" / "quartus" / "niosv_port.py"),
                        str(shutil.which("qsys-script") or qsys_bin / "qsys-script"), *[f"{q}.qsys" for q in QSYS]])
        rc = rc or run([str(shutil.which("qsys-generate") or qsys_bin / "qsys-generate"), f"{QSYS[-1]}.qsys",
                        "--synthesis=VERILOG", f"--search-path={out.as_posix()},$", f"--part={c.BOARDS['c10lp']['part']}"])
        rc = rc or run([c.QUARTUS_SH, "-t", str(HERE / "c10lp_project.tcl")])
        rc = rc or run([c.QUARTUS_SH, "--flow", "compile", "top_level"])
        flash = re.search(r"flash_device (\S+)", (c.board_dir("c10lp") / "flash.tcl").read_text()).group(1)
        rc = rc or run([str(Path(c.QUARTUS_SH).with_name("quartus_cpf")), "-c", "-d", flash, "-s",
                        c.BOARDS["c10lp"]["part"], "top_level.sof", "top_level.jic"])
    return rc


def discovery_ref(out, log):
    d = DESIGNS["discovery_ref"]
    repo = git_checkout("discovery_ref", d["source"], d["version"])
    return subprocess.run([c.LIBERO, f"SCRIPT:{(c.ROOT / 'flows' / 'libero' / 'build_reference.tcl').as_posix()}",
                           f"SCRIPT_ARGS:{repo.as_posix()} {out.as_posix()}", f"LOGFILE:{log.as_posix()}"],
                          cwd=OUT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode


def picosoc_zybo(out, log):
    """Upstream PicoSoC and PicoRV32 sources, unmodified, with the Zybo top level of designs/picosoc_zybo."""
    d = DESIGNS["picosoc_zybo"]
    repo = git_checkout("picorv32", d["source"], d["version"])
    port = c.ROOT / "designs" / "picosoc_zybo"
    (out / "rtl").mkdir(parents=True)
    (out / "board").mkdir()
    for f in ["picorv32.v", "picosoc/picosoc.v", "picosoc/spimemio.v", "picosoc/simpleuart.v"]:
        shutil.copy2(repo / f, out / "rtl")
    for f in ["board_top.v", "order.txt"]:
        shutil.copy2(port / "rtl" / f, out / "rtl")
    for f in ["pins.xdc", "clk_gen.v", "clocks.xdc"]:
        shutil.copy2(port / f, out / "board")
    with open(log, "w") as f:
        return subprocess.run([sys.executable, str(c.ROOT / "flows" / "openxc7" / "build.py"), str(out),
                               str(out / "board"), c.BOARDS["zybo_open"]["part"], str(out / "board" / "clocks.xdc"),
                               str(out / "out")], stdout=f, stderr=subprocess.STDOUT).returncode


def build(name):
    out = OUT / name
    log = OUT / f"{name}.log"
    shutil.rmtree(out, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    rc = globals()[name](out, log)
    sec = round(time.monotonic() - t0, 1)
    print(name, rc, sec)
    return [name, DESIGNS[name]["board"], rc, sec]


def check(name, recheck=False):
    board = DESIGNS[name]["board"]
    t = c.BOARDS[board]
    out = RESULTS / name
    out.mkdir(parents=True, exist_ok=True)
    bdir, pfile = build_dir(name), programming_file(name)
    target = ["--target-idcode", t["idcode"]] + (["--target-serial", t["serial"]] if "serial" in t else [])
    roles = [("experiments/public_designs/run.py" if a == "experiments/rq1_end_to_end/run.py" else a) for a in c.ROLES]
    c.egaudit("manifest", bdir, "--out", out / "manifest.json", "--release-id", name, *roles, *target)
    logs = sorted((out / "program").glob("*.log")) if recheck else c.program(board, pfile, out / "program")
    c.egaudit("deploy", "--vendor", t["flow"], *sum((["--log", l] for l in logs), []),
              "--file", pfile, "--operator", "board-operator", "--out", out / "deploy.json")
    c.egaudit("check", bdir, "--deploy", out / "deploy.json", "--out", out / "verdicts_default.csv")
    c.egaudit("check", bdir, "--manifest", out / "manifest.json", "--deploy", out / "deploy.json",
              "--out", out / "verdicts_release.csv")
    if board == "disco" and not recheck:
        c.restore_disco(out / "restore")


def summarize():
    cols, table = [], {}
    for name in DESIGNS:
        for cond in ("default", "release"):
            f = RESULTS / name / f"verdicts_{cond}.csv"
            if f.exists():
                cols.append(f"{name}:{cond}")
                for rec, (verdict, _) in c.read_verdicts(f).items():
                    table.setdefault(rec, {})[cols[-1]] = verdict
    c.write_csv(RESULTS / "verdicts.csv", ["record"] + cols,
                [[rec] + [v.get(col, "") for col in cols] for rec, v in table.items()])


def ip(name):
    """Compare the IP instances that the tool lists (Vivado's cell list; the .sopcinfo that Platform
    Designer writes) with those EGAudit extracted from the design files."""
    from egaudit.evidence import collect
    bdir = build_dir(name)
    if name == "zybo_hdmi":  # IP cells and hierarchical cells with a VLNV (AXI interconnects)
        listing = OUT / "zybo_hdmi_cells.txt"
        subprocess.run([c.VIVADO, "-mode", "batch", "-nojournal", "-nolog", "-source", str(HERE / "list_cells.tcl"),
                        "-tclargs", (bdir / "zybo-20-hw.xpr").as_posix(), listing.as_posix()], cwd=OUT,
                       stdout=subprocess.DEVNULL, check=True)
        tool = {f"{bd}/{cell}": vlnv for bd, cell, kind, vlnv in
                (l.rstrip(chr(10)).split("|") for l in open(listing)) if vlnv}
    elif name == "c10lp_multiproc":
        root = ET.parse(bdir / f"{QSYS[-1]}.sopcinfo").getroot()
        subsystems = {m.get("kind") for m in root.findall("module")} & set(QSYS)
        tool = {f"{QSYS[-1]}/{m.get('path').replace('.', '/')}": f"altera:{m.get('kind')}:{m.get('version')}"
                for m in root.findall("module") if m.get("kind") not in subsystems}
    else:
        raise SystemExit(f"{name}: no tool listing of IP instances (see rq3_extraction/ground_truth.csv)")
    got = {k: v["vlnv"] for k, v in collect(bdir)["ip"].items()}
    rows = [[k, v, got.get(k, ""), int(got.get(k) == v)] for k, v in sorted(tool.items())]
    rows += [[k, "", v, 0] for k, v in sorted(got.items()) if k not in tool]
    c.write_csv(RESULTS / f"ip_{name}.csv", ["instance", "tool", "egaudit", "match"], rows)
    print(f"{name}: tool {len(tool)}, egaudit {len(got)}, matched {sum(r[3] for r in rows)}")


if __name__ == "__main__":
    step, names = sys.argv[1], [a for a in sys.argv[2:] if not a.startswith("--")]
    names = names or [n for n in DESIGNS if DESIGNS[n]["board"]]
    RESULTS.mkdir(parents=True, exist_ok=True)
    if step == "build":
        f = RESULTS / "builds.csv"
        rows = {r["design"]: list(r.values()) for r in csv.DictReader(open(f))} if f.exists() else {}
        for n in names:
            rows[n] = build(n)
        c.write_csv(f, ["design", "board", "exit_code", "seconds"], list(rows.values()))
    elif step == "check":
        for n in names:
            check(n, recheck="--recheck" in sys.argv)
        summarize()
    else:
        for n in names if sys.argv[2:] else ["zybo_hdmi", "c10lp_multiproc"]:
            ip(n)
