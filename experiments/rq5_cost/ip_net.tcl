set units $::env(IPNET_UNITS)
proc vlnv {name} { lindex [lsort -dictionary [get_ipdefs -filter "NAME == $name"]] end }
foreach n {c_counter_binary mult_gen c_addsub c_shift_ram util_reduced_logic xlconcat} { set V($n) [vlnv $n] }

proc cell {name path} {
    global V
    create_bd_cell -type ip -vlnv $V($name) $path
}

proc reduce {path width bits} {
    set n [llength $bits]
    cell xlconcat $path/x_cat
    set_property CONFIG.NUM_PORTS $n [get_bd_cells $path/x_cat]
    for {set i 0} {$i < $n} {incr i} { connect_bd_net [get_bd_pins [lindex $bits $i]] [get_bd_pins $path/x_cat/In$i] }
    cell util_reduced_logic $path/x_red
    set_property -dict [list CONFIG.C_OPERATION {xor} CONFIG.C_SIZE $n] [get_bd_cells $path/x_red]
    connect_bd_net [get_bd_pins $path/x_cat/dout] [get_bd_pins $path/x_red/Op1]
    return $path/x_red/Res
}

create_bd_design ipnet
create_bd_port -dir I -type clk -freq_hz 100000000 clk
create_bd_port -dir O q
for {set i 0} {$i < $units} {incr i} {
    set sub "sub_[expr {$i / 100}]"
    set grp "$sub/grp_[expr {($i / 10) % 10}]"
    foreach h [list $sub $grp] {
        if {![llength [get_bd_cells -quiet $h]]} { create_bd_cell -type hier $h; create_bd_pin -dir I -type clk $h/clk }
    }
    set u "$grp/unit_$i"
    create_bd_cell -type hier $u
    create_bd_pin -dir I -type clk $u/clk
    create_bd_pin -dir O $u/b0
    cell c_counter_binary $u/x_cnt
    set_property -dict [list CONFIG.Output_Width 16 CONFIG.Increment_Value [format %X [expr {2 * $i + 1}]]] [get_bd_cells $u/x_cnt]
    cell mult_gen $u/x_mul
    set_property -dict [list CONFIG.PortAWidth 16 CONFIG.PortBWidth 16 CONFIG.PipeStages 1] [get_bd_cells $u/x_mul]
    cell c_addsub $u/x_add
    set_property -dict [list CONFIG.A_Width 16 CONFIG.B_Width 16 CONFIG.Out_Width 16 CONFIG.CE false CONFIG.Latency 1] [get_bd_cells $u/x_add]
    cell c_shift_ram $u/x_srl
    set_property -dict [list CONFIG.Width 16 CONFIG.Depth [expr {8 + $i % 24}]] [get_bd_cells $u/x_srl]
    cell util_reduced_logic $u/x_red
    set_property -dict [list CONFIG.C_OPERATION {xor} CONFIG.C_SIZE 16] [get_bd_cells $u/x_red]
    foreach p {x_cnt/CLK x_mul/CLK x_add/CLK x_srl/CLK} { connect_bd_net [get_bd_pins $u/clk] [get_bd_pins $u/$p] }
    connect_bd_net [get_bd_pins $u/x_cnt/Q] [get_bd_pins $u/x_mul/A] [get_bd_pins $u/x_mul/B] [get_bd_pins $u/x_add/B]
    create_bd_cell -type ip -vlnv [vlnv xlslice] $u/x_lo
    set_property -dict [list CONFIG.DIN_WIDTH 32 CONFIG.DIN_FROM 23 CONFIG.DIN_TO 8] [get_bd_cells $u/x_lo]
    connect_bd_net [get_bd_pins $u/x_mul/P] [get_bd_pins $u/x_lo/Din]
    connect_bd_net [get_bd_pins $u/x_lo/Dout] [get_bd_pins $u/x_add/A]
    connect_bd_net [get_bd_pins $u/x_add/S] [get_bd_pins $u/x_srl/D]
    connect_bd_net [get_bd_pins $u/x_srl/Q] [get_bd_pins $u/x_red/Op1]
    connect_bd_net [get_bd_pins $u/x_red/Res] [get_bd_pins $u/b0]
    connect_bd_net [get_bd_pins $grp/clk] [get_bd_pins $u/clk]
    dict lappend members $grp $u/b0
}
set subs {}
dict for {grp bits} $members {
    create_bd_pin -dir O $grp/b0
    connect_bd_net [get_bd_pins [reduce $grp 1 $bits]] [get_bd_pins $grp/b0]
    set sub [lindex [split $grp /] 0]
    dict lappend subs $sub $grp/b0
}
set top {}
dict for {sub bits} $subs {
    foreach g $bits { connect_bd_net [get_bd_pins $sub/clk] [get_bd_pins [file dirname $g]/clk] }
    create_bd_pin -dir O $sub/b0
    connect_bd_net [get_bd_pins [reduce $sub 1 $bits]] [get_bd_pins $sub/b0]
    connect_bd_net [get_bd_ports clk] [get_bd_pins $sub/clk]
    lappend top $sub/b0
}
if {[llength $top] == 1} {
    connect_bd_net [get_bd_pins [lindex $top 0]] [get_bd_ports q]
} else {
    connect_bd_net [get_bd_pins [reduce "" 1 $top]] [get_bd_ports q]
}
validate_bd_design
save_bd_design
set bd [get_files ipnet.bd]
set_property synth_checkpoint_mode None $bd
generate_target all $bd
add_files -norecurse [make_wrapper -files $bd -top]
puts "IPNET cells [llength [get_bd_cells -hierarchical -filter {TYPE == ip}]]"
