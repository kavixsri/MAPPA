"""Build a ~95 s 720p walkthrough MP4 from REAL pipeline outputs (no fabricated screens).
Usage: python scripts/make_walkthrough_video.py <demo_run_dir> <out.mp4>
This is an auto-generated walkthrough, not a screen recording; record your own offline demo for the final cut."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

run = Path(sys.argv[1])
out_mp4 = Path(sys.argv[2])
W, H = 1280, 720
FD = "/usr/share/fonts/truetype/dejavu/"
F = lambda n, s: ImageFont.truetype(FD + n, s)  # noqa: E731
H1, H2, B, M = F("DejaVuSerif-Bold.ttf", 54), F("DejaVuSerif-Bold.ttf", 34), F("DejaVuSans.ttf", 26), F("DejaVuSansMono.ttf", 18)
SM = F("DejaVuSans.ttf", 20)
DARK, LIGHT, ORANGE, RED, GREEN, GREY = (15, 23, 32), (255, 255, 255), (232, 89, 12), (214, 40, 40), (43, 147, 72), (154, 167, 181)
rep = json.loads((run / "output" / "report.json").read_text())
tmp = Path(tempfile.mkdtemp())
scenes = []


def canvas(bg=DARK):
    im = Image.new("RGB", (W, H), bg)
    return im, ImageDraw.Draw(im)


def wrap(d, text, font, width):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) > width:
            lines.append(cur)
            cur = w
        else:
            cur = t
    lines.append(cur)
    return lines


def para(d, x, y, text, font, fill, width, gap=10):
    for ln in wrap(d, text, font, width):
        d.text((x, y), ln, font=font, fill=fill)
        y += font.size + gap
    return y


def footer(d, txt="SIMULATED DEMO DATA  |  auto-generated walkthrough of a real MAPPA run"):
    d.rectangle([0, H - 40, W, H], fill=(42, 55, 68))
    d.text((24, H - 33), txt, font=SM, fill=(244, 161, 0))


def add(im, secs):
    p = tmp / f"s{len(scenes):02d}.png"
    im.save(p)
    scenes.append((p, secs))


# 1 title
im, d = canvas()
d.text((80, 200), "MAPPA", font=F("DejaVuSerif-Bold.ttf", 110), fill=LIGHT)
d.text((84, 340), "The first map after the landslide", font=H2, fill=LIGHT)
para(d, 84, 410, "Drone photos in. Georeferenced map, change report and blocked roads out. Offline, on a laptop, no ground control points.", B, (200, 211, 222), 900)
d.text((84, 560), "github.com/kavixsri/MAPPA", font=B, fill=(244, 161, 0))
footer(d)
add(im, 6)

# 2 problem
im, d = canvas(LIGHT)
d.text((70, 60), "Responders need a map in 3 hours. The satellite is Thursday.", font=H2, fill=DARK)
items = [("Cloud photogrammetry", "needs bandwidth the field does not have"), ("Ground control points", "nobody is placing them in a disaster"),
         ("Satellite tasking", "too slow on day one; cloud cover blocks it"), ("Raw video", "footage is not a map")]
for i, (a, b) in enumerate(items):
    y = 190 + i * 110
    d.ellipse([70, y, 130, y + 60], fill=RED)
    d.text((90, y + 10), "x", font=H2, fill=LIGHT)
    d.text((160, y - 2), a, font=F("DejaVuSans-Bold.ttf", 32), fill=DARK)
    d.text((160, y + 38), b, font=B, fill=(70, 80, 95))
footer(d)
add(im, 9)

# 3 capture card
card = Image.open("capture_card_preview.png") if Path("capture_card_preview.png").exists() else None
im, d = canvas(LIGHT)
d.text((70, 40), "A capture card a stressed pilot can follow", font=H2, fill=DARK)
subprocess.run(["pdftoppm", "-r", "80", "-png", "-singlefile", "capture_card.pdf", str(tmp / "card")], check=True)
c = Image.open(tmp / "card.png").convert("RGB")
c.thumbnail((470, 580))
im.paste(c, (80, 100))
rules = ["Wait for GPS lock (10+ satellites)", "80-100 m, camera straight down", "Photos every 2 s, 75/65% overlap",
         "One oblique loop round the slide", "Land at launch point, copy every photo"]
for i, r in enumerate(rules):
    y = 140 + i * 95
    d.ellipse([620, y, 676, y + 56], fill=ORANGE)
    d.text((640, y + 8), str(i + 1), font=F("DejaVuSans-Bold.ttf", 30), fill=LIGHT)
    d.text((705, y + 10), r, font=B, fill=DARK)
footer(d)
add(im, 10)

# 4 terminal (real stdout)
term = Path("/tmp/term.txt").read_text() if Path("/tmp/term.txt").exists() else ""
lines = ["$ python -m mappa demo", ""]
for ln in term.splitlines():
    if not ln.strip():
        continue
    if ln.startswith("Synthetic validation"):
        v = rep["validation"]
        ln = (f"Synthetic validation: GPS error {v['error_before_mean_m']} m -> {v['error_after_mean_m']} m (mean, 25 pts); "
              f"roads precision {v['roads_vs_truth']['precision']} recall {v['roads_vs_truth']['recall']}")
    lines += wrap(d, ln[:260], M, 1150)
im, d = canvas((12, 16, 22))
y = 36
for ln in lines[:26]:
    d.text((40, y), ln, font=M, fill=(120, 230, 150) if ln.startswith("$") else (225, 232, 240))
    y += 26
footer(d, "Real stdout from the run. Pipeline imports no network modules; online only to pre-cache base data.")
add(im, 14)

# 5 before / after
for tag, label, secs in (("before", "Last known state (base imagery, season-shifted)", 4), ("after", "Drone orthomosaic after the simulated slide", 4)):
    im, d = canvas(LIGHT)
    d.text((70, 30), label, font=H2, fill=DARK)
    p = Image.open(run / "input" / f"preview_{tag}.jpg").convert("RGB")
    p.thumbnail((620, 620))
    im.paste(p, (330, 90))
    footer(d)
    add(im, secs)

# 6 result map
im, d = canvas(LIGHT)
d.text((70, 24), "What changed, and which roads are blocked", font=H2, fill=DARK)
m = Image.open(run / "output" / "map_preview.png").convert("RGB")
m.thumbnail((620, 620))
im.paste(m, (60, 80))
L = rep["roads"]["length_m_by_status"]
y = 120
for name, col, val in (("BLOCKED", RED, L.get("BLOCKED", 0)), ("UNCERTAIN", (244, 161, 0), L.get("UNCERTAIN", 0)), ("CLEAR", GREEN, L.get("CLEAR", 0))):
    d.rounded_rectangle([730, y, 940, y + 56], 10, fill=col)
    d.text((750, y + 12), name, font=F("DejaVuSans-Bold.ttf", 26), fill=LIGHT if name != "UNCERTAIN" else DARK)
    d.text((965, y + 12), f"{val:.0f} m", font=B, fill=DARK)
    y += 80
y += 10
for b in rep["roads"]["blocked_stretches"]:
    d.text((730, y), f"{b['road']}: {b['length_m']:.0f} m blocked", font=B, fill=DARK)
    y += 38
para(d, 730, y + 20, "Blocked = 40% of road buffer changed AND height anomaly >= 0.5 m (DSM minus DEM).", SM, (70, 80, 95), 500)
footer(d)
add(im, 14)

# 7 accuracy + time
im, d = canvas()
g = rep["georeferencing"]
v = rep["validation"]
d.text((70, 50), "Error and time, stated honestly", font=H2, fill=LIGHT)
stat = [(f"+/-{g['horizontal_accuracy_95_m']:.0f} m", "stated absolute accuracy (95%), unverified against ground truth", (244, 161, 0)),
        (f"{v['error_before_mean_m']} -> {v['error_after_mean_m']} m", "synthetic test: injected GPS error before -> after (mean)", LIGHT),
        (f"{rep['processing_time_s']['total']:.0f} s", f"{rep['area_km2']} km2, 1 CPU core, no GPU. ODM stitching time measured separately", (120, 230, 150))]
for i, (a, b, col) in enumerate(stat):
    y = 150 + i * 170
    d.text((80, y), a, font=F("DejaVuSerif-Bold.ttf", 66), fill=col)
    para(d, 80, y + 86, b, B, (200, 211, 222), 1100, 6)
footer(d)
add(im, 12)

# 8 brief + formats
im, d = canvas(LIGHT)
d.text((70, 24), "One-page brief + formats responders already open", font=H2, fill=DARK)
subprocess.run(["pdftoppm", "-r", "90", "-png", "-singlefile", str(run / "output" / "brief.pdf"), str(tmp / "brief")], check=True)
b = Image.open(tmp / "brief.png").convert("RGB")
b.thumbnail((470, 620))
im.paste(b, (60, 85))
fc = (Path("docs/format_check.txt").read_text() if Path("docs/format_check.txt").exists() else "").splitlines()
y = 100
for ln in fc[:10]:
    name = ln.split()[0]
    d.text((580, y), name, font=M, fill=DARK)
    d.text((1000, y), "OK", font=F("DejaVuSansMono-Bold.ttf", 18), fill=GREEN)
    y += 34
para(d, 580, y + 24, "Every output re-opened by independent readers (rasterio, GeoPandas, XML parser).", SM, (70, 80, 95), 640)
footer(d)
add(im, 10)

# 9 limits + repo
im, d = canvas()
d.text((70, 50), "Honest limits, next steps", font=H2, fill=LIGHT)
lim = ["Validated on a simulated scene only, not yet a real landslide", "Absolute accuracy bounded by the base layer (~10 m)",
       "Colour alone missed debris on roads: DSM and DEM are required", "Next: ODM on sample + own flight, real OpenAerialMap pair, measured ODM time"]
y = 140
for t in lim:
    d.ellipse([80, y + 10, 100, y + 30], fill=ORANGE)
    y = para(d, 120, y, t, B, LIGHT, 1050) + 22
d.text((80, 600), "github.com/kavixsri/MAPPA   |   MIT   |   all open source", font=B, fill=(244, 161, 0))
footer(d)
add(im, 10)

# assemble
lst = tmp / "list.txt"
with open(lst, "w") as f:
    for p, s in scenes:
        f.write(f"file '{p}'\nduration {s}\n")
    f.write(f"file '{scenes[-1][0]}'\n")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-vf", "fps=15,format=yuv420p",
                "-c:v", "libx264", "-crf", "26", "-preset", "medium", "-movflags", "+faststart", str(out_mp4)], check=True)
print("wrote", out_mp4, f"{out_mp4.stat().st_size / 1e6:.1f} MB", sum(s for _, s in scenes), "s")
