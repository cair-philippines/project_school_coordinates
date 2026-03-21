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
| `DRRMS IMRS data 2025.csv` | Disaster incident reports with school coordinates (~16K unique schools) | DepEd DRRMS |
| `SY_2024_2025_School_Level_Data_on_Official_Enrollment.csv` | School-level enrollment data for universe expansion (identifies public schools not in coordinate sources) | DepEd LIS |

### Private School Pipeline (`scripts/build_private_coordinates.py`)

| Filename | Description | Source |
|---|---|---|
| `Private School Seats and TOSF ao 2025Oct27.xlsx` | Self-reported private school coordinates and GASTPE data (as of Oct 27, 2025) | DepEd Private Education Office (PEO) |

### PSGC Standardization (both pipelines)

| Filename | Description | Source |
|---|---|---|
| `SY 2024-2025 School Level Database WITH PSGC.xlsx` | School-to-PSGC crosswalk (60,094 schools, Q4 2024 PSGC) | DepEd (manually validated) |

The barangay shapefile for spatial validation is at `data/modified/phl_admbnda_adm4_updated/` (Q4 2025 PSGC, generated from `cair-philippines/open-data-philippine-maps`).
