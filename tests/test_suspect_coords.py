"""Regression tests for Pass 4 suspect-coordinate detection."""

import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.suspect_coords import detect_suspect


class TestSuspectDetection(unittest.TestCase):
    def test_placeholder_flagged(self):
        df = pd.DataFrame({
            "school_id": ["A"],
            # Close to the known TOSF default
            "latitude": [14.57929],
            "longitude": [121.06494],
            "coord_status": ["valid"],
            "coord_rejection_reason": [None],
            "municipality": ["Pasig"],
        })
        detect_suspect(df.copy())
        # detect_suspect mutates in place; run on df directly.
        out = df.copy()
        detect_suspect(out)
        self.assertEqual(out.loc[0, "coord_status"], "suspect")
        self.assertEqual(out.loc[0, "coord_rejection_reason"], "placeholder_default")

    def test_round_coordinates_flagged(self):
        df = pd.DataFrame({
            "school_id": ["A"],
            "latitude": [14.0],
            "longitude": [121.0],
            "coord_status": ["valid"],
            "coord_rejection_reason": [None],
            "municipality": ["Anywhere"],
        })
        detect_suspect(df)
        self.assertEqual(df.loc[0, "coord_status"], "suspect")
        self.assertEqual(df.loc[0, "coord_rejection_reason"], "round_coordinates")

    def test_cluster_flagged_across_municipalities(self):
        df = pd.DataFrame({
            "school_id": ["A", "B", "C"],
            "latitude": [14.57930, 14.57930, 14.57930],  # Shared coord
            "longitude": [121.2, 121.2, 121.2],
            "coord_status": ["valid", "valid", "valid"],
            "coord_rejection_reason": [None, None, None],
            "municipality": ["Muni1", "Muni2", "Muni3"],
        })
        detect_suspect(df)
        for i in range(3):
            self.assertEqual(df.loc[i, "coord_status"], "suspect")
            self.assertEqual(df.loc[i, "coord_rejection_reason"], "coordinate_cluster")

    def test_cluster_same_muni_not_flagged(self):
        # 3+ schools at same coordinate in the same municipality — legitimate
        # campus co-location, not a cluster.
        df = pd.DataFrame({
            "school_id": ["A", "B", "C"],
            "latitude": [14.57930, 14.57930, 14.57930],
            "longitude": [121.2, 121.2, 121.2],
            "coord_status": ["valid", "valid", "valid"],
            "coord_rejection_reason": [None, None, None],
            "municipality": ["SameMuni", "SameMuni", "SameMuni"],
        })
        detect_suspect(df)
        for i in range(3):
            self.assertEqual(df.loc[i, "coord_status"], "valid")

    def test_valid_precise_coords_not_flagged(self):
        df = pd.DataFrame({
            "school_id": ["A"],
            "latitude": [14.12345],
            "longitude": [121.67890],
            "coord_status": ["valid"],
            "coord_rejection_reason": [None],
            "municipality": ["Anywhere"],
        })
        detect_suspect(df)
        self.assertEqual(df.loc[0, "coord_status"], "valid")


if __name__ == "__main__":
    unittest.main()
