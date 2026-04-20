"""Regression tests for crosswalk behaviors — specifically the decisions that
silently conflate schools if wrong."""

import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.build_crosswalk import (
    _consolidate_duplicates,
    _dedupe_crosswalk_identity_first,
    remap_source,
)


class TestIdentityFirstDedup(unittest.TestCase):
    """When a historical_id has multiple canonical candidates, the row where
    historical_id == canonical_id must win. Prevents the 101701 class of bugs
    where a real school gets silently remapped to an unrelated school.
    """

    def test_identity_wins_over_cross_mapping(self):
        crosswalk = pd.DataFrame([
            # Cross-school mapping emitted FIRST by Excel iteration
            {"historical_id": "101701", "canonical_id": "500376", "match_method": "official_mapping"},
            # Identity emitted later
            {"historical_id": "101701", "canonical_id": "101701", "match_method": "official_mapping"},
            # 500376 identity, unrelated
            {"historical_id": "500376", "canonical_id": "500376", "match_method": "official_mapping"},
        ])
        deduped = _dedupe_crosswalk_identity_first(crosswalk)
        lookup = deduped.set_index("historical_id")["canonical_id"].to_dict()
        self.assertEqual(lookup["101701"], "101701", "Identity mapping must win")
        self.assertEqual(lookup["500376"], "500376")

    def test_identity_wins_regardless_of_order(self):
        # Reverse order — identity later, still wins.
        crosswalk = pd.DataFrame([
            {"historical_id": "101701", "canonical_id": "101701", "match_method": "official_mapping"},
            {"historical_id": "101701", "canonical_id": "500376", "match_method": "official_mapping"},
        ])
        deduped = _dedupe_crosswalk_identity_first(crosswalk)
        lookup = deduped.set_index("historical_id")["canonical_id"].to_dict()
        self.assertEqual(lookup["101701"], "101701")

    def test_no_identity_keeps_first(self):
        # When no identity exists, fall back to first-wins behavior.
        crosswalk = pd.DataFrame([
            {"historical_id": "A", "canonical_id": "X", "match_method": "official_mapping"},
            {"historical_id": "A", "canonical_id": "Y", "match_method": "official_mapping"},
        ])
        deduped = _dedupe_crosswalk_identity_first(crosswalk)
        self.assertEqual(deduped.set_index("historical_id")["canonical_id"]["A"], "X")


class TestRemapSource(unittest.TestCase):
    def test_101701_scenario(self):
        """Reproduce the 101701 bug: a school whose ID appears both as its own
        canonical and as a historical for another school must not be remapped away.
        """
        crosswalk = pd.DataFrame([
            {"historical_id": "101701", "canonical_id": "500376", "match_method": "official_mapping"},
            {"historical_id": "101701", "canonical_id": "101701", "match_method": "official_mapping"},
            {"historical_id": "500376", "canonical_id": "500376", "match_method": "official_mapping"},
        ])
        source = pd.DataFrame({
            "school_id": ["101701", "500376"],
            "school_name": ["Buho ES", "Macayo Integrated School"],
            "latitude": [14.14, 15.86],
            "longitude": [120.96, 120.51],
        })
        remapped, n_changed, n_merged = remap_source(source, crosswalk)
        self.assertEqual(n_changed, 0, "No school_id should change when identity rules apply")
        self.assertEqual(n_merged, 0)
        self.assertEqual(
            set(remapped["school_id"]), {"101701", "500376"},
            "Both distinct schools must survive"
        )

    def test_real_remap(self):
        """When a historical ID is not itself a canonical, it should remap."""
        crosswalk = pd.DataFrame([
            {"historical_id": "OLD123", "canonical_id": "NEW456", "match_method": "official_mapping"},
            {"historical_id": "NEW456", "canonical_id": "NEW456", "match_method": "official_mapping"},
        ])
        source = pd.DataFrame({"school_id": ["OLD123"], "latitude": [14.0], "longitude": [121.0]})
        remapped, n_changed, _ = remap_source(source, crosswalk)
        self.assertEqual(n_changed, 1)
        self.assertEqual(remapped.iloc[0]["school_id"], "NEW456")


class TestConsolidateDuplicates(unittest.TestCase):
    def test_prefers_row_with_valid_coords(self):
        df = pd.DataFrame({
            "school_id": ["A", "A", "B"],
            "latitude": [None, 14.5, 15.0],
            "longitude": [None, 121.0, 122.0],
            "school_name": ["Foo", "Foo", "Bar"],
        })
        deduped, n_merged = _consolidate_duplicates(df)
        self.assertEqual(n_merged, 1)
        # School A's surviving row should be the one with valid coords.
        row_a = deduped[deduped["school_id"] == "A"].iloc[0]
        self.assertAlmostEqual(row_a["latitude"], 14.5)

    def test_prefers_row_with_school_name(self):
        df = pd.DataFrame({
            "school_id": ["A", "A"],
            "latitude": [14.5, 14.5],
            "longitude": [121.0, 121.0],
            "school_name": [None, "Real Name"],
        })
        deduped, n_merged = _consolidate_duplicates(df)
        self.assertEqual(n_merged, 1)
        self.assertEqual(deduped.iloc[0]["school_name"], "Real Name")

    def test_no_dupes_passthrough(self):
        df = pd.DataFrame({
            "school_id": ["A", "B"],
            "latitude": [14.5, 15.0],
            "longitude": [121.0, 122.0],
            "school_name": ["Foo", "Bar"],
        })
        deduped, n_merged = _consolidate_duplicates(df)
        self.assertEqual(n_merged, 0)
        self.assertEqual(len(deduped), 2)


if __name__ == "__main__":
    unittest.main()
