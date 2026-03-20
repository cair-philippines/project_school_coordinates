# Raw Data Sources

This directory contains the untouched source files used by the pipelines. These files are not committed to the repository due to their size and sensitivity. To run the pipelines, obtain the following files and place them here.

## Expected Files

### Public School Pipeline (`scripts/build_coordinates.py`)

| Filename | Description | Source |
|---|---|---|
| `02. DepEd Data Encoding Monitoring Sheet.xlsx` | University-validated coordinates for ~11,331 flagged schools (sheets 1–5) | DepEd / partner university |
| `osmapaaralan_overpass_turbo_export.geojson` | School footprints from OpenStreetMap (~44K features) | Overpass Turbo export of OSMapaaralan data |
| `SY 2023-2024 LIST OF SCHOOLS WITH LONGITUDE AND LATITUDE.xlsx` | Official NSBI school list with coordinates (~47K schools) | DepEd NSBI system |
| `Geolocation of Public Schools_DepEd.xlsx` | Internal DepEd geolocation file with coordinates and School ID Mapping tab | DepEd internal office |

### Private School Pipeline (`scripts/build_private_coordinates.py`)

| Filename | Description | Source |
|---|---|---|
| `Private School Seats and TOSF ao 2025Oct27.xlsx` | Self-reported private school coordinates and GASTPE data (as of Oct 27, 2025) | DepEd Private Education Office (PEO) |
