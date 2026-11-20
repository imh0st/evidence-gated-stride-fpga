import re
from pathlib import Path

from .evidence import _digests, sha256

HDL = (".v", ".sv", ".vh", ".svh", ".vhd", ".vhdl")
LOGS = {
    "xsim": (("xvlog.log", "xvhdl.log"), ("xsim.log",)),
    "questa": (("vlog.log", "vcom.log"), ("vsim.log",)),
    "icarus": (("iverilog.deps",), ("vvp.log",)),
}
_XSIM_FILE = re.compile(r'Analyzing (?:System)?(?:Verilog|VHDL) file "([^"]+)"')
_QUESTA_CMD = re.compile(r"^(?:#\s*)?(?:vlog|vcom)\s+(.*)$", re.M)
_TOOL_ERROR = {"xsim": re.compile(r"^ERROR:", re.M), "questa": re.compile(r"^(?:#\s*)?\*\* (?:Error|Fatal)", re.M),
               "icarus": re.compile(r"^\S+:\d+: (?:error|syntax error)", re.M)}
_VERSION = {"xsim": re.compile(r"Vivado Simulator v?(\S+)"), "questa": re.compile(r"^(.*?vlog \S+)", re.M),
            "icarus": re.compile(r"Icarus Verilog version (\S+)")}


def compiled_files(simulator: str, text: str) -> list:
    if simulator == "xsim":
        return _XSIM_FILE.findall(text)
    if simulator == "questa":
        return [t for line in _QUESTA_CMD.findall(text) for t in line.split() if t.lower().endswith(HDL)]
    if simulator == "icarus":
        return [l.strip() for l in text.splitlines() if l.strip().lower().endswith(HDL)]
    raise ValueError(f"unknown simulator {simulator}")


def record(simulator: str, sim_dir, pass_pattern=r"\bPASS\b", fail_pattern=r"\bFAIL\b"):
    sim_dir = Path(sim_dir)
    compile_logs = [sim_dir / n for n in LOGS[simulator][0] if (sim_dir / n).exists()]
    run_logs = [sim_dir / n for n in LOGS[simulator][1] if (sim_dir / n).exists()]
    if not compile_logs or not run_logs:
        raise ValueError(f"no {simulator} compile or run log in {sim_dir}")
    compile_text = "\n".join(p.read_text(errors="ignore") for p in compile_logs)
    run_text = "\n".join(p.read_text(errors="ignore") for p in run_logs)
    files = []
    for f in compiled_files(simulator, compile_text):
        p = Path(f) if Path(f).is_absolute() else sim_dir / f
        if p not in files:
            files.append(p)
    if not files:
        raise ValueError(f"no compiled HDL file found in the {simulator} logs of {sim_dir}")
    if re.search(fail_pattern, run_text) or _TOOL_ERROR[simulator].search(compile_text + run_text):
        result = "FAIL"
    elif re.search(pass_pattern, run_text):
        result = "PASS"
    else:
        result = "UNKNOWN"
    version = _VERSION[simulator].search(compile_text + run_text)
    return {
        "simulator": simulator,
        "version": version.group(1) if version else None,
        "files": _digests(files),
        "logs": {p.name: sha256(p) for p in compile_logs + run_logs},
        "result": result,
        "pass_pattern": pass_pattern,
        "fail_pattern": fail_pattern,
    }


def verify(rec: dict, sim_dir) -> list:
    sim_dir = Path(sim_dir)
    return [f"simulation log {n} {'changed' if (sim_dir / n).exists() else 'missing'}"
            for n, d in rec.get("logs", {}).items() if not (sim_dir / n).exists() or sha256(sim_dir / n) != d]
