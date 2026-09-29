import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).absolute().parent.parent))
import common as c
from run import RESULTS, DESIGN, summarize

sys.path.insert(0, str(c.ROOT / "egaudit"))
sys.path.insert(0, str(c.ROOT / "flows" / "sim"))
from egaudit.evidence import collect, sha256
from run_sim import TB, simulate

TOOLS = Path(os.environ.get("OPENXC7_TOOLS", c.ROOT.parent / "tools"))
XILINX_LICENSES = Path(os.environ.get("APPDATA", "")) / "XilinxLicense"
LIBERO_ROOT = Path(c.LIBERO).parents[2] if len(Path(c.LIBERO).parents) > 2 else Path(c.LIBERO).parent
SIMULATOR = {"vivado": ("xsim", "xsim"), "quartus": ("questa", "questa"), "libero": ("questa_mchp", "questa"),
             "openxc7": ("icarus", "icarus")}


def tool_image(flow):
    if flow == "vivado":
        return [Path(c.VIVADO).parent / "unwrapped" / "win64.o" / "*.exe"]
    if flow == "quartus":
        return [Path(c.QUARTUS_SH).parent / "quartus_*.exe"]
    if flow == "libero":
        return [Path(c.LIBERO).parent / "*.exe", LIBERO_ROOT / "Synplify_Pro" / "bin" / "*.exe",
                LIBERO_ROOT / "Synplify_Pro" / "bin64" / "*.exe"]
    return [TOOLS / "oss-cad-suite" / "bin" / "yosys.exe", TOOLS / "openxc7" / "bin" / "*.exe"]


def license_source(flow):
    if flow == "vivado":
        return [{"file": p.name, "sha256": sha256(p)} for p in sorted(XILINX_LICENSES.glob("*.lic"))]
    if flow == "libero":
        return [{"server": os.environ.get("LM_LICENSE_FILE", "")}]
    if flow == "quartus":
        return [{"note": "no Quartus license file or server on this PC; Quartus Prime Standard logged no licensed feature"}]
    return [{"note": "open-source tools; no license server"}]


def run(board, recheck=False):
    t = c.BOARDS[board]
    flow = t["flow"]
    out = RESULTS / board
    bdir = c.BUILD / "rq1" / f"{DESIGN}_{board}"
    sim_name, rec_name = SIMULATOR[flow]
    sdir = c.BUILD / "rq1_sim" / board
    if recheck:
        check(bdir, out, sdir)
        return
    shutil.rmtree(sdir, ignore_errors=True)
    simulate(sim_name, sdir)
    c.egaudit("sim", "--simulator", rec_name, "--dir", sdir, "--out", sdir / "sim_record.json")
    rec = json.loads((sdir / "sim_record.json").read_text())
    if rec["result"] != "PASS":
        raise SystemExit(f"{board}: simulation {rec['result']}")
    shutil.copy2(sdir / "sim_record.json", out / "sim_record.json")

    ev = collect(bdir)
    record = {"tool": flow, "features_logged": ev["license"], "license_source": license_source(flow)}
    (out / "license_record.json").write_text(json.dumps(record, indent=2))

    target = ["--target-idcode", t["idcode"]] + (["--target-serial", t["serial"]] if "serial" in t else [])
    images = sum((["--tool-image", p] for p in tool_image(flow)), [])
    c.egaudit("manifest", bdir, "--out", out / "manifest_project.json", "--release-id", f"{DESIGN}_{board}",
              *c.ROLES, *target, "--testbench", TB, "--simulation", sdir / "sim_record.json", *images,
              "--license-record", out / "license_record.json")
    check(bdir, out, sdir)
    man = json.loads((out / "manifest_project.json").read_text())
    print(board, sim_name, rec["result"], sorted(rec["files"]), man["tool"]["image_files"], "executables")


def check(bdir, out, sdir):
    deploy = ["--deploy", out / "deploy.json"] if (out / "deploy.json").exists() else []
    c.egaudit("check", bdir, "--manifest", out / "manifest_project.json", *deploy,
              "--simulation", sdir / "sim_record.json", "--out", out / "verdicts_project.csv")


if __name__ == "__main__":
    for b in [a for a in sys.argv[1:] if not a.startswith("--")] or list(c.BOARDS):
        run(b, recheck="--recheck" in sys.argv)
    summarize()
