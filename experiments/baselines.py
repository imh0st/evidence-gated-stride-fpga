def vendor_flags(build_exit=0, timing_met=True, verify=None):
    return build_exit != 0 or timing_met is False or verify == "FAIL"
