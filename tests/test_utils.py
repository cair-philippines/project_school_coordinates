"""Regression tests for utils.py helpers."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.utils import (
    fix_swapped_coords,
    has_valid_coords,
    normalize_school_id,
    reject_out_of_ph_bounds,
)


class TestNormalizeSchoolID(unittest.TestCase):
    def test_scalar_none(self):
        self.assertIsNone(normalize_school_id(None))

    def test_scalar_nan(self):
        self.assertIsNone(normalize_school_id(float("nan")))

    def test_scalar_trailing_dot_zero(self):
        self.assertEqual(normalize_school_id("123.0"), "123")

    def test_scalar_plain(self):
        self.assertEqual(normalize_school_id("123456"), "123456")

    def test_scalar_whitespace(self):
        self.assertEqual(normalize_school_id("  123456  "), "123456")

    def test_series_trailing_dot_zero(self):
        out = normalize_school_id(pd.Series(["123.0", "456", "789.00", "1.0"]))
        self.assertListEqual(out.tolist(), ["123", "456", "789.00", "1"])


class TestFixSwappedCoords(unittest.TestCase):
    def test_obviously_swapped_row_is_corrected(self):
        df = pd.DataFrame({"latitude": [124.94, 14.5], "longitude": [11.0, 121.0]})
        fixed, n = fix_swapped_coords(df)
        self.assertEqual(n, 1)
        self.assertAlmostEqual(fixed.loc[0, "latitude"], 11.0)
        self.assertAlmostEqual(fixed.loc[0, "longitude"], 124.94)
        self.assertAlmostEqual(fixed.loc[1, "latitude"], 14.5)
        self.assertAlmostEqual(fixed.loc[1, "longitude"], 121.0)

    def test_valid_row_unchanged(self):
        df = pd.DataFrame({"latitude": [14.5, 8.0], "longitude": [121.0, 125.0]})
        fixed, n = fix_swapped_coords(df)
        self.assertEqual(n, 0)
        pd.testing.assert_frame_equal(df, fixed)

    def test_both_out_of_ph_not_swapped(self):
        # Coords both outside PH and not recoverable by swap — should not be fixed.
        df = pd.DataFrame({"latitude": [50.0], "longitude": [60.0]})
        fixed, n = fix_swapped_coords(df)
        self.assertEqual(n, 0)


class TestRejectOutOfPHBounds(unittest.TestCase):
    def test_rejects_out_of_bounds(self):
        df = pd.DataFrame({"latitude": [14.5, 0.0, 50.0], "longitude": [121.0, 0.0, 60.0]})
        out, n = reject_out_of_ph_bounds(df)
        self.assertEqual(n, 2)
        self.assertFalse(pd.isna(out.loc[0, "latitude"]))
        self.assertTrue(pd.isna(out.loc[1, "latitude"]))
        self.assertTrue(pd.isna(out.loc[2, "latitude"]))

    def test_null_unchanged(self):
        df = pd.DataFrame({"latitude": [np.nan], "longitude": [np.nan]})
        out, n = reject_out_of_ph_bounds(df)
        self.assertEqual(n, 0)


class TestHasValidCoords(unittest.TestCase):
    def test_accepts_finite_non_null(self):
        df = pd.DataFrame({"latitude": [14.5], "longitude": [121.0]})
        self.assertTrue(has_valid_coords(df).all())

    def test_rejects_null(self):
        df = pd.DataFrame({"latitude": [np.nan], "longitude": [121.0]})
        self.assertFalse(has_valid_coords(df).iloc[0])


if __name__ == "__main__":
    unittest.main()
