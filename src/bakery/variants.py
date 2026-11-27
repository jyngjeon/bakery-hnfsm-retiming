"""Instance variants for modelling-assumption checks (docs/TODO.md A5).

Variants are derived from data/processed/*-clean.json and written to a results
folder; data/processed/ itself is never modified.
- "expanded": the cleaned instance as is (batch >= 2 expanded into new groups).
- "no_batch": only batch 1 of every group (batches are not expanded).
- "g18_once": BK50 only; the batch-2 copy of Group 18 drops "Dough C" (p=1),
  so Dough C is produced once. Remaining products keep their offsets: p is
  renumbered and the first-stage WT is shifted so the old p=2 starts at 0.
"""

from __future__ import annotations

import json
from pathlib import Path

from bakery.paths import processed_json

BATCH_VARIANTS = ("expanded", "no_batch", "g18_once")


def batch_variant_data(inst: str, batch: str) -> dict:
    data = json.loads(processed_json(inst).read_text(encoding="utf-8"))
    ops = data["operations"]
    if batch == "expanded":
        return data
    if batch == "no_batch":
        ops = [o for o in ops if o["batch_no"] == 1]
    elif batch == "g18_once":
        g2 = {o["g"] for o in ops if o["orig_pr_group"] == 18 and o["batch_no"] == 2}
        if len(g2) != 1:
            raise ValueError("g18_once needs BK50 (Group 18 with a batch-2 copy)")
        g2 = g2.pop()
        assert all(o["product_name"] == "Dough C" for o in ops if o["g"] == g2 and o["p"] == 1)
        shift = min(o["WT"] for o in ops if o["g"] == g2 and o["p"] == 2 and o["s"] == 1)
        new_ops = []
        for o in ops:
            if o["g"] == g2:
                if o["p"] == 1:
                    continue
                o = dict(o, p=o["p"] - 1, WT=(o["WT"] - shift) if o["s"] == 1 else o["WT"])
            new_ops.append(o)
        ops = new_ops
    else:
        raise ValueError(f"unknown batch variant: {batch}")
    data["operations"] = ops
    return data


def write_batch_variant(inst: str, batch: str, out_dir: Path) -> Path:
    """Path of the instance JSON for a batch variant (the original for "expanded")."""
    if batch == "expanded":
        return processed_json(inst)
    path = Path(out_dir) / "instances" / f"{inst.lower()}-{batch.replace('_', '-')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(batch_variant_data(inst, batch), ensure_ascii=False), encoding="utf-8")
    return path
