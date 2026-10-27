"""Robustness check on SYNTHETIC scenes: several seeds x base resolutions x (with / without height cue).
Writes docs/ablation.md. Synthetic only: it shows behaviour of the method, not field accuracy."""
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mappa import demo_data, pipeline  # noqa: E402

rows = []
for base_res in (10.0, 20.0):
    for seed in (1, 2, 3):
        tmp = Path(tempfile.mkdtemp())
        p = demo_data.generate(str(tmp / "in"), seed=seed, base_res_m=base_res)
        for use_h in (True, False):
            rep = pipeline.run(p["ortho"], p["base"], p["roads"], str(tmp / f"out_{use_h}"),
                               dsm=p["dsm"] if use_h else None, dem=p["dem"] if use_h else None,
                               simulated=True, truth=p["truth"])
            if not use_h:
                # evaluate truth for no-DSM runs too (pipeline does it whenever truth is given)
                pass
            v = rep["validation"]
            rows.append((base_res, seed, "yes" if use_h else "no", v["error_before_mean_m"], v["error_after_mean_m"],
                         v["roads_vs_truth"]["precision"], v["roads_vs_truth"]["recall"],
                         v["roads_vs_truth"]["false_positive_m"], v["roads_vs_truth"]["false_negative_but_flagged_uncertain_m"], rep["georeferencing"]["method"].split()[0]))
        shutil.rmtree(tmp)

md = ["# Ablation on synthetic scenes\n",
      "Synthetic data only (known injected GPS error, known slide footprint). Shows how the method behaves, "
      "not how accurate it is in the field.\n",
      "| base res (m) | seed | height cue | GPS err before (m) | err after (m) | road precision | road recall | false-positive blocked (m) | missed but flagged UNCERTAIN (m) | registration |",
      "|---|---|---|---|---|---|---|---|---|---|"]
for r in rows:
    md.append("| " + " | ".join(str(x) for x in r) + " |")
out = Path(__file__).resolve().parents[1] / "docs" / "ablation.md"
out.write_text("\n".join(md) + "\n")
print("\n".join(md))
