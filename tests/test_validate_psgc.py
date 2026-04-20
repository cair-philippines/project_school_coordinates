"""Regression tests for validate_psgc.validate() and its coord_status awareness."""

import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.validate_psgc import validate


class TestValidateRespectsCoordStatus(unittest.TestCase):
    """validate() must not emit psgc_match or psgc_mismatch for rows whose
    coord_status marks the coordinate as untrustworthy. Otherwise we publish
    internally-contradictory labels (a school simultaneously "in the right
    barangay" and "in the wrong municipality")."""

    def test_suspect_row_becomes_no_validation(self):
        df = pd.DataFrame({
            "latitude": [14.5, 14.5],
            "longitude": [121.0, 121.0],
            "psgc_barangay": ["A123", "B456"],
            "psgc_observed_barangay": ["A123", "B456"],
            "coord_status": ["valid", "suspect"],
        })
        out = validate(df.copy())
        self.assertEqual(out.loc[0, "psgc_validation"], "psgc_match")
        self.assertEqual(out.loc[1, "psgc_validation"], "psgc_no_validation")

    def test_no_coords_becomes_no_validation(self):
        df = pd.DataFrame({
            "latitude": [14.5, None],
            "longitude": [121.0, None],
            "psgc_barangay": ["A123", "B456"],
            "psgc_observed_barangay": ["A123", None],
            "coord_status": ["valid", "no_coords"],
        })
        out = validate(df.copy())
        self.assertEqual(out.loc[0, "psgc_validation"], "psgc_match")
        self.assertEqual(out.loc[1, "psgc_validation"], "psgc_no_validation")

    def test_mismatch_preserved_for_valid(self):
        df = pd.DataFrame({
            "latitude": [14.5],
            "longitude": [121.0],
            "psgc_barangay": ["A123"],
            "psgc_observed_barangay": ["B999"],
            "coord_status": ["valid"],
        })
        out = validate(df.copy())
        self.assertEqual(out.loc[0, "psgc_validation"], "psgc_mismatch")

    def test_fixed_swap_trusted_like_valid(self):
        df = pd.DataFrame({
            "latitude": [14.5],
            "longitude": [121.0],
            "psgc_barangay": ["A123"],
            "psgc_observed_barangay": ["A123"],
            "coord_status": ["fixed_swap"],
        })
        out = validate(df.copy())
        self.assertEqual(out.loc[0, "psgc_validation"], "psgc_match")

    def test_no_coord_status_column_falls_back_to_has_coords(self):
        # Backwards-compatible behavior when upstream doesn't populate coord_status.
        df = pd.DataFrame({
            "latitude": [14.5, None],
            "longitude": [121.0, None],
            "psgc_barangay": ["A123", "B456"],
            "psgc_observed_barangay": ["A123", None],
        })
        out = validate(df.copy())
        self.assertEqual(out.loc[0, "psgc_validation"], "psgc_match")
        self.assertEqual(out.loc[1, "psgc_validation"], "psgc_no_validation")


if __name__ == "__main__":
    unittest.main()
