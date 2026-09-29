import copy
import unittest

from egaudit.rules import RULES, evaluate

EV = {
    "vendor": "AMD Vivado", "tool_version": "v2025.2", "device": "xc7z020clg400-1",
    "sources": {"top.v": "aa"}, "constraints": {"top.xdc": "cc"},
    "ip": {"clk_wiz_0": {"vlnv": "xilinx.com:ip:clk_wiz:6.0", "sha256": "ii"}},
    "options_digest": "oo", "seed": None, "license": ["Synthesis"],
    "netlists": ["synth.dcp"], "checkpoints": ["routed.dcp"], "transform_logs": ["synth.vds"],
    "timing_report": "timing.rpt", "timing_report_sha256": "tt", "timing_met": True, "wns": 1.0,
    "route_report": "util.rpt", "bitstream": "top.bit", "bitstream_sha256": "bb", "simulation": [],
}
MANIFEST = {
    "approved": {"sources": {"top.v": "aa"}, "constraints": {"top.xdc": "cc"},
                 "ip": {"clk_wiz_0": {"vlnv": "xilinx.com:ip:clk_wiz:6.0", "sha256": "ii", "provider": "AMD"}},
                 "options_digest": "oo", "reviewer": "r"},
    "tool": {"version": "v2025.2"},
    "reports": {"timing": "tt"},
    "bitstream": {"file": "top.bit", "sha256": "bb"},
    "signature": {"signer": "s", "approved_by": "a"},
    "release": {"id": "1", "approver": "a", "workflow": "w", "service_account": "svc"},
    "target": {"device": "xc7z020", "idcode": "23727093"},
}
DEPLOY = {"device": "xc7z020", "idcode": "23727093", "bitstream_sha256": "bb", "verify": "PASS"}


def verdicts(ev=EV, man=MANIFEST, dep=DEPLOY):
    return {rid: v for rid, v, _ in evaluate(ev, man, dep)}


class TestRules(unittest.TestCase):
    def test_all_24_records_have_a_rule(self):
        self.assertEqual(len(RULES), 24)

    def test_consistent_release_satisfies_tool_observable_records(self):
        v = verdicts()
        for rid in ("SIP-1", "SIP-2", "CFG-1", "CFG-2", "CFG-3", "TENV-3", "TRN-1", "TRN-2", "TRN-3",
                    "RPT-1", "RPT-2", "BSD-1", "BSD-3", "BSD-4", "DEP-1", "REL-1", "REL-2"):
            self.assertEqual(v[rid], "SATISFIED", rid)

    def test_no_manifest_means_partial_or_project(self):
        v = verdicts(man=None, dep=None)
        self.assertEqual(v["SIP-2"], "PARTIAL")
        self.assertEqual(v["REL-1"], "PROJECT")
        self.assertEqual(v["DEP-1"], "MISSING")

    def _fault(self, record, ev=None, man=None, dep=None, expect="VIOLATED"):
        v = verdicts(ev or EV, man or MANIFEST, dep or DEPLOY)
        self.assertEqual(v[record], expect)

    def test_A1_constraint_changed_after_approval(self):
        ev = copy.deepcopy(EV); ev["constraints"]["top.xdc"] = "c2"
        self._fault("CFG-1", ev=ev)

    def test_A1_unapproved_constraint_file_added(self):
        ev = copy.deepcopy(EV); ev["constraints"]["extra.xdc"] = "c3"
        self._fault("CFG-1", ev=ev)
        self._fault("RPT-2", ev=ev)

    def test_approved_constraint_file_removed(self):
        ev = copy.deepcopy(EV); ev["constraints"] = {"other.xdc": "cc"}
        self._fault("CFG-1", ev=ev)

    def test_violation_reason_names_the_file(self):
        ev = copy.deepcopy(EV); ev["constraints"]["extra.xdc"] = "c3"
        reason = {rid: r for rid, _, r in evaluate(ev, MANIFEST, DEPLOY)}["CFG-1"]
        self.assertIn("unapproved extra.xdc", reason)

    def test_unrecognized_timing_result_is_not_satisfied(self):
        self._fault("CFG-3", ev=dict(EV, timing_met=None), expect="PARTIAL")

    def test_A2_unrecorded_option_change(self):
        ev = copy.deepcopy(EV); ev["options_digest"] = "o2"
        self._fault("CFG-2", ev=ev)

    def test_A3_source_changed_after_review(self):
        ev = copy.deepcopy(EV); ev["sources"]["top.v"] = "a2"
        self._fault("SIP-2", ev=ev)

    def test_A4_report_edited(self):
        ev = dict(EV, timing_report_sha256="t2")
        self._fault("RPT-1", ev=ev)

    def test_A5_tool_version_misreported(self):
        man = copy.deepcopy(MANIFEST); man["tool"]["version"] = "v2024.1"
        self._fault("TENV-3", man=man)

    def test_A6_bitstream_substituted(self):
        ev = dict(EV, bitstream_sha256="b2")
        self._fault("BSD-1", ev=ev)

    def test_A7_wrong_target(self):
        self._fault("BSD-4", dep=dict(DEPLOY, idcode="0f8181cf"))

    def test_target_without_identity_is_partial(self):
        man = copy.deepcopy(MANIFEST); man["target"] = {"device": "xc7z020"}
        self._fault("BSD-4", man=man, expect="PARTIAL")

    def test_A8_deployed_file_differs(self):
        self._fault("DEP-1", dep=dict(DEPLOY, bitstream_sha256="b2"))

    def test_A8_verification_unsupported_is_partial(self):
        self._fault("DEP-1", dep=dict(DEPLOY, verify="UNSUPPORTED"), expect="PARTIAL")

    def test_ip_core_reconfigured_after_approval(self):
        ev = copy.deepcopy(EV); ev["ip"]["clk_wiz_0"]["sha256"] = "i2"
        self._fault("SIP-1", ev=ev)

    def test_ip_without_approved_list_is_partial(self):
        self.assertEqual(verdicts(man=None, dep=None)["SIP-1"], "PARTIAL")

    def test_A9_manifest_without_approval_or_signer(self):
        man = copy.deepcopy(MANIFEST)
        man["release"]["approver"] = None
        man["signature"] = {}
        v = verdicts(man=man)
        self.assertEqual(v["REL-1"], "MISSING")
        self.assertEqual(v["BSD-3"], "MISSING")


class TestNormalization(unittest.TestCase):
    def test_line_endings_do_not_change_source_digest(self):
        import os
        import tempfile
        from egaudit.evidence import source_sha256
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "a.xdc"), os.path.join(d, "b.xdc")
            open(a, "wb").write(b"set_max_delay 10\nset_bus_skew 13\n")
            open(b, "wb").write(b"set_max_delay 10\r\nset_bus_skew 13\r\n")
            self.assertEqual(source_sha256(a), source_sha256(b))

    def test_files_with_the_same_name_keep_separate_digests(self):
        import os
        import tempfile
        from egaudit.evidence import _digests
        with tempfile.TemporaryDirectory() as d:
            for sub in ("a", "b", "c"):
                os.makedirs(os.path.join(d, sub))
            open(os.path.join(d, "a", "top.v"), "w").write("module a; endmodule\n")
            open(os.path.join(d, "b", "top.v"), "w").write("module b; endmodule\n")
            open(os.path.join(d, "c", "pkg.v"), "w").write("")
            keys = _digests([os.path.join(d, s, f) for s, f in (("a", "top.v"), ("b", "top.v"), ("c", "pkg.v"))])
            self.assertEqual(sorted(keys), ["a/top.v", "b/top.v", "pkg.v"])

    def test_report_ignores_date_and_messages_but_not_slack(self):
        import os
        import tempfile
        from egaudit.evidence import report_sha256
        base = "; Worst-case Slack ; 5.968 ;\n"
        with tempfile.TemporaryDirectory() as d:
            p = [os.path.join(d, f"{i}.rpt") for i in range(3)]
            open(p[0], "w").write("| Date : Wed Sep 23 09:51:42 2026\n" + base + "Info: Elapsed time: 00:00:01\n")
            open(p[1], "w").write("| Date : Thu Sep 24 11:02:13 2026\n" + base + "Info: Elapsed time: 00:00:03\n")
            open(p[2], "w").write("| Date : Wed Sep 23 09:51:42 2026\n" + base.replace("5.968", "6.968"))
            self.assertEqual(report_sha256(p[0]), report_sha256(p[1]))
            self.assertNotEqual(report_sha256(p[0]), report_sha256(p[2]))


class TestHierarchicalIP(unittest.TestCase):
    def test_block_design_cells_at_every_level(self):
        from egaudit.evidence import _bd_cells
        comps = {"clk": {"vlnv": "xilinx.com:ip:clk_wiz:6.0", "inst_hier_path": "clk"},
                 "periph": {"components": {"inner": {"components": {
                     "c0": {"vlnv": "xilinx.com:ip:xlconstant:1.1", "inst_hier_path": "periph/inner/c0"}}}}}}
        self.assertEqual(sorted(c["inst_hier_path"] for c in _bd_cells(comps)), ["clk", "periph/inner/c0"])

    def _qsys(self, d, name, body):
        import os
        with open(os.path.join(d, f"{name}.qsys"), "w") as f:
            f.write(f'<?xml version="1.0"?><system name="{name}">{body}</system>')

    def test_platform_designer_subsystems_and_parameters(self):
        import tempfile
        from pathlib import Path
        from egaudit.evidence import _qsys_ip
        with tempfile.TemporaryDirectory() as d:
            pio = '<module name="pio" kind="altera_avalon_pio" version="25.1" enabled="1">' \
                  '<parameter name="width" value="{w}" /><parameter name="AUTO_GENERATION_ID" value="{g}" /></module>'
            top = '<module name="sub" kind="inner" version="1.0" enabled="1" />'
            self._qsys(d, "sys", top)

            def digest(w, g):
                self._qsys(d, "inner", pio.format(w=w, g=g))
                ip, systems = {}, []
                _qsys_ip(Path(d) / "sys.qsys", "sys", [], ip, systems)
                return ip, systems

            ip, systems = digest(4, 0)
            self.assertEqual(list(ip), ["sys/sub/pio"])
            self.assertEqual(ip["sys/sub/pio"]["vlnv"], "altera:altera_avalon_pio:25.1")
            self.assertEqual(sorted(s.name for s in systems), ["inner.qsys", "sys.qsys"])
            self.assertEqual(digest(4, 1790151912)[0], ip)
            self.assertNotEqual(digest(8, 0)[0], ip)

    def test_platform_designer_repeated_subsystem(self):
        import tempfile
        from pathlib import Path
        from egaudit.evidence import _qsys_ip
        with tempfile.TemporaryDirectory() as d:
            self._qsys(d, "unit", '<module name="tm" kind="altera_avalon_timer" version="25.1" enabled="1" />')
            self._qsys(d, "top", '<module name="u0" kind="unit" version="1.0" enabled="1" />'
                                  '<module name="u1" kind="unit" version="1.0" enabled="1" />')
            self._qsys(d, "loop", '<module name="self" kind="loop" version="1.0" enabled="1" />')
            ip, systems = {}, []
            _qsys_ip(Path(d) / "top.qsys", "top", [], ip, systems)
            self.assertEqual(sorted(ip), ["top/u0/tm", "top/u1/tm"])
            self.assertEqual(sorted(s.name for s in systems), ["top.qsys", "unit.qsys"])
            ip = {}
            _qsys_ip(Path(d) / "loop.qsys", "loop", [], ip, [])
            self.assertEqual(list(ip), ["loop/self"])


class TestQuartusTiming(unittest.TestCase):
    """A Quartus report without multicorner analysis has only one model's per-clock summaries."""

    def test_single_model_summaries(self):
        from egaudit.evidence import _min_slack
        table = ("+----+\n; {0} Summary                                ;\n+----+----+----+\n"
                 "; Clock               ; Slack  ; End Point TNS ;\n+----+----+----+\n"
                 "; clk_a               ; {1}  ; 0.000         ;\n"
                 "; altera_reserved_tck ; 41.404 ; 0.000         ;\n+----+----+----+\n\n")
        sta = table.format("Setup", "4.615") + table.format("Hold", "-0.020")
        self.assertEqual(_min_slack(sta, "Setup"), "4.615")
        self.assertEqual(_min_slack(sta, "Hold"), "-0.02")
        self.assertIsNone(_min_slack("; Worst-case Slack ; 1.0 ; 0.2 ;\n", "Setup"))


if __name__ == "__main__":
    unittest.main()
