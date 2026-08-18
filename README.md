# IDX-Exchange-Analysis

Summer 2026 IDX Exchange Data Analyst Internship

This repository stores the Python scripts used to prepare CRMLS listing and sold datasets for later analysis and Tableau dashboard work. Raw MLS data files are kept locally.

Week 0 - MLS Data Pipeline Orientation:
- Downloaded the monthly CRMLS listing and sold CSV files.
- Organized the raw files locally in `raw data/`.
- Confirmed monthly coverage from `202401` through `202607` for both listing and sold data.

Week 1 - Monthly Dataset Aggregation:
- Created `scripts/combine_monthly_files.py`.
- Combined monthly listing files into one unfiltered listing dataset.
- Combined monthly sold files into one unfiltered sold dataset.
- Created Residential-only filtered versions of both datasets.
- Verified and removed 11 exact duplicate columns from the monthly listing files.
- Created row-count reports showing monthly totals and Residential-filtered totals.

Week 2 - Dataset Validation:
- Created `scripts/dataset_validation.py`.
- Reviewed dataset dimensions, column types, and property-type distributions.
- Calculated missing counts and percentages for each field.
- Flagged fields with more than 90% missing data as drop recommendations when they do not support the Market Analysis or Competitive Analysis dashboards.
- Flagged fields with 50% to 90% missing data for usefulness review.
- Protected dashboard-relevant fields and created numeric summary reports for key MLS fields.

Week 3 - Exploratory Analysis and Mortgage Rate Enrichment:
- Created `scripts/exploratory_analysis.py`.
- Created numeric distribution summaries, histograms, and boxplots for key MLS fields.
- Reviewed sale-to-list performance, date consistency, and county-level median prices.
- Created `scripts/mortgage_rate_enrichment.py`.
- Added monthly mortgage rates to the Residential listing and sold datasets.
- Created `scripts/build_report_notebook.py`.
- Created `notebooks/Weeks_2_3_Report.ipynb` as a readable combined validation and market-analysis report.

Weeks 4-5 - Data Cleaning and Preparation:
- Created `scripts/data_cleaning_preparation.py`.
- Standardized date and numeric fields and removed columns with more than 90% missing data.
- Flagged invalid numeric values and date-order issues while keeping otherwise useful records.
- Limited the datasets to Residential properties using the official Census California boundary and a California state fallback for missing coordinates.
- Created cleaned listing and sold datasets, quality reports, and `notebooks/Weeks_4_5_Report.ipynb`.

Week 6 - Feature Engineering and Market Metrics:
- Created `scripts/feature_engineering.py`.
- Added price ratios, price per square foot, closing month fields, and contract timeline metrics.
- Assigned properties to official 2024-25 California school district boundaries using latitude and longitude.
- Created property type, property subtype, county, MLS area, office, and school district summaries.
- Created `notebooks/Week_6_Report.ipynb` as a readable feature-engineering report.

Week 7 - Outlier Detection and Data Quality:
- Created `scripts/outlier_detection.py`.
- Applied business rules and tiered IQR flags to key listing and sold fields.
- Preserved full flagged datasets and created separate analysis-ready filtered datasets.
- Compared dataset size, medians, and averages before and after filtering.
- Created `notebooks/Week_7_Report.ipynb` as a readable outlier-analysis report.

Week 8 - Tableau Data Preparation:
- Created `scripts/prepare_tableau_data.py` to produce streamlined Tableau sources from Residential California records using the 3.0 IQR extreme filter.
- Combined listing and sold activity into one market-analysis source while retaining the fields needed for metrics, geography, property filters, and school districts.
- Created `scripts/build_week8_tableau_workbook.py` and validated the initial Tableau worksheets and packaged extract.

Week 9 - California Market Pulse Dashboard:
- Created `scripts/build_market_pulse_dashboard.py` to generate and validate the first final dashboard.
- Built July 2026 KPI cards for median close price, new listings, closed sales, average days on market, and sale-to-original-list ratio.
- Added monthly price, market activity, days-on-market, sale ratio, and mortgage-rate trends with focused axes and shared county, city, and property-subtype filters.

Current Project Recap:
- The analysis covers January 2024 through July 2026 and uses Residential California properties for the dashboard population.
- The validated Tableau market source contains 1,006,536 listing and sold activity rows after applying the 3.0 IQR extreme-value filter.
- Raw data, generated CSV files, and packaged Tableau workbooks remain local; GitHub stores the reproducible Python scripts, reports, and documentation.

1st Dashboard: https://public.tableau.com/views/california_market_pulse_final/CaliforniaMarketPulse?:language=en-US&:sid=&:redirect=auth&:display_count=n&:origin=viz_share_link
