SATISFIED, PARTIAL, MISSING, VIOLATED, PROJECT = "SATISFIED", "PARTIAL", "MISSING", "VIOLATED", "PROJECT"


def _get(d, *keys):
    for k in keys:
        if not isinstance(d, dict) or d.get(k) in (None, "", [], {}):
            return None
        d = d[k]
    return d


def _digest_diff(actual: dict, approved: dict) -> list:
    return ([f"changed {n}" for n in sorted(approved) if n in actual and actual[n] != approved[n]] +
            [f"missing {n}" for n in sorted(approved) if n not in actual] +
            [f"unapproved {n}" for n in sorted(actual) if n not in approved])


def _digest_match(actual: dict, approved):
    if not approved:
        return None
    return not _digest_diff(actual, approved)


def _approved_set(ev_key, man_key, what):
    def rule(ev, man, dep):
        if not ev[ev_key]:
            return MISSING, f"no {what} found in the build"
        approved = _get(man, "approved", man_key)
        if not approved:
            return PARTIAL, f"{what} digests observed; no approved digests in a release manifest"
        diff = _digest_diff(ev[ev_key], approved)
        if diff:
            return VIOLATED, f"{what} files differ from the approved set: {', '.join(diff)}"
        if not _get(man, "approved", "reviewer"):
            return PARTIAL, f"{what} digests match but no approval is recorded"
        return SATISFIED, f"{what} digests match the approved set"
    return rule


def _same_value(ev_key, man_path, what):
    def rule(ev, man, dep):
        if not ev.get(ev_key):
            return MISSING, f"no {what} found in the build"
        claimed = _get(man, *man_path)
        if claimed is None:
            return PARTIAL, f"{what} observed; not recorded in a release manifest"
        if claimed != ev[ev_key]:
            return VIOLATED, f"{what} in manifest ({claimed}) differs from build ({ev[ev_key]})"
        return SATISFIED, f"{what} matches the release manifest"
    return rule


def _project_only(man_path, what):
    def rule(ev, man, dep):
        if _get(man, *man_path):
            return SATISFIED, f"{what} supplied as an organizational record"
        return PROJECT, f"{what} requires an organizational record"
    return rule


def _native(ev_key, what):
    def rule(ev, man, dep):
        return (SATISFIED, f"{what} present") if ev.get(ev_key) else (MISSING, f"no {what} in the build")
    return rule


def sip1(ev, man, dep):
    built = ev.get("ip") or {}
    if not built:
        return SATISFIED, "no third-party IP core in the build"
    approved = _get(man, "approved", "ip")
    if not approved:
        return PARTIAL, f"IP cores observed ({', '.join(v['vlnv'] or k for k, v in built.items())}); no approved IP list"
    bad = [k for k, v in built.items()
           if k not in approved or approved[k].get("vlnv") != v["vlnv"] or approved[k].get("sha256") != v["sha256"]]
    if bad:
        return VIOLATED, f"IP core or configuration differs from the approved list: {bad}"
    if not all(approved[k].get("provider") for k in built):
        return PARTIAL, "IP cores match the approved list; provider approval not recorded"
    return SATISFIED, "every IP core matches an approved core, configuration, and provider"


def sim1(ev, man, dep):
    rec = ev.get("simulation_record")
    if not rec:
        if _get(man, "simulation", "sha256"):
            return MISSING, "the simulation record named in the release manifest was not supplied"
        if ev["simulation"] or _get(man, "simulation", "results"):
            return PARTIAL, "simulation evidence present; linkage to the design digest not checked"
        return MISSING, "no simulation evidence in the build or manifest"
    problems = list(rec.get("_problems", []))
    testbench = _get(man, "approved", "testbench")
    approved = dict(_get(man, "approved", "sources") or {}, **(testbench or {}))
    same = lambda a, b: a == b or a.endswith("/" + b) or b.endswith("/" + a)
    for n, d in sorted(rec["files"].items()):
        keys = [k for k in approved if same(k, n)]
        if approved and not keys:
            problems.append(f"unapproved {n}")
        elif keys and all(approved[k] != d for k in keys):
            problems.append(f"changed {n}")
    problems += [f"missing {n}" for n in sorted(testbench or {}) if not any(same(n, k) for k in rec["files"])]
    if problems:
        return VIOLATED, f"simulation evidence differs from the approved design: {', '.join(problems)}"
    if rec["result"] != "PASS":
        return VIOLATED, f"simulation result {rec['result']} ({rec['simulator']})"
    if not testbench:
        return PARTIAL, "simulation record present; no approved testbench digest in a release manifest"
    return SATISFIED, f"simulated sources and testbench match the approved digests; result PASS ({rec['simulator']})"


def sim2(ev, man, dep):
    verdict, reason = sim1(ev, man, dep)
    if verdict != SATISFIED:
        return verdict, reason
    if _get(man, "access_log"):
        return SATISFIED, reason + "; result access log supplied as an organizational record"
    return PARTIAL, "simulation results linked to the approved design; result access log requires an organizational record"


def cfg3(ev, man, dep):
    if not ev["timing_report"]:
        return MISSING, "no timing report"
    if ev["timing_met"] is None:
        return PARTIAL, "timing report present; timing result not recognized"
    if ev["timing_met"] is False:
        return VIOLATED, f"timing goals not met (worst slack {ev['wns']} ns)"
    return SATISFIED, f"timing goals met (worst slack {ev['wns']} ns)"


def tenv1(ev, man, dep):
    if not ev["tool_version"]:
        return MISSING, "tool identity not recorded in the build logs"
    if _get(man, "tool", "image_sha256"):
        return SATISFIED, "tool version observed and installation digest recorded"
    return PARTIAL, "tool version observed; installation digest requires an organizational record"


def tenv2(ev, man, dep):
    if _get(man, "license", "record"):
        return SATISFIED, "license state recorded in the release manifest"
    if ev["license"]:
        return PARTIAL, f"licensed features logged ({', '.join(ev['license'])}); no license record"
    return PROJECT, "license state not logged by this tool; requires an organizational record"


def trn1(ev, man, dep):
    if ev["netlists"] and ev["transform_logs"]:
        return SATISFIED, "synthesized netlist and transformation log present"
    return (PARTIAL, "netlist present without transformation log") if ev["netlists"] \
        else (MISSING, "no synthesized netlist")


def rpt1(ev, man, dep):
    if not ev["timing_report"]:
        return MISSING, "no timing report"
    claimed = _get(man, "reports", "timing")
    if claimed is None:
        return PARTIAL, "timing report present; digest not recorded at signoff"
    if claimed != ev["timing_report_sha256"]:
        return VIOLATED, "timing report differs from the digest recorded at signoff"
    return SATISFIED, "timing report matches the digest recorded at signoff"


def rpt2(ev, man, dep):
    if man is None:
        return PROJECT, "source-to-bitstream lineage requires a release attestation"
    checks = [_digest_match(ev["sources"], _get(man, "approved", "sources")),
              _digest_match(ev["constraints"], _get(man, "approved", "constraints")),
              _get(man, "bitstream", "sha256") == ev.get("bitstream_sha256") if _get(man, "bitstream") else None]
    if False in checks:
        return VIOLATED, "lineage broken: an input or output digest differs from the attestation"
    if None in checks or not _get(man, "release", "workflow"):
        return PARTIAL, "lineage incomplete: missing digests or workflow identity"
    extra = ev.get("unaccounted") or []
    if extra:
        return PARTIAL, f"lineage incomplete: {len(extra)} unaccounted artifact(s): {', '.join(extra[:5])}"
    return SATISFIED, "source, constraint, and bitstream digests chain to one workflow"


def bsd1(ev, man, dep):
    if not ev["bitstream"]:
        return MISSING, "no bitstream"
    claimed = _get(man, "bitstream", "sha256")
    if claimed is None:
        return PARTIAL, "bitstream present; not bound to a release manifest"
    if claimed != ev["bitstream_sha256"]:
        return VIOLATED, "released bitstream digest differs from the built bitstream"
    rb = ev.get("rebuild")
    if rb is None:
        return SATISFIED, "bitstream digest matches the release manifest"
    approved = _get(man, "approved") or {}
    if any(rb.get(k) != approved.get(k) for k in ("sources", "constraints", "options_digest")):
        return PARTIAL, "bitstream digest matches the release manifest; the rebuild does not use the approved inputs"
    if rb.get("config_sha256") is None or ev.get("config_sha256") is None:
        return PARTIAL, "bitstream digest matches the release manifest; configuration not readable"
    if rb["config_sha256"] != ev["config_sha256"]:
        return VIOLATED, "configuration differs from a separate rebuild of the approved inputs"
    return SATISFIED, "bitstream digest matches the release manifest; configuration equals a separate rebuild"


def bsd3(ev, man, dep):
    if man is None:
        return PROJECT, "signing authority requires a release manifest"
    if _get(man, "signature", "signer") and _get(man, "signature", "approved_by"):
        return SATISFIED, "signer and signing approval recorded"
    return MISSING, "release manifest has no signer or signing approval"


def bsd4(ev, man, dep):
    if dep is None:
        return MISSING, "no programming record"
    target = _get(man, "target")
    if target is None:
        return PARTIAL, f"programmed {dep.get('device')} ({dep.get('idcode')}); no authorized target in manifest"
    if not (target.get("idcode") or target.get("serial")):
        return PARTIAL, f"programmed {dep.get('device')} ({dep.get('idcode')}); authorized target lacks an IDCODE or serial number"
    for key in ("idcode", "serial"):
        if target.get(key) and target[key].lower() != str(dep.get(key, "")).lower():
            return VIOLATED, f"programmed target {key} {dep.get(key)} is not the authorized {target[key]}"
    return SATISFIED, "programmed device matches the authorized target"


def dep1(ev, man, dep):
    if dep is None:
        return MISSING, "no programming record"
    released = _get(man, "bitstream", "sha256") or ev.get("bitstream_sha256")
    if dep.get("bitstream_sha256") != released:
        return VIOLATED, "deployed programming file differs from the released bitstream"
    verify = dep.get("verify")
    if verify == "PASS":
        return SATISFIED, f"device verification passed ({dep.get('verify_method')})"
    if verify == "FAIL":
        return VIOLATED, "device verification failed"
    return PARTIAL, f"device programmed; device verification {verify or 'not recorded'}"


def rel1(ev, man, dep):
    if man is None:
        return PROJECT, "release manifest not supplied"
    if _get(man, "release", "id") and _get(man, "release", "approver"):
        return SATISFIED, "release manifest with release approval"
    return MISSING, "release manifest lacks release id or approver"


def rel2(ev, man, dep):
    if man is None:
        return PROJECT, "release pipeline identity not supplied"
    if _get(man, "release", "workflow") and _get(man, "release", "service_account"):
        return SATISFIED, "release workflow and service account recorded"
    return MISSING, "release manifest lacks workflow or service-account identity"


RULES = {
    "SIP-1": sip1,
    "SIP-2": _approved_set("sources", "sources", "source"),
    "SIP-3": _project_only(("access_log",), "source access log"),
    "SIM-1": sim1,
    "SIM-2": sim2,
    "CFG-1": _approved_set("constraints", "constraints", "constraint"),
    "CFG-2": _same_value("options_digest", ("approved", "options_digest"), "tool-option digest"),
    "CFG-3": cfg3,
    "TENV-1": tenv1,
    "TENV-2": tenv2,
    "TENV-3": _same_value("tool_version", ("tool", "version"), "tool version"),
    "TRN-1": trn1,
    "TRN-2": _native("checkpoints", "implementation database"),
    "TRN-3": _native("route_report", "placement and routing report"),
    "RPT-1": rpt1,
    "RPT-2": rpt2,
    "RPT-3": _project_only(("access_log",), "report access log"),
    "BSD-1": bsd1,
    "BSD-2": _project_only(("keys", "handling_record"), "key-handling record"),
    "BSD-3": bsd3,
    "BSD-4": bsd4,
    "DEP-1": dep1,
    "REL-1": rel1,
    "REL-2": rel2,
}


def evaluate(ev, manifest=None, deploy=None):
    return [(rid, *rule(ev, manifest, deploy)) for rid, rule in RULES.items()]
