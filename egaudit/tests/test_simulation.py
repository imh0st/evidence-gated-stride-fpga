import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from egaudit import simulation
from egaudit.evidence import source_sha256
from egaudit.rules import evaluate

from test_rules import DEPLOY, EV, MANIFEST

SRC = "module top(input a, output b); assign b = a; endmodule\n"
TB = "module tb; top u(.a(1'b0), .b()); initial begin $display(\"PASS\"); $finish; end endmodule\n"


def make_sim(root: Path, simulator: str, tb_text=TB, result="PASS"):
    src, tb = root / "top.v", root / "tb.v"
    src.write_text(SRC)
    tb.write_text(tb_text)
    s = root / "sim"
    s.mkdir()
    if simulator == "xsim":
        (s / "xvlog.log").write_text(
            "".join(f'INFO: [VRFC 10-2263] Analyzing Verilog file "{p.as_posix()}" into library work\n' for p in (src, tb)))
        (s / "xsim.log").write_text(f"{result}\nINFO: [Common 17-206] Exiting xsim\n")
    elif simulator == "questa":
        (s / "vlog.log").write_text("Questa Altera Starter FPGA Edition-64 vlog 2025.2 Compiler\n"
                                    f"vlog -work work -l vlog.log {src.as_posix()} {tb.as_posix()}\n"
                                    "-- Compiling module top\nErrors: 0, Warnings: 0\n")
        (s / "vsim.log").write_text(f"# {result}\n")
    else:
        (s / "iverilog.deps").write_text(f"{src.as_posix()}\n{tb.as_posix()}\n")
        (s / "vvp.log").write_text(f"{result}\n")
    return s, src, tb


def manifest_with_testbench(src: Path, tb: Path):
    man = copy.deepcopy(MANIFEST)
    man["approved"]["sources"] = {"top.v": source_sha256(src)}
    man["approved"]["testbench"] = {"tb.v": source_sha256(tb)}
    return man


def sim_verdicts(rec, man):
    ev = dict(EV, sources=man["approved"]["sources"], simulation_record=rec)
    return {rid: (v, why) for rid, v, why in evaluate(ev, man, DEPLOY) if rid.startswith("SIM")}


class TestSimulationRecord(unittest.TestCase):
    def test_each_simulator_log_names_the_compiled_files(self):
        for sim in ("xsim", "questa", "icarus"):
            with tempfile.TemporaryDirectory() as d:
                s, src, tb = make_sim(Path(d), sim)
                rec = simulation.record(sim, s)
                self.assertEqual(sorted(rec["files"]), ["tb.v", "top.v"], sim)
                self.assertEqual(rec["result"], "PASS", sim)

    def test_fail_marker_gives_fail(self):
        with tempfile.TemporaryDirectory() as d:
            s, _, _ = make_sim(Path(d), "questa", result="FAIL")
            self.assertEqual(simulation.record("questa", s)["result"], "FAIL")

    def test_record_is_linked_to_the_approved_design(self):
        with tempfile.TemporaryDirectory() as d:
            s, src, tb = make_sim(Path(d), "xsim")
            v = sim_verdicts(simulation.record("xsim", s), manifest_with_testbench(src, tb))
            self.assertEqual(v["SIM-1"][0], "SATISFIED")
            self.assertEqual(v["SIM-2"][0], "PARTIAL")

    def test_access_log_completes_sim2(self):
        with tempfile.TemporaryDirectory() as d:
            s, src, tb = make_sim(Path(d), "icarus")
            man = manifest_with_testbench(src, tb)
            man["access_log"] = {"file": "acl.csv", "sha256": "00"}
            self.assertEqual(sim_verdicts(simulation.record("icarus", s), man)["SIM-2"][0], "SATISFIED")

    def test_testbench_changed_after_approval_is_violated(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _, src, tb = make_sim(root, "questa")
            man = manifest_with_testbench(src, tb)
            weak = root / "weak"
            weak.mkdir()
            s, _, _ = make_sim(weak, "questa", tb_text=TB.replace("tb;", "tb; // shorter run"))
            v = sim_verdicts(simulation.record("questa", s), man)
            self.assertEqual(v["SIM-1"][0], "VIOLATED")
            self.assertIn("changed tb.v", v["SIM-1"][1])
            self.assertEqual(v["SIM-2"][0], "VIOLATED")

    def test_failed_simulation_is_violated(self):
        with tempfile.TemporaryDirectory() as d:
            s, src, tb = make_sim(Path(d), "xsim", result="FAIL")
            v = sim_verdicts(simulation.record("xsim", s), manifest_with_testbench(src, tb))
            self.assertEqual(v["SIM-1"][0], "VIOLATED")

    def test_log_edited_after_the_record_is_violated(self):
        with tempfile.TemporaryDirectory() as d:
            s, src, tb = make_sim(Path(d), "xsim", result="FAIL")
            rec = simulation.record("xsim", s)
            (s / "xsim.log").write_text("PASS\n")
            rec["_problems"] = simulation.verify(rec, s)
            self.assertEqual(rec["_problems"], ["simulation log xsim.log changed"])
            v = sim_verdicts(rec, manifest_with_testbench(src, tb))
            self.assertEqual(v["SIM-1"][0], "VIOLATED")

    def test_without_record_verdicts_are_unchanged(self):
        v = {rid: vd for rid, vd, _ in evaluate(EV, MANIFEST, DEPLOY)}
        self.assertEqual((v["SIM-1"], v["SIM-2"]), ("MISSING", "MISSING"))


class TestCommandLine(unittest.TestCase):
    def run_egaudit(self, *args):
        return subprocess.run([sys.executable, "-m", "egaudit", *map(str, args)], check=True,
                              capture_output=True, text=True, cwd=Path(__file__).parents[1])

    def test_manifest_records_project_evidence_digests(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            s, src, tb = make_sim(root, "icarus")
            self.run_egaudit("sim", "--simulator", "icarus", "--dir", s, "--out", s / "sim_record.json")
            rec = json.loads((s / "sim_record.json").read_text())
            self.assertEqual(rec["result"], "PASS")
            b = root / "build"
            b.mkdir()
            (b / "synth.ys").write_text(f"read_verilog {src.as_posix()}\n")
            for name in ("lic.json", "acl.csv", "keys.txt", "tool.exe"):
                (root / name).write_text(name)
            self.run_egaudit("manifest", b, "--out", root / "m.json", "--testbench", tb,
                             "--simulation", s / "sim_record.json", "--tool-image", root / "*.exe",
                             "--license-record", root / "lic.json", "--access-log", root / "acl.csv",
                             "--key-record", root / "keys.txt")
            m = json.loads((root / "m.json").read_text())
            self.assertEqual(m["approved"]["testbench"], {"tb.v": source_sha256(tb)})
            self.assertEqual(len(m["simulation"]["sha256"]), 64)
            self.assertEqual(m["tool"]["image_files"], 1)
            self.assertEqual(sorted(k for k in m if k in ("license", "access_log", "keys")),
                             ["access_log", "keys", "license"])
            out = self.run_egaudit("check", b, "--manifest", root / "m.json",
                                   "--simulation", s / "sim_record.json").stdout
            rows = dict(l.split(",", 2)[:2] for l in out.splitlines()[1:])
            self.assertEqual(len(m["tool"]["image_sha256"]), 64)
            for rid in ("SIM-1", "SIM-2", "TENV-2", "SIP-3", "RPT-3", "BSD-2"):
                self.assertEqual(rows[rid], "SATISFIED", rid)


if __name__ == "__main__":
    unittest.main()
