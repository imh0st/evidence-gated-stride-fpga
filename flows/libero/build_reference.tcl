lassign $argv repo out_dir
file delete -force $out_dir
file copy $repo $out_dir
file delete -force [file join $out_dir .git]
file mkdir [file join $out_dir export]
cd $out_dir
set ::argv [list VERIFY_TIMING "EXPORT_FPE:[file join $out_dir export]"]
set ::argc 2
source MPFS_DISCOVERY_KIT_REFERENCE_DESIGN.tcl
file mkdir [file join $out_dir MPFS_DISCOVERY export]
foreach f [glob -nocomplain [file join $out_dir export *]] {
    file copy -force $f [file join $out_dir MPFS_DISCOVERY export]
}
