#!/usr/bin/env python3
"""
Step 1: dark-map background of Haiti (img/national.jpg), a Sentinel-2 true-colour mosaic at
200 m in Web Mercator (EPSG:3857), so it lines up exactly with a Leaflet image overlay.

Source: Element 84 Earth Search (no account needed), Nov 2025 - Apr 2026.
  1. For each MGRS tile, paint its 3 least-cloudy items (cloud < 15%), best last.
  2. Fill remaining holes with each tile's least-cloudy FULL-swath item (no-data < 5%).
  3. Tiles 18QYF / 18QYE (Port-au-Prince) only have partial swaths among their clearest items,
     which left a hole over the capital; fill it from named full-swath items.
Reads COG overviews (1/16 resolution), so it downloads little. Takes a few minutes.
Rebuilding may not match the published image pixel for pixel (catalogue contents change).
"""
import numpy as np
import rasterio
from PIL import Image
from pystac_client import Client
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject, transform_bounds

from common import IMG, WORK, load_meta, save_meta

LON0, LAT0, LON1, LAT1 = -74.55, 17.9, -71.55, 20.15
CROP_LAT = 18.02   # the southern strip has a grey cloud-filled patch at sea; crop it off
RES = 200
PAP_FILL = ["S2B_18QYF_20260211_0_L2A", "S2C_18QYF_20260318_0_L2A", "S2C_18QYE_20260417_0_L2A",
            "S2B_18QYE_20260412_0_L2A"]


def grid():
    x0, y0, x1, y1 = transform_bounds("EPSG:4326", "EPSG:3857", LON0, LAT0, LON1, LAT1)
    w, h = int(round((x1 - x0) / RES)), int(round((y1 - y0) / RES))
    return from_bounds(x0, y0, x1, y1, w, h), w, h


def paint(hrefs, T, w, h, dec=16):
    dst = np.zeros((3, h, w), np.uint8)
    for href in hrefs:   # worst first, best last
        with rasterio.open(href) as s:
            oh, ow = s.height // dec, s.width // dec
            a = s.read(out_shape=(3, oh, ow))   # default (nearest) read: average resampling zeroed partial swaths
            st = s.transform * s.transform.scale(s.width / ow, s.height / oh)
            tmp = np.zeros((3, h, w), np.uint8)
            reproject(a, tmp, src_transform=st, src_crs=s.crs, dst_transform=T, dst_crs="EPSG:3857",
                      resampling=Resampling.bilinear, src_nodata=0, dst_nodata=0)
        m = tmp.sum(0) > 0
        dst[:, m] = tmp[:, m]
        print("painted", href.split("/")[-2], flush=True)
    return dst


def by_tile(items):
    out = {}
    for it in items:
        out.setdefault(it.properties["grid:code"], []).append(it)
    for v in out.values():
        v.sort(key=lambda i: i.properties["eo:cloud_cover"])
    return out


def main():
    c = Client.open("https://earth-search.aws.element84.com/v1")
    T, w, h = grid()
    bbox = [LON0, LAT0, LON1, LAT1]
    tiles = by_tile(c.search(collections=["sentinel-2-l2a"], bbox=bbox, datetime="2025-11-01/2026-04-30",
                             query={"eo:cloud_cover": {"lt": 15}}, max_items=800).items())
    img = paint([i.assets["visual"].href for l in tiles.values() for i in l[:3][::-1]], T, w, h)

    full = by_tile(c.search(collections=["sentinel-2-l2a"], bbox=bbox, datetime="2025-10-01/2026-05-30",
                            query={"eo:cloud_cover": {"lt": 25}, "s2:nodata_pixel_percentage": {"lt": 5}},
                            max_items=800).items())
    fill = paint([l[0].assets["visual"].href for l in full.values()], T, w, h)
    m = img.sum(0) == 0
    img[:, m] = fill[:, m]

    fill = paint([i.assets["visual"].href for i in c.search(collections=["sentinel-2-l2a"], ids=PAP_FILL).items()],
                 T, w, h)
    m = (fill.sum(0) > 0) & (img.astype(int).sum(0) < 15)
    img[:, m] = fill[:, m]
    np.save(WORK / "national.npy", img)

    _, ycut, _, _ = transform_bounds("EPSG:4326", "EPSG:3857", LON0, CROP_LAT, LON1, CROP_LAT + 0.01)
    rows = int((T.f - ycut) / RES)
    Image.fromarray(img[:, :rows].transpose(1, 2, 0)).save(IMG / "national.jpg", quality=80, optimize=True,
                                                            progressive=True)
    meta = load_meta()
    meta["national"] = [[CROP_LAT, LON0], [LAT1, LON1]]
    save_meta(meta)
    print("wrote img/national.jpg")


if __name__ == "__main__":
    main()
