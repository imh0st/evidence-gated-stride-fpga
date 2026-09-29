"""Port a Platform Designer system from Nios II to Nios V/m.

Quartus Prime Standard 25.1 no longer offers the Nios II processor (altera_nios2_gen2): a system
that contains one loads it as a missing module. This script reads each Nios II instance of a .qsys
file, writes a qsys-script that replaces it by a Nios V/m processor (intel_niosv_m) of the same
name, and runs it. The new processor keeps the clock, reset, debug reset, memory, and interrupt
connections of the old one, with the same base addresses and interrupt numbers, and the same
absolute reset vector; the debug agent and the timer agent of Nios V receive free addresses. A
Nios II/e (Tiny) core becomes a non-pipelined Nios V/m, and the reset input of the Nios V debug
module receives the system reset of the processor. Connections and exports of a Nios II
interface without a Nios V counterpart are left out, also in the parent system. Every other
instance and connection of the system is unchanged.

    python niosv_port.py <qsys-script executable> <system>.qsys ...
"""
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REMOVED = set()  # exports removed from subsystems ported earlier in the same run
MAP = {"data_master": "data_manager", "instruction_master": "instruction_manager",
       "debug_mem_slave": "dm_agent", "irq": "platform_irq_rx", "clk": "clk", "reset": "reset",
       "debug_reset_request": "dbg_reset_out"}
DIR = {"start": "source", "end": "sink"}


def port_script(qsys):
    root = ET.parse(qsys).getroot()
    lines = ["package require -exact qsys 25.1"]
    for cpu in [m for m in root.findall("module") if m.get("kind") == "altera_nios2_gen2"]:
        name = cpu.get("name")
        par = {p.get("name"): p.get("value") for p in cpu.findall("parameter")}
        lines += [f"remove_instance {name}", f"add_instance {name} intel_niosv_m",
                  f"set_instance_parameter_value {name} enableDebug 1",
                  f"set_instance_parameter_value {name} enableDebugReset 1",
                  f"set_instance_parameter_value {name} pipelineArch {0 if par.get('impl') == 'Tiny' else 1}"]
        if par.get("resetSlave") == "Absolute":
            lines.append(f"set_instance_parameter_value {name} resetSlave Absolute")
        elif par.get("resetSlave"):
            lines.append(f"set_instance_parameter_value {name} resetSlave {par['resetSlave']}")
        lines.append(f"set_instance_parameter_value {name} resetOffset {par.get('resetOffset', '0')}")
        for c in root.findall("connection"):
            ends = [c.get("start"), c.get("end")]
            if name not in (ends[0].split(".")[0], ends[1].split(".")[0]):
                continue
            new = []
            for e in ends:
                inst, port = e.split(".", 1)
                new.append(e if inst != name else f"{inst}.{MAP[port]}" if port in MAP else None)
            if None in new or any(e.split(".", 1)[1] in REMOVED for e in ends):
                lines.append(f"# left out: {ends[0]} -> {ends[1]} (no Nios V equivalent)")
                continue
            if new[0].endswith(".dm_agent") or new[1].endswith(".dm_agent"):
                base = None  # the Nios V debug agent is larger than the Nios II debug slave
            else:
                base = next((p.get("value") for p in c.findall("parameter") if p.get("name") == "baseAddress"), None)
            irq = next((p.get("value") for p in c.findall("parameter") if p.get("name") == "irqNumber"), None)
            lines.append(f"add_connection {new[0]} {new[1]}")
            if new[1] == f"{name}.reset" and not ends[0].endswith(("debug_reset_request", "jtag_debug_module_reset")):
                # the debug module of Nios V has its own reset input, fed by the system reset
                lines.append(f"add_connection {new[0]} {name}.ndm_reset_in")
            if base:
                lines.append(f"set_connection_parameter_value {new[0]}/{new[1]} baseAddress {base}")
            if irq:
                lines.append(f"set_connection_parameter_value {new[0]}/{new[1]} irqNumber {irq}")
        lines.append(f"add_connection {name}.data_manager {name}.timer_sw_agent")
        for i in root.findall("interface"):
            if i.get("internal", "").split(".")[0] != name:
                continue
            port = i.get("internal").split(".")[1]
            lines.append(f"catch {{remove_interface {i.get('name')}}}")
            if port in MAP:  # export the Nios V interface under the old name
                lines += [f"add_interface {i.get('name')} {i.get('type')} {DIR[i.get('dir')]}",
                          f"set_interface_property {i.get('name')} EXPORT_OF {name}.{MAP[port]}"]
            else:
                REMOVED.add(i.get("name"))
        lines.append(f"auto_assign_base_addresses {name}")
    lines.append("save_system")
    return "\n".join(lines) + "\n"


def drop_dangling(qsys):
    """Remove the connections that still name an export removed from a subsystem (the tool cannot)."""
    tree = ET.parse(qsys)
    root = tree.getroot()
    gone = [c for c in root.findall("connection")
            if any(e.split(".", 1)[1] in REMOVED for e in (c.get("start"), c.get("end")))]
    for c in gone:
        root.remove(c)
    if gone:
        tree.write(qsys, encoding="UTF-8", xml_declaration=True)


if __name__ == "__main__":
    exe = sys.argv[1]
    for q in map(Path, sys.argv[2:]):
        script = q.with_suffix(".niosv.tcl")
        script.write_text(port_script(q))
        out = subprocess.run([exe, f"--system-file={q}", f"--script={script}"], capture_output=True, text=True)
        drop_dangling(q)
        errs = [l for l in (out.stdout + out.stderr).splitlines() if "Error" in l]
        print(q.name, "errors:", len(errs))
        for l in errs[:10]:
            print("  ", l)
