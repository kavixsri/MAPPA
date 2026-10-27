# Ablation on synthetic scenes

Synthetic data only (known injected GPS error, known slide footprint). Shows how the method behaves, not how accurate it is in the field.

| base res (m) | seed | height cue | GPS err before (m) | err after (m) | road precision | road recall | false-positive blocked (m) | missed but flagged UNCERTAIN (m) | registration |
|---|---|---|---|---|---|---|---|---|---|
| 10.0 | 1 | yes | 5.69 | 0.45 | 1.0 | 1.0 | 0 | 0 | SIFT+RANSAC |
| 10.0 | 1 | no | 5.69 | 0.45 | None | 0.0 | 0 | 0 | SIFT+RANSAC |
| 10.0 | 2 | yes | 5.69 | 0.34 | 1.0 | 1.0 | 0 | 0 | SIFT+RANSAC |
| 10.0 | 2 | no | 5.69 | 0.34 | None | 0.0 | 0 | 0 | SIFT+RANSAC |
| 10.0 | 3 | yes | 5.69 | 0.38 | 1.0 | 1.0 | 0 | 0 | SIFT+RANSAC |
| 10.0 | 3 | no | 5.69 | 0.38 | None | 0.0 | 0 | 0 | SIFT+RANSAC |
| 20.0 | 1 | yes | 5.69 | 0.7 | 1.0 | 0.8 | 0 | 20 | SIFT+RANSAC |
| 20.0 | 1 | no | 5.69 | 0.7 | 0.0 | 0.0 | 59 | 20 | SIFT+RANSAC |
| 20.0 | 2 | yes | 5.69 | 2.7 | 1.0 | 1.0 | 0 | 0 | SIFT+RANSAC |
| 20.0 | 2 | no | 5.69 | 2.7 | 0.0 | 0.0 | 79 | 0 | SIFT+RANSAC |
| 20.0 | 3 | yes | 5.69 | 1.35 | 1.0 | 0.8 | 0 | 20 | SIFT+RANSAC |
| 20.0 | 3 | no | 5.69 | 1.35 | 0.0 | 0.0 | 59 | 0 | SIFT+RANSAC |

**Reading the table.** With the height cue (DSM−DEM) the road precision was 1.0 in all 6 runs and recall 0.8–1.0 (the 0.8 cases miss ~20 m flagged UNCERTAIN). Without it, colour change alone produced no BLOCKED calls at 10 m (debris on a dirt road looks like the road) and false BLOCKED calls at 20 m. `None` precision = no BLOCKED predictions made. Registration error after correction was 0.3–0.5 m at 10 m base resolution and 0.7–2.7 m at 20 m. All synthetic.
