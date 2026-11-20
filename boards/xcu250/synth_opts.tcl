set ip_run [create_ip_run [get_ips clk_wiz_0]]
launch_runs $ip_run
wait_on_run $ip_run

launch_runs synth_1 -scripts_only
set run_dir [get_property DIRECTORY [get_runs synth_1]]
if {$tcl_platform(platform) eq "windows"} {
    set launcher [file join $run_dir rundef.js]
    set run [list cmd /c [file nativename [file join $run_dir runme.bat]]]
} else {
    set launcher [file join $run_dir runme.sh]
    set run [list /bin/sh $launcher]
}
set f [open $launcher]
set text [read $f]
close $f
if {[regsub -- {-mode batch} $text {-stack 2000 -mode batch} text] != 1} { error "synth_1 launcher: Vivado command not found" }
set f [open $launcher w]
puts -nonewline $f $text
close $f
catch {exec {*}$run}
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} { error "synth_1 failed" }
