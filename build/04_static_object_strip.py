#!/usr/bin/env python3
"""
Step 4: "The ship that never moved" strip: the masked fixed object off Port-au-Prince
(optical_ml/static_mask/static_mask.geojson) on one clear day per year.

Picks, for each Oct-Sep year 2021-22 .. 2025-26, the clearest December-March day on which the
object was detected. Days with two satellite passes are skipped: the chip, the per-pass
detection file and the size estimates could otherwise come from different passes.

  img/wreck_<date>.png   500 x 500 m, native 10 m pixels
Also records where the object sits in the hero / before-after crop (build/work/meta.json).
"""
import glob
import json

import numpy as np
import pandas as pd
import rasterio
from PIL import Image
from pyproj import Transformer

from common import IMG, OML, PAPBOX, load_meta, save_meta

SITE, R = "port_au_prince_main", 25


def main():
    f = json.loads((OML / "static_mask" / "static_mask.geojson").read_text())["features"][0]
    lon0, lat0 = f["geometry"]["coordinates"]
    to_m = Transformer.from_crs("EPSG:4326", "EPSG:32618", always_xy=True)
    mx, my = to_m.transform(lon0, lat0)
    D = pd.read_csv(OML / "vessel_size" / "detections_size.csv")
    D = D[D.counted_filtered & (D.site == SITE)]
    x, y = to_m.transform(D.lon.values, D.lat.values)
    D = D[np.hypot(x - mx, y - my) <= f["properties"]["radius_m"]]

    daily = pd.read_csv(OML / "exports" / "haiti_ports_vessel_counts_daily.csv")
    daily = daily[daily.site_id == SITE]
    single = set(daily[daily.n_passes == 1].date)
    clear = dict(zip(daily.date, daily.clear_fraction))
    dates = [d for d in sorted(D.date.unique()) if d in single]
    pick = []
    for y0 in range(2021, 2026):
        c = [d for d in dates if f"{y0}-10-01" <= d < f"{y0 + 1}-10-01" and d[5:7] in ("12", "01", "02", "03")]
        pick.append(sorted(c, key=lambda d: -clear.get(d, 0))[0])

    tiles = []
    for d in pick:
        chip = glob.glob(str(OML / "daily5y" / "chips" / SITE / f"{SITE}_{d}_*.tif"))[0]
        with rasterio.open(chip) as s:
            a = s.read([1, 2, 3]).astype(float); T = s.transform
            off = 1000 if int(s.tags().get("processing_baseline", 400)) >= 400 else 0
        c, r = ~T * to_m.transform(lon0, lat0)
        c, r = int(round(c)), int(round(r))
        sub = a[:, r - R:r + R, c - R:c + R] - off
        lo = np.percentile(sub.reshape(3, -1), 1, axis=1)[:, None, None] * 0.7
        im = (np.clip((sub - lo) / 1900, 0, 1) ** 0.9 * 255).astype(np.uint8).transpose(1, 2, 0)
        Image.fromarray(im).resize((2 * R * 8, 2 * R * 8), Image.NEAREST).save(IMG / f"wreck_{d}.png", optimize=True)
        row = D[D.date == d].iloc[0]
        tiles.append(dict(date=d, file=f"img/wreck_{d}.png", len=int(round(row.length_m)), type=row.type))

    meta = load_meta()
    meta["wreck"] = dict(tiles=tiles, m=2 * R * 10)
    # position in the PAPBOX crop of the hero chip (same grid as before.jpg)
    chip = glob.glob(str(OML / "daily5y" / "chips" / SITE / f"{SITE}_2026-05-02_*.tif"))[0]
    with rasterio.open(chip) as s:
        T = s.transform
    c0, r0 = ~T * to_m.transform(PAPBOX[0], PAPBOX[3])
    c1, r1 = ~T * to_m.transform(PAPBOX[2], PAPBOX[1])
    c, r = ~T * to_m.transform(lon0, lat0)
    meta["wreck_in_crop"] = dict(x=round((c - round(c0)) / (round(c1) - round(c0)), 4),
                                 y=round((r - round(r0)) / (round(r1) - round(r0)), 4))
    save_meta(meta)
    print(pick)


if __name__ == "__main__":
    main()
