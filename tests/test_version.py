#!/usr/bin/env python3
"""Tests de coherence des versions du bridge (backend + UI + add-on)."""
import json
import os
import re
import sys

import pytest

sys.path.insert(0, "/home/ubuntu/aldes-bridge")

from server import __version__
from server.version import format_banner, format_version, read_ui_version

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_ROOT = "/home/ubuntu/aldes-haos-addons"
SEMVER_BETA = re.compile(r"^\d+\.\d+\.\d+(-beta\d+)?$")


def _ui_version() -> str:
    with open(os.path.join(REPO_ROOT, "web", "package.json"), encoding="utf-8") as f:
        return json.load(f)["version"]


def test_version_format_is_canonical():
    assert SEMVER_BETA.match(__version__), f"format non canonique : {__version__}"


def test_ui_version_matches_backend():
    assert _ui_version() == __version__


def test_addon_version_matches_backend():
    config = os.path.join(ADDON_ROOT, "aldes-bridge-beta", "config.yaml")
    if not os.path.isfile(config):
        pytest.skip("repo aldes-haos-addons absent")

    with open(config, encoding="utf-8") as f:
        addon_version = re.search(r'^version:\s*"?([^"\n]+)"?', f.read(), re.M).group(1)

    assert addon_version == __version__


def test_read_ui_version_tolere_les_deux_cles(tmp_path):
    (tmp_path / "version.json").write_text(json.dumps({"ui": "0.2.0"}), encoding="utf-8")
    assert read_ui_version(str(tmp_path)) == "0.2.0"

    (tmp_path / "version.json").write_text(json.dumps({"version": "0.2.0"}), encoding="utf-8")
    assert read_ui_version(str(tmp_path)) == "0.2.0"


def test_format_version_prefixe_unique():
    assert format_version("0.2.0") == "v0.2.0"
    assert format_version("v0.2.0") == "v0.2.0"
    assert format_version("") == "?"
    assert format_version("dev") == "dev"


def test_banniere_sans_double_v():
    banniere = format_banner("0.19.1-beta1", "0.19.1-beta1", "v0.19.1-beta1")

    assert "vv" not in banniere
    assert banniere.count("0.19.1-beta1") == 3
    assert banniere == (
        "=== Aldes Bridge v0.19.1-beta1 | UI v0.19.1-beta1 | Add-on v0.19.1-beta1 ==="
    )
