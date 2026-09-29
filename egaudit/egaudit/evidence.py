import hashlib
import json
import re
import shlex
import xml.etree.ElementTree as ET
from pathlib import Path

from .artifacts import VERILOG, VHDL, account, generated, hdl_reads, moved, tcl_sources

FAMILY_BY_SUFFIX = {
    "F1": {".v", ".sv", ".vhd", ".vhdl", ".xci", ".xcix", ".ip", ".qip", ".cxf"},
    "F2": {".wlf", ".vcd", ".fst", ".do"},
    "F3": {".xdc", ".sdc", ".pdc", ".fdc", ".qsf", ".qpf", ".xpr", ".prjx", ".tcl", ".ys"},
    "F4": {".dcp", ".vds", ".vdi", ".hdb", ".cdb", ".ddb", ".rdb", ".qdb", ".srm", ".srd", ".vm",
           ".adl", ".afl", ".json"},
    "F5": {".rpt", ".summary", ".srr", ".log", ".htm", ".rpx", ".smsg", ".qmsg"},
    "F6": {".bit", ".msk", ".rbd", ".bin", ".sof", ".pof", ".jic", ".rbf", ".job", ".stp", ".ppd",
           ".digest"},
}
F2_DIRS = {"simulation", "stimulus", "sim_1"}


def family(path: Path) -> str:
    if path.name in ("release_manifest.json", "deploy_record.json"):
        return "F7"
    if F2_DIRS & set(path.parts) or path.name.startswith("tb_"):
        return "F2"
    for fam, suffixes in FAMILY_BY_SUFFIX.items():
        if path.suffix.lower() in suffixes:
            return fam
    return "other"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


TEXT_SOURCES = {".v", ".sv", ".vhd", ".vhdl", ".xdc", ".sdc", ".pdc", ".fdc", ".tcl", ".qsf", ".bd", ".qsys"}

_VOLATILE_REPORT_LINE = re.compile(
    r"(\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b.*\b\d{1,2}:\d{2}:\d{2}\b)|(\bDate\s*:)|(^\|\s*(Host|Command)\s*:)"
    r"|(^\s*(Info|Warning|Critical Warning|Error)\b( \(\d+\))?:)"
    r"|(Peak virtual memory|Elapsed time|Total CPU time|Average used|Maximum used|Processors? \d|Processing (started|ended))",
    re.I)


def source_sha256(path: Path) -> str:
    path = Path(path)
    if path.suffix.lower() in TEXT_SOURCES:
        return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    return sha256(path)


_SLACK_ROW = re.compile(r"^;\s*(-?\d+\.\d+)\s*;")


def report_sha256(path: Path) -> str:
    lines = [l for l in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines()
             if not _VOLATILE_REPORT_LINE.search(l)]
    out, run, key = [], [], None
    for line in lines + [""]:
        m = _SLACK_ROW.match(line)
        k = m.group(1) if m else None
        if k is not None and k == key:
            run.append(line)
            continue
        out.extend(sorted(run))
        run, key = ([line], k) if k is not None else ([], None)
        if k is None:
            out.append(line)
    return text_sha256("\n".join(out[:-1]))


def generated_sha256(path: Path) -> str:
    lines = Path(path).read_text(encoding="utf-8", errors="ignore").splitlines()
    return text_sha256("\n".join(l for l in lines if not l.lstrip().startswith(("//", "--"))))


def inventory(build: Path):
    return [{"path": p.relative_to(build).as_posix(), "family": family(p),
             "bytes": p.stat().st_size, "sha256": sha256(p)}
            for p in sorted(build.rglob("*")) if p.is_file()]


def _first(pattern, text, group=1):
    m = re.search(pattern, text, re.M)
    return m.group(group).strip() if m else None


def _read(path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path and Path(path).exists() else ""


def _digests(paths, generated=()):
    paths = [Path(p) for p in paths if Path(p).exists()]
    generated = {Path(p) for p in generated}
    keys, n = {p: p.name for p in paths}, 1
    while True:
        groups = {}
        for p in paths:
            groups.setdefault(keys[p], []).append(p)
        clash = [p for group in groups.values() if len(group) > 1 for p in group if len(p.parts) > n]
        if not clash:
            break
        n += 1
        for p in clash:
            keys[p] = "/".join(p.parts[-n:])
    return {keys[p]: (generated_sha256 if p in generated or any(s.endswith(".gen") for s in p.parts)
                      else source_sha256)(p) for p in paths}


def _bd_cells(components):
    for cell in components.values():
        if "vlnv" in cell:
            yield cell
        yield from _bd_cells(cell.get("components", {}))


def _qsys_ip(qsys: Path, prefix: str, search, ip: dict, systems: list, path=()):
    if qsys not in systems:
        systems.append(qsys)
    path = (*path, qsys)
    root = ET.parse(qsys).getroot()
    for m in root.iter("module"):
        kind, name = m.get("kind"), m.get("name")
        sub = next((d / f"{kind}.qsys" for d in [qsys.parent, *search] if (d / f"{kind}.qsys").exists()), None)
        # a subsystem instantiated several times is expanded at every instance; only a system that
        # contains itself (directly or through its subsystems) is not entered again
        if sub is not None and sub not in path:
            _qsys_ip(sub, f"{prefix}/{name}", search, ip, systems, path)
            continue
        params = sorted(f'{p.get("name")}={p.get("value", p.text or "")}' for p in m.iter("parameter")
                        if p.get("name") != "AUTO_GENERATION_ID")
        ip[f"{prefix}/{name}"] = {"vlnv": f"altera:{kind}:{m.get('version')}",
                                   "sha256": text_sha256("\n".join([f"enabled={m.get('enabled')}", *params]))}


def _one(build: Path, pattern):
    hits = sorted(build.rglob(pattern))
    return hits[0] if hits else None


def _rel(build: Path, p):
    return p.relative_to(build).as_posix() if p and Path(p).exists() else None


def _logged(paths, known, build):
    same = {}
    for k in known:
        same.setdefault(Path(k).name.lower(), []).append(Path(k))
    keep, lost = [], []
    for p in map(Path, paths):
        twins = same.get(p.name.lower(), [])
        p = moved(p, [build])
        if p.is_file():
            if not any(q.is_file() and source_sha256(q) == source_sha256(p) for q in twins):
                keep.append(p)
        else:
            lost.append(f"log names {p.as_posix()}, not found")
    return keep, lost


def vivado(build: Path) -> dict:
    xpr = _one(build, "*.xpr")
    proj = _read(xpr)

    def resolve(p):
        return Path(p.replace("$PPRDIR", str(xpr.parent)).replace("$PSRCDIR", str(xpr.with_suffix(".srcs")))
                    .replace("$PGENDIR", str(xpr.with_suffix(".gen"))))

    files, constraint_files, attrs = [], [], []
    for _, fs_type, body in re.findall(r'<FileSet Name="([^"]+)" Type="([^"]+)"[^>]*>(.*?)</FileSet>', proj, re.S):
        for path, inner in re.findall(r'<File Path="([^"]+)"(?:/>|>(.*?)</File>)', body, re.S):
            a = re.findall(r'<Attr Name="([^"]+)" Val="([^"]*)"/>', inner or "")
            used = {v for k, v in a if k == "UsedIn"}
            if fs_type not in ("DesignSrcs", "Constrs", "BlockSrcs") or ("UserDisabled", "1") in a \
                    or (used and not used & {"synthesis", "implementation"}):
                continue
            (constraint_files if fs_type == "Constrs" else files).append(resolve(path))
            attrs += [f"file {Path(path).name} {k}={v}" for k, v in sorted(a)]
    logs = sorted(build.rglob("runme.log")) + sorted(build.parent.glob(f"{build.name}.log"))
    log_text = "\n".join(_read(p) for p in logs)
    inc_dirs = [resolve(p) for p in re.findall(r'<Option Name="VerilogDir" Val="([^"]+)"', proj)]
    hdl = [f for f in files if f.suffix.lower() in VERILOG + VHDL]
    read, unresolved = hdl_reads(hdl, inc_dirs, [xpr.parent])
    logged, lost = _logged(re.findall(r"\$readmem data file '([^']+)' is read", log_text), files + read, build)
    read += logged
    unresolved += lost
    sourced, missing = tcl_sources([f for f in constraint_files if f.suffix.lower() == ".tcl"], [xpr.parent])
    constraint_files += sourced
    unresolved += missing
    read = [p for p in dict.fromkeys(p.resolve() for p in read if p.is_file())
            if not generated(build, "vivado", xpr.stem, p)]
    timing = build / "reports" / "timing_summary.rpt"
    t = _read(timing)
    wns = _first(r"^\s*WNS\(ns\).*\n\s*-+.*\n\s*(-?[\d.]+)", t)
    volatile = r'\s(?:Dir|AutoIncrementalDir|AutoRQSDir|State|Path)="[^"]*"'
    options = "\n".join(sorted([re.sub(volatile, "", l.strip()) for l in proj.splitlines()
                                if re.search(r"<(Option Name=|Run Id=|Step Id=|Verilog_Define |Generic )", l)
                                and '<Option Name="Id"' not in l] + attrs))
    hooks = [resolve(p) for p in re.findall(r'TclHook="([^"]+)"', proj)]
    hook_sourced, missing = tcl_sources(hooks, [xpr.parent])
    unresolved += missing
    hooks += hook_sourced
    options += "".join(f"\nhook {h.name} {sha256(h) if h.exists() else 'missing'}" for h in hooks)
    ip, bd_xci = {}, []
    for x in (f for f in files if f.suffix == ".xci" and f.exists()):
        ip[x.stem] = {"vlnv": _first(r"(xilinx\.com:ip:[\w]+:[\d.]+)", _read(x)), "sha256": sha256(x)}
    for bd in (f for f in files if f.suffix == ".bd" and f.exists()):
        for cell in _bd_cells(json.loads(_read(bd)).get("design", {}).get("components", {})):
            xci = bd.parent / cell.get("xci_path", "").replace("\\", "/")
            if cell.get("xci_path") and xci.is_file():
                bd_xci.append(xci)
            config = sha256(xci) if cell.get("xci_path") and xci.is_file() else \
                text_sha256(json.dumps(cell.get("parameters", {}), sort_keys=True))
            ip[f"{bd.stem}/{cell.get('inst_hier_path', cell.get('xci_name'))}"] = {"vlnv": cell["vlnv"], "sha256": config}
    return {
        "vendor": "AMD Vivado",
        "tool_version": _first(r"Vivado (v\d{4}\.\d)", log_text),
        "device": _first(r'Part="([^"]+)"', proj),
        "sources": _digests([f for f in files if f.suffix.lower() != ".xci"] + read),
        "constraints": _digests(constraint_files),
        "ip": ip,
        "_inputs": files + constraint_files + read + bd_xci + hooks,
        "_unresolved": unresolved,
        "options_digest": text_sha256(options) if options else None,
        "seed": None,
        "license": sorted(set(re.findall(r"Got license for feature '([^']+)'", log_text))),
        "netlists": [p.relative_to(build).as_posix() for p in build.rglob("synth_1/*.dcp")],
        "checkpoints": [p.relative_to(build).as_posix() for p in build.rglob("*_routed.dcp")],
        "transform_logs": [p.relative_to(build).as_posix() for p in build.rglob("*.vd[si]")],
        "timing_report": _rel(build, timing),
        "timing_met": ("All user specified timing constraints are met" in t) if t else None,
        "wns": float(wns) if wns else None,
        "route_report": _rel(build, build / "reports" / "utilization.rpt"),
        "bitstream": _rel(build, _one(build, "*.bit")),
    }


def _table(report: str, title: str) -> str:
    """One table of a Quartus report, from its title to the blank line after it (the whole report if absent)."""
    i = report.find(f"; {title}")
    if i < 0:
        return report
    j = report.find("\n\n", i)
    return report[i:] if j < 0 else report[i:j + 1]


def _min_slack(sta: str, kind: str):
    m = re.search(rf"^; {kind} Summary\s*;\n(?:[+;].*\n){{3}}((?:;.*\n)+)", sta, re.M)
    slacks = [float(v) for v in re.findall(r"^;[^;]+;\s*(-?[\d.]+)\s*;", m.group(1), re.M)] if m else []
    return str(min(slacks)) if slacks else None


def quartus(build: Path) -> dict:
    qsf_path = _one(build, "*.qsf")
    qsf = _read(qsf_path)
    rev = qsf_path.stem
    out = build / "output_files" if (build / "output_files").exists() else build
    flow, sta, mapr = (_read(out / f"{rev}.{r}.rpt") for r in ("flow", "sta", "map"))
    def local(p):
        return moved(Path(p), [build]) if Path(p).is_absolute() else build / p
    design_keys = ("VERILOG|SYSTEMVERILOG|VHDL|AHDL|BDF|EDIF|VQM|GDF|VERILOG_INCLUDE|INCLUDE|MIF|HEX|IP|SIP"
                   "|SIGNALTAP|USE_SIGNALTAP|STP|SMF|ELF")
    files = [local(p) for p in re.findall(rf'-name (?:{design_keys})_FILE "?([^"\n]+)"?', qsf)]
    sdcs = [local(p) for p in re.findall(r'-name (?:SDC|SDC_ENTITY|RTL_SDC)_FILE "?([^"\n]+)"?', qsf)]
    listed = {f.resolve() for f in files}
    read, lost = [], []
    listed |= {s.resolve() for s in sdcs}
    files_read = _table(mapr, "Analysis & Synthesis Source Files Read")
    for entered, _, absolute in re.findall(r"^; (.+?)\s*; (?:yes|no)\s*; (User [^;]*?|Auto-Found [^;]*?)\s*; (.+?)\s*;", files_read, re.M):
        p = local(entered) if local(entered).is_file() else Path(absolute)
        if not p.drive:
            p = Path(build.resolve().drive + str(p))
        p = moved(p, [build])
        if not p.is_file():
            lost.append(f"synthesis report names {absolute}, not found")
        elif p.resolve() not in listed and not generated(build, "quartus", rev, p):
            read.append(p)
    inc_dirs = [local(p) for p in ";".join(re.findall(r'-name SEARCH_PATH "?([^"\n]+)"?', qsf)).split(";") if p]
    scanned, unresolved_hdl = hdl_reads([f for f in files if f.suffix.lower() in VERILOG + VHDL], inc_dirs, [build])
    known = {p.resolve() for p in read} | listed
    read += [p for p in scanned if p.resolve() not in known and not generated(build, "quartus", rev, p)]
    lost += unresolved_hdl
    pins = "\n".join(sorted(l.strip() for l in qsf.splitlines()
                            if l.startswith(("set_location_assignment", "set_instance_assignment"))))
    design_files = r"-name (?:VERILOG|SYSTEMVERILOG|VHDL|SDC|QIP|IP|SIP|QSYS)_FILE "
    options = "\n".join(sorted(l.strip() for l in qsf.splitlines()
                               if l.startswith("set_global_assignment") and not re.search(design_files, l)
                               and "LAST_QUARTUS_VERSION" not in l and "PROJECT_OUTPUT_DIRECTORY" not in l
                               and "PROJECT_CREATION_TIME_DATE" not in l))
    scripts = [local(s) for s in re.findall(r'-name \w+_SCRIPT_FILE "?(?:\w+:)?([^"\n]+)"?', qsf)]
    sourced, unresolved = tcl_sources(scripts, [build])
    unresolved += lost
    scripts += sourced
    for p in scripts:
        options += f"\nscript {p.name} {sha256(p) if p.exists() else 'missing'}"
    constraints = _digests(sdcs)
    if pins:
        constraints["qsf:assignments"] = text_sha256(pins)
    tops = [local(p) for p in re.findall(r'-name QSYS_FILE "?([^"\n]+)"?', qsf)]
    for qip in (local(p) for p in re.findall(r'-name QIP_FILE "?([^"\n]+)"?', qsf)):
        tops += [qip.parent / p for p in re.findall(r'MISC_FILE \[file join \$::quartus\(qip_path\) "([^"]+\.qsys)"\]', _read(qip))]
    search = [local(p) for p in ";".join(re.findall(r'-name IP_SEARCH_PATHS "?([^"\n]+)"?', qsf)).split(";") if p]
    ip, systems = {}, []
    for top in (t for t in tops if t.exists()):
        _qsys_ip(top, top.stem, search, ip, systems)
    version = _first(r"Quartus Prime Version\s*;?\s*([\d.]+)", flow)
    names = {s.stem for s in systems}
    for m in re.finditer(r"; Parameter Settings for User Entity Instance: (\S+)\s*;\n(.*?)\n\n", mapr, re.S):
        inst, table = m.group(1), m.group(2)
        core = inst.rsplit("|", 1)[-1].split(":")[0]
        if core.startswith("alt") and not {seg.split(":")[0] for seg in inst.split("|")} & names:
            ip[inst] = {"vlnv": f"altera:{core}:{version}", "sha256": text_sha256(table)}
    slack = _first(r"^; Worst-case Slack\s*;\s*(-?[\d.]+)\s*;\s*(-?[\d.]+)", sta)
    hold = _first(r"^; Worst-case Slack\s*;\s*-?[\d.]+\s*;\s*(-?[\d.]+)", sta)
    if slack is None:  # multicorner analysis turned off: the report has one model's per-clock summaries
        slack, hold = _min_slack(sta, "Setup"), _min_slack(sta, "Hold")
    return {
        "vendor": "Altera Quartus Prime",
        "tool_version": _first(r"Quartus Prime Version\s*;?\s*([\w.]+ Build \d+)", flow),
        "device": _first(r"-name DEVICE (\S+)", qsf),
        "sources": _digests([*files, *systems, *read]),
        "_inputs": [*files, *systems, *read, *sdcs, qsf_path, *scripts],
        "_unresolved": unresolved,
        "constraints": constraints,
        "ip": ip,
        "options_digest": text_sha256(options) if options else None,
        "seed": _first(r"-name SEED (\d+)", qsf) or "1 (default)",
        "license": [],
        "netlists": [p.relative_to(build).as_posix() for p in build.glob("db/*.map.cdb")],
        "checkpoints": [p.relative_to(build).as_posix() for p in build.glob("db/*.cmp.cdb")],
        "transform_logs": [p.relative_to(build).as_posix() for p in out.glob(f"{rev}.map.rpt")] +
                          [p.relative_to(build).as_posix() for p in out.glob(f"{rev}.fit.rpt")],
        "timing_report": _rel(build, out / f"{rev}.sta.rpt"),
        "timing_met": (float(slack) >= 0 and float(hold) >= 0) if slack and hold else None,
        "wns": float(slack) if slack else None,
        "route_report": _rel(build, out / f"{rev}.fit.rpt"),
        "bitstream": _rel(build, _one(build, "*.jic") or _one(build, "*.sof")),
    }


LIBERO_DEFAULTS = {"RESTRICTSPIPINS": "0"}


def libero(build: Path) -> dict:
    prjx_path = _one(build, "*.prjx")
    prjx, project_name = _read(prjx_path), prjx_path.stem if prjx_path else ""
    root = _one(build, "designer/*/*_has_violations")
    top = root.parent if root else None
    timing = top / f"{top.name}_max_timing_multi_corner.xml" if top else None
    t = _read(timing)
    summary = re.sub(r"\s+", " ", t)
    i = summary.find("<cell>Worst Slack (ns)</cell>")
    rows = re.findall(r"<row>\s*<cell>[^<]*</cell>\s*<cell>[^<]*</cell>\s*<cell>[^<]*</cell>\s*<cell>(-?[\d.]+)</cell>",
                      summary[i:summary.find("</table>", i)]) if i >= 0 else []
    wns = str(min(float(x) for x in rows)) if rows else None
    status = _read(root)
    srr = _one(build, "synthesis/*.srr")
    tools = _read(_one(build, "tooldata/*_tools.xml"))
    options = []
    for tag in ("device", "advancedoptions"):
        m = re.search(r"<%s ([^>]*?)/?>" % tag, tools)
        if m:
            options += [f"{tag} {k}={v}" for k, v in re.findall(r'(\w[\w.]*)="([^"]*)"', m.group(1))
                        if LIBERO_DEFAULTS.get(k) != v]
    for m in re.finditer(r'<tool [^>]*internal_name="(\w+)"[^>]*>\s*<configuration>(.*?)</configuration>', tools, re.S):
        for name, value in re.findall(r'<spirit:hwParameter spirit:name="([^"]+)"(?:/>|>([^<]*)</spirit:hwParameter>)', m.group(2)):
            options.append(f"tool {m.group(1)} {name}={value}")
    options = "\n".join(sorted(options))
    def local(v):
        v = v.replace("<project>", str(build)).replace("\\", "/")
        return moved(Path(v), [build]) if Path(v).is_absolute() else build / v
    cons, assoc = [], []
    for tool, body in re.findall(r"^LIST (\w*Constraints)\n(.*?)^ENDLIST", prjx, re.M | re.S):
        for i, (path, kind) in enumerate(re.findall(r'^VALUE "([^",]+),([^"]+)"', body, re.M)):
            assoc.append(f"assoc {tool} {i} {Path(path.replace(chr(92), '/')).name} {kind}")
            f = local(path)
            if not f.name.endswith("_derived_constraints.sdc") and f not in cons:
                cons.append(f)
    options = "\n".join(sorted(options.splitlines() + assoc))
    ip, smartdesigns, ip_files = {}, [], []
    for comp in sorted(build.glob("component/work/*/*.cxf")):
        cxf = _read(comp)
        ip_files += [comp, *comp.parent.glob("*/*.cxf"), *comp.parent.glob("*.cfg")]
        if "<category>SmartCoreDesign</category>" in cxf:
            smartdesigns.append(comp.with_suffix(".v"))
            continue
        m = re.search(r"(Actel|Microsemi|Microchip)/(\w+)/(\w+)/([\d.]+)/", cxf)
        cfg = comp.with_suffix(".cfg")
        inst = sorted(comp.parent.glob("*/*.cxf"))
        if not m and cfg.exists():
            ip[comp.stem] = {"vlnv": "Microchip:MSS:PFSOC_MSS", "sha256": source_sha256(cfg)}
            continue
        ip[comp.stem] = {"vlnv": ":".join(m.groups()) if m else None,
                         "sha256": text_sha256(sha256(comp) + (sha256(inst[0]) if inst else ""))}
    fm = re.search(r"^LIST FileManager\n(.*?)^ENDLIST", prjx, re.M | re.S)
    hdl = [local(v) for v, kind in re.findall(r'^VALUE "([^",]+),(\w+)"', fm.group(1) if fm else "", re.M)
           if kind == "hdl" and not v.replace("\\", "/").startswith("<project>/component/")]
    srr_text = _read(srr)
    read = [Path(i) for i in re.findall(r'^@I:"[^"]+":"([^"]+)"', srr_text, re.M)]
    read += [Path(f) for f in re.findall(r"^Opening data file (.+?) from directory", srr_text, re.M)]
    scanned, unresolved = hdl_reads(hdl, base_dirs=[build])
    read, lost = _logged(read, hdl + scanned, build)
    unresolved += lost
    read = [p for p in dict.fromkeys(p.resolve() for p in read + scanned if p.is_file())
            if not generated(build, "libero", project_name, p)]
    sources = {(p.relative_to(build).as_posix() if p.resolve().is_relative_to(build.resolve()) else p.name):
               source_sha256(p) for p in hdl + read if p.exists()}
    sources.update({f"smartdesign/{p.stem}": generated_sha256(p) for p in smartdesigns if p.exists()})
    synlog = _read(build / "synthesis" / "synplify.log")
    return {
        "vendor": "Microchip Libero SoC",
        "tool_version": _first(r'KEY CAPTURE "([^"]+)"', prjx),
        "device": _first(r'KEY VendorTechnology_Die "([^"]+)"', prjx),
        "sources": sources,
        "constraints": _digests(cons),
        "_inputs": hdl + read + cons + ip_files + [p for p in smartdesigns if p.exists()],
        "_unresolved": unresolved,
        "ip": ip,
        "options_digest": text_sha256(options) if options else None,
        "seed": None,
        "license": sorted(set(re.findall(r"License checkout: (\S+)", synlog))),
        "netlists": [p.relative_to(build).as_posix() for p in build.glob("synthesis/*.vm")] +
                    [p.relative_to(build).as_posix() for p in build.glob("synthesis/*.srm")],
        "checkpoints": [p.relative_to(build).as_posix() for p in top.glob("*.adl")] if top else [],
        "transform_logs": [_rel(build, srr)] if srr else [],
        "timing_report": _rel(build, timing),
        "timing_met": ("_max_timing_multi_corner met" in status and "_min_timing_multi_corner met" in status)
                      if status else None,
        "wns": float(wns) if wns else None,
        "route_report": _rel(build, _one(build, "designer/*/*_compile_netlist_resources.rpt")),
        "bitstream": _rel(build, _one(build, "export/*.job")),
    }


def openxc7(build: Path) -> dict:
    ys = _read(build / "synth.ys")
    args = _read(build / "pnr.args").split()
    files = {"--chipdb", "--xdc", "--json", "--write", "--fasm", "--report", "--log"}
    value = {a: [args[i + 1] for i, x in enumerate(args[:-1]) if x == a] for a in files}
    srcs, inc_dirs, read_flags = [], [], []
    for line in (l for l in ys.splitlines() if l.startswith("read_verilog")):
        toks = shlex.split(line, posix=False)[1:]
        i = 0
        while i < len(toks):
            t = toks[i]
            if t in ("-D", "-I") and i + 1 < len(toks):
                read_flags.append(f"{t} {toks[i + 1]}")
                if t == "-I":
                    inc_dirs.append(build / toks[i + 1])
                i += 2
                continue
            if t.startswith("-"):
                read_flags.append(t)
                if t.startswith("-I") and len(t) > 2:
                    inc_dirs.append(build / t[2:])
            else:
                srcs.append(build / t.strip('"'))
            i += 1
    read, unresolved = hdl_reads(srcs, inc_dirs, [build])
    options = [l for l in ys.splitlines() if not l.startswith(("read_verilog", "write_"))] + read_flags
    options += [a for i, a in enumerate(args) if a not in files and (i == 0 or args[i - 1] not in files)]
    options += [f"chipdb {Path(p).name}" for p in value["--chipdb"]]
    build_log = _read(build / "build.log")
    report = build / "report.json"
    fmax = json.loads(_read(report) or "{}").get("fmax", {})
    slack = [1000 / c["constraint"] - 1000 / c["achieved"] for c in fmax.values() if c.get("achieved")]
    yosys, pnr = _first(r"^\s*Yosys (\S+)", _read(build / "yosys.log")), _first(r"\(Version (\w+)\)", build_log)
    return {
        "vendor": "openXC7 (Yosys, nextpnr-xilinx)",
        "tool_version": f"Yosys {yosys}; nextpnr-xilinx {pnr}" if yosys and pnr else None,
        "device": _first(r"--part_name (\S+)", build_log),
        "sources": _digests(srcs + read),
        "constraints": _digests(build / p for p in value["--xdc"]),
        "_inputs": srcs + read + [build / p for p in value["--xdc"]],
        "_unresolved": unresolved,
        "ip": {},
        "options_digest": text_sha256("\n".join(options)) if options else None,
        "seed": _first(r"--seed (\d+)", " ".join(args)),
        "license": [],
        "netlists": [p.relative_to(build).as_posix() for p in build.glob("design.json")],
        "checkpoints": [p.relative_to(build).as_posix() for p in build.glob("routed.json")],
        "transform_logs": [p.relative_to(build).as_posix() for p in build.glob("*.log") if p.name != "build.log"],
        "timing_report": _rel(build, report),
        "timing_met": all(s >= 0 for s in slack) if slack else None,
        "wns": round(min(slack), 3) if slack else None,
        "route_report": _rel(build, report),
        "bitstream": _rel(build, _one(build, "*.bit")),
    }


def bitstream_digests(build: Path, flow: str, bitstream: str):
    whole, config, sync = hashlib.sha256(), hashlib.sha256(), None
    with open(build / bitstream, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            whole.update(chunk)
            if sync is None:
                i = chunk.find(bytes.fromhex("aa995566"))
                sync = i >= 0
                chunk = chunk[i:] if sync else chunk
            config.update(chunk)
    if flow == "libero":
        return whole.hexdigest(), _first(r"Entire bitstream digest: ([0-9a-f]{64})",
                                         "".join(_read(p) for p in build.glob("export/*.digest")))
    if flow in ("vivado", "openxc7"):
        return whole.hexdigest(), config.hexdigest()
    if bitstream.lower().endswith(".sof"):
        return whole.hexdigest(), hashlib.sha256((build / bitstream).read_bytes()[1024:-2]).hexdigest()
    return whole.hexdigest(), whole.hexdigest()


ADAPTERS = [("*.xpr", "vivado", vivado), ("*.qsf", "quartus", quartus), ("*.prjx", "libero", libero),
            ("synth.ys", "openxc7", openxc7)]


def collect(build: Path) -> dict:
    build = Path(build).absolute()
    for pattern, flow, adapter in ADAPTERS:
        if any(build.glob(pattern)):
            ev = adapter(build)
            if ev["bitstream"]:
                ev["bitstream_sha256"], ev["config_sha256"] = bitstream_digests(build, flow, ev["bitstream"])
            else:
                ev["config_sha256"] = None
            if ev["timing_report"]:
                ev["timing_report_sha256"] = report_sha256(build / ev["timing_report"])
            ev["simulation"] = [p.relative_to(build).as_posix() for p in build.rglob("*")
                                if p.is_file() and family(p) == "F2" and p.suffix in (".wlf", ".vcd", ".log")]
            project = next(build.glob(pattern)).stem if pattern.startswith("*") else ""
            ev["unaccounted"] = account(build, flow, project, ev.pop("_inputs")) +                 [f"unresolved reference {r}" for r in ev.pop("_unresolved")]
            return ev
    raise ValueError(f"no supported project file in {build}")
