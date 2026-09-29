import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).absolute().parent.parent))
import common as c

HERE = Path(__file__).absolute().parent
RESULTS = HERE / "results"
DESIGN = "cdc_ref"


def run(board, do_program=True, recheck=False, reprogram=False):
    t = c.BOARDS[board]
    out = RESULTS / board
    out.mkdir(parents=True, exist_ok=True)
    bdir = c.BUILD / "rq1" / f"{DESIGN}_{board}"
    if not recheck and not reprogram:
        rc, sec = c.build(DESIGN, board, bdir)
        if rc:
            raise SystemExit(f"{board}: build failed ({rc}), see {bdir}.log")
        c.write_csv(out / "build.csv", ["design", "board", "exit_code", "seconds"], [[DESIGN, board, rc, sec]])

    target = ["--target-idcode", t["idcode"]] + (["--target-serial", t["serial"]] if "serial" in t else [])
    c.egaudit("manifest", bdir, "--out", out / "manifest.json", "--release-id", f"{DESIGN}_{board}",
              *c.ROLES, *target)

    deploy = []
    if do_program:
        pfile = c.programming_file(bdir)
        if recheck:
            logs = sorted((out / "program").glob("*.log"))
        else:
            logs = c.program(board, pfile, out / "program")
        c.egaudit("deploy", "--vendor", t["flow"], *sum((["--log", l] for l in logs), []),
                  "--file", pfile, "--operator", "board-operator", "--out", out / "deploy.json")
        deploy = ["--deploy", out / "deploy.json"]

    c.egaudit("check", bdir, *deploy, "--out", out / "verdicts_default.csv")
    c.egaudit("check", bdir, "--manifest", out / "manifest.json", *deploy, "--out", out / "verdicts_release.csv")


def summarize():
    cols, table = [], {}
    for board in c.BOARDS:
        for cond in ("default", "release", "project"):
            f = RESULTS / board / f"verdicts_{cond}.csv"
            if f.exists():
                cols.append(f"{board}:{cond}")
                for rec, (verdict, _) in c.read_verdicts(f).items():
                    table.setdefault(rec, {})[cols[-1]] = verdict
    c.write_csv(RESULTS / "rq1_verdicts.csv", ["record"] + cols,
                [[rec] + [v.get(col, "") for col in cols] for rec, v in table.items()])


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for b in args or list(c.BOARDS):
        run(b, do_program="--no-program" not in sys.argv, recheck="--recheck" in sys.argv,
            reprogram="--reprogram" in sys.argv)
    summarize()
