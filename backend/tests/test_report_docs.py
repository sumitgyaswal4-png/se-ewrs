"""The written report must stay consistent with itself and with the code.

``docs/report.md`` cross-references by number — figures, tables,
citations, a contents list — and ``docs/report_appendices.md`` copies
SQL and Python out of the repository. Every one of those can go stale
without anything failing, and a stale figure number or a schema listing
that no longer matches ``schema.sql`` is exactly what an examiner
notices. These tests make each of them fail loudly instead.
"""

import importlib.util
import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[2] / "docs"
REPORT = (DOCS / "report.md").read_text()
# Everything from the contents list on; the title page and declarations precede it.
BODY = REPORT[REPORT.index("\n## Contents\n"):]


def _build_appendices():
    spec = importlib.util.spec_from_file_location("build_appendices", DOCS / "build_appendices.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build()


def _slug(heading: str) -> str:
    """GitHub's heading anchor: lower case, punctuation dropped, spaces to hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def _section(title: str) -> str:
    return BODY.split(f"\n## {title}\n", 1)[1].split("\n## ", 1)[0]


def test_appendices_match_the_sources_they_copy():
    assert (DOCS / "report_appendices.md").read_text() == _build_appendices(), (
        "docs/report_appendices.md is stale; run: python docs/build_appendices.py"
    )


def test_contents_lists_every_heading_in_order():
    headings = re.findall(r"^#{2,3} (.+)$", BODY.split("\n## List of figures\n", 1)[1], re.M)
    headings = [h for h in headings if h != "List of tables"]
    listed = re.findall(r"^\s*- \[(.+)\]\(#(.+)\)$", _section("Contents"), re.M)
    assert [title for title, _ in listed] == headings
    for title, anchor in listed:
        assert anchor == _slug(title), title


@pytest.mark.parametrize("kind", ["Figure", "Table"])
def test_captions_are_numbered_in_order_and_listed(kind):
    captions = re.findall(rf"^\*\*({kind} (\d+)\.(\d+) — .+?)\*\*$", BODY, re.M)
    expected, last = [], (0, 0)
    for _, chapter, n in captions:
        chapter, n = int(chapter), int(n)
        # Numbering restarts at 1 in each chapter and never skips.
        assert (chapter, n) == ((last[0], last[1] + 1) if chapter == last[0] else (chapter, 1))
        last = (chapter, n)
    listed = re.findall(r"^- (.+)$", _section(f"List of {kind.lower()}s"), re.M)
    assert listed == [caption for caption, _, _ in captions]


def test_every_table_in_the_body_has_a_caption():
    lines = BODY.split("\n## References\n")[0].splitlines()
    for i, line in enumerate(lines):
        if line.startswith("|---"):
            assert re.match(r"\*\*Table \d+\.\d+ — ", lines[i - 3]), lines[i - 1]


def test_every_figure_image_exists():
    images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", REPORT)
    assert len(images) == 17
    for path in images:
        assert (DOCS / path).is_file(), path


def test_figure_references_in_the_text_exist():
    defined = set(re.findall(r"^\*\*Figure (\d+\.\d+) — ", BODY, re.M))
    for ref in re.findall(r"Figures? (\d+\.\d+)", BODY):
        assert ref in defined, ref


def test_citations_and_references_agree():
    refs = re.findall(r"^\[(\d+)\] ", _section("References"), re.M)
    assert refs == [str(n) for n in range(1, len(refs) + 1)]
    text = BODY.split("\n## References\n")[0]
    cited = [int(n) for n in re.findall(r"\[(\d+)\](?!\()", text)]
    # IEEE style: numbered by first citation, and nothing listed but unused.
    first_use = list(dict.fromkeys(cited))
    assert first_use == list(range(1, len(refs) + 1))
