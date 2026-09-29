# Quartus project for Intel's multiprocessor design after the Nios V port: the assignments of the
# design's platform_setup.tcl, with the .qip of the system generated beforehand by qsys-generate
# in place of the .qsys file.
project_new top_level -overwrite
source platform_setup.tcl
setup_project
set_global_assignment -name QSYS_FILE multiprocessor_tutorial_main_system.qsys -remove
set_global_assignment -name QIP_FILE multiprocessor_tutorial_main_system/synthesis/multiprocessor_tutorial_main_system.qip
project_close
