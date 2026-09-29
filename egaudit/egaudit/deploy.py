import re
from pathlib import Path

from .evidence import sha256


def _text(logs):
    return "\n".join(Path(p).read_text(encoding="utf-8", errors="ignore") for p in logs)


def vivado(logs):
    t = _text(logs)
    m = re.search(r"DEVICE (\S+) IDCODE ([01]{32})", t)
    verified = re.search(r"Verified device (\S+) with bitfile\s+(\S+)", t.replace("\n", ""))
    compared = re.search(r"READBACK_COMPARE (PASS|FAIL)", t)
    if verified:
        verify, method = "PASS", "masked configuration readback"
    elif compared:
        verify, method = compared.group(1), "configuration readback compared with the bitstream, user memory masked"
    else:
        verify = "FAIL" if "verify_hw_devices" in t and "ERROR" in t else "NOT_RUN"
        method = "masked configuration readback"
    return {
        "tool": "Vivado Hardware Manager",
        "device": m.group(1) if m else None,
        "idcode": f"{int(m.group(2), 2):08x}" if m else None,
        "serial": None,
        "verify": verify,
        "verify_method": method,
    }


def quartus(logs):
    t = _text(logs)
    ok = "Successfully performed operation(s)" in t
    flash = "Start Serial Flash Loader programming" in t
    if flash:
        verified = ok and "Performing CRC verification on device(s)" in t
        verify, method = ("PASS" if verified else "FAIL"), "configuration flash programmed and verified (CRC)"
    else:
        verify = "UNSUPPORTED" if "Configuration succeeded" in t else "FAIL"
        method = "none (verify of an SRAM configuration not supported; CONF_DONE only)"
    return {
        "tool": "Quartus Prime Programmer",
        "device": (re.search(r"for device (\S+)@", t) or [None, None])[1],
        "idcode": (re.search(r"JTAG ID code 0x([0-9A-Fa-f]{8})", t) or [None, None])[1],
        "serial": None,
        "verify": verify,
        "verify_method": method,
    }


def fpexpress(logs):
    t = _text(logs)
    idcode = re.search(r"IDCODE\[32\] = ([0-9a-fA-F]{8})", t)
    dsn = re.search(r"DSN\[128\] = ([0-9a-fA-F]{32})", t)
    verify = "PASS" if "Executing action VERIFY PASSED" in t else "NOT_RUN"
    digest = "PASS" if "Executing action VERIFY_DIGEST PASSED" in t else "NOT_RUN"
    if "FAILED" in t:
        verify = "FAIL"
    return {
        "tool": "FlashPro Express",
        "device": (re.search(r"device '(\S+)' : Executing", t) or [None, None])[1],
        "idcode": idcode.group(1) if idcode else None,
        "serial": dsn.group(1) if dsn else None,
        "verify": "PASS" if verify == "PASS" and digest == "PASS" else verify,
        "verify_method": "array verify and device digest check",
    }


PARSERS = {"vivado": vivado, "quartus": quartus, "libero": fpexpress, "openxc7": vivado}


def record(vendor, logs, programming_file, operator=None):
    rec = PARSERS[vendor](logs)
    rec["programming_file"] = Path(programming_file).name
    rec["bitstream_sha256"] = sha256(Path(programming_file))
    rec["operator"] = operator
    return rec
