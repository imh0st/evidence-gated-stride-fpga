"""RQ5 IP-count experiment for Quartus Prime Standard: a Platform Designer system with the hierarchy
of ip_net.tcl (Vivado block design). Platform Designer connects IP through Avalon-MM, so a unit holds
six memory-mapped IP instances: a bridge that is the unit's port, two interval timers, two mutexes,
and a system ID. Units are grouped by ten into group systems and groups by ten into subsystems, as in
the block design; each group, subsystem, and the top system adds a
bridge and a system ID, as the block design adds a concatenation and a reduction (the top system
always does, the block design only with more than one subsystem). Every system also
holds its clock source. A loop in the board top writes and reads back every IP register, so no IP
is removed.

    python ip_qsys.py <units>...     build and record
    python ip_qsys.py time           time EGAudit on the recorded builds
"""
import re
import shutil
import statistics
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).absolute().parent
sys.path.insert(0, str(HERE))
import ip_scaling as ips
from logic_scaling import c, time_check, utilization

BOARD = "c10lp"
OUT = c.BUILD / "rq5_ip_qsys"
QSYS_BIN = Path(shutil.which(c.QUARTUS_SH) or c.QUARTUS_SH).parent.parent / "sopc_builder" / "bin"
QS_SCRIPT = shutil.which("qsys-script") or str(QSYS_BIN / "qsys-script")
QS_GENERATE = shutil.which("qsys-generate") or str(QSYS_BIN / "qsys-generate")
PART = c.BOARDS[BOARD]["part"]

HEAD = f"""package require -exact qsys 25.1
set_project_property DEVICE_FAMILY {{Cyclone 10 LP}}
set_project_property DEVICE {PART}
proc wire_clk {{n}} {{
    foreach i [get_instance_interfaces $n] {{
        set k [get_instance_interface_property $n $i CLASS_NAME]
        if {{[string equal $k clock_sink]}} {{ add_connection clk.clk $n.$i }}
        if {{[string equal $k reset_sink]}} {{ add_connection clk.clk_reset $n.$i }}
    }}
}}
proc slave_of {{n}} {{
    foreach i [get_instance_interfaces $n] {{
        if {{[string equal [get_instance_interface_property $n $i CLASS_NAME] avalon_slave]}} {{ return $i }}
    }}
}}
proc bridge {{n aw}} {{
    add_instance $n altera_avalon_mm_bridge
    set_instance_parameter_value $n DATA_WIDTH 32
    set_instance_parameter_value $n ADDRESS_WIDTH $aw
    set_instance_parameter_value $n ADDRESS_UNITS SYMBOLS
    set_instance_parameter_value $n PIPELINE_COMMAND 0
    set_instance_parameter_value $n PIPELINE_RESPONSE 0
    wire_clk $n
}}
proc attach {{br n base}} {{
    set s [slave_of $n]
    add_connection $br.m0 $n.$s
    set_connection_parameter_value $br.m0/$n.$s baseAddress $base
}}
proc finish {{name}} {{
    add_interface clk clock sink
    set_interface_property clk EXPORT_OF clk.clk_in
    add_interface reset reset sink
    set_interface_property reset EXPORT_OF clk.clk_in_reset
    add_interface s0 avalon slave
    set_interface_property s0 EXPORT_OF x_br.s0
    save_system $name.qsys
}}
"""


def system(name, body):
    return HEAD + f"create_system {name}\nadd_instance clk clock_source\n" \
        f"set_instance_parameter_value clk clockFrequencyKnown false\n{body}finish {name}\n"


def unit():
    body = "bridge x_br 8\n"
    for k, (n, kind) in enumerate([("x_tm0", "altera_avalon_timer"), ("x_tm1", "altera_avalon_timer"),
                                   ("x_mx0", "altera_avalon_mutex"), ("x_mx1", "altera_avalon_mutex"),
                                   ("x_id", "altera_avalon_sysid_qsys")]):
        body += f"add_instance {n} {kind}\nwire_clk {n}\nattach x_br {n} {32 * k}\n"
    return system("ip_unit", body)


def reducer(name, members, kind_of, stride, aw):
    body = f"bridge x_br {aw}\n"
    for k, m in enumerate(members):
        body += f"add_instance u_{m} {kind_of(m)}\nwire_clk u_{m}\nattach x_br u_{m} {k * stride}\n"
    body += f"add_instance x_id altera_avalon_sysid_qsys\nwire_clk x_id\nattach x_br x_id {len(members) * stride}\n"
    return system(name, body)


def make_design(units):
    src = ips.make_design(units)  # test design, board top with ipnet_wrapper, logic_fill with no lanes
    d = OUT / "designs" / src.name
    shutil.rmtree(d, ignore_errors=True)
    shutil.copytree(src, d)
    q = d / "qsys"
    q.mkdir()
    groups, subs = {}, {}
    for i in range(units):
        groups.setdefault((i // 100, (i // 10) % 10), []).append(i)
    scripts = {"ip_unit": unit()}
    for (s, g), members in groups.items():
        scripts[f"ip_grp_{s}_{g}"] = reducer(f"ip_grp_{s}_{g}", members, lambda _: "ip_unit", 256, 12)
        subs.setdefault(s, []).append(g)
    for s, gs in subs.items():
        scripts[f"ip_sub_{s}"] = reducer(f"ip_sub_{s}", gs, lambda g, s=s: f"ip_grp_{s}_{g}", 4096, 16)
    scripts["ipnet"] = reducer("ipnet", list(subs), lambda s: f"ip_sub_{s}", 65536, 20)
    for name, text in scripts.items():  # children first: each system instantiates saved ones
        (q / f"{name}.tcl").write_text(text)
        r = subprocess.run([QS_SCRIPT, f"--script={name}.tcl", f"--search-path={q.as_posix()},$"],
                           cwd=q, capture_output=True, text=True)
        errs = [l for l in (r.stdout + r.stderr).splitlines() if "Error" in l]
        if errs or not (q / f"{name}.qsys").exists():
            raise SystemExit(f"{name}: {errs[:5]}")
    r = subprocess.run([QS_GENERATE, "ipnet.qsys", "--synthesis=VERILOG", f"--search-path={q.as_posix()},$",
                        f"--part={PART}"], cwd=q, capture_output=True, text=True)
    if "Error" in r.stdout + r.stderr:
        raise SystemExit([l for l in (r.stdout + r.stderr).splitlines() if "Error" in l][:5])
    ports = re.findall(r"(input|output)\s+wire\s+(\[\d+:0\])?\s*(s0_\w+|clk_clk|reset_reset_n)",
                       (q / "ipnet" / "synthesis" / "ipnet.v").read_text())
    (d / "rtl" / "ipnet_wrapper.v").write_text(wrapper(ports))
    (d / "qsys.tcl").write_text(f"set_global_assignment -name QIP_FILE {(q / 'ipnet' / 'synthesis' / 'ipnet.qip').as_posix()}\n")
    return d, count_ip(q, "ipnet")


def count_ip(q, name):
    n = 0
    for m in ET.parse(q / f"{name}.qsys").getroot().iter("module"):
        sub = q / f"{m.get('kind')}.qsys"
        n += count_ip(q, m.get("kind")) if sub.exists() else 1
    return n


def wrapper(ports):
    names = {p[2] for p in ports}
    aw = next(int(w[1:-3]) + 1 for _, w, n in ports if n == "s0_address")
    conn = [".clk_clk(clk)", ".reset_reset_n(1'b1)", ".s0_address(addr)", ".s0_read(!wr)", ".s0_write(wr)",
            ".s0_writedata(lfsr)", ".s0_readdata(rdata)"]
    ties = {"s0_byteenable": "4'hf", "s0_burstcount": "1'b1", "s0_debugaccess": "1'b0"}
    conn += [f".{n}({v})" for n, v in ties.items() if n in names]
    conn += [f".{n}({n[3:]})" for n in ("s0_waitrequest", "s0_readdatavalid") if n in names]
    return f"""`timescale 1ns / 1ps
// generated by rq5_cost/ip_qsys.py: writes changing data to every register of the Platform Designer
// system and reads it back, one register after another
module ipnet_wrapper (input wire clk, output reg q);
    reg  [{aw - 1}:0] addr = 0;
    reg         wr = 1'b1;
    reg  [31:0] lfsr = 32'h1;
    wire [31:0] rdata;
    wire waitrequest, readdatavalid;
    ipnet u_sys ({", ".join(conn)});
    always @(posedge clk) begin
        if (!waitrequest) begin
            if (!wr) addr <= addr + 4;
            wr   <= !wr;
            lfsr <= {{lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]}};
        end
        q <= ^rdata;
    end
endmodule
"""


def build(units):
    t0 = time.monotonic()
    d, n_ip = make_design(units)  # the build time includes system generation, as Vivado and Libero generate theirs
    gen = time.monotonic() - t0
    bdir = OUT / BOARD / f"u{units}_n0"
    rc, sec = c.build(d, BOARD, bdir, opts=d / "qsys.tcl")
    row = {"board": BOARD, "units": units, "ip_instances": n_ip, "vendor_build_s": round(gen + sec, 1), "exit_code": rc}
    if rc == 0:
        row.update(zip(["logic_unit", "logic_used", "logic_available"], utilization(bdir, "quartus")[:3]))
    ips.upsert(row)


def time_all():
    for row in ips.load():
        if row["board"] != BOARD or str(row["exit_code"]) != "0":
            continue
        bdir = OUT / BOARD / f"u{row['units']}_n0"
        ev, runs = time_check(bdir)
        files = [p for p in bdir.rglob("*") if p.is_file()]
        row.update(egaudit_ip=len([k for k in ev["ip"] if "/" in k]), hier_levels=3, files=len(files),
                   bytes=sum(p.stat().st_size for p in files),
                   egaudit_mean_s=round(statistics.mean(runs), 3), egaudit_sd_s=round(statistics.stdev(runs), 3))
        ips.upsert(row)


if __name__ == "__main__":
    if sys.argv[1] == "time":
        time_all()
    else:
        for u in map(int, sys.argv[1:]):
            build(u)
