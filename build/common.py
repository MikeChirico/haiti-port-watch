"""Shared paths for the build scripts.

HAITI_GW points at the analysis project (default ~/Desktop/Haiti_gw). Rendered images go to
img/ and intermediate files (the national mosaic array, meta.json) to build/work/, which is
not committed.
"""
import json
import math
import os
from pathlib import Path

from pyproj import Transformer

REPO = Path(__file__).resolve().parent.parent
HAITI_GW = Path(os.environ.get("HAITI_GW", Path.home() / "Desktop" / "Haiti_gw"))
OML = HAITI_GW / "optical_ml"
IMG = REPO / "img"
WORK = REPO / "build" / "work"
DATA = REPO / "data" / "story_data.json"
META = WORK / "meta.json"
IMG.mkdir(exist_ok=True)
WORK.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")

# manual review of every story example date (Haiti_gw/review_app/make_story_review.py)
REVIEW = HAITI_GW / "review_projects" / "story_map_check" / "review_data"

# Port-au-Prince bay view used by the hero image and the before/after slider
PAPBOX = (-72.405, 18.535, -72.335, 18.585)

_TO_M = Transformer.from_crs("EPSG:4326", "EPSG:32618", always_xy=True)
_MASK = [(f["properties"]["site"], *_TO_M.transform(*f["geometry"]["coordinates"]), f["properties"]["radius_m"])
         for f in json.loads((OML / "static_mask" / "static_mask.geojson").read_text())["features"]]


def is_masked(site, lon, lat):
    """Inside the static-location mask, applied exactly as optical_ml/export_counts.py does."""
    x, y = _TO_M.transform(lon, lat)
    return any(site == s and math.hypot(x - mx, y - my) <= r for s, mx, my, r in _MASK)


def load_meta():
    return json.loads(META.read_text()) if META.exists() else {}


def save_meta(meta):
    META.write_text(json.dumps(meta, indent=1))


def tci_href(item_id):
    """Sentinel-2 L2A true-colour COG on Element 84's public bucket."""
    _, tile, ymd = item_id.split("_")[:3]
    return (f"https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/{tile[:2]}/{tile[2]}/"
            f"{tile[3:]}/{ymd[:4]}/{int(ymd[4:6])}/{item_id}/TCI.tif")
