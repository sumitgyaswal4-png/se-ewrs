"""Render the Mermaid diagrams in ``docs/er_diagram.md`` to PNG for the report.

    python docs/figures/render_diagrams.py

The full ER diagram cannot be read on an A4 page: sixteen entities with
every attribute come out at under two points. So besides the engagement
spine, this derives from the one source in er_diagram.md

* an overview — every entity and relationship, no attributes, and
* one detail view per area of the schema, with attributes, holding only
  the relationships inside that area.

Nothing is copied by hand, so editing er_diagram.md and re-running this
keeps every figure in step. Needs Google Chrome (or Chromium) and, the
first time, network access to fetch a pinned Mermaid release.
"""

import html
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "er_diagram.md"
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"

# Printed width available on an A4 page with the report's margins, in CSS px.
PAGE_WIDTH_PX = 640
FONT_PX = 14

AREAS = {
    "er-people-courses": ["DEPARTMENTS", "USERS", "STUDENTS", "COURSES", "COURSE_INSTRUCTORS", "ENROLLMENTS"],
    "er-engagement": ["ENROLLMENTS", "ATTENDANCE_RECORDS", "LMS_ACTIVITY_LOGS", "ASSESSMENTS", "ASSESSMENT_RESULTS"],
    "er-risk-response": ["ENROLLMENTS", "RISK_ASSESSMENTS", "RISK_ALERTS", "ALERT_STATUS_HISTORY", "INTERVENTIONS"],
    "er-administration": ["USERS", "AUDIT_LOGS", "SYSTEM_SETTINGS"],
}

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<style>html,body{{margin:0;background:#fff}} #d{{display:inline-block;padding:24px}}</style>
<script src="mermaid.min.js"></script></head><body><div id="d"><pre class="mermaid">{code}</pre></div>
<script>
mermaid.initialize({{startOnLoad: false, theme: 'neutral', fontSize: {font},
                     er: {{useMaxWidth: false, fontSize: {font}}}, flowchart: {{useMaxWidth: false}}}});
mermaid.run().then(() => {{
  const r = document.getElementById('d').getBoundingClientRect();
  document.body.setAttribute('data-size', Math.ceil(r.width) + 'x' + Math.ceil(r.height));
}});
</script></body></html>"""


def parse(er: str):
    """Relationship lines and entity blocks of an ``erDiagram``."""
    relations = re.findall(r"^\s+([A-Z_]+) (\S+) ([A-Z_]+) : (\".*?\")\s*$", er, re.M)
    blocks = dict(re.findall(r"^\s+([A-Z_]+) \{\n(.*?)^\s+\}", er, re.M | re.S))
    return relations, blocks


def er_view(relations, blocks, entities=None) -> str:
    """An erDiagram restricted to ``entities``; attributes only when restricted."""
    lines = ["erDiagram"]
    for left, link, right, label in relations:
        if entities is None or (left in entities and right in entities):
            lines.append(f"    {left} {link} {right} : {label}")
    if entities is not None:
        for name in entities:
            lines += [f"    {name} {{", blocks[name].rstrip("\n"), "    }"]
    return "\n".join(lines) + "\n"


def diagrams():
    source = SOURCE.read_text()
    full, spine = re.findall(r"```mermaid\n(.*?)```", source, re.S)[:2]
    relations, blocks = parse(full)
    missing = {e for area in AREAS.values() for e in area} - set(blocks)
    if missing or set(blocks) - {e for area in AREAS.values() for e in area}:
        sys.exit(f"AREAS and er_diagram.md disagree: {sorted(missing ^ (set(blocks) - set().union(*AREAS.values())))}")
    yield "er-overview", er_view(relations, blocks)
    for name, entities in AREAS.items():
        yield name, er_view(relations, blocks, entities)
    yield "engagement-spine", spine


def main() -> None:
    chrome = next((c for c in ("google-chrome", "chromium", "chromium-browser") if shutil.which(c)), None)
    if not chrome:
        sys.exit("Chrome or Chromium is required")
    base = [chrome, "--headless=new", "--no-sandbox", "--disable-gpu",
            "--allow-file-access-from-files", "--virtual-time-budget=15000"]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        urllib.request.urlretrieve(MERMAID, tmp / "mermaid.min.js")
        for name, code in diagrams():
            page = tmp / f"{name}.html"
            page.write_text(PAGE.format(code=html.escape(code), font=FONT_PX))
            # First pass measures the rendered diagram, second captures it at that size.
            dom = subprocess.run(base + ["--window-size=6000,6000", "--dump-dom", page.as_uri()],
                                 capture_output=True, text=True).stdout
            size = re.search(r'data-size="(\d+)x(\d+)"', dom)
            if not size:
                sys.exit(f"{name}: Mermaid did not render")
            width, height = map(int, size.groups())
            png = HERE / f"{name}.png"
            subprocess.run(base + [f"--window-size={width},{height}", "--force-device-scale-factor=2",
                                   "--hide-scrollbars", f"--screenshot={png}", page.as_uri()],
                           capture_output=True, check=True)
            # 1 CSS px prints at 0.75 pt when the image fits the page unscaled.
            printed = FONT_PX * 0.75 * min(1, PAGE_WIDTH_PX / width)
            print(f"{png.relative_to(HERE.parent.parent)}  {width}×{height}  text ≈ {printed:.1f} pt on A4")


if __name__ == "__main__":
    main()
