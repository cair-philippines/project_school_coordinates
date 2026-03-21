# Feedback: open-data-philippine-maps Repository

Notes from attempting to run `scripts/update_shapefiles.py` from a fresh clone of `cair-philippines/open-data-philippine-maps` in a clean environment (Python 3.11, Docker-based data science container, no Git LFS installed).

**Goal**: Generate the updated barangay-level shapefile `phl_admbnda_adm4_updated.shp` from the base PSA/NAMRIA 2023 shapefile using the PSGC update configuration.

**Outcome**: Successfully generated the output, but required several manual interventions that could be eliminated with improvements to the repository.

---

## 1. Git LFS: Large Files Are Inaccessible from a Fresh Clone

**Problem**: The input shapefile `data/PH_Adm4_BgySubMuns.shp.zip` is tracked by Git LFS, but after cloning the repository, the file is a 134-byte LFS pointer — not the actual data. Running the script against this pointer silently fails or produces errors.

**What I had to do**: Manually download the zip file from the GitHub web UI and place it in the `data/` directory.

**Suggested fix**:
- Document the Git LFS requirement prominently in the README, including installation instructions (`git lfs install && git lfs pull`)
- Add a setup verification step (e.g., a script that checks file sizes and warns if LFS pointers haven't been resolved)
- Alternatively, consider hosting the base shapefile externally (e.g., Google Drive, S3) with a download script, since LFS has storage/bandwidth quotas that can surprise collaborators

## 2. The Script Cannot Run from a Fresh Clone Without Manual Steps

**Problem**: Running `python scripts/update_shapefiles.py` from the repository root fails for multiple reasons. Each requires a manual workaround:

| Step | Issue | Workaround Applied |
|---|---|---|
| Import | `from shapefile_functions import ShapefileUpdater` fails because `scripts/` is not on the Python path | Set `PYTHONPATH=scripts` before running |
| Config | `load_config("shp_config.yaml")` fails because the file is in `configs/shp_config.yaml`, not the repo root | Copied `configs/shp_config.yaml` to the root |
| Input data | Shapefile is inside a zip that must be extracted first | Extracted manually with `zipfile.extractall()` |
| Output directory | `out/phl_admbnda_adm4_updated.shp` assumes `out/` exists | Created `out/` directory manually |

**Suggested fix**: Add a `run.sh` or `Makefile` that handles all prerequisites:

```bash
#!/bin/bash
set -euo pipefail

# Extract input shapefile if needed
if [ ! -f data/phl_admbnda_adm4_psa_namria_20231106.shp ]; then
    echo "Extracting input shapefile..."
    python3 -c "import zipfile; zipfile.ZipFile('data/PH_Adm4_BgySubMuns.shp.zip').extractall('data/')"
fi

# Create output directory
mkdir -p out

# Copy config to expected location
cp configs/shp_config.yaml shp_config.yaml

# Run
PYTHONPATH=scripts python3 scripts/update_shapefiles.py
```

This makes the repo reproducible in one command: `bash run.sh`.

## 3. Hardcoded Relative Paths in the Script

**Problem**: `update_shapefiles.py` defines four hardcoded paths:

```python
INPUT_SHP = "data/phl_admbnda_adm4_psa_namria_20231106.shp"
OUTPUT_SHP = "out/phl_admbnda_adm4_updated.shp"
CONFIG = "shp_config.yaml"
LOG_FILE = "shp_changelog.csv"
```

These only resolve correctly if the script is run from the repository root with the exact expected directory layout. Running from `scripts/` or any other directory breaks all four paths.

**Suggested fix**: Either:
- Accept these as CLI arguments with sensible defaults (using `argparse`)
- Or resolve paths relative to the script's own location:

```python
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
INPUT_SHP = REPO_ROOT / "data" / "phl_admbnda_adm4_psa_namria_20231106.shp"
```

## 4. Missing Setup Instructions in the README

**Problem**: The repository has a `requirements.txt` but the README does not mention installing dependencies. The script requires `geopandas`, `pyogrio`, `pyyaml`, and `shapely` — packages that are not part of a standard Python installation. A new contributor would encounter import errors with no guidance on resolution.

**Suggested fix**: Add a "Getting Started" section to the README:

```markdown
## Getting Started

### Prerequisites
- Python 3.10+
- Git LFS (`git lfs install`)

### Setup
git clone git@github.com:cair-philippines/open-data-philippine-maps.git
cd open-data-philippine-maps
git lfs pull
pip install -r requirements.txt

### Generate Updated Shapefile
bash run.sh
```

## 5. Output File Documentation

**Problem**: The script produces a shapefile, which is actually a set of 5 companion files (`.shp`, `.dbf`, `.shx`, `.prj`, `.cpg`). This isn't documented anywhere. Someone expecting a single `.shp` file may not realize the other files are required — a shapefile without its `.dbf` or `.shx` is unreadable by most GIS tools.

**Suggested fix**: Document the output files and their roles:

| File | Size | Purpose |
|---|---|---|
| `.shp` | ~260 MB | Geometry (polygon boundaries) |
| `.dbf` | ~48 MB | Attribute table (names, codes, metadata) |
| `.shx` | ~329 KB | Spatial index |
| `.prj` | ~145 B | Coordinate reference system definition |
| `.cpg` | ~5 B | Character encoding declaration |

All five files must be kept together in the same directory for the shapefile to be usable.

---

## Summary

The core logic of the repository works well — the PSGC update operations are clearly structured in YAML, the `ShapefileUpdater` class handles complex operations (merges, transfers, renames, resets) correctly, and the output shapefile passes validation. The improvements above are purely about **reproducibility and onboarding** — making it possible for someone to clone, run, and get results without prior knowledge of the repo's internal layout.
