import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

HERE = Path(__file__).absolute().parent
R = HERE / "results"

plt.rcParams.update({"font.family": "Arial", "font.size": 7.5, "axes.linewidth": 0.6, "xtick.major.width": 0.6,
                     "ytick.major.width": 0.6, "xtick.major.size": 3, "ytick.major.size": 3,
                     "axes.spines.top": False, "axes.spines.right": False, "pdf.fonttype": 42})
INK, GRID, NOTE, FS = "#1a1a1a", "#dcdcdc", "#606060", 7
TOOL = {"vivado": ("Vivado", "#0072B2"), "quartus": ("Quartus", "#D55E00"), "libero": ("Libero", "#882255"),
        "open": ("open flow", "#009E73")}
FLOW = {"zybo": "vivado", "xcu25": "vivado", "xcu250": "vivado", "c10lp": "quartus", "disco": "libero",
        "zybo_open": "open"}
COL = {bd: TOOL[f][1] for bd, f in FLOW.items()}
ONE = dict(ls="none", marker="o", ms=5.2, mec="white", mew=0.5)
IPS = dict(marker="s", ms=4.4, mec="white", mew=0.4, lw=0.8)
LAN = dict(marker="^", ms=5, mfc="white", mew=0.9, lw=0.8)
CPY = dict(marker="o", ms=3.8, mfc="white", mew=0.8, lw=1.0, ls="--")


def rd(name):
    return list(csv.DictReader(open(R / name)))


def t(r, k="egaudit_mean_s"):
    return float(r[k])


over = rd("overhead.csv")
ipb = [r for r in rd("ip_scaling.csv") if r["exit_code"] == "0" and r["egaudit_mean_s"]]
logic = [r for r in rd("logic_scaling.csv") if r["exit_code"] == "0" and r["egaudit_mean_s"]]
soc = rd("litex_soc.csv")[0]
scal = rd("scaling.csv")

fig = plt.figure(figsize=(6.85, 5.25))
top = fig.add_gridspec(1, 2, left=0.075, right=0.985, top=0.865, bottom=0.515, wspace=0.2)
bot = fig.add_gridspec(1, 4, left=0.075, right=0.985, top=0.385, bottom=0.085, wspace=0.34)
a = fig.add_subplot(top[0, 0])
b = fig.add_subplot(top[0, 1], sharey=a)
m = [fig.add_subplot(bot[0, i]) for i in range(4)]

share = []
for bd in FLOW:
    for rows, style, z in (([r for r in ipb if r["board"] == bd and r["vendor_build_s"]], IPS, 4),
                           ([r for r in logic if r["board"] == bd and r["vendor_build_s"]], LAN, 3)):
        rows = sorted(rows, key=lambda r: t(r, "vendor_build_s"))
        a.plot([t(r, "vendor_build_s") for r in rows], [t(r) for r in rows], color=COL[bd], mec=style.get("mec", COL[bd]),
               zorder=z, **{k: v for k, v in style.items() if k != "mec"})
        share += [(t(r) / t(r, "vendor_build_s"), r) for r in rows]
for r in over:
    a.plot(t(r, "vendor_build_s"), t(r), color=COL[r["build"].split("/")[1]], zorder=5, **ONE)
    share.append((t(r) / t(r, "vendor_build_s"), r))
a.plot(t(soc, "vendor_build_s"), t(soc), color=COL["xcu250"], zorder=5, **ONE)
share.append((t(soc) / t(soc, "vendor_build_s"), soc))
print("builds in (a):", len(share))
for s, lab, xl in ((1e-2, "1% of build time", 75), (1e-3, "0.1%", 4000), (1e-4, "0.01%", 32000), (1e-5, "0.001%", 50000)):
    a.plot([1, 1e6], [s, s * 1e6], color="#b0b0b0", lw=0.6, ls=(0, (4, 3)), zorder=1)
    a.text(xl, s * xl * 1.25, lab, rotation=37.5, rotation_mode="anchor", fontsize=FS, color="#707070", ha="left",
           va="bottom")
hi, lo = max(share, key=lambda p: p[0]), min(share, key=lambda p: p[0])
a.annotate(f"{100 * hi[0]:.2f}%", (t(hi[1], "vendor_build_s"), t(hi[1])), xytext=(9, 0.45), fontsize=FS, color=INK,
           ha="center", arrowprops=dict(arrowstyle="-", lw=0.5, color=INK, shrinkA=1, shrinkB=3))
a.annotate(f"{100 * lo[0]:.4f}%".rstrip("0") + f"\n({int(lo[1]['logic_used']):,} LUTs)",
           (t(lo[1], "vendor_build_s"), t(lo[1])), xytext=(9000, 0.02), fontsize=FS, color=INK, ha="center",
           va="center", arrowprops=dict(arrowstyle="-", lw=0.5, color=INK, shrinkA=1, shrinkB=3))
a.text(t(soc, "vendor_build_s") / 1.3, t(soc), "32-core SoC", fontsize=FS, color=INK, ha="right", va="center")
for bd, lab, x, f, va in (("xcu250", "XCU250", 3000, 1.17, "bottom"), ("xcu25", "XCU25", 5200, 1 / 1.17, "top"),
                          ("zybo", "Zybo", 1180, 1.0, "center")):
    y = np.mean([t(r) for r in logic if r["board"] == bd])
    a.text(x, y * f, lab, fontsize=FS, ha="left", va=va, color=INK)
a.set_xscale("log")
a.set_yscale("log")
a.set_xlim(5, 2.5e5)
a.set_ylim(0.007, 9)
a.set_yticks([0.01, 0.1, 1])
a.set_yticklabels(["0.01", "0.1", "1"])
a.set_xticks([10, 100, 1000, 10000, 100000])
a.set_xticklabels(["10", "100", "1,000", "10,000", "100,000"])
a.set_xlabel("build time (s)")
a.set_ylabel("checking time (s)")


def line(ax, bd, rows, xs, **kw):
    order = sorted(range(len(rows)), key=lambda i: xs[i])
    kw = {"color": COL[bd], "capsize": 1.5, "elinewidth": 0.6, "clip_on": False, **kw}
    kw.setdefault("mec", COL[bd])
    ax.errorbar([xs[i] for i in order], [t(rows[i]) for i in order], yerr=[t(rows[i], "egaudit_sd_s") for i in order], **kw)


for bd in FLOW:
    rs = [r for r in logic if r["board"] == bd]
    line(b, bd, rs, [int(r["logic_used"]) for r in rs], **LAN)
rs = [r for r in ipb if r["board"] == "xcu250"]
line(b, "xcu250", rs, [int(r["logic_used"]) for r in rs], **{**IPS, "ls": "none"})
b.plot([int(soc["logic_used"])], [t(soc)], color=COL["xcu250"], zorder=5, **ONE)
xip = max(t(r) for r in ipb if r["board"] == "xcu250")
b.text(2.9e4, xip, "936 IP instances (XCU250)", fontsize=FS, ha="right", va="center", color=INK)
b.text(8.0e5, t(soc), "32-core SoC (XCU250)", fontsize=FS, ha="right", va="center", color=INK)
for bd, lab, x, f, va in (("xcu250", "XCU250", 1.1e5, 1.17, "bottom"), ("xcu25", "XCU25", 1.1e5, 1 / 1.17, "top"),
                          ("zybo", "Zybo", 386, 1 / 1.17, "top")):
    y = np.mean([t(r) for r in logic if r["board"] == bd])
    b.text(x, y * f, lab, fontsize=FS, ha="left", va=va, color=INK)
b.axvline(1e6, color="#b0b0b0", lw=0.6, ls=(0, (1, 2)), zorder=0)
b.set_xscale("log")
b.set_xlim(250, 2.2e6)
b.set_xticks([1e3, 1e4, 1e5, 1e6])
b.set_xticklabels(["1,000", "10,000", "100,000", "1,000,000"])
b.set_xlabel("logic used (vendor unit)")
b.tick_params(labelleft=True)


def slope(xs, ys):
    return np.polyfit(np.array(xs, float), np.array(ys, float), 1)[0]


def rng(v, d):
    lo, hi = f"{min(v):.{d}f}", f"{max(v):.{d}f}"
    return lo if lo == hi else f"{lo}-{hi}"


for bd in ("zybo", "c10lp", "disco", "zybo_open"):
    rs = [r for r in ipb if r["board"] == bd]
    line(m[0], bd, rs, [int(r["ip_instances"]) for r in rs], **{**IPS, "ms": 3.8, "lw": 1.0})
zb = [r for r in scal if r["board"] == "zybo" and r["bitstream_mib"] == "4" and r["hdl_mib"] == "0"]
rs = [r for r in zb if r["extra_files"] == "0"]
line(m[0], "zybo", rs, [int(r["ip_seen"]) for r in rs], **CPY)
m[0].set_xlim(0, 1080)
m[0].set_ylim(bottom=0)
m[0].set_xticks([0, 500, 1000])
m[0].set_xlabel("IP instances")
m[0].set_ylabel("checking time (s)")

fs = []
for bd in ("c10lp", "disco", "zybo", "zybo_open"):
    rs = [r for r in scal if r["board"] == bd and r["extra_ip"] == "0" and r["hdl_mib"] == "0"
          and r["bitstream_mib"] == ("4" if bd == "zybo" else "0")]
    xs = [int(r["extra_files"]) for r in rs]
    line(m[1], bd, rs, xs, **CPY)
    fs.append(1e3 * slope(xs, [t(r) for r in rs]))
m[1].set_xlim(0, 33000)
m[1].set_ylim(bottom=0)
m[1].set_xticks([0, 10000, 20000, 30000])
m[1].set_xticklabels(["0", "10k", "20k", "30k"])
m[1].set_xlabel("files added to build directory")
m[1].text(0.06, 0.93, rng(fs, 2) + " ms per file", transform=m[1].transAxes, fontsize=FS, color=NOTE,
          va="top")

hs, bs = [], []
for bd in ("c10lp", "disco", "zybo", "zybo_open"):
    rs = [r for r in scal if r["board"] == bd and r["extra_ip"] == "0" and r["extra_files"] == "0"]
    h = [r for r in rs if r["bitstream_mib"] == ("4" if bd == "zybo" else "0")]
    line(m[2], bd, h, [int(r["hdl_mib"]) for r in h], **CPY)
    hs.append(slope([int(r["hdl_mib"]) for r in h], [t(r) for r in h]))
    p = [r for r in rs if r["hdl_mib"] == "0"]
    line(m[3], bd, p, [int(r["bitstream_bytes"]) / 2**20 for r in p], **CPY)
    bs.append(1e3 * slope([int(r["bitstream_bytes"]) / 2**20 for r in p], [t(r) for r in p]))
m[2].set_xlim(0, 70)
m[2].set_ylim(bottom=0)
m[2].set_xticks([0, 16, 32, 64])
m[2].set_xlabel("HDL source added (MiB)")
m[2].text(0.06, 0.93, rng(hs, 2) + " s per MiB", transform=m[2].transAxes, fontsize=FS, color=NOTE,
          va="top")
m[3].set_xlim(0, 280)
m[3].set_ylim(bottom=0)
m[3].set_xticks([0, 64, 128, 256])
m[3].set_xlabel("bitstream size (MiB)")
m[3].text(0.06, 0.93, rng(bs, 1) + " ms per MiB", transform=m[3].transAxes, fontsize=FS, color=NOTE,
          va="top")

for ax in [a, b] + m:
    ax.grid(axis="y", color=GRID, lw=0.5)
    ax.set_axisbelow(True)
    ax.minorticks_off()
for ax, title in zip([a, b] + m, ["(a) Cost against build time", "(b) Logic size", "(c) IP instances", "(d) Files",
                                  "(e) HDL source size", "(f) Bitstream size"]):
    ax.set_title(title, loc="left", fontsize=8, pad=4)

g = "#555555"
flows = [Line2D([], [], ls="none", marker="o", ms=5, color=c, label=n) for n, c in TOOL.values()]
kinds = [Line2D([], [], color=g, label="test, public, or SoC design", **ONE),
         Line2D([], [], color=g, label="IP-count designs", **IPS),
         Line2D([], [], color=g, mec=g, label="lane (logic-size) designs", **LAN),
         Line2D([], [], color=g, mec=g, label="copy of a build with evidence added", **CPY)]
fig.legend(handles=flows, loc="upper left", bbox_to_anchor=(0.07, 1.0), ncol=4, frameon=False, fontsize=FS,
           handletextpad=0.2, columnspacing=1.6, borderaxespad=0.2)
fig.legend(handles=kinds, loc="upper left", bbox_to_anchor=(0.07, 0.962), ncol=4, frameon=False, fontsize=FS,
           handletextpad=0.5, columnspacing=1.3, borderaxespad=0.2, handlelength=2.4)
fig.savefig(sys.argv[1] if len(sys.argv) > 1 else "fig_cost.pdf")
