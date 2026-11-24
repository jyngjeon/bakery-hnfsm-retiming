"""Build data/processed/{bk15,bk50}-clean.{json,xlsx} from the raw Mendeley Excel files.

Usage: uv run python experiments/preprocess-data.py
"""

from bakery.preprocess import PIPELINES, save

for name, pipeline in PIPELINES.items():
    tables = pipeline()
    json_path, xlsx_path = save(name, tables)
    m, e, ops = tables["machines"], tables["employees"], tables["operations"]
    n_oven = int((m["machine_type"] == "OVEN").sum())
    print(f"[{name}] machines={len(m)} (ovens {n_oven}), employees={len(e)}, "
          f"operations={len(ops)}, groups={ops['g'].nunique()} -> {json_path.name}, {xlsx_path.name}")
