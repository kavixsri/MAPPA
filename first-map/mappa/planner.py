"""Pilot-side tools: flight-plan arithmetic + lawnmower KML path + the one-page 'capture card' PDF."""
from __future__ import annotations

import math

import simplekml
from pyproj import Transformer
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

# Example camera: 1/1.3" class sensor, 24 mm-equivalent lens, 12 MP. CHECK YOUR OWN DRONE'S SPEC.
CAM = dict(sensor_w_mm=9.6, sensor_h_mm=7.2, focal_mm=6.7, img_w=4000, img_h=3000)


def plan(width_m: float, height_m: float, alt_m: float = 90, fwd: float = 0.75, side: float = 0.65,
         interval_s: float = 2.0, cam: dict | None = None) -> dict:
    c = {**CAM, **(cam or {})}
    across = alt_m * c["sensor_w_mm"] / c["focal_mm"]
    along = alt_m * c["sensor_h_mm"] / c["focal_mm"]
    line_sp = across * (1 - side)
    photo_sp = along * (1 - fwd)
    speed = photo_sp / interval_s
    lines = math.ceil(height_m / line_sp) + 1
    imgs = lines * (math.ceil(width_m / photo_sp) + 1)
    return dict(altitude_m=alt_m, gsd_cm_px=round(100 * alt_m * c["sensor_w_mm"] / (c["focal_mm"] * c["img_w"]), 2),
                footprint_m=(round(across), round(along)), line_spacing_m=round(line_sp, 1),
                photo_spacing_m=round(photo_sp, 1), max_speed_ms=round(speed, 1), n_lines=lines, n_images=imgs,
                flight_time_min=round((lines * width_m / speed) / 60 * 1.15, 1))


def write_mission_kml(lat: float, lon: float, width_m: float, height_m: float, path: str, alt_m: float = 90, **kw):
    p = plan(width_m, height_m, alt_m, **kw)
    zone = int((lon + 180) // 6) + 1
    epsg = (32600 if lat >= 0 else 32700) + zone
    fwd, back = Transformer.from_crs(4326, epsg, always_xy=True), Transformer.from_crs(epsg, 4326, always_xy=True)
    e0, n0 = fwd.transform(lon, lat)
    kml = simplekml.Kml(name="MAPPA lawnmower grid")
    coords = []
    for i in range(p["n_lines"]):
        y = n0 - height_m / 2 + min(i * p["line_spacing_m"], height_m)
        xs = (e0 - width_m / 2, e0 + width_m / 2)
        xs = xs if i % 2 == 0 else xs[::-1]
        for x in xs:
            lo, la = back.transform(x, y)
            coords.append((lo, la, alt_m))
    ls = kml.newlinestring(name=f"Survey path {alt_m:g} m AGL", coords=coords)
    ls.altitudemode = simplekml.AltitudeMode.relativetoground
    ls.extrude = 0
    ls.style.linestyle.color = "ff00ffff"
    ls.style.linestyle.width = 3
    kml.save(path)
    return p


def capture_card(path: str, example: dict | None = None):
    c = canvas.Canvas(path, pagesize=A4)
    W, H = A4
    c.setFillColor(colors.HexColor("#111111"))
    c.rect(0, H - 34 * mm, W, 34 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 26)
    c.drawString(15 * mm, H - 18 * mm, "MAPPA  |  30-SECOND CAPTURE CARD")
    c.setFont("Helvetica", 11)
    c.drawString(15 * mm, H - 27 * mm, "Landslide / flood survey. Read it once. Do these 5 things, in this order.")
    rules = [
        ("1", "WAIT FOR GPS", "10+ satellites and 'Home point recorded'. Take off from open ground. No GPS lock = no flight."),
        ("2", "FLY HIGH, LOOK DOWN", "80-100 m above the launch point. Camera straight down (-90 deg). Fly the pre-loaded grid. Press START."),
        ("3", "PHOTOS, NOT VIDEO", "Interval mode, every 2 s, JPEG with GPS. Slow and steady: 75% forward / 65% side overlap is the whole game."),
        ("4", "ONE EXTRA LOOP", "Camera tilted 45 deg, one slow circle around the slide's toe (bottom) and head (top), above the debris."),
        ("5", "LAND WHERE YOU STARTED", "Land at the launch point. Photograph the drone screen: battery + GPS log. Copy ALL photos to the laptop."),
    ]
    y = H - 50 * mm
    for n, head, body in rules:
        c.setFillColor(colors.HexColor("#e63946"))
        c.circle(23 * mm, y + 5 * mm, 9 * mm, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 26)
        c.drawCentredString(23 * mm, y + 1.5 * mm, n)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 17)
        c.drawString(38 * mm, y + 7 * mm, head)
        c.setFont("Helvetica", 10.5)
        words, line, ly = body.split(), "", y + 0.5 * mm
        for w in words:
            if c.stringWidth(line + " " + w, "Helvetica", 10.5) > W - 55 * mm:
                c.drawString(38 * mm, ly, line.strip())
                line, ly = w, ly - 5 * mm
            else:
                line += " " + w
        c.drawString(38 * mm, ly, line.strip())
        y -= 28 * mm
    c.setFillColor(colors.HexColor("#f1f1f1"))
    c.rect(12 * mm, 14 * mm, W - 24 * mm, 36 * mm, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(16 * mm, 44 * mm, "IF SOMETHING GOES WRONG")
    c.setFont("Helvetica", 9.5)
    for i, t in enumerate(["Wind strong / rain / low light: do not fly. Safety first, no map is worth a crash.",
                           "Battery < 30%: land now, swap battery, resume from the last line (overlap those 2 lines).",
                           "Lost GPS mid-flight: hover, then land manually. Note the time on your phone.",
                           "Only fly where permitted (India: check Digital Sky zones; get disaster-authority clearance)."]):
        c.drawString(16 * mm, 38 * mm - i * 5.5 * mm, "-  " + t)
    if example:
        c.setFont("Helvetica-Oblique", 8)
        c.setFillColor(colors.HexColor("#555555"))
        c.drawString(15 * mm, 9 * mm, f"Example plan for 600 x 500 m: {example['n_images']} photos, {example['gsd_cm_px']} cm/px, "
                                      f"max {example['max_speed_ms']} m/s, ~{example['flight_time_min']} min. "
                                      f"Numbers assume a 1/1.3\" 12 MP camera; check your drone.")
    c.save()
