import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).absolute().parents[2]
RTL = [ROOT / "designs" / "cdc_ref" / "rtl" / f for f in ("async_fifo.v", "reset_sync.v", "cdc_ref_core.v")]
TB = ROOT / "designs" / "cdc_ref" / "tb" / "tb_cdc_ref.v"
TOP = "tb_cdc_ref"
BIN = {
    "xsim": Path(os.environ.get("VIVADO_BIN", "")),
    "questa": Path(os.environ.get("QUESTA_BIN", "")),
    "questa_mchp": Path(os.environ.get("QUESTA_MCHP_BIN", "")),
    "icarus": Path(os.environ.get("OSS_CAD_BIN", ROOT.parent / "tools" / "oss-cad-suite" / "bin")),
}


def run(cmd, out, log=None):
    with open(out / (log or "run.out"), "a") as f:
        return subprocess.run([str(c) for c in cmd], cwd=out, stdout=f, stderr=subprocess.STDOUT).returncode


def simulate(sim, out, tb=TB):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    files = [p.as_posix() for p in RTL + [Path(tb)]]
    b = BIN[sim]
    if sim == "xsim":
        run(["cmd", "/c", b / "xvlog.bat", *files], out)
        run(["cmd", "/c", b / "xelab.bat", "-debug", "off", TOP, "-s", TOP], out)
        run(["cmd", "/c", b / "xsim.bat", TOP, "-R"], out)
    elif sim in ("questa", "questa_mchp"):
        if sim == "questa_mchp":
            lic = os.environ.get("QUESTA_MCHP_LICENSE", os.environ.get("LM_LICENSE_FILE", ""))
            os.environ["SALT_LICENSE_SERVER"] = os.environ["MGLS_LICENSE_FILE"] = lic
        run([b / "vlib.exe", "work"], out)
        run([b / "vlog.exe", "-work", "work", "-l", "vlog.log", *files], out)
        run([b / "vsim.exe", "-c", "-l", "vsim.log", "-do", "run -all; quit -f", TOP], out)
    elif sim == "icarus":
        env_path = os.environ["PATH"]
        os.environ["PATH"] = os.pathsep.join([str(b), str(b.parent / "lib"), env_path])
        run([b / "iverilog.exe", "-g2012", "-M", "iverilog.deps", "-s", TOP, "-o", f"{TOP}.vvp", *files], out,
            "iverilog.log")
        run([b / "vvp.exe", "-n", f"{TOP}.vvp"], out, "vvp.log")
        os.environ["PATH"] = env_path
    else:
        raise SystemExit(f"unknown simulator {sim}")
    return out


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tb = Path(sys.argv[sys.argv.index("--tb") + 1]) if "--tb" in sys.argv else TB
    if "--tb" in sys.argv:
        args.remove(sys.argv[sys.argv.index("--tb") + 1])
    simulate(args[0], args[1], tb)
