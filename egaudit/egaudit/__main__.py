import argparse
import csv
import glob
import hashlib
import json
import sys
from pathlib import Path

from . import deploy as deploy_mod
from . import simulation as sim_mod
from .evidence import _digests, collect, inventory, sha256
from .rules import evaluate


def _load(path):
    return json.loads(Path(path).read_text()) if path else None


def _file_record(path, key="file"):
    return {key: Path(path).name, "sha256": sha256(Path(path))}


def cmd_check(a):
    ev = collect(Path(a.build))
    if a.rebuild:
        rb = collect(Path(a.rebuild))
        ev["rebuild"] = {k: rb[k] for k in ("sources", "constraints", "options_digest", "config_sha256")}
    man = _load(a.manifest)
    if a.simulation:
        rec = _load(a.simulation)
        rec["_problems"] = sim_mod.verify(rec, Path(a.simulation).parent)
        released = (man or {}).get("simulation", {}).get("sha256")
        if released and released != sha256(Path(a.simulation)):
            rec["_problems"].insert(0, "simulation record differs from the released one")
        ev["simulation_record"] = rec
    rows = evaluate(ev, man, _load(a.deploy))
    out = open(a.out, "w", newline="") if a.out else sys.stdout
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["record", "verdict", "reason"])
    w.writerows(rows)


def cmd_inventory(a):
    rows = inventory(Path(a.build))
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["path", "family", "bytes", "sha256"])
        w.writeheader()
        w.writerows(rows)


def cmd_manifest(a):
    ev = collect(Path(a.build))
    m = {
        "design": Path(a.build).name,
        "approved": {"sources": ev["sources"], "constraints": ev["constraints"],
                     "ip": {k: dict(v, provider=a.ip_provider) for k, v in ev["ip"].items()},
                     "options_digest": ev["options_digest"], "reviewer": a.reviewer},
        "tool": {"vendor": ev["vendor"], "version": ev["tool_version"]},
        "reports": {"timing": ev.get("timing_report_sha256")},
        "bitstream": {"file": ev["bitstream"], "sha256": ev.get("bitstream_sha256")},
        "signature": {"signer": a.signer, "approved_by": a.approver},
        "release": {"id": a.release_id, "approver": a.approver,
                    "workflow": a.workflow, "service_account": a.service_account},
        "target": {"device": ev["device"], "idcode": a.target_idcode, "serial": a.target_serial},
    }
    if a.testbench:
        m["approved"]["testbench"] = _digests(a.testbench)
    if a.simulation:
        m["simulation"] = _file_record(a.simulation, "record")
    if a.tool_image:
        files = sorted({Path(f) for pattern in a.tool_image for f in glob.glob(pattern)}, key=lambda p: p.name)
        if not files:
            raise SystemExit(f"--tool-image matched no file: {a.tool_image}")
        lines = "".join(f"{p.name} {sha256(p)}\n" for p in files)
        m["tool"]["image_sha256"] = hashlib.sha256(lines.encode()).hexdigest()
        m["tool"]["image_files"] = len(files)
    if a.license_record:
        m["license"] = _file_record(a.license_record, "record")
    if a.access_log:
        m["access_log"] = _file_record(a.access_log)
    if a.key_record:
        m["keys"] = _file_record(a.key_record, "handling_record")
    Path(a.out).write_text(json.dumps(m, indent=2))


def cmd_deploy(a):
    rec = deploy_mod.record(a.vendor, a.log, a.file, a.operator)
    Path(a.out).write_text(json.dumps(rec, indent=2))


def cmd_sim(a):
    rec = sim_mod.record(a.simulator, a.dir, a.pass_pattern, a.fail_pattern)
    Path(a.out).write_text(json.dumps(rec, indent=2))


def main():
    p = argparse.ArgumentParser(prog="egaudit", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("check")
    s.add_argument("build")
    s.add_argument("--manifest")
    s.add_argument("--deploy")
    s.add_argument("--simulation", help="simulation record written by 'egaudit sim', next to its logs")
    s.add_argument("--rebuild", help="build directory of a separate rebuild of the approved inputs")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_check)

    s = sub.add_parser("inventory")
    s.add_argument("build")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_inventory)

    s = sub.add_parser("manifest")
    s.add_argument("build")
    s.add_argument("--out", required=True)
    for opt in ("reviewer", "approver", "signer", "release-id", "workflow",
                "service-account", "target-idcode", "target-serial", "ip-provider"):
        s.add_argument(f"--{opt}")
    s.add_argument("--testbench", action="append", help="approved testbench file (repeatable)")
    s.add_argument("--simulation", help="simulation record written by 'egaudit sim'")
    s.add_argument("--tool-image", action="append",
                   help="tool executable or glob pattern; the digests of all matches form the installation digest")
    s.add_argument("--license-record", help="record of the license state")
    s.add_argument("--access-log", help="access log of the source, report, and result stores")
    s.add_argument("--key-record", help="key-handling record")
    s.set_defaults(fn=cmd_manifest)

    s = sub.add_parser("deploy")
    s.add_argument("--vendor", required=True, choices=sorted(deploy_mod.PARSERS))
    s.add_argument("--log", required=True, action="append")
    s.add_argument("--file", required=True)
    s.add_argument("--operator")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_deploy)

    s = sub.add_parser("sim")
    s.add_argument("--simulator", required=True, choices=sorted(sim_mod.LOGS))
    s.add_argument("--dir", required=True, help="directory with the simulator's compile and run logs")
    s.add_argument("--pass-pattern", default=r"\bPASS\b", help="regular expression the testbench prints on success")
    s.add_argument("--fail-pattern", default=r"\bFAIL\b", help="regular expression the testbench prints on failure")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_sim)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
