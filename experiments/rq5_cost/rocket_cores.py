import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def update_script(text, cores):
    text = re.sub(r"^(git reset --hard 4f19.*)$", r"\1\ngit submodule update --init --recursive", text, flags=re.M)
    text = text.replace("for MODEL in small medium linux full", "for MODEL in full")
    text = text.replace("for CORES in 1 2 4 8", f"for CORES in {cores}")
    text = text.replace("for WIDTH in 1 2 4 8", "for WIDTH in 1")
    assert text.count(f"for CORES in {cores};") == 2
    return text


def main(cores, checkout, work):
    data = Path(checkout).resolve() / "pythondata_cpu_rocket" / "verilog"
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    with open(data / "update.sh", newline="") as f:
        text = f.read()
    with open(work / "update.sh", "w", newline="") as f:
        f.write(update_script(text, cores))
    env = dict(os.environ, RISCV=os.environ.get("RISCV", "/usr"), JVM_MEMORY=os.environ.get("JVM_MEMORY", "24G"))
    subprocess.run(["bash", "update.sh"], cwd=work, env=env, check=True)
    for suffix in (".v", ".behav_srams.v"):
        name = f"freechips.rocketchip.system.LitexConfig_full_{cores}_1{suffix}"
        shutil.copy(work / "generated-src" / name, data / "generated-src" / name)


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2], sys.argv[3])
