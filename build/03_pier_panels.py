#!/usr/bin/env python3
"""
Step 3: the three pier panels (Cap-Haitien wharf, 2026-02-26), from the L2A dock-zone band crops.

  img/pier_rgb.png    true colour
  img/pier_freq.png   share of the OTHER clear passes on which each pixel was water (NDWI > 0)
  img/pier_flip.png   pixels in the dock zone that are usually water (>= 60%) but not water today,
                      i.e. the water-flip detector's candidates (same rule as
                      sar_pipeline/detect_docked_ships_optical.py)
The pier filter's decision on each candidate (kept / removed, p) goes to build/work/meta.json.
"""
import glob
import json

import numpy as np
import pandas as pd
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.features import rasterize
from shapely.geometry import shape
from shapely.ops import transform as shp_transform

from common import HAITI_GW, IMG, OML, load_meta, save_meta

SITE, TARGET, DATE = "cap_haitien_port", "S2C_18QYG_20260226_0_L2A", "2026-02-26"
CLOUD_SCL = {0, 1, 3, 8, 9, 10}   # no-data, saturated, cloud shadow, cloud med/high, cirrus
SCALE = 8


def save(a, name):
    Image.fromarray((a * 255).astype(np.uint8)).resize((a.shape[1] * SCALE, a.shape[0] * SCALE), Image.NEAREST) \
        .save(IMG / name, optimize=True)


def main():
    files = sorted(glob.glob(str(OML / "daily5y" / "s2_bands" / SITE / "*.tif")))
    water, valid = [], []
    for f in files:   # bands: blue, green, red, nir, swir16, swir22, scl
        with rasterio.open(f) as s:
            d = s.read(); T = s.transform; crs = s.crs
        g, n = d[1], d[3]
        ndwi = np.where(g + n > 0, (g - n) / np.maximum(g + n, 1e-6), -1)
        water.append(ndwi > 0); valid.append(~np.isin(d[6], list(CLOUD_SCL)))
        if TARGET in f:
            D = d
    idx = next(i for i, f in enumerate(files) if TARGET in f)
    W, V = np.array(water), np.array(valid)
    other = np.ones(len(files), bool); other[idx] = False
    freq = (W[other] & V[other]).sum(0) / np.maximum(V[other].sum(0), 1)

    rgb = np.stack([D[2], D[1], D[0]], -1).astype(float)
    lo, hi = np.percentile(rgb, 1, axis=(0, 1)), np.percentile(rgb, 99.5, axis=(0, 1))
    rgb = np.clip((rgb - lo) / (hi - lo), 0, 1) ** 0.9
    save(rgb, "pier_rgb.png")
    c0, c1 = np.array([0.10, 0.11, 0.13]), np.array([0.36, 0.62, 0.95])
    save(c0 + (c1 - c0) * freq[..., None], "pier_freq.png")

    gj = json.loads((HAITI_GW / "sar_pipeline" / "sar_bounds" / f"{SITE}_dock_zone.geojson").read_text())
    tf = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    dock = rasterize([shp_transform(tf.transform, shape(f["geometry"])) for f in gj["features"]],
                     out_shape=freq.shape, transform=T).astype(bool)
    flip = (freq >= 0.6) & ~W[idx] & V[idx] & dock
    ov = rgb * 0.45
    ov[flip] = np.array([0.106, 0.686, 0.478])   # #1baf7a, the "at the pier" colour used on both pages
    save(ov, "pier_flip.png")

    sc = pd.read_csv(OML / "dock_filter" / "detections_scored.csv")
    boxes = []
    for r in sc[sc.item_id == TARGET].itertuples():
        c, rr = ~T * tf.transform(r.lon, r.lat)
        boxes.append(dict(x=round(c / rgb.shape[1], 4), y=round(rr / rgb.shape[0], 4), p=round(r.p_vessel, 2),
                          kept=bool(r.kept)))
    meta = load_meta()
    meta["pier"] = dict(w=rgb.shape[1] * SCALE, h=rgb.shape[0] * SCALE, m=[rgb.shape[1] * 10, rgb.shape[0] * 10],
                        boxes=boxes, n_dates=int(other.sum()), date=DATE)
    save_meta(meta)
    print(meta["pier"])


if __name__ == "__main__":
    main()
