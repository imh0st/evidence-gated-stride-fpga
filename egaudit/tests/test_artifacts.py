import copy
import tempfile
import unittest
from pathlib import Path

from egaudit.artifacts import account, hdl_reads
from egaudit.evidence import libero, openxc7, quartus, vivado
from egaudit.rules import evaluate

from test_rules import DEPLOY, EV, MANIFEST


def write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


XPR = """<Project>
  <FileSets>
    <FileSet Name="sources_1" Type="DesignSrcs" RelSrcDir="x">
      <File Path="$PPRDIR/top.v"><FileInfo><Attr Name="UsedIn" Val="synthesis"/><Attr Name="UsedIn" Val="implementation"/></FileInfo></File>
      <File Path="$PPRDIR/old.v"><FileInfo><Attr Name="UserDisabled" Val="1"/><Attr Name="UsedIn" Val="synthesis"/></FileInfo></File>
      <File Path="$PPRDIR/params.vh"><FileInfo><Attr Name="UsedIn" Val="synthesis"/></FileInfo></File>
      <File Path="$PPRDIR/rom.mem"><FileInfo><Attr Name="UsedIn" Val="synthesis"/></FileInfo></File>
      <Config><Option Name="VerilogDir" Val="$PPRDIR/inc"/><Verilog_Define Name="FOO" Val="1"/></Config>
    </FileSet>
    <FileSet Name="constrs_1" Type="Constrs" RelSrcDir="x">
      <File Path="$PPRDIR/pins.xdc"><FileInfo><Attr Name="UsedIn" Val="implementation"/><Attr Name="ProcessingOrder" Val="NORMAL"/></FileInfo></File>
      <File Path="$PPRDIR/extra.tcl"><FileInfo><Attr Name="UsedIn" Val="implementation"/></FileInfo></File>
    </FileSet>
    <FileSet Name="sim_1" Type="SimulationSrcs" RelSrcDir="x">
      <File Path="$PPRDIR/tb.v"><FileInfo><Attr Name="UsedIn" Val="simulation"/></FileInfo></File>
    </FileSet>
  </FileSets>
</Project>
"""


class TestVivadoInputs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.b = Path(self.tmp.name)
        write(self.b, "p.xpr", XPR)
        write(self.b, "top.v", '`include "inc/deep.vh"\nmodule top; initial $readmemh("table.mem", m); endmodule\n')
        write(self.b, "inc/deep.vh", "localparam D = 1;\n")
        write(self.b, "table.mem", "00\n")
        for n in ("old.v", "tb.v", "params.vh", "rom.mem", "pins.xdc", "extra.tcl"):
            write(self.b, n, "x\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_listed_inputs_of_every_kind(self):
        ev = vivado(self.b)
        self.assertEqual(sorted(ev["sources"]), ["deep.vh", "params.vh", "rom.mem", "table.mem", "top.v"])
        self.assertEqual(sorted(ev["constraints"]), ["extra.tcl", "pins.xdc"])

    def test_disabled_and_simulation_files_are_not_inputs(self):
        ev = vivado(self.b)
        self.assertNotIn("old.v", ev["sources"])
        self.assertNotIn("tb.v", ev["sources"])

    def test_define_and_file_property_are_options(self):
        d0 = vivado(self.b)["options_digest"]
        (self.b / "p.xpr").write_text(XPR.replace('Val="1"/></Config>', 'Val="2"/></Config>'))
        d1 = vivado(self.b)["options_digest"]
        (self.b / "p.xpr").write_text(XPR.replace('"ProcessingOrder" Val="NORMAL"', '"ProcessingOrder" Val="LATE"'))
        d2 = vivado(self.b)["options_digest"]
        self.assertEqual(len({d0, d1, d2}), 3)


class TestQuartusInputs(unittest.TestCase):
    def test_named_files_and_files_synthesis_read(self):
        with tempfile.TemporaryDirectory() as t:
            b = Path(t)
            write(b, "top.v", "module top; endmodule\n")
            write(b, "rom.mif", "DEPTH = 1;\n")
            write(b, "x.sdc", "create_clock -period 10 clk\n")
            found = write(b, "found/rom.hex", ":00\n")
            write(b, "top.qsf", 'set_global_assignment -name VERILOG_FILE top.v\n'
                                'set_global_assignment -name MIF_FILE rom.mif\n'
                                'set_global_assignment -name SDC_ENTITY_FILE x.sdc\n')
            write(b, "top.map.rpt", f"; top.v ; yes ; User Verilog HDL File ; {(b / 'top.v').as_posix()} ; ;\n"
                                     f"; found/rom.hex ; yes ; Auto-Found Unspecified File ; {found.as_posix()} ; ;\n"
                                     f"; altpll.tdf ; yes ; Megafunction ; c:/tool/altpll.tdf ; ;\n")
            ev = quartus(b)
            self.assertEqual(sorted(ev["sources"]), ["rom.hex", "rom.mif", "top.v"])
            self.assertIn("x.sdc", ev["constraints"])

    def test_moved_build_names_its_own_files(self):
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as old:
            b, o = Path(t), Path(old)
            for root in (b, o):
                write(root, "top.v", "module top; endmodule\n")
                write(root, "inc/defs.vh", "`define X 1\n")
            write(b, "top.qsf", 'set_global_assignment -name VERILOG_FILE top.v\n')
            write(b, "top.map.rpt", f"; top.v ; yes ; User Verilog HDL File ; {(o / 'top.v').as_posix()} ; ;\n"
                                     f"; inc/defs.vh ; yes ; Auto-Found Unspecified File ; {(o / 'inc/defs.vh').as_posix()} ; ;\n")
            ev = quartus(b)
            self.assertEqual(sorted(ev["sources"]), ["defs.vh", "top.v"])
            self.assertEqual({Path(p).resolve() for p in ev["_inputs"]} - {(b / "top.qsf").resolve()},
                             {(b / "top.v").resolve(), (b / "inc/defs.vh").resolve()})


PRJX = """KEY CAPTURE "v2025.2"
LIST FileManager
VALUE "<project>\\hdl\\top.v,hdl"
ENDFILE
VALUE "<project>\\component\\work\\C0\\C0.v,hdl"
ENDFILE
VALUE "<project>\\constraint\\io\\unused.pdc,io_pdc"
ENDFILE
ENDLIST
LIST SynthesisConstraints
VALUE "<project>\\constraint\\syn.fdc,fdc"
VALUE "<project>\\constraint\\net.ndc,ndc"
ENDLIST
LIST PNRConstraints
VALUE "<project>\\constraint\\io\\pins.pdc,io_pdc"
VALUE "<project>\\constraint\\fp\\floor.pdc,fp_pdc"
VALUE "<project>\\constraint\\top_derived_constraints.sdc,sdc"
ENDLIST
"""


class TestLiberoInputs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.b = Path(self.tmp.name)
        write(self.b, "p.prjx", PRJX)
        write(self.b, "hdl/top.v", "module top; endmodule\n")
        write(self.b, "component/work/C0/C0.v", "module C0; endmodule\n")
        for n in ("constraint/syn.fdc", "constraint/net.ndc", "constraint/io/pins.pdc", "constraint/fp/floor.pdc",
                  "constraint/io/unused.pdc", "constraint/top_derived_constraints.sdc"):
            write(self.b, n, "x\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_constraints_are_the_tool_associations(self):
        ev = libero(self.b)
        self.assertEqual(sorted(ev["constraints"]), ["floor.pdc", "net.ndc", "pins.pdc", "syn.fdc"])
        self.assertEqual(sorted(ev["sources"]), ["hdl/top.v"])

    def test_unused_constraint_file_is_unaccounted(self):
        ev = libero(self.b)
        self.assertIn("constraint/io/unused.pdc", account(self.b, "libero", "p", ev["_inputs"]))

    def test_association_order_is_an_option(self):
        d0 = libero(self.b)["options_digest"]
        (self.b / "p.prjx").write_text(PRJX.replace('pins.pdc,io_pdc"\nVALUE "<project>\\constraint\\fp\\floor.pdc,fp_pdc"',
                                                    'floor.pdc,fp_pdc"\nVALUE "<project>\\constraint\\io\\pins.pdc,io_pdc"')
                                       .replace("constraint\\io\\floor.pdc", "constraint\\fp\\floor.pdc")
                                       .replace("constraint\\fp\\pins.pdc", "constraint\\io\\pins.pdc"))
        self.assertNotEqual(d0, libero(self.b)["options_digest"])


class TestOpenFlowInputs(unittest.TestCase):
    def test_read_verilog_flags_files_and_hdl_reads(self):
        with tempfile.TemporaryDirectory() as t:
            b = Path(t)
            write(b, "a.v", '`include "defs.vh"\nmodule a; endmodule\n')
            write(b, "b.v", 'module b; initial $readmemb("rom.bin", m); endmodule\n')
            write(b, "inc/defs.vh", "`define X 1\n")
            write(b, "rom.bin", "0\n")
            write(b, "synth.ys", "read_verilog -D WIDTH=8 -I inc a.v b.v\nsynth_xilinx -top a\n")
            write(b, "pnr.args", "--xdc pins.xdc")
            write(b, "pins.xdc", "x\n")
            ev = openxc7(b)
            self.assertEqual(sorted(ev["sources"]), ["a.v", "b.v", "defs.vh", "rom.bin"])
            (b / "synth.ys").write_text("read_verilog -D WIDTH=16 -I inc a.v b.v\nsynth_xilinx -top a\n")
            self.assertNotEqual(ev["options_digest"], openxc7(b)["options_digest"])

    def test_missing_reference_is_reported(self):
        with tempfile.TemporaryDirectory() as t:
            b = Path(t)
            write(b, "a.v", 'module a; initial $readmemh("gone.mem", m); endmodule\n')
            found, missing = hdl_reads([b / "a.v"], base_dirs=[b])
            self.assertEqual((found, len(missing)), ([], 1))


class TestHdlReads(unittest.TestCase):
    def test_file_named_through_parameter_macro_or_generic(self):
        with tempfile.TemporaryDirectory() as t:
            b = Path(t)
            write(b, "a.v", 'module a #(parameter INIT = "rom.mem") (); reg [7:0] m[0:3]; initial $readmemh(INIT, m); endmodule\n')
            write(b, "top.v", 'module top; a #(.INIT("other.mem")) u (); endmodule\n')
            write(b, "c.v", '`define HDR "h.vh"\n`include `HDR\nmodule c; endmodule\n')
            write(b, "v.vhd", 'generic (F : string := "init.txt");\nfile f : text open read_mode is F;\n')
            for n in ("rom.mem", "other.mem", "h.vh", "init.txt"):
                write(b, n, "0\n")
            found, missing = hdl_reads([b / n for n in ("a.v", "top.v", "c.v", "v.vhd")], base_dirs=[b])
            self.assertEqual(sorted(f.name for f in found), ["h.vh", "init.txt", "other.mem", "rom.mem"])
            self.assertEqual(missing, [])

    def test_copy_in_the_checked_tree_wins_over_an_old_absolute_path(self):
        with tempfile.TemporaryDirectory() as t:
            old, new = Path(t) / "old", Path(t) / "new"
            write(old, "build/data/rom.mem", "approved\n")
            write(new, "build/data/rom.mem", "changed\n")
            ref = (old / "build/data/rom.mem").as_posix()
            write(new, "build/src/a.v", f'module a; initial $readmemh("{ref}", m); endmodule\n')
            found, missing = hdl_reads([new / "build/src/a.v"], base_dirs=[new / "build/src"])
            self.assertEqual(missing, [])
            self.assertIn(new / "build/data/rom.mem", found)
            self.assertNotIn(old / "build/data/rom.mem", found)

    def test_absolute_reference_found_after_the_repository_moved(self):
        with tempfile.TemporaryDirectory() as t:
            b = Path(t)
            write(b, "data/rom.mem", "0\n")
            write(b, "src/a.v", 'module a; initial $readmemh("C:/old/place/data/rom.mem", m); endmodule\n')
            found, _ = hdl_reads([b / "src/a.v"], base_dirs=[b / "src"])
            self.assertEqual([f.resolve() for f in found], [(b / "data/rom.mem").resolve()])

    def test_tcl_source_is_followed_or_reported(self):
        with tempfile.TemporaryDirectory() as t:
            b = Path(t)
            write(b, "p.xpr", XPR)
            write(b, "top.v", "module top; endmodule\n")
            for n in ("old.v", "tb.v", "params.vh", "rom.mem", "pins.xdc"):
                write(b, n, "x\n")
            write(b, "extra.tcl", "source [file dirname [info script]]/more.tcl\nsource $::env(X)/gone.tcl\n")
            write(b, "more.tcl", "set_false_path -from [get_clocks a]\n")
            ev = vivado(b)
            self.assertIn("more.tcl", ev["constraints"])
            self.assertEqual(len(ev["_unresolved"]), 1)


class TestEvidenceTemplate(unittest.TestCase):
    COMPUTED = {"bitstream_sha256", "config_sha256", "timing_report_sha256", "simulation", "unaccounted"}

    def test_every_adapter_returns_the_template_fields(self):
        import csv
        with open(Path(__file__).parents[2] / "catalog" / "evidence_sources.csv", newline="", encoding="utf-8") as f:
            fields = {r["field"] for r in csv.DictReader(f)}
        with tempfile.TemporaryDirectory() as t:
            b = Path(t)
            write(b, "p.xpr", XPR)
            write(b, "q/top.qsf", "set_global_assignment -name DEVICE X\n")
            write(b, "l/p.prjx", PRJX)
            write(b, "o/synth.ys", "read_verilog a.v\n")
            write(b, "o/pnr.args", "--xdc pins.xdc")
            for fn, d in ((vivado, b), (quartus, b / "q"), (libero, b / "l"), (openxc7, b / "o")):
                keys = set(fn(d)) - {"_inputs", "_unresolved"}
                self.assertEqual(keys, {f for f in fields if not f.startswith(("deploy.", "sim."))} - self.COMPUTED,
                                 fn.__name__)


class TestAccounting(unittest.TestCase):
    def test_byproducts_pass_and_other_files_are_unaccounted(self):
        with tempfile.TemporaryDirectory() as t:
            b = Path(t)
            src = write(b, "cdc_ref.qsf", "x\n")
            write(b, "db/cdc_ref.map.hdb", "x")
            write(b, "cdc_ref.jic", "x")
            write(b, "notes/extra.sdc", "x")
            self.assertEqual(account(b, "quartus", "cdc_ref", [src]), ["notes/extra.sdc"])


class TestOrganizationalRecords(unittest.TestCase):
    def v(self, man):
        return {rid: verdict for rid, verdict, _ in evaluate(EV, man, DEPLOY)}

    def test_absent_records_stay_project_partial_or_missing(self):
        v = self.v(MANIFEST)
        self.assertEqual([v[r] for r in ("SIP-3", "RPT-3", "BSD-2", "TENV-1", "SIM-1")],
                         ["PROJECT", "PROJECT", "PROJECT", "PARTIAL", "MISSING"])

    def test_supplied_records_are_accepted(self):
        man = copy.deepcopy(MANIFEST)
        man.update({"access_log": "acl.csv", "keys": {"handling_record": "kms.txt"},
                    "license": {"record": "lic.txt"}, "simulation": {"results": "xsim.log"}})
        man["tool"]["image_sha256"] = "11"
        v = self.v(man)
        self.assertEqual([v[r] for r in ("SIP-3", "RPT-3", "BSD-2", "TENV-1", "TENV-2", "SIM-1", "SIM-2")],
                         ["SATISFIED", "SATISFIED", "SATISFIED", "SATISFIED", "SATISFIED", "PARTIAL", "PARTIAL"])

    def test_rebuild_configuration_is_compared(self):
        approved = MANIFEST["approved"]
        rb = {"sources": approved["sources"], "constraints": approved["constraints"],
              "options_digest": approved["options_digest"], "config_sha256": "c1"}
        verdict = lambda ev: {r: v for r, v, _ in evaluate(ev, MANIFEST, DEPLOY)}["BSD-1"]
        self.assertEqual(verdict(dict(EV, config_sha256="c1", rebuild=rb)), "SATISFIED")
        self.assertEqual(verdict(dict(EV, config_sha256="c2", rebuild=rb)), "VIOLATED")
        self.assertEqual(verdict(dict(EV, config_sha256="c1", rebuild=dict(rb, options_digest="other"))), "PARTIAL")

    def test_unaccounted_artifact_leaves_lineage_partial(self):
        ev = dict(EV, unaccounted=["notes/extra.sdc"])
        v = {rid: (verdict, why) for rid, verdict, why in evaluate(ev, MANIFEST, DEPLOY)}
        self.assertEqual(v["RPT-2"][0], "PARTIAL")
        self.assertIn("notes/extra.sdc", v["RPT-2"][1])


if __name__ == "__main__":
    unittest.main()
