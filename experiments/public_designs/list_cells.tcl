lassign $argv xpr out
open_project $xpr
set f [open $out w]
foreach bd [get_files -filter {FILE_TYPE == "Block Designs"}] {
    open_bd_design $bd
    foreach c [get_bd_cells -hierarchical] {
        puts $f "[file rootname [file tail $bd]]|[string trimleft $c /]|[get_property TYPE $c]|[get_property VLNV $c]"
    }
    close_bd_design [current_bd_design]
}
close $f
close_project
