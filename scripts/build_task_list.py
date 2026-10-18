#!/usr/bin/env python3
"""Snapshot the SODAT task dictionary into the dashboard's task-list.json.

The canonical dictionary lives in the *sodat-matching* repo
(`data/task_types_seed.csv`). The sodat_control dashboard shows it read-only
as a reference tab, grouped by 作目 (crop) → 工程 (process) → 作業名 (task name).
Aptitude and task IDs are intentionally omitted.

This produces a committed snapshot so the dashboard has no runtime dependency
on the matching repo or its deployment. Re-run it when the dictionary changes:

    python3 scripts/build_task_list.py \
        --src ../sodat-matching/data/task_types_seed.csv

Only 作目別 (crop-level, item == "common") rows are emitted — per
sodat-matching ADR 0019, per-品目 (e.g. tomato) expansions are not part of the
canonical dictionary yet.
"""
import argparse
import csv
import json
import os
from datetime import datetime, timezone

# Display order + Japanese labels for the crops in the dictionary.
CROP_ORDER = ["veg", "fruit", "tea", "dairy", "winegrape"]
CROP_LABELS = {
    "veg": "野菜", "fruit": "果樹", "tea": "茶",
    "dairy": "酪農", "winegrape": "醸造用ぶどう",
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SRC = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "sodat-matching",
                                           "data", "task_types_seed.csv"))
DEFAULT_OUT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "docs", "dashboard",
                                           "task-list.json"))


def primary_process(raw):
    """First 工程 listed (the row's primary process); '—' when blank."""
    for part in str(raw or "").replace("；", ";").split(";"):
        p = part.strip()
        if p:
            return p
    return "—"


def build(src):
    rows = list(csv.DictReader(open(src, encoding="utf-8")))
    crops = {}
    for r in rows:
        crop = (r.get("crop") or "").strip()
        name = (r.get("task_name") or "").strip()
        if not crop or not name:
            continue
        proc = primary_process(r.get("process"))
        c = crops.setdefault(crop, {"order": [], "by_proc": {}})
        if proc not in c["by_proc"]:
            c["by_proc"][proc] = []
            c["order"].append(proc)
        c["by_proc"][proc].append(name)

    ordered = CROP_ORDER + [c for c in crops if c not in CROP_ORDER]
    out_crops = []
    for crop in ordered:
        if crop not in crops:
            continue
        c = crops[crop]
        processes = [{"process": p, "tasks": c["by_proc"][p]} for p in c["order"]]
        count = sum(len(p["tasks"]) for p in processes)
        out_crops.append({
            "crop": crop,
            "label": CROP_LABELS.get(crop, crop),
            "count": count,
            "processes": processes,
        })
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "sodat-matching/data/task_types_seed.csv",
        "note": "作目別（item=common）の正本スナップショット。適性・IDは非掲載。",
        "crops": out_crops,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default=DEFAULT_SRC, help="path to task_types_seed.csv")
    ap.add_argument("--out", default=DEFAULT_OUT, help="output task-list.json")
    args = ap.parse_args()
    data = build(args.src)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    total = sum(c["count"] for c in data["crops"])
    print(f"wrote {args.out}: {len(data['crops'])} crops, {total} tasks")
    for c in data["crops"]:
        print(f"  {c['label']:10} {c['count']:3}  ({len(c['processes'])} 工程)")


if __name__ == "__main__":
    main()
