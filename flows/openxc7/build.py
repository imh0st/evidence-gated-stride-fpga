import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).absolute().parents[2]
TOOLS = Path(os.environ.get("OPENXC7_TOOLS", ROOT.parent / "tools"))
YOSYS = TOOLS / "oss-cad-suite" / "bin" / "yosys.exe"
X7 = TOOLS / "openxc7"
DB = X7 / "share" / "nextpnr" / "external" / "prjxray-db" / "zynq7"


def run(cmd, log, cwd, stdout=None):
    env = dict(os.environ, PATH=os.pathsep.join([str(YOSYS.parent), str(TOOLS / "oss-cad-suite" / "lib"),
                                                str(X7 / "bin"), os.environ["PATH"]]))
    with open(log, "a") as f:
        f.write("$ " + " ".join(map(str, cmd)) + "\n")
        f.flush()
        rc = subprocess.run(list(map(str, cmd)), cwd=cwd, env=env, stdout=stdout or f, stderr=f).returncode
    if rc:
        raise SystemExit(f"{Path(cmd[0]).name} failed ({rc}), see {log}")


def main(design, board_dir, part, cdc_xdc, out, opts="-"):
    board_dir, cdc_xdc, out = Path(board_dir).absolute(), Path(cdc_xdc).absolute(), Path(out)
    rtl = Path(design) / "rtl" if Path(design).is_dir() else ROOT / "designs" / design / "rtl"
    name = Path(design).name
    out.mkdir(parents=True, exist_ok=True)

    def rel(p):
        return Path(os.path.relpath(Path(p).absolute(), out.absolute())).as_posix()

    # a design whose files must be read in a given order lists them in rtl/order.txt
    order = rtl / "order.txt"
    rtl_files = ([rtl.absolute() / n for n in order.read_text().split()] if order.exists()
                 else sorted(rtl.absolute().glob("*.v")))
    sources = rtl_files + [board_dir / "clk_gen.v"]
    (out / "synth.ys").write_text(
        "".join(f"read_verilog {rel(p)}\n" for p in sources) +
        "synth_xilinx -flatten -abc9 -arch xc7 -top board_top\n"
        "write_json design.json\n")
    args = ["--chipdb", (X7 / "chipdb" / f"{part.rsplit('-', 1)[0]}.bin").as_posix(),
            "--xdc", rel(board_dir / "pins.xdc"), "--xdc", rel(cdc_xdc),
            "--json", "design.json", "--write", "routed.json", "--fasm", "design.fasm",
            "--report", "report.json", "--timing-allow-fail"]
    if opts and opts != "-":
        args += Path(opts).read_text().split()
    (out / "pnr.args").write_text("\n".join(args) + "\n")

    run([X7 / "bin" / "nextpnr-xilinx.exe", "--version"], out / "build.log", out)
    run([YOSYS, "-q", "-l", "yosys.log", "-s", "synth.ys"], out / "build.log", out)
    run([X7 / "bin" / "nextpnr-xilinx.exe", "--log", "nextpnr.log", *args], out / "build.log", out)
    with open(out / "design.frames", "w") as frames:
        run([X7 / "bin" / "fasm2frames.cmd", "--part", part, "--db-root", DB, "design.fasm"],
            out / "build.log", out, stdout=frames)
    run([X7 / "bin" / "xc7frames2bit.exe", "--part_file", DB / part / "part.yaml", "--part_name", part,
         "--frm_file", "design.frames", "--output_file", f"{name}.bit"], out / "build.log", out)


if __name__ == "__main__":
    main(*sys.argv[1:])
