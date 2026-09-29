lassign $argv job project_dir action
if {$action ni {DEVICE_INFO PROGRAM VERIFY VERIFY_DIGEST}} { error "action not allowed: $action" }
file mkdir $project_dir
create_job_project -job_project_location $project_dir -job_file $job -overwrite 1
set_programming_action -name {MPFS095T} -action $action
run_selected_actions
save_log -file [file join $project_dir $action.log]
close_project
