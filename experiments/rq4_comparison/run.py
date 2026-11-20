import csv
import sys
from pathlib import Path

HERE = Path(__file__).absolute().parent
sys.path.insert(0, str(HERE.parent))
import common as c

RQ2 = HERE.parent / "rq2_detection" / "results"


def main():
    rq2 = list(csv.DictReader(open(RQ2 / "rq2_detection.csv", newline="")))
    attacks = list(csv.DictReader(open(HERE / "attacks.csv", newline="")))
    rows = []
    for a in attacks:
        flows, found, agree = [], 0, True
        if a["case"]:
            runs = [r for r in rq2 if r["case"] in a["case"].split(";") and r["egaudit_detected"] != ""]
            flows = [r["board"] for r in runs]
            found = sum(r["egaudit_detected"] == "1" for r in runs)
            agree = all(r["expected"] == a["records"] for r in runs)
        rows.append([a["attack"], a["nsa_jfac_td"], a["slsa_threat"], a["records"], a["coverage"], a["case"],
                     f"{found}/{len(flows)}" if flows else "", int(agree)])
    c.write_csv(HERE / "results" / "attacks_rq2.csv",
                ["attack", "nsa_jfac_td", "slsa_threat", "records", "coverage", "case", "egaudit_detected_flows",
                 "records_match_rq2"], rows)
    for r in rows:
        print(r[5] or "-", r[6] or "-", r[7], r[0])


if __name__ == "__main__":
    main()
