#!/usr/bin/env python3
"""
Step 2: port imagery for the story.

  img/map_pap.jpg, img/map_cap.jpg   ~10 m heat-map backgrounds (L2A true colour, Web Mercator),
                                     Port-au-Prince + Lafito 2026-01-07, Cap-Haitien 2026-01-12
  img/hero.jpg, img/before.jpg       Port-au-Prince bay 2026-05-02 / 2023-03-14 (L1C chips)
  img/cap_anchorage.jpg              Cap-Haitien anchorage 2023-10-10
  img/pixel.png                      the 175 m ship at native 10 m pixels
  img/cloudy.jpg                     rejected cloudy pass, Port-au-Prince 2022-04-18 (L2A true colour)
  img/review_tool.jpg                crop of optical_ml/exports/images/fig7_review_tool.png
Detection boxes for each crop go to build/work/meta.json. They start from the COUNTED set (pier
filter applied, static-location mask removed, as in the exports), then the manual review of that
date is applied: detections a reviewer marked Invalid are dropped, a corrected box moves the
detection to the corrected box's centre, and vessels the reviewer added are drawn too
(src "added", no length estimate). So the story's example images show reviewed vessels, and their
counts can differ from the exported CSVs for those days.

Every date used here must also be queued for manual review:
Haiti_gw/review_app/make_story_review.py (STORY_DATES).
"""
import glob

import numpy as np
import pandas as pd
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import from_bounds as win_from_bounds

import json

from common import IMG, OML, PAPBOX, REVIEW, is_masked, load_meta, save_meta, tci_href

SZ = pd.read_csv(OML / "vessel_size" / "detections_size.csv")
SZ = SZ[SZ.counted_filtered]
SZ = SZ[[not is_masked(s, lo, la) for s, lo, la in zip(SZ.site, SZ.lon, SZ.lat)]]


STATE = json.loads((REVIEW / "review_state.json").read_text())
ADDED = json.loads((REVIEW / "manual_additions.geojson").read_text())["features"]


def review_id(site, item_id, lon, lat):
    """Same id the review app uses (review_app/project.py detection_id)."""
    return f"{site}|optical|{item_id}|{round(lon, 4)}_{round(lat, 4)}"


def reviewed_vessels(site, date):
    """[(lon, lat, length_m or None, type or None, src)] for one date, after the manual review."""
    item_id = json.loads(next((OML / "daily5y" / "pass_detections" / site).glob(f"{site}_{date}_*.geojson"))
                         .read_text())["item_id"]
    out = []
    for r in SZ[(SZ.site == site) & (SZ.date == date)].itertuples():
        rec = STATE.get(review_id(site, item_id, r.lon, r.lat), {})
        if rec.get("status") == "invalid":
            continue
        lon, lat = r.lon, r.lat
        if rec.get("corrected_box"):
            ring = rec["corrected_box"]["coordinates"][0][:-1]
            lon, lat = sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)
        out.append((lon, lat, round(r.length_m), r.type, "open" if r.source == "ai2" else "dock"))
    for f in ADDED:
        p = f["properties"]
        if p.get("site") == site and p.get("item_id") == item_id:
            ring = f["geometry"]["coordinates"][0][:-1]
            out.append((sum(q[0] for q in ring) / len(ring), sum(q[1] for q in ring) / len(ring), None, None, "added"))
    return out


def jpg(a, name, q=84):
    Image.fromarray(a).save(IMG / name, quality=q, optimize=True, progressive=True)


def tci_mercator(item_id, lon0, lat0, lon1, lat1, res=10.5):
    X0, Y0, X1, Y1 = transform_bounds("EPSG:4326", "EPSG:3857", lon0, lat0, lon1, lat1)
    w, h = int((X1 - X0) / res), int((Y1 - Y0) / res)
    T = from_bounds(X0, Y0, X1, Y1, w, h)
    with rasterio.open(tci_href(item_id)) as s:
        win = win_from_bounds(*transform_bounds("EPSG:4326", s.crs, lon0 - .01, lat0 - .01, lon1 + .01, lat1 + .01),
                              s.transform)
        a = s.read(window=win)
        d = np.zeros((3, h, w), np.uint8)
        reproject(a, d, src_transform=s.window_transform(win), src_crs=s.crs, dst_transform=T, dst_crs="EPSG:3857",
                  resampling=Resampling.lanczos)
    return d.transpose(1, 2, 0)


def l1c(site, date):
    """RGB of a 9-band L1C chip, offset removed per processing baseline, light haze removal."""
    f = glob.glob(str(OML / "daily5y" / "chips" / site / f"{site}_{date}_*.tif"))[0]
    with rasterio.open(f) as s:
        a = s.read([1, 2, 3]).astype(float)
        off = 1000 if int(s.tags().get("processing_baseline", 400)) >= 400 else 0
        return a - off, s.transform, s.crs


def stretch(a, k=1900, gamma=0.9):
    lo = np.percentile(a.reshape(3, -1), 0.5, axis=1)[:, None, None] * 0.7
    return np.clip((a - lo) / k, 0, 1) ** gamma


def chip(site, date, box, name, scale=2):
    a, T, crs = l1c(site, date)
    rgb = (stretch(a) * 255).astype(np.uint8).transpose(1, 2, 0)
    tf = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    c0, r0 = ~T * tf.transform(box[0], box[3])
    c1, r1 = ~T * tf.transform(box[2], box[1])
    c0, r0, c1, r1 = [int(round(v)) for v in (c0, r0, c1, r1)]
    crop = rgb[max(r0, 0):r1, max(c0, 0):c1]
    im = Image.fromarray(crop).resize((crop.shape[1] * scale, crop.shape[0] * scale), Image.LANCZOS)
    im.save(IMG / name, quality=86, optimize=True, progressive=True)
    boxes = []
    for lon, lat, length, vtype, src in reviewed_vessels(site, date):
        c, rr = ~T * tf.transform(lon, lat)
        x, y = (c - c0) / (c1 - c0), (rr - r0) / (r1 - r0)
        if 0 <= x <= 1 and 0 <= y <= 1:
            boxes.append(dict(x=round(x, 4), y=round(y, 4), len=length, type=vtype, src=src))
    return dict(w=im.width, h=im.height, px_m=10 / scale, boxes=boxes, km=[(c1 - c0) / 100, (r1 - r0) / 100])


def pixel_zoom(site, date, length_m, R=15):
    rows = SZ[(SZ.site == site) & (SZ.date == date)]
    r = rows.iloc[(rows.length_m - length_m).abs().argmin()]
    a, T, crs = l1c(site, date)
    c, rr = ~T * Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(r.lon, r.lat)
    sub = stretch(a[:, int(rr) - R:int(rr) + R, int(c) - R:int(c) + R])
    Image.fromarray((sub * 255).astype(np.uint8).transpose(1, 2, 0)).resize((2 * R * 20, 2 * R * 20), Image.NEAREST) \
        .save(IMG / "pixel.png", optimize=True)
    return dict(len=round(r.length_m), px=2 * R, type=r.type)


def main():
    meta = load_meta()
    jpg(tci_mercator("S2C_18QYF_20260107_0_L2A", -72.47, 18.49, -72.27, 18.75), "map_pap.jpg", 80)
    jpg(tci_mercator("S2B_18QYG_20260112_0_L2A", -72.27, 19.70, -72.11, 19.81), "map_cap.jpg", 80)
    meta["map_pap"] = [[18.49, -72.47], [18.75, -72.27]]
    meta["map_cap"] = [[19.70, -72.27], [19.81, -72.11]]

    meta["hero"] = meta["after"] = chip("port_au_prince_main", "2026-05-02", PAPBOX, "hero.jpg")
    meta["before"] = chip("port_au_prince_main", "2023-03-14", PAPBOX, "before.jpg")
    meta["cap"] = chip("cap_haitien_port", "2023-10-10", (-72.205, 19.744, -72.170, 19.765), "cap_anchorage.jpg",
                       scale=3)
    meta["pixel"] = pixel_zoom("cap_haitien_port", "2023-10-10", 175)

    # rejected cloudy pass: no L1C chip exists for it, so crop the L2A true-colour image
    with rasterio.open(tci_href("S2A_18QYF_20220418_0_L2A")) as s:
        a = s.read(window=win_from_bounds(*transform_bounds("EPSG:4326", s.crs, *PAPBOX), s.transform))
    Image.fromarray(a.transpose(1, 2, 0)).resize((a.shape[2] * 2, a.shape[1] * 2), Image.LANCZOS) \
        .save(IMG / "cloudy.jpg", quality=82, optimize=True, progressive=True)

    Image.open(OML / "exports" / "images" / "fig7_review_tool.png").convert("RGB").crop((300, 0, 1140, 620)) \
        .save(IMG / "review_tool.jpg", quality=88, optimize=True)
    save_meta(meta)
    print({k: len(meta[k]["boxes"]) for k in ("hero", "before", "cap")}, meta["pixel"])


if __name__ == "__main__":
    main()
