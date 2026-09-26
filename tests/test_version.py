#!/usr/bin/env python3
"""Tests de coherence des versions du bridge (backend + UI + add-on)."""
import json
import os
import re
import sys

import pytest

sys.path.insert(0, "/home/ubuntu/aldes-bridge")

from server import __version__

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
