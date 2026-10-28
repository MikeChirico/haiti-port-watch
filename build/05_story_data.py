#!/usr/bin/env python3
"""
Step 5: data/story_data.json, everything the page's charts and map read.

  pts    every counted vessel sighting (pier filter + static mask applied, as in the exports):
         [lat, lon, days since 2021-10-01, site index, 0 open water / 1 pier, length m, type index]
  mon    monthly rows from optical_ml/exports/haiti_ports_vessel_counts_monthly.csv
  obs    observed (clear, counted) days per port, for "per clear pass" on the map
  val    56 reviewed passes: [site, date, pipeline count, reviewer count], computed exactly as
         optical_ml/make_readme_images.py fig6 (held-out pier-filter scores, static mask)
  mask   the static-location mask and how much it removed
  latest each port's most recent counted day, for "latest clear look": export counts, plus the
         reviewed count once that date's manual review is complete (the pages show that one)
  meta   crop geometry and boxes from steps 1-4 (build/work/meta.json)
Also copies the two exported CSVs to data/, where the dashboard offers them for download.
"""
import csv
import datetime as dt
import glob
import json

import shutil

import joblib
import numpy as np
import pandas as pd

from common import DATA, OML, REVIEW, is_masked, load_meta

SITES = ["port_au_prince_main", "cap_haitien_port", "port_lafito"]
TYPES = ["cargo", "tanker", "service", "passenger", "fishing", "pleasure", "enforcement", "sar"]
D0 = dt.date(2021, 10, 1)


def reviewed_count(site, date):
    """Vessels on one date after the manual review (confirmed detections + added boxes), or None
    if that date's scene check isn't finished. Same rule as the example images in step 2."""
    state = json.loads((REVIEW / "review_state.json").read_text())
    recs = [(k, v) for k, v in state.items() if v.get("site") == site and v.get("date") == date]
    if not any(k.endswith("|scene") and v.get("status") in ("valid", "invalid") for k, v in recs):
        return None
    added = json.loads((REVIEW / "manual_additions.geojson").read_text())["features"]
    return (sum(1 for k, v in recs if not k.endswith("|scene") and v.get("status") == "valid")
            + sum(1 for f in added if f["properties"].get("site") == site and f["properties"].get("date") == date))


def nan(v):
    return None if pd.isna(v) else v


def main():
    sz = pd.read_csv(OML / "vessel_size" / "detections_size.csv")
    sz = sz[sz.counted_filtered].copy()
    sz["masked"] = [is_masked(s, lo, la) for s, lo, la in zip(sz.site, sz.lon, sz.lat)]
    masked, sz = sz[sz.masked], sz[~sz.masked]
    mf = json.loads((OML / "static_mask" / "static_mask.geojson").read_text())["features"]
    mask = dict(n=int(len(masked)), dates=int(masked.date.nunique()), first=masked.date.min(), last=masked.date.max(),
                median_len=int(round(masked.length_m.median())),
                spots=[dict(lat=f["geometry"]["coordinates"][1], lon=f["geometry"]["coordinates"][0],
                            **f["properties"]) for f in mf])
    pts = [[round(r.lat, 5), round(r.lon, 5), (dt.date.fromisoformat(r.date) - D0).days, SITES.index(r.site),
            0 if r.source == "ai2" else 1, int(round(r.length_m)), TYPES.index(r.type)] for r in sz.itertuples()]

    M = pd.read_csv(OML / "exports" / "haiti_ports_vessel_counts_monthly.csv")
    # [month, clear days, mean, open water, pier, >=60 m, low confidence, cargo/tanker, SE, min, max]
    # (the story reads 0-6; the dashboard reads all of them)
    mon = {s: [[r.month, r.days_observed, nan(r.vessels_mean), nan(r.open_water_mean), nan(r.docked_mean),
                nan(r.ge60m_mean), str(r.low_confidence).upper() == "TRUE", nan(r.cargo_tanker_mean),
                nan(r.vessels_se), nan(r.vessels_min), nan(r.vessels_max)] for r in M[M.site_id == s].itertuples()]
           for s in SITES}
    daily = pd.read_csv(OML / "exports" / "haiti_ports_vessel_counts_daily.csv")
    obs = [[SITES.index(r.site_id), (dt.date.fromisoformat(r.date) - D0).days]
           for r in daily[daily.status == "observed"].itertuples()]
    # each port's most recent counted day ("latest clear look"; queued for review by make_story_review.py)
    latest = {}
    for s in SITES:
        r = daily[(daily.site_id == s) & (daily.status == "observed")].sort_values("date").iloc[-1]
        latest[s] = dict(date=r.date, vessels=float(r.vessels), ge60m=float(r.vessels_ge60m),
                         cargo=float(r.vessels_cargo_tanker), reviewed=reviewed_count(s, r.date))
    export_end = daily.date.max()

    review = json.loads((OML / "timeseries" / "review_sample" / "score.json").read_text())["per_pass"]
    passes = {(r["site"], r["date"]) for r in csv.DictReader(open(OML / "daily5y" / "pass_counts.csv"))}
    oof = pd.read_csv(OML / "dock_filter" / "oof.csv")
    thr = joblib.load(OML / "dock_filter" / "model.joblib")["thresholds"]["keep90"]
    open_dets = {}
    for f in glob.glob(str(OML / "daily5y" / "pass_detections" / "*" / "*.geojson")):
        fc = json.loads(open(f).read())
        open_dets[(fc["site"], fc["date"])] = [ft["geometry"]["coordinates"] for ft in fc["features"]
                                               if ft["properties"]["source"] == "ai2"]
    val = []
    for p in review:
        if p["scene"] != "valid" or (p["site"], p["date"]) not in passes:
            continue
        d = oof[(oof.site == p["site"]) & (oof.date == p["date"])]
        n_open = sum(not is_masked(p["site"], lo, la) for lo, la in open_dets.get((p["site"], p["date"]), []))
        n_dock = sum(pv >= thr and not is_masked(p["site"], lo, la) for pv, lo, la in zip(d.p_oof, d.lon, d.lat))
        val.append([SITES.index(p["site"]), p["date"], n_open + n_dock, p["truth"]])
    v = np.array([[a[2], a[3]] for a in val])
    print(f"validation: {len(val)} passes, pipeline {v[:, 0].sum()} vs reviewer {v[:, 1].sum()}, "
          f"r = {np.corrcoef(v.T)[0, 1]:.3f}; {len(pts)} sightings; {mask['n']} masked")

    DATA.parent.mkdir(exist_ok=True)
    for name in ("haiti_ports_vessel_counts_daily.csv", "haiti_ports_vessel_counts_monthly.csv"):
        shutil.copy2(OML / "exports" / name, DATA.parent / name)
    DATA.write_text(json.dumps(dict(pts=pts, types=TYPES, sites=SITES, mon=mon, obs=obs, val=val, mask=mask, latest=latest, export_end=export_end,
                                    meta=load_meta(), d0=str(D0)), separators=(",", ":")))


if __name__ == "__main__":
    main()
