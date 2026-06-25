# IDX-Exchange-Analysis

Summer 2026 IDX Exchange Data Analyst Internship

This repository stores the Python scripts used to prepare CRMLS listing and sold datasets for later analysis and Tableau dashboard work. Raw MLS data files are kept locally.

Week 0 - MLS Data Pipeline Orientation:
- Downloaded the monthly CRMLS listing and sold CSV files.
- Organized the raw files locally in `raw data/`.
- Confirmed monthly coverage from `202401` through `202605` for both listing and sold data.

Week 1 - Monthly Dataset Aggregation:
- Created `scripts/combine_monthly_files.py`.
- Combined monthly listing files into one unfiltered listing dataset.
- Combined monthly sold files into one unfiltered sold dataset.
- Created Residential-only filtered versions of both datasets.
- Created row-count reports showing monthly totals and Residential-filtered totals.
