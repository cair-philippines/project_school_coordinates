# Gold — Published Pipeline Outputs

Canonical coordinate datasets produced by the pipelines. These files are committed to the repository so downstream consumers can clone and read directly.

| Filename | Pipeline | Description |
|---|---|---|
| `public_school_coordinates.parquet` | public | Canonical public-school coordinates (~48K rows) |
| `public_school_coordinates.csv` | public | CSV export of above |
| `public_school_coordinates.xlsx` | public | Excel workbook: Metadata + Coordinates + Crosswalk sheets |
| `public_school_id_crosswalk.parquet` | public | Historical → canonical school ID mapping (~72K entries) |
| `private_school_coordinates.parquet` | private | Cleaned private-school coordinates (~12K rows) |
| `private_school_coordinates.csv` | private | CSV export of above |
| `private_school_coordinates.xlsx` | private | Excel workbook: Metadata + Coordinates sheets |
| `build_public_metrics.json` | public | Structured run metrics for programmatic comparison (used by `scripts/diff_metrics.py`) |
| `build_private_metrics.json` | private | Same for private pipeline |

Human-readable build reports are in `output/build_*_report.txt` (not committed).
