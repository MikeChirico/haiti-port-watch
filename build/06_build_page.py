#!/usr/bin/env python3
"""
Step 6: inline data/story_data.json into index.html and dashboard.html (the `const DATA = ...;`
line), so both pages render with no fetch and work when opened straight from disk.

The image strip in the "ship that never moved" section is written into the HTML too, from
meta.wreck, so its dates and captions always match the images built in step 4.
"""
import json
import re

from common import DATA, REPO


def main():
    page = REPO / "index.html"
    s = page.read_text()
    data = DATA.read_text()
    tiles = "".join(
        f'<figure><img src="{t["file"]}" alt="The fixed object off Port-au-Prince on {t["date"]}, unchanged in shape '
        f'and position." loading="lazy"><figcaption><b>{t["date"][:4]}</b>{t["date"][5:7]}/{t["date"][8:]} · read as '
        f'a {t["len"]} m {t["type"]} ship</figcaption></figure>' for t in json.loads(data)["meta"]["wreck"]["tiles"])
    s, n1 = re.subn(r'<div class="wreck">.*?</div>\n', lambda m: f'<div class="wreck">{tiles}</div>\n', s, count=1,
                    flags=re.S)
    s, n2 = re.subn(r"const DATA = .*?;\n</script>", lambda m: f"const DATA = {data};\n</script>", s, count=1,
                    flags=re.S)
    if (n1, n2) != (1, 1):
        raise SystemExit(f"index.html markers not found (wreck strip: {n1}, DATA: {n2})")
    page.write_text(s)
    print(f"index.html updated ({len(s) // 1024} KB)")

    dash = REPO / "dashboard.html"
    d, n = re.subn(r"const DATA = .*?;\n</script>", lambda m: f"const DATA = {data};\n</script>", dash.read_text(),
                   count=1, flags=re.S)
    if n != 1:
        raise SystemExit("dashboard.html DATA marker not found")
    dash.write_text(d)
    print(f"dashboard.html updated ({len(d) // 1024} KB)")


if __name__ == "__main__":
    main()
