"""The API reference must describe the API that is actually served.

Documentation drifts silently: an endpoint gets added, the table in
``docs/api_documentation.md`` does not, and nothing fails. Worse, a
permission column can claim a stricter rule than the code enforces,
which reads like a security guarantee while being fiction.

These tests read the routes off the running app and the table out of the
Markdown, so both failures are caught the moment they appear.
"""

import re
from pathlib import Path
from typing import Dict, Set

import pytest

from app.main import app

DOC = Path(__file__).resolve().parents[2] / "docs" / "api_documentation.md"
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def _normalise(path: str) -> str:
    """``/api/alerts/{alert_id}`` and ``/api/alerts/{id}`` are one route."""
    return re.sub(r"\{[^}]*\}", "{}", path.rstrip("/")) or "/"


def _served() -> Dict[tuple, Set[str]]:
    """Every ``/api`` route, with the permissions it actually requires."""
    routes: Dict[tuple, Set[str]] = {}
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if not methods or not route.path.startswith("/api/"):
            continue
        needed: Set[str] = set()

        def walk(dependant) -> None:
            for dep in getattr(dependant, "dependencies", []) or []:
                # require_permissions is a callable class holding the
                # permission names; FastAPI flattens router-level
                # dependencies into each route, so this sees both.
                needed.update(getattr(getattr(dep, "call", None), "permissions", None) or ())
                walk(dep)

        walk(getattr(route, "dependant", None))
        for method in methods - {"HEAD", "OPTIONS"}:
            routes.setdefault((method, _normalise(route.path)), set()).update(needed)
    return routes


def _documented() -> Dict[tuple, str]:
    """Each documented row, resolved against the routes that exist.

    Row paths are written relative to the section heading in most tables
    and relative to ``/api`` in a few, so both readings are tried.
    """
    served = _served()
    bases: list = []
    blanket = None
    rows: Dict[tuple, str] = {}

    for line in DOC.read_text().splitlines():
        if line.startswith("### "):
            bases = re.findall(r"`(/api/[^`]*)`", line)
            blanket = None
            continue
        banner = re.search(r"All require `([a-z_]+:[a-z]+)`", line)
        if banner:
            blanket = banner.group(1)
            continue

        row = re.match(
            r"^\|\s*(GET|POST|PUT|PATCH|DELETE)\s*\|\s*`([^`]*)`\s*\|\s*([^|]*)\|", line
        )
        if row:
            method, suffix, claim = row.group(1), row.group(2).strip(), row.group(3)
            claim = claim.strip().strip("` ")
        else:
            # The reports table has no method column: | `/path` | ... |
            plain = re.match(r"^\|\s*`(/[^`]*)`\s*\|", line)
            if not (plain and blanket):
                continue
            method, suffix, claim = "GET", plain.group(1).strip(), blanket

        candidates = [_normalise(base + suffix) for base in bases]
        candidates.append(_normalise("/api" + suffix))
        if suffix.startswith("/api/"):
            candidates.append(_normalise(suffix))
        for candidate in candidates:
            if (method, candidate) in served:
                rows[(method, candidate)] = claim
                break
    return rows


def test_every_served_endpoint_is_documented():
    undocumented = sorted(set(_served()) - set(_documented()))
    assert not undocumented, "endpoints with no row in docs/api_documentation.md: " + ", ".join(
        f"{m} {p}" for m, p in undocumented
    )


@pytest.mark.parametrize("key", sorted(_documented()))
def test_documented_permission_matches_what_is_enforced(key):
    """A permission column must not promise more than the code requires."""
    claim = _documented()[key]
    enforced = _served()[key]
    method, path = key

    if claim in {"public", "any signed-in"}:
        assert not enforced, (
            f"{method} {path} is documented as '{claim}' but enforces {sorted(enforced)}"
        )
        return

    claimed = {part.strip() for part in claim.split("+") if part.strip()}
    assert claimed <= enforced, (
        f"{method} {path} documents {sorted(claimed)} but enforces {sorted(enforced)}"
    )
