# Bronze — Live

Source files expected to refresh on a cadence. Each refresh typically arrives as a new file with a different filename (e.g. `SY 2024-2025 LIST...` replacing `SY 2023-2024 LIST...`). When that happens, update the corresponding `RAW_PATH` constant in the loader module.

| Filename | Description | Cadence | Used by |
|---|---|---|---|
| `SY 2023-2024 LIST OF SCHOOLS WITH LONGITUDE AND LATITUDE.xlsx` | Official NSBI school list with coordinates (~47K schools). | Yearly per school year. | `modules/load_nsbi.py` → priority 3 coords |
| `DRRMS IMRS data 2025.csv` | Disaster incident reports with school coordinates (~16K unique schools). | Accumulates continuously during the school year. | `modules/load_drrms.py` → priority 5 coords |
| `Private School Seats and TOSF ao 2025Oct27.xlsx` | Self-reported private school coordinates + GASTPE program flags. Two sheets: `SCHOOLS WITHOUT SUBMISSION` (LIS master list) and `RAW DATA` (submissions). | Annual TOSF submission cycle. | `modules/load_private_tosf.py` → private pipeline main input |
| `project_bukas_enrollment_2024-25.csv` | School-level enrollment data (all sectors) with metadata: management, annex status, curricular offerings, SHS strands, NIR-aware region. | Annual (per school year). | `modules/load_enrollment.py` → universe expansion, enrollment status tagging, metadata enrichment |

When the next school year's enrollment file arrives, update `ENROLLMENT_FILES` in both `scripts/build_coordinates.py` and `scripts/build_private_coordinates.py` to point at the new filename, then rerun.
