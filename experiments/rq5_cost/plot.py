import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).absolute().parent
R = HERE / "results"

plt.rcParams.update({
    "font.family": "Arial", "mathtext.fontset": "custom", "mathtext.rm": "Arial", "font.size": 8,
    "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "xtick.major.size": 3, "ytick.major.size": 3, "axes.spines.top": False,
    "axes.spines.right": False, "pdf.fonttype": 42, "legend.fontsize": 7.5,
})
INK, BAR, GRID = "#1a1a1a", "#7a7a7a", "#dcdcdc"
FLOWS = [("zybo", "Zybo, Vivado (LUT)", "#0072B2", "o", "-"),
         ("zybo_open", "Zybo, open flow (LUT sites)", "#009E73", "^", ":"),
         ("c10lp", "Cyclone 10 LP, Quartus (LE)", "#D55E00", "s", "--"),
         ("disco", "PolarFire SoC, Libero (4LUT)", "#CC79A7", "D", "-."),
         ("xcu25", "XCU25, Vivado (LUT)", "#E69F00", "v", "-")]

scal = list(csv.DictReader(open(R / "scaling.csv")))
over = list(csv.DictReader(open(R / "overhead.csv")))
ipb = [r for r in csv.DictReader(open(R / "ip_scaling.csv")) if r["exit_code"] == "0" and r["egaudit_mean_s"]]
PUBLIC = {"zybo_hdmi/zybo": ("HDMI demo", "zybo"), "c10lp_multiproc/c10lp": ("Intel system", "c10lp"),
          "discovery_ref/disco": ("Discovery ref.", "disco"), "picosoc_zybo/zybo_open": ("PicoSoC", "zybo_open")}
pub = [r for r in over if r["build"] in PUBLIC and int(r["ip_cores"]) > 0]
logic = [r for r in csv.DictReader(open(R / "logic_scaling.csv")) if r["exit_code"] == "0" and r["egaudit_mean_s"]]

fig = plt.figure(figsize=(6.85, 5.0))
top = fig.add_gridspec(1, 2, left=0.085, right=0.97, top=0.94, bottom=0.57, wspace=0.28)
bottom = fig.add_gridspec(1, 1, left=0.25, right=0.97, top=0.42, bottom=0.09)
ax = [fig.add_subplot(top[0, 0]), fig.add_subplot(top[0, 1]), fig.add_subplot(bottom[0, 0])]

ip = [r for r in scal if r["bitstream_mib"] == "4"]
ax[0].errorbar([int(r["ip_seen"]) for r in ip], [float(r["egaudit_mean_s"]) for r in ip],
               yerr=[float(r["egaudit_sd_s"]) for r in ip], color=INK, lw=1.3, marker="o", ms=4.5,
               capsize=2.5, elinewidth=0.7, label="flat project")
COLOR = {key: (col, mk, ls) for key, _, col, mk, ls in FLOWS}
IPLABEL = {"zybo": "block design, Vivado", "c10lp": "Platform Designer, Quartus", "disco": "SmartDesign, Libero",
           "zybo_open": "module hierarchy, open flow"}
for key in ("zybo", "zybo_open", "c10lp", "disco"):
    col, mk, ls = COLOR[key]
    rs = sorted((r for r in ipb if r["board"] == key), key=lambda r: int(r["ip_instances"]))
    ax[0].errorbar([int(r["ip_instances"]) for r in rs], [float(r["egaudit_mean_s"]) for r in rs],
                   yerr=[float(r["egaudit_sd_s"]) for r in rs], color=col, lw=1.3, ls=ls, marker=mk, ms=4.5,
                   mec=col, mfc="white", capsize=2.5, elinewidth=0.7, label=IPLABEL[key])
for r in pub:
    name, key = PUBLIC[r["build"]]
    col = COLOR[key][0]
    x, y = int(r["ip_cores"]), float(r["egaudit_mean_s"])
    ax[0].errorbar([x], [y], yerr=[float(r["egaudit_sd_s"])], color=col, ls="none", marker="*", ms=8,
                   capsize=2.5, elinewidth=0.7)
    ty = {"Intel system": 0.62, "HDMI demo": 0.4, "Discovery ref.": 0.2}[name]  # labels left of the curves
    ax[0].annotate(name, (x, y), xytext=(8, ty), textcoords="data", fontsize=7, color=col, ha="right",
                   va="center", arrowprops=dict(arrowstyle="-", lw=0.5, color=col, shrinkA=1, shrinkB=4))
ax[0].set_xscale("log")
ax[0].set_yscale("log")
ax[0].set_ylim(0.005, 40)
ax[0].set_yticks([0.01, 0.03, 0.1, 0.3, 1.0, 3.0])
ax[0].set_yticklabels(["0.01", "0.03", "0.1", "0.3", "1", "3"])
ax[0].minorticks_off()
ax[0].set_xticks([1, 10, 100, 1000])
ax[0].set_xticklabels(["1", "10", "100", "1000"])
ax[0].set_xlabel("IP instances (flat project: IP cores added)")
ax[0].set_ylabel("EGAudit time (s)")
ax[0].legend(frameon=False, loc="upper left", handlelength=2.2, borderaxespad=0.1, fontsize=6.5)

for key, label, col, mk, ls in FLOWS:
    rs = sorted((r for r in logic if r["board"] == key), key=lambda r: int(r["logic_used"]))
    ax[1].errorbar([int(r["logic_used"]) for r in rs], [float(r["egaudit_mean_s"]) for r in rs],
                   yerr=[float(r["egaudit_sd_s"]) for r in rs], color=col, lw=1.3, ls=ls, marker=mk, ms=4.5,
                   mec=col, mfc="white" if mk in ("^", "D") else col, capsize=2, elinewidth=0.7, label=label)
ax[1].set_xscale("log")
ax[1].minorticks_off()
ax[1].set_ylim(0, 0.22)
ax[1].set_xlim(250, 1e6)
ax[1].set_yticks([0, 0.05, 0.1, 0.15, 0.2])
ax[1].set_yticklabels(["0", "0.05", "0.1", "0.15", "0.2"])
ax[1].set_xlabel("logic used (vendor unit)")
ax[1].set_ylabel("EGAudit time (s)")
LABEL_AT = {"zybo": (330, 0.052, "left"), "zybo_open": (1100, 0.008, "left"), "c10lp": (300, 0.185, "left"),
            "disco": (560, 0.084, "left"), "xcu25": (9.5e5, 0.078, "right")}
for key, label, col, mk, ls in FLOWS:
    x, y, ha = LABEL_AT[key]
    ax[1].text(x, y, label, color=col, fontsize=7.5, va="center", ha=ha)

names = {"cdc_ref/zybo": "Test design, Vivado", "cdc_ref/c10lp": "Test design, Quartus",
         "cdc_ref/disco": "Test design, Libero", "cdc_ref/zybo_open": "Test design, open flow",
         "zybo_hdmi/zybo": "HDMI demo, Vivado", "c10lp_multiproc/c10lp": "Intel system, Quartus",
         "discovery_ref/disco": "Discovery ref., Libero", "picosoc_zybo/zybo_open": "PicoSoC, open flow"}
FLOWNAME = {"zybo": "Vivado", "c10lp": "Quartus", "disco": "Libero", "zybo_open": "open flow"}
rows = [dict(r, build=names[r["build"]]) for r in over]
for r in ipb:
    if r["units"] == max((x["units"] for x in ipb if x["board"] == r["board"]), key=int):
        rows.append(dict(r, build=f'{r["ip_instances"]} IP, {FLOWNAME[r["board"]]}',
                         overhead_pct=100 * float(r["egaudit_mean_s"]) / float(r["vendor_build_s"])))
rows = rows[::-1]
pct = [float(r["overhead_pct"]) for r in rows]
ax[2].barh([r["build"] for r in rows], pct, color=BAR, height=0.6)
for i, (p, r) in enumerate(zip(pct, rows)):
    ax[2].text(p + 0.004, i, f'{float(r["egaudit_mean_s"]):.3f} s / {float(r["vendor_build_s"]):.0f} s',
               va="center", fontsize=7.5, color=INK)
ax[2].set_xlim(0, 0.5)
ax[2].set_xticks([0, 0.1, 0.2, 0.3, 0.4, 0.5])
ax[2].set_xlabel("EGAudit time / build time (%)")
ax[2].tick_params(axis="y", length=0)

for a in ax[:2]:
    a.grid(axis="y", color=GRID, lw=0.5)
    a.set_axisbelow(True)
ax[2].grid(axis="x", color=GRID, lw=0.5)
ax[2].set_axisbelow(True)
for a, t in zip(ax, ["(a) IP count", "(b) Logic size", "(c) Share of the build time"]):
    a.set_title(t, loc="left", fontsize=8.5, pad=6)

fig.savefig(sys.argv[1] if len(sys.argv) > 1 else "fig_cost.pdf")
