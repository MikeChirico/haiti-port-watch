# Haiti Port Watch

A scrolling story for donors and stakeholders about counting cargo ships at Haiti's ports
from free satellite imagery. It covers why no other source works (Haiti has no usable ship-tracking
data), how the detectors were built and checked, and five years of results, and it ends with an
interactive heat map of every vessel sighting from October 2021 to October 2026.

The site is two static pages: the story (`index.html`) and a data dashboard (`dashboard.html`), plus
`img/` and `data/`. It needs no server or build step
to view. Open `index.html` in a browser, or see it live at
https://mikechirico.github.io/haiti-port-watch/.

## What's in the repository

| Path | Contents |
|---|---|
| `index.html` | The story. Styles, scripts and data are inline; it loads Leaflet 1.9.4 from cdnjs and fonts from Google Fonts |
| `dashboard.html` | Data dashboard: map, monthly chart and summary linked by port, vessel type and a draggable period, plus a sortable monthly table that downloads as CSV |
| `img/` | Sentinel-2 imagery rendered for the story (about 2.5 MB) |
| `data/story_data.json` | Vessel sightings, monthly counts, validation results and crop geometry. The same data is inlined in both pages |
| `data/haiti_ports_vessel_counts_*.csv` | The project's full daily and monthly export, offered for download on the dashboard. Column definitions are in the export README (`Haiti_gw/optical_ml/exports/README.md`, section 11) |
| `build/` | Scripts that regenerate `img/`, `data/` and the data in `index.html` from the analysis project |

## Where the numbers come from

All figures come from the analysis project's export of 22 October 2026
(`Haiti_gw/optical_ml/exports/`, documented in its `README.md`):

- daily and monthly vessel counts for Port-au-Prince, Cap-Haïtien and Port Lafito, from every
  clear Sentinel-2 pass between 1 Oct 2021 and 15 Oct 2026
- the open-water detector (Allen Institute for AI), the pier water-flip detector with its learned
  filter, and the static-location mask
- validation against a human review of 56 passes: 119 vessels counted vs 130 found by the reviewer
  (0.92×), correlation 0.95, precision 0.85, recall 0.78

When the export changes, rebuild (below) and update any numbers quoted in the text of
`index.html` to match the export README. The build scripts refresh the data, not the prose.

## Rebuilding

The scripts read the analysis project at `$HAITI_GW` (default `~/Desktop/Haiti_gw`) and run in its
`spatial` conda environment:

```
conda activate spatial
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:$LD_LIBRARY_PATH"
cd build
python 01_national_mosaic.py      # Haiti background mosaic, downloads COG overviews (a few minutes)
python 02_port_imagery.py         # port backgrounds, example crops, cloudy pass, review-tool crop
python 03_pier_panels.py          # the three pier water-flip panels
python 04_static_object_strip.py  # "the ship that never moved" strip
python 05_story_data.py           # data/story_data.json, and copies the two CSVs into data/
python 06_build_page.py           # inline the data into index.html and dashboard.html
```

Steps 2–6 reproduce the committed files exactly. Step 1 searches a live catalogue, so a rebuild may
differ slightly from the committed `img/national.jpg`. Intermediate files go to `build/work/`, which
is not committed. Imagery is read from public buckets (Element 84 Earth Search on AWS), and no account
is needed.

**Review rule:** every specific date used as an example in the story is queued for manual review in
the project's review app, so that nothing in the story rests on an unchecked count. When you add or
change an example date, add it to `STORY_DATES` in `Haiti_gw/review_app/make_story_review.py` and run
that script. Avoid days with two satellite passes as examples, because the image, the detections and
the size estimates can come from different passes.

## Credits

- Imagery: contains modified Copernicus Sentinel data 2021–2026 (ESA / European Commission),
  accessed through Google Cloud Public Datasets and Element 84 Earth Search on AWS Open Data.
- Open-water vessel detector and vessel size model: Allen Institute for AI,
  [rslearn_projects](https://github.com/allenai/rslearn_projects) (Apache-2.0).
- Map library: [Leaflet](https://leafletjs.com) 1.9.4 (BSD-2-Clause); its stylesheet is inlined in
  `index.html`.
- Pier detector, pier filter, static-location mask, cloud screening, review tool and all Haiti
  labels: this project.
