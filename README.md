# Evidence-Gated STRIDE for FPGA Development Toolchains

Artifact for the paper *Evidence-Gated STRIDE Threat Modeling for FPGA Development Toolchains*
(Computers & Security, manuscript COSE-D-26-03864). It contains the 24 threat records, the checker
EGAudit (command and Python package `egaudit`) that assigns a verdict to each record from build outputs, release manifests, programming logs, and simulator logs,
the test design and flows of the evaluation, and the results reported in the paper.

## Layout

| Path | Contents |
|---|---|
| `catalog/records.csv` | The 24 threat records with all fields |
| `catalog/capabilities.csv` | The five attacker capabilities of Table 1 and the records whose attacker capability falls under each |
| `catalog/mitigation_families.csv` | The 13 mitigation families and the records assigned to each |
| `catalog/candidates.csv` | The 62 candidate threats and the gate decision for each |
| `catalog/generic_baseline.csv` | The 54 generic questions of the baseline (six STRIDE categories for each of the nine record groups) and their outcome |
| `catalog/evidence_sources.csv` | Template of the evidence to collect: each evidence field, the records that read it, and where Vivado, Quartus, Libero, and the open flow write it (a unit test keeps it equal to the adapters) |
| `egaudit/` | The checker (Python 3.9 or later, no dependencies) and its unit tests |
| `egaudit/egaudit/simulation.py` | Simulator log parsers for `egaudit sim`: the files a simulation compiled (xvlog log of the Vivado simulator, vlog log of Questa, dependency file of Icarus Verilog), their digests at simulation time, and the pass or fail line |
| `egaudit/egaudit/artifacts.py` | Artifact rules per flow: which build file is check evidence and which a tool byproduct; any other file that is no approved input leaves RPT-2 Partial |
| `designs/cdc_ref/` | Test design (dual-clock FIFO between two PLL clocks) and its testbench |
| `designs/picosoc_zybo/`, `designs/public.csv` | PicoSoC top level, pins, and PLL for the Zybo Z7-20, and the sources, versions, and licenses of the public designs |
| `boards/` | Per-target PLL wrapper, IP configuration, pin, and timing constraints (`zybo_open`: open flow; `xcu25`: build only) |
| `flows/` | Build scripts (Vivado, Quartus Prime Standard, Libero SoC, openXC7), programming and readback scripts, simulation with the simulator of each flow (`flows/sim/run_sim.py`) |
| `experiments/` | One folder per research question, each with `run.py` and `results/` |

## Paper tables and figures

Commands run from `experiments/`. Expected results are the values in the paper.

| Paper | Expected result | Command | Output |
|---|---|---|---|
| Fig. 1, Fig. 4 (running example, attack A1 on the Zybo) | CFG-1 Violated: `changed cdc.xdc`; the A1 bitstream programmed and verified on the board; with its deployment record, the verdict counts of Fig. 4 | `python rq2_detection/run.py zybo`; for Fig. 4, `egaudit deploy` and `egaudit check` as below | `rq2_detection/results/zybo/A1.csv`, `A1_program.log` (kept programming log), `A1.deploy.json`, `A1_deployed.csv` |
| Table 1 (attacker capabilities) | five capabilities; the attacker capability of every record falls under one or two | (data) | `catalog/capabilities.csv` |
| Table 3, Table 4 (records) | 24 records and the check of each | (data) | `catalog/records.csv`, `egaudit/egaudit/rules.py` |
| Table 5 (setup) | design sizes from the tool reports (public designs: in `build/public/` after `public_designs/run.py build`) | `python rq1_end_to_end/run.py`, `python public_designs/run.py build` | implementation reports in `build/rq1/<board>/` and `build/public/`; `rq1_end_to_end/results/<board>/build.csv` and `public_designs/results/builds.csv` list each build's exit code and time |
| Table 6 (RQ1) | Satisfied from tool outputs: 5 (Vivado, Quartus, Libero) and 6 (open flow); with the manifest: 17 in every flow, 23 of 24 records agree across flows; with the testbed evidence (simulation record with the simulator of each flow, tool installation digest, license record): 20 in every flow, all 24 agree | `python rq1_end_to_end/run.py`, then `python rq1_end_to_end/project_evidence.py` | `rq1_end_to_end/results/rq1_verdicts.csv`; per flow `manifest_project.json` (with the tool installation digest), `sim_record.json`, `license_record.json`, `verdicts_project.csv` |
| RQ1 (public designs, text) | one public design per flow programmed and verified on its board; Satisfied from tool outputs 5, 5, 5, 6 and with the manifest 16, 16, 16, 17 (HDMI demo, Intel system, Discovery reference design, PicoSoC); RPT-2 Partial in the three vendor designs (files outside the release) | `python public_designs/run.py build`, then `python public_designs/run.py check` | `public_designs/results/verdicts.csv`, `public_designs/results/<design>/` |
| Table 7 (RQ2) | 70 of 70 attack cases (18 attacks in four flows) detected; N1, N3, N4, N5 change no verdict | `python rq2_detection/run.py`, `extra_attacks.py`, `rebuilds.py`, `input_attacks.py`, `rebuild_attacks.py`, `sim_attack.py` (after `rq1_end_to_end/project_evidence.py`) | `rq2_detection/results/rq2_detection.csv` |
| RQ3 (text) | 72 of 72 field values correct (eight builds); all 27 IP instances of the HDMI demo and all 30 of the Intel system | `python rq3_extraction/run.py`, `python public_designs/run.py ip` | `rq3_extraction/results/accuracy_by_vendor.csv`, `public_designs/results/ip_*.csv` |
| Table 8 (RQ4) | A1–A9 and A18 detected in every flow; A17 in Vivado, Libero, and the open flow | `python rq4_comparison/run.py` | `rq4_comparison/results/attacks_rq2.csv` |
| Fig. 6 (RQ5) | overhead at most 0.51% of the build time (0.011–0.38% on the builds of Fig. 6c: test and public designs, largest IP-count design per flow); IP-count designs of the same structure in every flow (Vivado 16–936 instances, Libero 18–936, Quartus 23–270, open flow 16–622); time linear in the instance count in Vivado and Quartus (3.4 s for 936, 0.79 s for 270), 0.21 s for 936 in Libero (one record per configured core) | `python rq5_cost/run.py`, `python rq5_cost/logic_scaling.py time`, `python rq5_cost/ip_scaling.py time`, `python rq5_cost/ip_qsys.py time`, `python rq5_cost/ip_sd.py time`, `python rq5_cost/ip_rtl.py time`, `python rq5_cost/plot.py` | `rq5_cost/results/*.csv`, `fig_cost.pdf` |
| Supplementary tables | | | the CSV file named in the caption, where there is one |

Figures 2–3 (diagrams), Figure 5 (photo of the boards), and Table 2 (STRIDE interpretation) have no data file.

## All commands

| Result | Command | Output |
|---|---|---|
| RQ1: verdicts per record, flow, and condition | `python rq1_end_to_end/run.py` | `rq1_end_to_end/results/rq1_verdicts.csv` |
| RQ1: testbed evidence (simulation with the simulator of each flow, tool installation digest, license record; needs the four simulators, or `--recheck` to use the logs in `build/rq1_sim/`) | `python rq1_end_to_end/project_evidence.py` | `rq1_end_to_end/results/<board>/manifest_project.json`, `sim_record.json`, `license_record.json`, `verdicts_project.csv`; simulator logs in `build/rq1_sim/` |
| RQ2: attacks A1–A9 and benign changes N1–N4 | `python rq2_detection/run.py` | `rq2_detection/results/rq2_detection.csv` |
| RQ2: attacks A10–A13 | `python rq2_detection/extra_attacks.py` | `rq2_detection/results/<board>/cases_extra.csv` |
| RQ2: attacks A14–A15 (files that only the HDL names) | `python rq2_detection/input_attacks.py` | `rq2_detection/results/<board>/cases_inputs.csv` |
| RQ2: attacks A16–A17 and N5 (checked against a separate rebuild) | `python rq2_detection/rebuild_attacks.py` | `rq2_detection/results/<board>/cases_rebuild.csv` |
| RQ2: attack A18 (testbench weakened after review, NSA/JFAC TD 3.2; `--recheck` uses the logs in `build/rq2_sim/`) | `python rq2_detection/sim_attack.py` | `rq2_detection/results/<board>/cases_sim.csv`; simulator logs in `build/rq2_sim/` |
| RQ2: rebuild N2 repeated four more times (five rebuilds per flow) | `python rq2_detection/rebuilds.py` | `rq2_detection/results/<board>/rebuilds.csv` |
| RQ2: configuration change of the attack-case builds | `python rq2_detection/config_changed.py` | `rq2_detection/results/config_changed.csv` |
| RQ3: extraction accuracy | `python rq3_extraction/run.py` | `rq3_extraction/results/accuracy_by_vendor.csv` |
| RQ3: differences between tool outputs | (observations) | `rq3_extraction/semantic_differences.csv` |
| RQ4: attacks against threat models, checked against RQ2 | `python rq4_comparison/run.py` | `rq4_comparison/results/attacks_rq2.csv` |
| RQ5: overhead and scaling | `python rq5_cost/run.py`, then `python rq5_cost/plot.py` | `rq5_cost/results/*.csv` |
| RQ5: time against logic size | `python rq5_cost/logic_scaling.py <board> <N> ...`, then `python rq5_cost/logic_scaling.py time` | `rq5_cost/results/logic_scaling.csv` |
| RQ5: time against IP count (designs of six or seven IP instances per unit in three hierarchy levels: Vivado block designs `rq5_cost/ip_net.tcl`, Quartus Platform Designer `ip_qsys.py`, Libero SmartDesign `ip_sd.py`, open-flow HDL modules `ip_rtl.py`) | `python rq5_cost/ip_scaling.py zybo <units>` for 2, 17, 50, 100, 150; `python rq5_cost/ip_qsys.py 2 10 20 30 36`; `python rq5_cost/ip_sd.py 2 17 50 100 150`; `python rq5_cost/ip_rtl.py 2 17 50 100 150`; then `time` for each | `rq5_cost/results/ip_scaling.csv`; builds in `build/rq5_ip/` |
| RQ1, RQ3, and RQ5: public designs, one per flow (run before the RQ3 and RQ5 scripts): build, release manifest, programming and device verification, EGAudit (`--recheck` uses the existing builds and programming logs), IP instances against the tool's list | `python public_designs/run.py build`, `python public_designs/run.py check`, `python public_designs/run.py ip` | `public_designs/results/`, `build/public/` |
| Simulation of the test design | `python ..\flows\sim\run_sim.py <xsim\|questa\|questa_mchp\|icarus> <out_dir>` | the simulator's logs in `<out_dir>` |

`python -m egaudit check <build> --manifest M.json --rebuild <rebuild>` also compares the release's configuration with a
separate rebuild of the approved inputs (BSD-1). `python -m egaudit sim --simulator <xsim|questa|icarus> --dir <sim_dir> --out <sim_dir>/sim_record.json`
records a simulation run; `egaudit manifest` takes `--testbench`, `--simulation`, `--tool-image` (glob of the tool executables),
`--license-record`, `--access-log`, and `--key-record`, and `egaudit check` takes `--simulation`. The Fig. 4 counts come from
`python -m egaudit deploy --vendor vivado --log rq2_detection/results/zybo/A1_program.log --file ../build/rq2_zybo/A1/cdc_ref.bit --out rq2_detection/results/zybo/A1.deploy.json`
and `python -m egaudit check ../build/rq2_zybo/A1 --manifest rq2_detection/results/zybo/A1.manifest.json --deploy rq2_detection/results/zybo/A1.deploy.json --out rq2_detection/results/zybo/A1_deployed.csv`
(with `egaudit/` on `PYTHONPATH`).
The manifest key `approved.reviewer` records the approver of the inputs. `--recheck` (RQ1 and RQ2 scripts) derives the verdicts again from existing builds and programming logs without
building or programming. `--no-program` skips board programming, and `--reprogram` (RQ1) programs the existing
builds again without building them. `python -m egaudit inventory <build> --out F.csv` lists every file of a build with
its artifact family, size, and digest. In `egaudit/`,
`python -m unittest discover -s tests` runs the unit tests.

## Device verification

| Flow | Board | Verification after programming |
|---|---|---|
| Vivado | Zybo Z7-20 | `verify_hw_devices` with the `.msk` mask |
| Quartus Prime Standard | Cyclone 10 LP Evaluation Kit | configuration flash (EPCQ128A) programmed from a `.jic` with CRC verification |
| Libero SoC | PolarFire SoC Discovery Kit | FlashPro Express VERIFY and VERIFY_DIGEST |
| Open flow (openXC7) | Zybo Z7-20 | readback compared with the bitstream (UG470 ch. 6, method 2), user memory masked (`flows/program/`) |

## Build evidence

`build_evidence/` holds the builds from which the RQ1 and RQ2 verdicts are derived, as one `tar.gz` split into
parts below GitHub's file-size limit: the release build of each flow, the attack-case builds A1–A3, A10, and A11, the
rebuilds N2 and N2r1–N2r4, the memory-file variant of the test design with its release R14, rebuild R14r, and attack-case builds A14, A15, and
A17, the modified inputs, the A8 programming logs, and the simulator logs and records of the RQ1 testbed evidence
and of A18 (`build/rq1_sim/`, `build/rq2_sim/`). The recheck recreates A4, A6, A12,
and N1 from the release build. Left out: output that the vendor tools generate for their IP cores and Vivado
run-status files. The logs record the absolute paths of the machine that built them; they are kept as produced,
because the checks hash them. Folder names map to the paper as F1cdc = A1, F3src = A3, F10board = A10,
F11cdc = A11, and F14data/F14src = the memory-file variant of A14–A17. Unpack into the repository root, which creates `build/`:

```
cat build_evidence/build_evidence.tar.gz.part* > build_evidence.tar.gz          # Linux, macOS
copy /b build_evidence\build_evidence.tar.gz.part* build_evidence.tar.gz         # Windows
tar -xzf build_evidence.tar.gz
```

`build_evidence/SHA256SUMS` lists the digest of each part and of the joined archive. With `build/` in place,
the `--recheck` commands derive the RQ1 and RQ2 verdicts without the vendor tools or the boards.

## Requirements

- AMD Vivado 2025.2, Altera Quartus Prime Standard 25.1, Microchip Libero SoC 2025.2. Set `VIVADO`,
  `QUARTUS_SH`, `QUARTUS_PGM`, `LIBERO`, and `FPEXPRESS` if the tools are not on `PATH`.
- Open flow: openXC7 (nextpnr-xilinx, Project X-Ray database) and Yosys from OSS CAD Suite, as distributed by the
  apio project (`fpgawars/tools-openxc7` release 2026-09-22, `fpgawars/tools-oss-cad-suite` release
  2026-09-15), under `$OPENXC7_TOOLS` (default `../tools`). Set `PRJXRAY_DB` if the database is elsewhere. The open
  flow runs nextpnr-xilinx with `--timing-allow-fail`, so that, as in the vendor flows, a build that misses timing
  still produces a bitstream and the failure is left to CFG-3 (attack A11).
- Python 3.9 or later; `rq5_cost/plot.py` needs matplotlib. To run `python -m egaudit` directly, put `egaudit/` on
  `PYTHONPATH`; the experiment scripts do this themselves.
- Simulators (RQ1 testbed evidence and A18): the Vivado simulator, Questa FPGA Starter Edition (Quartus),
  QuestaSim Pro of Libero, and Icarus Verilog of OSS CAD Suite. Set `VIVADO_BIN`, `QUESTA_BIN`, `QUESTA_MCHP_BIN`,
  `QUESTA_MCHP_LICENSE`, and `OSS_CAD_BIN` if the simulators are not on `PATH` (`OSS_CAD_BIN` defaults to `../tools/oss-cad-suite/bin`).
- Public designs: set `INTEL_PAR` to the Intel design's `top.par` (see the table below). On Windows, the HDMI
  demo's paths exceed 260 characters under a deep folder; set `PUBLIC_BUILD` to a short path (for example a drive
  letter mapped with `subst`) for `public_designs/run.py`.
- Boards: Digilent Zybo Z7-20, Cyclone 10 LP Evaluation Kit, PolarFire SoC Discovery Kit. Set `DISCO_RESTORE_JOB` to
  the `.job` file of Microchip's released Discovery Kit image before programming that board.

Board safety: the scripts use only program, verify, readback, and device-information actions; no eFUSE,
key, or security setting is written. Back up the Cyclone 10 LP configuration flash before programming it.
The PolarFire SoC flash is overwritten; `common.restore_disco()` programs Microchip's released Discovery Kit
image back.

## Third-party designs and tools

The public designs are downloaded by `experiments/public_designs/run.py` at the versions below (listed in
`designs/public.csv`); none of their files is included in this repository except where noted.

| Design | Source | Version | License | Use |
|---|---|---|---|---|
| Zybo Z7-20 HDMI demo (Digilent) | https://github.com/Digilent/Zybo-Z7/releases/tag/20%2FHDMI%2F2025.1-1 | release `20/HDMI/2025.1-1` | no license file in the release | Vivado, Zybo Z7-20 |
| Digilent vivado-library (driver files of `axi_dynclk` missing from the HDMI release) | https://github.com/Digilent/vivado-library | `f4613fff` | MIT | HDMI demo build |
| Digilent vivado-boards (Zybo Z7-20 board files, shipped with the HDMI release) | https://github.com/Digilent/vivado-boards | as shipped | MIT | HDMI demo build |
| Cyclone 10 LP multiprocessor Nios II system (Intel) | https://docs.altera.com/r/example-designs/714849/current/cyclone-10-lp-fpga-multiprocessor-nios-ii-processor-system-reference-design/detailed-description | `top.par`, Quartus 17.0 | Intel design example license; download it yourself and set `INTEL_PAR` | Quartus, Cyclone 10 LP kit; ported to Nios V by `flows/quartus/niosv_port.py` |
| PolarFire SoC Discovery Kit reference design (Microchip) | https://github.com/polarfire-soc/polarfire-soc-discovery-kit-reference-design | `f09b6e0d` | Microchip license (`LICENSE.md` of the repository) | Libero, Discovery Kit |
| Discovery Kit released image (Microchip) | https://github.com/polarfire-soc/polarfire-soc-discovery-kit-reference-design/releases/tag/v2026.04 | `MPFS_DISCOVERY_2026_04.zip` | as above | restores the board (`DISCO_RESTORE_JOB`) |
| PicoRV32 and PicoSoC (YosysHQ) | https://github.com/YosysHQ/picorv32 | `87c89acc` | ISC | open flow, Zybo Z7-20; the Zybo top level, pins, and PLL in `designs/picosoc_zybo/` are ours (port of `picosoc/hx8kdemo.v`) |

Open-flow tools: Yosys (https://github.com/YosysHQ/yosys, ISC), nextpnr-xilinx of openXC7
(https://github.com/openXC7/nextpnr-xilinx, ISC), and Project X-Ray (https://github.com/f4pga/prjxray, ISC).

## License

Code under MIT, data and documentation under CC BY 4.0 (see `LICENSE`). Third-party designs keep their own
licenses.
