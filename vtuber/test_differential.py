"""Harness-ul diferențial, într-o versiune rapidă pentru suită.

Rulează 24 de cazuri (colțurile parametrilor + câteva combinații), nu toate 281 — cele
281 se rulează cu `python vtuber/differential.py`, care durează ~3 minute.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

import differential
import rig_preview as rp


@pytest.fixture(scope="module")
def layers():
    return rp.load_layers()


def test_rest_frame_has_no_hole_at_the_collar(layers):
    frame = rp.render(layers)
    assert differential.closed_holes(np.asarray(frame.getchannel("A"))) < 300
    assert differential.closed_holes(np.asarray(frame.getchannel("A")), differential.COLLAR) == 0


@pytest.mark.parametrize("angle", [-30.0, 30.0])
def test_extreme_head_angles_keep_the_collar_closed(layers, angle):
    for other in (-30.0, 0.0, 30.0):
        for third in (-30.0, 0.0, 30.0):
            frame = rp.render(layers, angle, other, third)
            alpha = np.asarray(frame.getchannel("A"))
            assert differential.closed_holes(alpha, differential.COLLAR) == 0, (angle, other, third)


def test_no_parameter_combination_loses_more_than_two_percent_of_the_body(layers):
    rest = np.asarray(rp.render(layers).getchannel("A")) > 24
    for case in differential.cases(24):
        frame = rp.render(layers, case["angle_x"], case["angle_y"], case["angle_z"],
                          eyeball_x=case["eyeball_x"], eyeball_y=case["eyeball_y"],
                          eye_open=case["eye_open"], mouth=case["mouth"])
        solid = np.asarray(frame.getchannel("A")) > 24
        change = abs(int(solid.sum()) - int(rest.sum())) / max(1, int(rest.sum()))
        assert change < 0.02, (case, change)


def test_cases_are_reproducible_and_unique():
    first = differential.cases(281)
    second = differential.cases(281)
    assert first == second
    assert len(first) == 281
    keys = {(c["angle_x"], c["angle_y"], c["angle_z"], c["eye_open"], c["mouth"]) for c in first}
    assert len(keys) > 250, "prea multe cazuri identice"


def test_closed_holes_counts_only_enclosed_pockets():
    """O gaură închisă se numără, un golf deschis spre margine nu."""
    a = np.zeros((40, 40), dtype=np.uint8)
    a[5:35, 5:35] = 255                      # pătrat plin
    assert differential.closed_holes(a) == 0
    a[15:20, 15:20] = 0                      # gaură în interior
    assert differential.closed_holes(a) == 25
    a[30:35, 15:20] = 0                      # golf legat de marginea de jos
    assert differential.closed_holes(a) == 25
