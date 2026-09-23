"""
Unit tests verifying temperature color bins and thresholds.
Ensures conformance with teacher acceptance requirements:
  - < 10°C is blue
  - around 20-25°C is yellow-ish
  - > 35°C is deep red
"""

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from normalize import get_temperature_color_and_category, COLOR_NO_DATA


def test_temperature_below_10_is_blue():
    """Verify temperatures below 10°C map to blue (#2563EB)."""
    for temp in [-5.0, 0.0, 5.0, 7.2, 9.9]:
        color, category = get_temperature_color_and_category(temp)
        assert color == "#2563EB", f"Expected blue #2563EB for {temp}°C, got {color}"
        assert "<10" in category


def test_temperature_20_to_25_is_yellowish():
    """Verify temperatures in 20-25°C map to yellowish (#EAB308)."""
    for temp in [20.0, 21.5, 22.8, 24.9]:
        color, category = get_temperature_color_and_category(temp)
        assert color == "#EAB308", f"Expected yellowish #EAB308 for {temp}°C, got {color}"
        assert "20-25" in category


def test_temperature_above_35_is_deep_red():
    """Verify temperatures above 35°C map to deep red (#991B1B)."""
    for temp in [35.0, 36.5, 38.0, 42.0]:
        color, category = get_temperature_color_and_category(temp)
        assert color == "#991B1B", f"Expected deep red #991B1B for {temp}°C, got {color}"
        assert ">35" in category


def test_temperature_intermediate_bins():
    """Verify intermediate temperature bins are continuous and intuitive."""
    # 10 - 15 is cyan
    c1, cat1 = get_temperature_color_and_category(12.5)
    assert c1 == "#06B6D4"

    # 15 - 20 is green/teal
    c2, cat2 = get_temperature_color_and_category(18.0)
    assert c2 == "#10B981"

    # 25 - 30 is warm orange
    c3, cat3 = get_temperature_color_and_category(27.5)
    assert c3 == "#F97316"

    # 30 - 35 is red
    c4, cat4 = get_temperature_color_and_category(32.5)
    assert c4 == "#EF4444"


def test_missing_temperature():
    """Verify None/missing temperature maps to slate gray and no-data category."""
    color, category = get_temperature_color_and_category(None)
    assert color == COLOR_NO_DATA
    assert category == "無資料"
