"""Build the executed Weeks 4-5 cleaning report and HTML copy."""

from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient
from nbconvert import HTMLExporter


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_DIR = ROOT / "notebooks"
NOTEBOOK_PATH = NOTEBOOK_DIR / "Weeks_4_5_Report.ipynb"
HTML_PATH = NOTEBOOK_DIR / "Weeks_4_5_Report.html"


def markdown(text: str):
    return nbf.v4.new_markdown_cell(text.strip())


def code(text: str):
    return nbf.v4.new_code_cell(text.strip())


notebook = nbf.v4.new_notebook()
notebook["metadata"] = {
    "kernelspec": {
        "display_name": "IDX Exchange (.venv)",
        "language": "python",
        "name": "python3",
    },
    "language_info": {
        "name": "python",
        "version": "3.14",
    },
}

notebook["cells"] = [
    markdown(
        """
# Weeks 4-5 Residential Data Cleaning and California Preparation

**IDX Exchange Data Analyst Internship**  
**Analysis period:** January 2024 through June 2026

This report documents the cleaning decisions applied after the Week 2
validation and Week 3 market analysis. It covers new June rows, removed
columns, invalid numeric values, date inconsistencies, and the final
California-only Residential datasets.
"""
    ),
    code(
        """
from pathlib import Path
import sys

import pandas as pd
from IPython.display import HTML, display


ROOT = Path.cwd()
if ROOT.name == "notebooks":
    ROOT = ROOT.parent

CLEANED_DIR = ROOT / "data" / "cleaned"
ENRICHED_DIR = ROOT / "data" / "enriched"
PROCESSED_DIR = ROOT / "data" / "processed"

COLORS = {
    "ink": "#1F2937",
    "teal": "#0F766E",
    "blue": "#1F6B8C",
    "amber": "#D97706",
    "red": "#B91C1C",
    "green": "#15803D",
    "gray": "#6B7280",
}

pd.set_option("display.max_columns", 30)
pd.set_option("display.float_format", lambda value: f"{value:,.2f}")
"""
    ),
    code(
        """
cleaning = pd.read_csv(CLEANED_DIR / "cleaning_summary.csv")
column_removals = pd.read_csv(CLEANED_DIR / "column_removal_report.csv")
data_types = pd.read_csv(CLEANED_DIR / "data_type_report.csv")
listing_months = pd.read_csv(
    PROCESSED_DIR / "combined_listings_row_counts.csv"
)
sold_months = pd.read_csv(PROCESSED_DIR / "combined_sold_row_counts.csv")

required_reports = {
    "cleaning summary": cleaning,
    "column removals": column_removals,
    "data types": data_types,
    "listing monthly counts": listing_months,
    "sold monthly counts": sold_months,
}
assert all(not report.empty for report in required_reports.values())


def cleaning_value(dataset, metric):
    match = cleaning[
        cleaning["dataset"].eq(dataset)
        & cleaning["metric"].eq(metric)
    ]
    if match.empty:
        raise KeyError(f"Missing cleaning metric: {dataset}/{metric}")
    return int(match.iloc[0]["value"])


print("Weeks 4-5 cleaning report inputs loaded successfully.")
"""
    ),
    markdown("## Final Cleaning Snapshot"),
    code(
        """
final_listings = cleaning_value("listings_residential", "output_rows")
final_sold = cleaning_value("sold_residential", "output_rows")
removed_rows = (
    cleaning_value("listings_residential", "rows_removed_total")
    + cleaning_value("sold_residential", "rows_removed_total")
)
removed_columns = (
    cleaning_value("listings_residential", "columns_removed")
    + cleaning_value("sold_residential", "columns_removed")
)

dashboard_html = f'''
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:8px 0 18px 0;">
  <div style="border-top:5px solid {COLORS["teal"]};padding:16px;background:#F7FAFA;">
    <div style="color:{COLORS["gray"]};font-size:13px;">Final California Listings</div>
    <div style="color:{COLORS["ink"]};font-size:28px;font-weight:700;">{final_listings:,}</div>
  </div>
  <div style="border-top:5px solid {COLORS["blue"]};padding:16px;background:#F7F9FB;">
    <div style="color:{COLORS["gray"]};font-size:13px;">Final California Sold</div>
    <div style="color:{COLORS["ink"]};font-size:28px;font-weight:700;">{final_sold:,}</div>
  </div>
  <div style="border-top:5px solid {COLORS["amber"]};padding:16px;background:#FFFBF3;">
    <div style="color:{COLORS["gray"]};font-size:13px;">Rows Removed</div>
    <div style="color:{COLORS["ink"]};font-size:28px;font-weight:700;">{removed_rows:,}</div>
  </div>
  <div style="border-top:5px solid {COLORS["red"]};padding:16px;background:#FFF7F7;">
    <div style="color:{COLORS["gray"]};font-size:13px;">Columns Removed</div>
    <div style="color:{COLORS["ink"]};font-size:28px;font-weight:700;">{removed_columns:,}</div>
  </div>
</div>
'''
display(HTML(dashboard_html))
"""
    ),
    markdown(
        """
## June 2026 Data Addition

The June monthly files were added before cleaning. Only the Residential rows
continued into the Weeks 4-5 process.
"""
    ),
    code(
        """
june_rows = pd.concat(
    [
        listing_months[
            pd.to_numeric(listing_months["month"], errors="coerce").eq(202606)
        ],
        sold_months[
            pd.to_numeric(sold_months["month"], errors="coerce").eq(202606)
        ],
    ],
    ignore_index=True,
)[
    ["group", "file", "total_rows", "residential_rows", "non_residential_rows"]
].copy()
june_rows.columns = [
    "Dataset",
    "June Source File",
    "New Rows",
    "New Residential Rows",
    "New Non-Residential Rows",
]

display(
    june_rows.style
    .hide(axis="index")
    .format(
        {
            "New Rows": "{:,.0f}",
            "New Residential Rows": "{:,.0f}",
            "New Non-Residential Rows": "{:,.0f}",
        }
    )
)
"""
    ),
    markdown(
        """
## Week 4: Cleaning Decisions

The cleaning script converted the required date and numeric fields, removed
fields with more than 90% missing data, and flagged invalid numeric values.
Missing values were left blank instead of being filled with estimates.
"""
    ),
    code(
        """
cleaning_overview = pd.DataFrame(
    [
        {
            "Dataset": "Residential Listings",
            "Rows Before": cleaning_value("listings_residential", "source_rows"),
            "Rows After": cleaning_value("listings_residential", "output_rows"),
            "Rows Removed": cleaning_value("listings_residential", "rows_removed_total"),
            "Columns Before": cleaning_value("listings_residential", "source_columns"),
            "Columns Removed": cleaning_value("listings_residential", "columns_removed"),
            "Final Columns": cleaning_value("listings_residential", "output_columns"),
        },
        {
            "Dataset": "Residential Sold",
            "Rows Before": cleaning_value("sold_residential", "source_rows"),
            "Rows After": cleaning_value("sold_residential", "output_rows"),
            "Rows Removed": cleaning_value("sold_residential", "rows_removed_total"),
            "Columns Before": cleaning_value("sold_residential", "source_columns"),
            "Columns Removed": cleaning_value("sold_residential", "columns_removed"),
            "Final Columns": cleaning_value("sold_residential", "output_columns"),
        },
    ]
)
cleaning_overview["Rows Removed (%)"] = (
    cleaning_overview["Rows Removed"]
    / cleaning_overview["Rows Before"]
    * 100
)

display(
    cleaning_overview.style
    .hide(axis="index")
    .format(
        {
            "Rows Before": "{:,.0f}",
            "Rows After": "{:,.0f}",
            "Rows Removed": "{:,.0f}",
            "Columns Before": "{:,.0f}",
            "Columns Removed": "{:,.0f}",
            "Final Columns": "{:,.0f}",
            "Rows Removed (%)": "{:.3f}%",
        }
    )
)
"""
    ),
    markdown(
        """
### Invalid Numeric Values

Each invalid value was replaced with blank/missing while the property row was
retained. The flag columns identify affected records in the cleaned datasets.
"""
    ),
    code(
        """
numeric_rules = [
    ("ClosePrice", "Zero or below", "nonpositive", "close_price_nonpositive_flag"),
    ("LivingArea", "Zero or below", "nonpositive", "living_area_nonpositive_flag"),
    ("DaysOnMarket", "Below zero", "negative", "days_on_market_negative_flag"),
    ("BedroomsTotal", "Below zero", "negative", "bedrooms_negative_flag"),
    (
        "BathroomsTotalInteger",
        "Below zero",
        "negative",
        "bathrooms_negative_flag",
    ),
]

numeric_replacements = pd.DataFrame(
    [
        {
            "Field": field,
            "Invalid Rule": rule,
            "Listings Flagged": cleaning_value("listings_residential", flag),
            "Sold Flagged": cleaning_value("sold_residential", flag),
            "Replacement": "Blank/missing; row retained",
        }
        for field, rule, comparison, flag in numeric_rules
    ]
)

display(
    numeric_replacements.style
    .hide(axis="index")
    .format(
        {
            "Listings Flagged": "{:,.0f}",
            "Sold Flagged": "{:,.0f}",
        }
    )
)
"""
    ),
    code(
        """
scripts_path = str(ROOT / "scripts")
if scripts_path not in sys.path:
    sys.path.insert(0, scripts_path)

from data_cleaning_preparation import points_in_california


source_files = {
    "Residential Listings": ENRICHED_DIR / "listings_residential_with_mortgage_rates.csv",
    "Residential Sold": ENRICHED_DIR / "sold_residential_with_mortgage_rates.csv",
}
invalid_examples = []

for dataset_label, source_path in source_files.items():
    fields = [field for field, _, _, _ in numeric_rules]
    source = pd.read_csv(
        source_path,
        usecols=fields + ["StateOrProvince", "Latitude", "Longitude"],
        low_memory=False,
    )
    latitude = pd.to_numeric(source["Latitude"], errors="coerce")
    longitude = pd.to_numeric(source["Longitude"], errors="coerce")
    state = (
        source["StateOrProvince"]
        .astype("string")
        .str.strip()
        .str.upper()
        .fillna("")
    )
    has_coordinates = latitude.notna() & longitude.notna()
    california_rows = points_in_california(longitude, latitude) | (
        ~has_coordinates & state.eq("CA")
    )
    source = source.loc[california_rows]

    for field, rule, comparison, flag in numeric_rules:
        values = pd.to_numeric(source[field], errors="coerce")
        invalid = values.le(0) if comparison == "nonpositive" else values.lt(0)
        for invalid_value, occurrences in (
            values[invalid.fillna(False)].value_counts().head(8).items()
        ):
            invalid_examples.append(
                {
                    "Dataset": dataset_label,
                    "Field": field,
                    "Invalid Value": invalid_value,
                    "Occurrences": int(occurrences),
                    "Cleaned Value": "Blank/missing",
                }
            )

invalid_examples = pd.DataFrame(invalid_examples)
display(HTML("<h4>Invalid values actually found</h4>"))
display(
    invalid_examples.style
    .hide(axis="index")
    .format({"Invalid Value": "{:,.2f}", "Occurrences": "{:,.0f}"})
)
"""
    ),
    markdown(
        """
### Columns Removed

These are the only columns removed under the more-than-90%-missing rule.
"""
    ),
    code(
        """
removed_columns = column_removals.copy()
removed_columns.columns = [
    "Dataset",
    "Removed Column",
    "Reason",
    "Missing Rows",
    "Missing Percent",
]

display(
    removed_columns.style
    .hide(axis="index")
    .format({"Missing Rows": "{:,.0f}", "Missing Percent": "{:.2f}%"})
)
"""
    ),
    markdown(
        """
### Data Types and Missing Values

Dates were parsed and saved as `YYYY-MM-DD`. Key prices, property fields,
coordinates, timing fields, and mortgage rates were converted to numeric
values. No nonblank values failed conversion.
"""
    ),
    code(
        """
conversion_summary = (
    data_types.groupby("dataset")
    .agg(
        fields_confirmed=("column", "count"),
        conversion_failures=(
            "nonblank_values_that_failed_conversion",
            "sum",
        ),
    )
    .reset_index()
)
conversion_summary.columns = [
    "Dataset",
    "Date and Numeric Fields Confirmed",
    "Nonblank Conversion Failures",
]

display(
    conversion_summary.style
    .hide(axis="index")
    .format(
        {
            "Date and Numeric Fields Confirmed": "{:,.0f}",
            "Nonblank Conversion Failures": "{:,.0f}",
        }
    )
)

complete_types_html = data_types.to_html(index=False, border=0)
display(
    HTML(
        "<details><summary><b>Open complete data-type report</b></summary>"
        "<div style='overflow-x:auto;max-height:500px;overflow-y:auto;"
        "margin-top:10px;'>"
        + complete_types_html
        + "</div></details>"
    )
)
"""
    ),
    markdown(
        """
## Week 5: California-Only Filter

Coordinates are the primary location check. Rows with missing coordinates are
kept only when the original state is `CA`. Rows whose coordinates confirm
California but whose state label is wrong are corrected to `CA`; the original
label is retained in `StateOrProvinceOriginal`.
"""
    ),
    code(
        """
california_flow = pd.DataFrame(
    [
        {
            "Dataset": "Residential Listings",
            "Starting Rows": cleaning_value("listings_residential", "source_rows"),
            "Kept by Coordinates": cleaning_value("listings_residential", "rows_inside_california_boundary"),
            "Kept by CA State Fallback": cleaning_value("listings_residential", "rows_kept_by_ca_state_fallback"),
            "Removed Outside CA": cleaning_value("listings_residential", "rows_removed_outside_california"),
            "Removed Missing Coordinates/Non-CA": cleaning_value("listings_residential", "rows_removed_missing_coordinates_non_ca_state"),
            "State Labels Corrected": cleaning_value("listings_residential", "state_labels_corrected_from_coordinates"),
            "Final Rows": cleaning_value("listings_residential", "output_rows"),
        },
        {
            "Dataset": "Residential Sold",
            "Starting Rows": cleaning_value("sold_residential", "source_rows"),
            "Kept by Coordinates": cleaning_value("sold_residential", "rows_inside_california_boundary"),
            "Kept by CA State Fallback": cleaning_value("sold_residential", "rows_kept_by_ca_state_fallback"),
            "Removed Outside CA": cleaning_value("sold_residential", "rows_removed_outside_california"),
            "Removed Missing Coordinates/Non-CA": cleaning_value("sold_residential", "rows_removed_missing_coordinates_non_ca_state"),
            "State Labels Corrected": cleaning_value("sold_residential", "state_labels_corrected_from_coordinates"),
            "Final Rows": cleaning_value("sold_residential", "output_rows"),
        },
    ]
)

display(
    california_flow.style
    .hide(axis="index")
    .format(
        {
            column: "{:,.0f}"
            for column in california_flow.columns
            if column != "Dataset"
        }
    )
)
"""
    ),
    code(
        """
removed_states = cleaning[
    cleaning["category"].eq("removed_state_label")
][["dataset", "metric", "value"]].copy()
removed_states.columns = ["Dataset", "Original State Label", "Rows Removed"]
removed_states = removed_states.sort_values(
    ["Dataset", "Rows Removed"],
    ascending=[True, False],
)

display(HTML("<h3>Original state labels among removed rows</h3>"))
display(
    removed_states.style
    .hide(axis="index")
    .format({"Rows Removed": "{:,.0f}"})
)
"""
    ),
    markdown(
        """
### Geographic Data Quality

Zero coordinates and positive longitudes are invalid for California and were
excluded by the coordinate boundary. Missing-coordinate rows retained through
the CA-state fallback remain flagged in the final datasets.
"""
    ),
    code(
        """
geographic_metrics = {
    "rows_missing_coordinates": "Rows Missing Coordinates",
    "zero_coordinate_rows": "Zero-Coordinate Rows",
    "positive_longitude_rows": "Positive-Longitude Rows",
}
geographic_rows = []
for dataset_name, dataset_label in [
    ("listings_residential", "Residential Listings"),
    ("sold_residential", "Residential Sold"),
]:
    for metric, label in geographic_metrics.items():
        geographic_rows.append(
            {
                "Dataset": dataset_label,
                "Check": label,
                "Rows": cleaning_value(dataset_name, metric),
            }
        )

geographic_review = pd.DataFrame(geographic_rows)
display(
    geographic_review.style
    .hide(axis="index")
    .format({"Rows": "{:,.0f}"})
)
"""
    ),
    markdown(
        """
### Date and Timeline Inconsistencies

Timeline issues are flagged rather than automatically deleted because the row
may still contain useful price, location, or competitive-analysis information.
"""
    ),
    code(
        """
cleaned_files = {
    "Residential Listings": (
        "listings_residential",
        CLEANED_DIR / "listings_residential_california_clean.csv",
    ),
    "Residential Sold": (
        "sold_residential",
        CLEANED_DIR / "sold_residential_california_clean.csv",
    ),
}
timeline_rows = []

for dataset_label, (dataset_name, cleaned_path) in cleaned_files.items():
    dates = pd.read_csv(
        cleaned_path,
        usecols=["ListingContractDate", "PurchaseContractDate", "CloseDate"],
    )
    for field in dates.columns:
        dates[field] = pd.to_datetime(dates[field], errors="coerce")
    listing_after_purchase = (
        dates["ListingContractDate"] > dates["PurchaseContractDate"]
    ).sum()

    timeline_rows.extend(
        [
            {
                "Dataset": dataset_label,
                "Inconsistency": "Listing date after close date",
                "Flagged Rows": cleaning_value(dataset_name, "listing_after_close_flag"),
            },
            {
                "Dataset": dataset_label,
                "Inconsistency": "Purchase date after close date",
                "Flagged Rows": cleaning_value(dataset_name, "purchase_after_close_flag"),
            },
            {
                "Dataset": dataset_label,
                "Inconsistency": "Listing date after purchase date",
                "Flagged Rows": int(listing_after_purchase),
            },
            {
                "Dataset": dataset_label,
                "Inconsistency": "Any out-of-order timeline",
                "Flagged Rows": cleaning_value(dataset_name, "negative_timeline_flag"),
            },
        ]
    )

timeline_review = pd.DataFrame(timeline_rows)
timeline_review["Treatment"] = "Flagged; row retained"
display(
    timeline_review.style
    .hide(axis="index")
    .format({"Flagged Rows": "{:,.0f}"})
)
"""
    ),
    markdown(
        """
## Final Outputs

- `listings_residential_california_clean.csv`
- `sold_residential_california_clean.csv`
- `cleaning_summary.csv`
- `column_removal_report.csv`
- `data_type_report.csv`

The cleaned datasets are ready for the next analysis and Tableau preparation
steps.
"""
    ),
    markdown(
        """
## Sources

- CRMLS monthly listing and sold files, January 2024 through June 2026
- Mortgage-enriched Residential listing and sold datasets
- Week 4-5 cleaning summaries and California-only output datasets
"""
    ),
]

NOTEBOOK_DIR.mkdir(parents=True, exist_ok=True)
nbf.write(notebook, NOTEBOOK_PATH)

client = NotebookClient(
    notebook,
    timeout=300,
    kernel_name="python3",
    resources={"metadata": {"path": str(ROOT)}},
)
client.execute()
nbf.write(notebook, NOTEBOOK_PATH)

exporter = HTMLExporter()
exporter.exclude_input_prompt = True
exporter.exclude_output_prompt = True
html, _ = exporter.from_notebook_node(notebook)
HTML_PATH.write_text(html, encoding="utf-8")

print(f"Saved {NOTEBOOK_PATH}")
print(f"Saved {HTML_PATH}")
