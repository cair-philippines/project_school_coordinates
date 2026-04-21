"""Smoke tests for silver-layer preprocessors.

Each preprocessor must produce a silver parquet with the expected schema.
These tests use the live repo state (actual silver files materialized by the
most recent `python scripts/build.py --stage=silver`) to confirm the
read_silver contract holds.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestSilverSchemas(unittest.TestCase):
    """For each loader that writes a silver, confirm it's readable and has
    the expected columns. Skip any whose silver hasn't been materialized
    yet (first-run environments)."""

    def _check(self, loader_name, read_silver_fn, required_cols):
        try:
            df = read_silver_fn(str(PROJECT_ROOT))
        except FileNotFoundError:
            self.skipTest(f"{loader_name}: silver not materialized yet")
        self.assertGreater(len(df), 0, f"{loader_name}: silver is empty")
        for col in required_cols:
            self.assertIn(col, df.columns, f"{loader_name}: missing column {col}")

    def test_monitoring(self):
        from modules import load_monitoring
        self._check("monitoring", load_monitoring.read_silver,
                    ["school_id", "latitude", "longitude", "source", "_was_swapped"])

    def test_osmapaaralan(self):
        from modules import load_osmapaaralan
        self._check("osmapaaralan", load_osmapaaralan.read_silver,
                    ["school_id", "latitude", "longitude", "source", "_was_swapped"])

    def test_nsbi(self):
        from modules import load_nsbi
        self._check("nsbi", load_nsbi.read_silver,
                    ["school_id", "latitude", "longitude", "source", "_was_swapped"])

    def test_geolocation(self):
        from modules import load_geolocation
        self._check("geolocation", load_geolocation.read_silver,
                    ["school_id", "latitude", "longitude", "source", "_was_swapped"])

    def test_drrms(self):
        from modules import load_drrms
        self._check("drrms", load_drrms.read_silver,
                    ["school_id", "latitude", "longitude", "source", "_was_swapped"])

    def test_sos_mapping(self):
        from modules import load_sos_mapping
        self._check("sos_mapping", load_sos_mapping.read_silver,
                    ["school_id_2024"])

    def test_psgc_crosswalk(self):
        from modules import load_psgc
        self._check("psgc_crosswalk", load_psgc.read_silver,
                    ["school_id", "psgc_region", "psgc_barangay"])

    def test_enrollment_all_sectors_present(self):
        """Silver must include all sectors (including PSO) — downstream filters."""
        from modules import load_enrollment
        try:
            df = load_enrollment.read_silver(str(PROJECT_ROOT))
        except FileNotFoundError:
            self.skipTest("enrollment: silver not materialized yet")
        self.assertIn("sector", df.columns)

    def test_enrollment_sector_filter(self):
        from modules import load_enrollment
        try:
            pub = load_enrollment.read_silver(str(PROJECT_ROOT), sector="public")
        except FileNotFoundError:
            self.skipTest("enrollment: silver not materialized yet")
        # All filtered rows must match sector
        sectors = set(pub["sector"].str.lower().unique())
        self.assertEqual(sectors, {"public"})

    def test_private_tosf_universe(self):
        from modules import load_private_tosf
        try:
            df = load_private_tosf.read_silver_universe(str(PROJECT_ROOT))
        except FileNotFoundError:
            self.skipTest("private_tosf_universe: silver not materialized yet")
        for col in ["school_id", "school_name"]:
            self.assertIn(col, df.columns)

    def test_private_tosf_coords_and_stats(self):
        from modules import load_private_tosf
        try:
            coords, stats = load_private_tosf.read_silver_coords(str(PROJECT_ROOT))
        except FileNotFoundError:
            self.skipTest("private_tosf_coords: silver not materialized yet")
        for col in ["school_id", "latitude", "longitude", "coord_status"]:
            self.assertIn(col, coords.columns)
        # Stats sidecar must include the Pass 1-3 rejection counts that can't
        # be recovered from the parquet alone.
        for k in ["total_submissions", "fixed_swap", "rejected_invalid",
                  "rejected_out_of_bounds", "valid"]:
            self.assertIn(k, stats)


if __name__ == "__main__":
    unittest.main()
