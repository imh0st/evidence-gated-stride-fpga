import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).absolute().parent.parent
BUILD = ROOT / "build"

VIVADO = os.environ.get("VIVADO") or shutil.which("vivado") or "vivado"
QUARTUS_SH = os.environ.get("QUARTUS_SH") or shutil.which("quartus_sh") or "quartus_sh"
QUARTUS_PGM = os.environ.get("QUARTUS_PGM") or shutil.which("quartus_pgm") or "quartus_pgm"
LIBERO = os.environ.get("LIBERO") or shutil.which("libero") or "libero"
FPEXPRESS = os.environ.get("FPEXPRESS") or shutil.which("FPExpress") or "FPExpress"
PRJXRAY_DB = Path(os.environ.get("PRJXRAY_DB",
                                 ROOT.parent / "tools" / "openxc7" / "share" / "nextpnr" / "external" / "prjxray-db" / "zynq7"))
DISCO_RESTORE_JOB = os.environ.get("DISCO_RESTORE_JOB", "")

BOARDS = {
    "zybo":  {"flow": "vivado",  "part": "xc7z020clg400-1", "cdc": "cdc.xdc", "idcode": "23727093"},
    "c10lp": {"flow": "quartus", "part": "10CL025YU256I7G", "cdc": "cdc.sdc", "idcode": "020F30DD"},
    "disco": {"flow": "libero",  "part": "MPFS095T-1FCSG325E", "cdc": "cdc.sdc", "idcode": "0f8181cf",
              "serial": "6646180cba578c73b3eb984f201a9204"},
    "zybo_open": {"flow": "openxc7", "part": "xc7z020clg400-1", "cdc": "cdc.xdc", "idcode": "23727093"},
}

ROLES = ["--reviewer", "design-reviewer", "--approver", "release-approver", "--signer", "release-signer",
         "--workflow", "experiments/rq1_end_to_end/run.py", "--service-account", "svc-release",
         "--ip-provider", "fpga-vendor"]


def board_dir(board):
    return ROOT / "boards" / board


def approved_cdc(board):
    return board_dir(board) / BOARDS[board]["cdc"]


def build(design, board, out, cdc=None, log=None, opts=None):
    b, cdc = BOARDS[board], Path(cdc or approved_cdc(board))
    design = Path(design).as_posix() if Path(design).is_dir() else design
    opts = Path(opts).as_posix() if opts else "-"
    out, log = Path(out), Path(log or f"{out}.log")
    if out.exists():
        shutil.rmtree(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    log.unlink(missing_ok=True)
    t0 = time.monotonic()
    if b["flow"] == "vivado":
        cmd = [VIVADO, "-mode", "batch", "-nojournal", "-log", str(log),
               "-source", str(ROOT / "flows" / "vivado" / "build.tcl"), "-tclargs",
               design, board_dir(board).as_posix(), b["part"], cdc.as_posix(), out.as_posix(), opts]
        rc = subprocess.run(cmd, cwd=out.parent, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
    elif b["flow"] == "quartus":
        cmd = [QUARTUS_SH, "-t", str(ROOT / "flows" / "quartus" / "build.tcl"),
               design, board_dir(board).as_posix(), b["part"], cdc.as_posix(), out.as_posix(), opts]
        with open(log, "w") as f:
            rc = subprocess.run(cmd, cwd=out.parent, stdout=f, stderr=subprocess.STDOUT).returncode
    elif b["flow"] == "openxc7":
        cmd = [sys.executable, str(ROOT / "flows" / "openxc7" / "build.py"),
               design, board_dir(board).as_posix(), b["part"], cdc.as_posix(), out.as_posix(), opts]
        with open(log, "w") as f:
            rc = subprocess.run(cmd, cwd=out.parent, stdout=f, stderr=subprocess.STDOUT).returncode
    else:
        cmd = [LIBERO, f"SCRIPT:{(ROOT / 'flows' / 'libero' / 'build.tcl').as_posix()}",
               f"SCRIPT_ARGS:{design} {board_dir(board).as_posix()} {cdc.as_posix()} {out.as_posix()} {opts}",
               f"LOGFILE:{log.as_posix()}"]
        rc = subprocess.run(cmd, cwd=out.parent, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
    return rc, round(time.monotonic() - t0, 1)


def programming_file(build_dir):
    for pattern in ("*.bit", "*.jic", "*.sof", "export/*.job"):
        hits = sorted(Path(build_dir).glob(pattern))
        if hits:
            return hits[0]
    raise FileNotFoundError(f"no programming file in {build_dir}")


def program(board, pfile, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    flow = BOARDS[board]["flow"]
    if flow == "openxc7":
        log, cmp_log = out / "program.log", out / "readback_compare.log"
        rb, mask = out / "readback.bin", out / "readback_mask.bin"
        subprocess.run([VIVADO, "-mode", "batch", "-nojournal", "-log", str(log),
                        "-source", str(ROOT / "flows" / "program" / "vivado_readback.tcl"), "-tclargs",
                        pfile.as_posix(), "-", rb.as_posix()], cwd=out, stdout=subprocess.DEVNULL, check=True)
        subprocess.run([sys.executable, str(ROOT / "flows" / "program" / "readback_mask.py"),
                        str(PRJXRAY_DB / "xc7z020clg400-1" / "part.yaml"), str(PRJXRAY_DB / "xc7z020" / "tilegrid.json"),
                        str(PRJXRAY_DB), str(pfile.parent / "routed.json"), str(mask)], check=True)
        subprocess.run([sys.executable, str(ROOT / "flows" / "program" / "readback_compare.py"), str(pfile), str(rb),
                        "--mask-words", str(mask), "--log", str(cmp_log)])
        return [log, cmp_log]
    if flow == "vivado":
        log = out / "program.log"
        msk = pfile.with_suffix(".msk")
        subprocess.run([VIVADO, "-mode", "batch", "-nojournal", "-log", str(log),
                        "-source", str(ROOT / "flows" / "program" / "vivado.tcl"), "-tclargs",
                        pfile.as_posix(), msk.as_posix() if msk.exists() else "-", (out / "readback.rbd").as_posix()],
                       cwd=out, stdout=subprocess.DEVNULL, check=True)
        return [log]
    if flow == "quartus":
        log = out / "program.log"
        with open(log, "w") as f:
            if pfile.suffix == ".jic":
                cdf = out / "chain.cdf"
                cdf.write_text(_jic_chain(board, pfile))
                cmd = [QUARTUS_PGM, "-c", "1", str(cdf)]
            else:
                cmd = [QUARTUS_PGM, "-c", "1", "-m", "JTAG", "-o", f"p;{pfile.as_posix()}"]
            subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, check=True)
        return [log]
    logs = []
    for action in ("DEVICE_INFO", "PROGRAM", "VERIFY", "VERIFY_DIGEST"):
        log = out / f"{action.lower()}.log"
        subprocess.run([FPEXPRESS, f"SCRIPT:{(ROOT / 'flows' / 'program' / 'fpexpress.tcl').as_posix()}",
                        f"SCRIPT_ARGS:{pfile.as_posix()} {(out / 'fpx').as_posix()} {action}",
                        f"LOGFILE:{log.as_posix()}"], check=True)
        logs.append(log)
    return logs


def _jic_chain(board, pfile):
    """Chain description for programming the configuration flash from a .jic: the FPGA erases, blank-checks,
    programs, and CRC-verifies the flash through the Serial Flash Loader; any other device that the
    programmer detects on the chain is left alone."""
    detected = subprocess.run([QUARTUS_PGM, "-c", "1", "-a"], capture_output=True, text=True).stdout
    flash = (board_dir(board) / "flash.tcl").read_text().split()[-1]
    lines = []
    for idcode, name in re.findall(r"^\s*([0-9A-F]{8})\s+(\S+)", detected, re.M):
        if idcode == BOARDS[board]["idcode"]:
            lines.append(f'\tP ActionCode(Cfg)\n\t\tDevice PartName({BOARDS[board]["part"][:-3]}) '
                         f'Path("{pfile.parent.as_posix()}/") File("{pfile.name}") '
                         f'MfrSpec(OpMask(1) SEC_Device({flash}) Child_OpMask(1 7));')
        else:
            lines.append(f"\tP ActionCode(Ign)\n\t\tDevice PartName({name}) MfrSpec(OpMask(0));")
    return ("JedecChain;\n\tFileRevision(JESD32A);\n\tDefaultMfr(6E);\n" + "\n".join(lines) +
            "\nChainEnd;\nAlteraBegin;\n\tChainType(JTAG);\nAlteraEnd;\n")


def restore_disco(out):
    if not DISCO_RESTORE_JOB:
        raise SystemExit("set DISCO_RESTORE_JOB to the .job file of Microchip's released Discovery Kit image")
    return program("disco", Path(DISCO_RESTORE_JOB), out)


def egaudit(*args):
    subprocess.run([sys.executable, "-m", "egaudit", *map(str, args)], cwd=ROOT / "egaudit", check=True)


def read_verdicts(path):
    with open(path, newline="") as f:
        return {r["record"]: (r["verdict"], r["reason"]) for r in csv.DictReader(f)}


def write_csv(path, header, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def load_json(path):
    return json.loads(Path(path).read_text())
