"""Build ``docs/report_appendices.md`` from the files it reproduces.

The appendices are copies of SQL, Python and documentation that already
live elsewhere in the repository. Copies kept by hand drift; copies made
by this script cannot, and ``backend/tests/test_report_docs.py`` fails
the moment the committed file stops matching what this script produces.

Appendix C also shows each analytical query's *output*. That needs a
live MySQL, so it is captured separately and committed under
``docs/analytics_output/``:

    python docs/build_appendices.py --capture     # needs MySQL, see below
    python docs/build_appendices.py               # rebuild from sources

``--capture`` runs the ``mysql`` client with the same environment
variables as ``setup.sh`` (``MYSQL_UNIX_PORT``, ``MYSQL_HOST``,
``MYSQL_USER``, ``MYSQL_PASSWORD``) against the ``se_ewrs`` database
loaded with the demo data.
"""

import argparse
import ast
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database"
OUTPUT_DIR = ROOT / "docs" / "analytics_output"
TARGET = ROOT / "docs" / "report_appendices.md"

# Long result sets are cut here; the appendix says how many rows were left out.
MAX_ROWS = 20

# Why a query returns no rows on a freshly seeded database. An empty result
# with no explanation reads like a broken query.
EMPTY_BECAUSE = {
    "11": "The seed runs one risk calculation per enrolment, so no enrolment has "
          "a previous score to compare with. One more run of "
          "`sp_recalculate_all_risk` and all 80 active enrolments return a row.",
    "12": "Every alert in the demonstration data is raised when the seed's risk "
          "calculation runs, so none is yet older than seven days. The query is "
          "the escalation view an operating system would see after a week.",
}

# Appendix E: (file, function names) — extracted by name, not by line number.
LISTINGS = [
    ("backend/app/services/risk_engine.py",
     ["compute_engagement_score", "compute_risk", "_reconcile_alert"]),
    ("backend/app/api/deps.py", ["get_current_user", "require_permissions"]),
]


def split_queries() -> List[Tuple[str, str, str]]:
    """``analytics_queries.sql`` as ``(number, header comment, query)``.

    Each query is introduced by a dashed comment block naming it ``Qn.``
    and printing a label row first; the label is for a terminal reader
    and is dropped here, where the heading does the same job.
    """
    text = (DB / "analytics_queries.sql").read_text()
    parts = re.split(r"^-- -{20,}\n(?=-- Q\d+\.)", text, flags=re.M)[1:]
    queries = []
    for part in parts:
        header, _, body = part.partition("\n-- " + "-" * 69 + "\n")
        number = re.match(r"-- Q(\d+)\.", header).group(1)
        comment = "\n".join(line[3:] for line in header.splitlines())
        body = re.sub(r"^SELECT '[^']*' AS query_label;\n", "", body.strip(), flags=re.M)
        queries.append((number, comment.strip(), body.strip()))
    return queries


def capture() -> None:
    """Run every query against MySQL and store its tabular output."""
    command = ["mysql", "--table", "-u", os.environ.get("MYSQL_USER", "root")]
    if os.environ.get("MYSQL_HOST"):
        command += ["-h", os.environ["MYSQL_HOST"]]
    if os.environ.get("MYSQL_PASSWORD"):
        command.append("-p" + os.environ["MYSQL_PASSWORD"])
    command.append("se_ewrs")
    OUTPUT_DIR.mkdir(exist_ok=True)
    for number, _, query in split_queries():
        result = subprocess.run(command, input=query, capture_output=True, text=True, check=True)
        (OUTPUT_DIR / f"q{int(number):02d}.txt").write_text(result.stdout)
        print(f"Q{number}: {len(result.stdout.splitlines())} lines")


def truncate(table: str) -> str:
    """Keep the header and the first ``MAX_ROWS`` rows of a ``mysql --table`` grid."""
    if not table.strip():
        return "Empty set"
    lines = table.rstrip("\n").splitlines()
    # A grid is: border, header, border, rows..., border.
    rows = lines[3:-1]
    if len(rows) <= MAX_ROWS:
        return "\n".join(lines)
    kept = lines[:3] + rows[:MAX_ROWS] + [lines[-1]]
    return "\n".join(kept) + f"\n({len(rows) - MAX_ROWS} further rows omitted; {len(rows)} in total)"


def extract(path: str, names: List[str]) -> str:
    """The source of the named top-level functions or classes, in file order."""
    source = (ROOT / path).read_text()
    lines = source.splitlines()
    chunks = []
    for node in ast.parse(source).body:
        if getattr(node, "name", None) in names:
            start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
            chunks.append("\n".join(lines[start - 1:node.end_lineno]))
    found = {n for n in names if re.search(rf"^(?:def|class) {n}\b", source, flags=re.M)}
    missing = set(names) - found
    if missing:
        raise SystemExit(f"{path}: not found: {', '.join(sorted(missing))}")
    return "\n\n\n".join(chunks)


def sql_appendix(letter: str, title: str, intro: str, files: List[str]) -> str:
    out = [f"## Appendix {letter} — {title}", "", intro, ""]
    for name in files:
        out += [f"### `database/{name}`", "", "```sql", (DB / name).read_text().rstrip(), "```", ""]
    return "\n".join(out)


def api_table() -> str:
    """Section 4 of the API reference, headings demoted to sit under the appendix."""
    text = (ROOT / "docs" / "api_documentation.md").read_text()
    section = text.split("\n## 4. Endpoints\n", 1)[1].split("\n## 5.", 1)[0].strip()
    section = re.sub(r"^### 4\.", "### D.", section, flags=re.M)
    return section.replace("](#", "](api_documentation.md#")


def build() -> str:
    parts = [
        "# SE-EWRS — Report appendices",
        "",
        "Appendices A–E to `docs/report.md`. **This file is generated** by",
        "`docs/build_appendices.py` from the files it reproduces; edit those,",
        "not this. A test fails if the two disagree.",
        "",
        "---",
        "",
        sql_appendix(
            "A", "Schema",
            "The complete data definition: sixteen tables, their keys, "
            "`CHECK` constraints and indexes (Chapter 4).",
            ["schema.sql"]),
        "---",
        "",
        sql_appendix(
            "B", "Views, procedures and triggers",
            "The twelve views, three stored functions, six stored procedures "
            "and twelve triggers (Chapters 5 and 6.2). `procedures.sql` holds "
            "the SQL implementation of the risk model that §5.6 compares "
            "with the Python one in Appendix E.",
            ["views.sql", "procedures.sql", "triggers.sql"]),
        "---",
        "",
        "## Appendix C — Analytical queries with output",
        "",
        "The fifteen queries of `database/analytics_queries.sql` (§6.3), each "
        "followed by the output it produced against the MySQL 8 demonstration "
        "database. The seed writes dates as offsets from `CURDATE()`, so a "
        f"fresh load reproduces these figures. Result sets longer than {MAX_ROWS} "
        "rows are cut, with the number of rows left out stated beneath.",
        "",
    ]
    for number, comment, query in split_queries():
        title, _, concepts = comment.partition("\nConcepts:")
        title = " ".join(title.split()[1:]).replace(" -- ", " — ").rstrip(".")
        output = OUTPUT_DIR / f"q{int(number):02d}.txt"
        if not output.exists():
            raise SystemExit(f"{output.relative_to(ROOT)} missing; run with --capture")
        parts += [f"### C.{number} {title}", ""]
        if concepts:
            parts += [f"*Concepts:* {' '.join(concepts.split())}", ""]
        parts += ["```sql", query, "```", "", "Output:", "", "```text",
                  truncate(output.read_text()), "```", ""]
        if number in EMPTY_BECAUSE:
            parts += [f"*Why it is empty:* {EMPTY_BECAUSE[number]}", ""]
    parts += [
        "---",
        "",
        "## Appendix D — API endpoints",
        "",
        "Section 4 of `docs/api_documentation.md`. `backend/tests/test_api_docs.py` "
        "checks every row against the routes the application actually serves.",
        "",
        api_table(),
        "",
        "---",
        "",
        "## Appendix E — Selected source listings",
        "",
        "The functions at the centre of Chapter 5: the Python risk model, the "
        "alert reconciliation that keeps one open alert per enrolment, and the "
        "server-side permission check behind every protected endpoint.",
        "",
    ]
    for path, names in LISTINGS:
        parts += [f"### `{path}` — {', '.join(f'`{n}`' for n in names)}", "",
                  "```python", extract(path, names), "```", ""]
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--capture", action="store_true",
                        help="re-run the analytical queries against MySQL first")
    args = parser.parse_args()
    if args.capture:
        capture()
    TARGET.write_text(build())
    print(f"wrote {TARGET.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
