"""RQ5 IP-count experiment for Libero SoC: SmartDesigns with the hierarchy of ip_net.tcl (Vivado block
design). SmartDesign connects DirectCore IP through APB, so a unit holds six IP instances: a CoreAPB3
bus that is the unit's port, three CoreTimer, and two CoreGPIO (inputs tied low, outputs unused).
Units are grouped by ten into group SmartDesigns and groups by ten into subsystem SmartDesigns; each
group, subsystem, and the top SmartDesign adds a CoreAPB3 and a CoreTimer, as the block design adds
a concatenation and a reduction. Each level decodes its slots from a different address field.
A loop in the board top writes and reads back every IP register, so no IP is removed.

    python ip_sd.py <units>...       build and record
    python ip_sd.py time             time EGAudit on the recorded builds
"""
import shutil
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).absolute().parent
sys.path.insert(0, str(HERE))
import ip_scaling as ips
from logic_scaling import c, time_check, utilization

BOARD = "disco"
OUT = c.BUILD / "rq5_ip_sd"
SLOTS = 16


HEAD = r"""proc apb {name slots maddr} {
    set p [list "APB_DWIDTH:32" "MADDR_BITS:$maddr" "UPR_NIBBLE_POSN:8"]
    for {set k 0} {$k < 16} {incr k} { lappend p "APBSLOT${k}ENABLE:[expr {$k < $slots ? {true} : {false}}]" }
    create_and_configure_core -core_vlnv {Actel:DirectCore:CoreAPB3:4.2.100} -component_name $name -params $p
}
proc ports {sd} {
    sd_create_scalar_port -sd_name $sd -port_name {PCLK} -port_direction {IN}
    sd_create_scalar_port -sd_name $sd -port_name {PRESETN} -port_direction {IN}
    sd_create_bus_port -sd_name $sd -port_name {PADDR} -port_direction {IN} -port_range {[31:0]}
    foreach p {PSEL PENABLE PWRITE} { sd_create_scalar_port -sd_name $sd -port_name $p -port_direction {IN} }
    sd_create_bus_port -sd_name $sd -port_name {PWDATA} -port_direction {IN} -port_range {[31:0]}
    sd_create_bus_port -sd_name $sd -port_name {PRDATA} -port_direction {OUT} -port_range {[31:0]}
    foreach p {PREADY PSLVERR} { sd_create_scalar_port -sd_name $sd -port_name $p -port_direction {OUT} }
    foreach p {PADDR PSEL PENABLE PWRITE PWDATA PRDATA PREADY PSLVERR} {
        sd_show_bif_pins -sd_name $sd -bif_pin_name {x_br:APB3mmaster} -pin_names "x_br:$p"
        sd_connect_pins -sd_name $sd -pin_names [list $p "x_br:$p"]
    }
}
proc clk {sd inst rst} {
    sd_connect_pins -sd_name $sd -pin_names [list PCLK "$inst:PCLK"]
    sd_connect_pins -sd_name $sd -pin_names [list PRESETN "$inst:$rst"]
}
proc slot_sd {sd k inst} {
    foreach p [list PADDRS PSELS$k PENABLES PWRITES PWDATAS PRDATAS$k PREADYS$k PSLVERRS$k] {
        sd_show_bif_pins -sd_name $sd -bif_pin_name "x_br:APBmslave$k" -pin_names "x_br:$p"
    }
    foreach {a b} [list PADDRS PADDR PSELS$k PSEL PENABLES PENABLE PWRITES PWRITE PWDATAS PWDATA PRDATAS$k PRDATA PREADYS$k PREADY PSLVERRS$k PSLVERR] {
        sd_connect_pins -sd_name $sd -pin_names [list "x_br:$a" "$inst:$b"]
    }
}
proc timer {sd k inst} {
    sd_instantiate_component -sd_name $sd -component_name {timer_c} -instance_name $inst
    clk $sd $inst PRESETn
    sd_mark_pins_unused -sd_name $sd -pin_names "$inst:TIMINT"
    sd_connect_pins -sd_name $sd -pin_names [list "x_br:APBmslave$k" "$inst:APBslave"]
}
proc gpio {sd k inst} {
    sd_instantiate_component -sd_name $sd -component_name {gpio_c} -instance_name $inst
    clk $sd $inst PRESETN
    sd_connect_pins_to_constant -sd_name $sd -pin_names "$inst:GPIO_IN" -value {GND}
    sd_mark_pins_unused -sd_name $sd -pin_names "$inst:GPIO_OUT"
    sd_mark_pins_unused -sd_name $sd -pin_names "$inst:INT"
    sd_connect_pins -sd_name $sd -pin_names [list "x_br:APBmslave$k" "$inst:APB_bif"]
}
proc sub {sd k inst comp} {
    sd_instantiate_component -sd_name $sd -component_name $comp -instance_name $inst
    clk $sd $inst PRESETN
    slot_sd $sd $k $inst
}
proc begin_sd {sd bus} {
    create_smartdesign -sd_name $sd
    sd_instantiate_component -sd_name $sd -component_name $bus -instance_name {x_br}
    ports $sd
}
proc end_sd {sd} {
    save_smartdesign -sd_name $sd
    generate_component -component_name $sd
}
"""


def smartdesign(name, members, bus):
    """members: list of (instance, component, kind) with kind timer/gpio/sd; bus: CoreAPB3 component."""
    t = [f"begin_sd {name} {bus}"]
    for k, (inst, comp, kind) in enumerate(members):
        t.append(f"sub {name} {k} {inst} {comp}" if kind == "sd" else f"{kind} {name} {k} {inst}")
    t.append(f"end_sd {name}")
    return "\n".join(t) + "\n"


def design_tcl(units):
    groups, subs, n_ip = {}, {}, 0
    for i in range(units):
        groups.setdefault((i // 100, (i // 10) % 10), []).append(i)
    tcl = [HEAD, "apb apb_unit 5 12\n",
           'create_and_configure_core -core_vlnv {Actel:DirectCore:CoreTimer:2.0.103} -component_name {timer_c} -params {"WIDTH:16"}\n',
           'create_and_configure_core -core_vlnv {Actel:DirectCore:CoreGPIO:3.2.102} -component_name {gpio_c} -params {"APB_WIDTH:32" "IO_NUM:4"}\n']
    tcl.append(smartdesign("ip_unit", [("x_tm0", "timer_c", "timer"), ("x_tm1", "timer_c", "timer"),
                                       ("x_tm2", "timer_c", "timer"), ("x_gp0", "gpio_c", "gpio"),
                                       ("x_gp1", "gpio_c", "gpio")], "apb_unit"))
    n_ip += 6 * units
    buses = set()

    def reducer(name, members, comp_of, maddr):
        nonlocal n_ip
        bus = f"apb_{maddr}_{len(members) + 1}"
        if bus not in buses:
            tcl.append(f"apb {bus} {len(members) + 1} {maddr}\n")
            buses.add(bus)
        tcl.append(smartdesign(name, [(f"u_{m}", comp_of(m), "sd") for m in members] + [("x_tm", "timer_c", "timer")], bus))
        n_ip += 2
    for (s, g), members in groups.items():
        reducer(f"ip_grp_{s}_{g}", members, lambda _: "ip_unit", 16)
        subs.setdefault(s, []).append(g)
    for s, gs in subs.items():
        reducer(f"ip_sub_{s}", gs, lambda g, s=s: f"ip_grp_{s}_{g}", 20)
    reducer("ipnet", list(subs), lambda s: f"ip_sub_{s}", 24)
    tcl.append("build_design_hierarchy\nset_root -module {board_top::work}\n")
    return "".join(tcl), n_ip


WRAPPER = """`timescale 1ns / 1ps
// generated by rq5_cost/ip_sd.py: writes changing data to every APB register of the SmartDesign and
// reads it back, one register after another
module ipnet_wrapper (input wire clk, output reg q);
    reg  [23:0] addr = 0;
    reg         phase = 0;
    reg         wr = 1'b1;
    reg  [31:0] lfsr = 32'h1;
    wire [31:0] prdata;
    wire        pready, pslverr;
    ipnet u_sys (.PCLK(clk), .PRESETN(1'b1), .PADDR({8'd0, addr}), .PSEL(1'b1), .PENABLE(phase), .PWRITE(wr),
                 .PWDATA(lfsr), .PRDATA(prdata), .PREADY(pready), .PSLVERR(pslverr));
    always @(posedge clk) begin
        if (!phase) phase <= 1'b1;
        else if (pready) begin
            phase <= 1'b0;
            wr    <= !wr;
            if (!wr) addr <= addr + 4;
            lfsr  <= {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
        end
        q <= ^prdata;
    end
endmodule
"""


def make_design(units):
    src = ips.make_design(units)  # test design, board top with ipnet_wrapper, logic_fill with no lanes
    d = OUT / "designs" / src.name
    shutil.rmtree(d, ignore_errors=True)
    shutil.copytree(src, d)
    (d / "rtl" / "ipnet_wrapper.v").write_text(WRAPPER)
    tcl, n_ip = design_tcl(units)
    (d / "sd.tcl").write_text(tcl)
    return d, n_ip


def build(units):
    d, n_ip = make_design(units)
    bdir = OUT / BOARD / f"u{units}_n0"
    rc, sec = c.build(d, BOARD, bdir, opts=d / "sd.tcl")
    row = {"board": BOARD, "units": units, "ip_instances": n_ip, "vendor_build_s": round(sec, 1), "exit_code": rc}
    if rc == 0:
        row.update(zip(["logic_unit", "logic_used", "logic_available"], utilization(bdir, "libero")[:3]))
    ips.upsert(row)


def time_all():
    for row in ips.load():
        if row["board"] != BOARD or str(row["exit_code"]) != "0":
            continue
        bdir = OUT / BOARD / f"u{row['units']}_n0"
        ev, runs = time_check(bdir)
        files = [p for p in bdir.rglob("*") if p.is_file()]
        row.update(egaudit_ip=len(ev["ip"]), hier_levels=3, files=len(files), bytes=sum(p.stat().st_size for p in files),
                   egaudit_mean_s=round(statistics.mean(runs), 3), egaudit_sd_s=round(statistics.stdev(runs), 3))
        ips.upsert(row)


if __name__ == "__main__":
    if sys.argv[1] == "time":
        time_all()
    else:
        for u in map(int, sys.argv[1:]):
            build(u)
