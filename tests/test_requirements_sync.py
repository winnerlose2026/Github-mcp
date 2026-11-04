"""requirements.txt must mirror [project.dependencies] in pyproject.toml.

The 0.19.0 port moved pyproject.toml to mcp>=2,<3 but left requirements.txt on
mcp<2, so installing from requirements.txt gave an mcp that the server cannot
import. This keeps the two in lockstep.
"""

from pathlib import Path

import pytest

tomllib = pytest.importorskip("tomllib")  # stdlib on 3.11+

ROOT = Path(__file__).resolve().parents[1]


def _normalise(spec: str) -> tuple[str, frozenset[str]]:
    spec = spec.replace(" ", "")
    for i, ch in enumerate(spec):
        if ch in "<>=!~":
            return spec[:i].lower(), frozenset(spec[i:].split(","))
    return spec.lower(), frozenset()


def test_requirements_txt_matches_pyproject():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = {_normalise(d) for d in pyproject["project"]["dependencies"]}
    lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    listed = {_normalise(ln) for ln in (s.strip() for s in lines) if ln and not ln.startswith("#")}
    assert listed == declared
