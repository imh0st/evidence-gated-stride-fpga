import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).absolute().parent.parent))
import common as c

sys.path.insert(0, str(c.ROOT / "flows" / "sim"))
sys.path.insert(0, str(c.ROOT / "experiments" / "rq1_end_to_end"))
from run_sim import TB, simulate
from project_evidence import SIMULATOR, tool_image

HERE = Path(__file__).absolute().parent
RESULTS = HERE / "results"
RQ1 = HERE.parent / "rq1_end_to_end" / "results"
DESIGN = "cdc_ref"
EXPECTED = ["SIM-1"]
BAD = {"VIOLATED", "MISSING"}


def weaken(tb_text: str) -> str:
    old = "localparam integer RUN_US    = 200;"
    assert tb_text.count(old) == 1
    return tb_text.replace(old, "localparam integer RUN_US    = 2;")


def run(board, recheck=False):
    t = c.BOARDS[board]
    flow = t["flow"]
    out = RESULTS / board
    work = c.BUILD / "rq2_sim" / board
    sim_name, rec_name = SIMULATOR[flow]
    bdir = c.BUILD / "rq1" / f"{DESIGN}_{board}"
    if recheck:
        sdir = work / "sim"
    else:
        shutil.rmtree(work, ignore_errors=True)
        (work / "tb").mkdir(parents=True)
        tb = work / "tb" / TB.name
        tb.write_text(weaken(TB.read_text()))
        sdir = simulate(sim_name, work / "sim", tb)
        c.egaudit("sim", "--simulator", rec_name, "--dir", sdir, "--out", sdir / "sim_record.json")
        target = ["--target-idcode", t["idcode"]] + (["--target-serial", t["serial"]] if "serial" in t else [])
        images = sum((["--tool-image", p] for p in tool_image(flow)), [])
        c.egaudit("manifest", bdir, "--out", out / "A18.manifest.json", "--release-id", f"{DESIGN}_{board}",
                  *c.ROLES, *target, "--testbench", TB, "--simulation", sdir / "sim_record.json", *images,
                  "--license-record", RQ1 / board / "license_record.json")
    rec = json.loads((sdir / "sim_record.json").read_text())
    c.egaudit("check", bdir, "--manifest", out / "A18.manifest.json", "--deploy", RQ1 / board / "deploy.json",
              "--simulation", sdir / "sim_record.json", "--out", out / "A18.csv")
    verdicts = {r: v for r, (v, _) in c.read_verdicts(out / "A18.csv").items()}
    baseline = {r: v for r, (v, _) in c.read_verdicts(RQ1 / board / "verdicts_project.csv").items()}
    worse = sorted(r for r, v in verdicts.items() if r not in EXPECTED and v != baseline[r] and v in BAD | {"PARTIAL", "PROJECT"}
                   and baseline[r] == "SATISFIED")
    changed = sorted(r for r, v in verdicts.items() if v != baseline[r])
    detected = all(verdicts[r] in BAD for r in EXPECTED)
    note = f"simulator={sim_name} result={rec['result']} changed_from_project_baseline={';'.join(changed)}"
    c.write_csv(out / "cases_sim.csv", ["board", "case", "expected", "egaudit_verdict", "egaudit_detected",
                                        "other_records_worse", "vendor_flags", "note"],
                [[board, "A18", ";".join(EXPECTED), ";".join(verdicts[r] for r in EXPECTED), int(detected),
                  ";".join(worse), int(rec["result"] != "PASS"), note]])
    print(board, sim_name, rec["result"], verdicts["SIM-1"], verdicts["SIM-2"], "changed:", changed)


if __name__ == "__main__":
    for b in [a for a in sys.argv[1:] if not a.startswith("--")] or list(c.BOARDS):
        run(b, recheck="--recheck" in sys.argv)
    import importlib.util
    spec = importlib.util.spec_from_file_location("rq2_run", HERE / "run.py")
    rq2_run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rq2_run)
    rq2_run.summarize()
