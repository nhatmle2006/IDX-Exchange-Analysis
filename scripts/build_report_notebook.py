import base64
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient
from nbconvert import HTMLExporter


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_DIR = ROOT / "notebooks"
NOTEBOOK_PATH = NOTEBOOK_DIR / "Weeks_2_3_Report.ipynb"
HTML_PATH = NOTEBOOK_DIR / "Weeks_2_3_Report.html"
PREVIEW_DIR = ROOT / "tmp" / "week3-notebook-previews"


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
# Weeks 2-3 Residential Dataset Validation and Market Analysis

**IDX Exchange Data Analyst Internship**  
**Analysis period:** January 2024 through June 2026

Week 2 covers dataset validation and Week 3 covers exploratory analysis and
mortgage-rate enrichment. All market results are limited to **Residential
properties**, following the team's approved scope.
"""
    ),
    code(
        """
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from IPython.display import HTML, Image, display


ROOT = Path.cwd()
if ROOT.name == "notebooks":
    ROOT = ROOT.parent

ANALYSIS_DIR = ROOT / "data" / "analysis"
VALIDATION_DIR = ROOT / "data" / "validation"
ENRICHED_DIR = ROOT / "data" / "enriched"

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
market = pd.read_csv(ANALYSIS_DIR / "market_summary.csv")
counties = pd.read_csv(ANALYSIS_DIR / "county_price_summary.csv")
numeric = pd.read_csv(ANALYSIS_DIR / "numeric_distribution_summary.csv")
mortgage = pd.read_csv(ENRICHED_DIR / "mortgage_monthly_rates.csv")
merge_validation = pd.read_csv(ENRICHED_DIR / "mortgage_merge_validation.csv")
datasets = pd.read_csv(VALIDATION_DIR / "dataset_summary.csv")
property_types = pd.read_csv(VALIDATION_DIR / "property_type_counts.csv")
field_quality = pd.read_csv(VALIDATION_DIR / "field_quality_report.csv")

required_files = {
    "market summary": market,
    "county summary": counties,
    "numeric summary": numeric,
    "mortgage rates": mortgage,
    "merge validation": merge_validation,
    "dataset summary": datasets,
    "property types": property_types,
    "field quality": field_quality,
}
assert all(not frame.empty for frame in required_files.values())

print("Weeks 2-3 report inputs loaded successfully.")
"""
    ),
    markdown(
        """
## Week 2: Dataset Scope and Residential Filter

The monthly source files were first combined without removing any property
types. The team then approved a Residential-only analysis scope. The filtered
datasets therefore keep rows where `PropertyType == "Residential"`; the
unfiltered datasets remain available for validation and comparison.
"""
    ),
    code(
        """
scope = datasets[
    ["dataset", "rows", "columns", "residential_rows"]
].copy()
scope["residential_share_percent"] = (
    scope["residential_rows"] / scope["rows"] * 100
)
scope.columns = [
    "Dataset",
    "Rows",
    "Columns",
    "Residential Rows",
    "Residential Share (%)",
]

display(
    scope.style
    .hide(axis="index")
    .format(
        {
            "Rows": "{:,.0f}",
            "Columns": "{:,.0f}",
            "Residential Rows": "{:,.0f}",
            "Residential Share (%)": "{:.2f}%",
        }
    )
)
"""
    ),
    markdown(
        """
### Property Types Found

The original combined files include Residential Lease, Commercial, Land, and
other property types. Only Residential records are included in the analysis.
"""
    ),
    code(
        """
property_type_review = property_types[
    property_types["dataset"].isin(["listings_all", "sold_all"])
].copy()
property_type_review["included_in_analysis"] = (
    property_type_review["PropertyType"].eq("Residential")
)
property_type_review.columns = [
    "Dataset",
    "Property Type",
    "Rows",
    "Percent of Dataset",
    "Included in Analysis",
]

display(
    property_type_review.style
    .hide(axis="index")
    .format(
        {
            "Rows": "{:,.0f}",
            "Percent of Dataset": "{:.2f}%",
        }
    )
)
"""
    ),
    markdown(
        """
## Week 2: Dataset Structure and Field Roles

The validation script reviews column data types and separates likely market
analysis fields from metadata and fields needing manual review. This preserves
useful identifiers and core analysis fields while keeping the review organized.
"""
    ),
    code(
        """
type_summary = (
    field_quality.groupby(["dataset", "sample_dtype"], dropna=False)
    .size()
    .reset_index(name="field_count")
)
type_summary.columns = ["Dataset", "Sample Data Type", "Field Count"]

field_role_summary = (
    field_quality.groupby(["dataset", "field_group"], dropna=False)
    .size()
    .reset_index(name="field_count")
)
field_role_summary.columns = ["Dataset", "Field Group", "Field Count"]

display(HTML("<h3>Column data types</h3>"))
display(
    type_summary.style
    .hide(axis="index")
    .format({"Field Count": "{:,.0f}"})
)

display(HTML("<h3>Market-analysis and metadata field groups</h3>"))
display(
    field_role_summary.style
    .hide(axis="index")
    .format({"Field Count": "{:,.0f}"})
)
"""
    ),
    markdown(
        """
## Week 2: Missing Values and Drop-vs-Retain Review

`missing_percent` is the share of rows where a field is blank. For example,
100% missing means the column exists but has no values in that dataset version.

Two missing-value levels are intentionally shown:

- **Over 90% missing:** recommended to drop when the field does not support the
  Market Analysis or Competitive Analysis dashboard.
- **50% to 90% missing:** review for usefulness before keeping it in the final
  dashboard dataset.

Dashboard-relevant fields are retained or manually reviewed when they support
required metrics, filters, comparisons, or traceability.
"""
    ),
    code(
        """
missing_summary = (
    field_quality.groupby("dataset")
    .agg(
        total_fields=("column", "size"),
        fields_over_90_percent_missing=("over_90_percent_missing", "sum"),
        fields_50_to_90_percent_missing=(
            "between_50_and_90_percent_missing",
            "sum",
        ),
        fields_recommended_to_drop=(
            "recommended_action",
            lambda values: values.eq("drop_high_missing_field").sum(),
        ),
        optional_fields_for_review=(
            "recommended_action",
            lambda values: values.eq("review_optional_field_for_drop").sum(),
        ),
        dashboard_fields_needing_review=(
            "recommended_action",
            lambda values: values.isin(
                [
                    "review_before_drop_dashboard_field",
                    "retain_dashboard_field_review_missingness",
                ]
            ).sum(),
        ),
    )
    .reset_index()
)
missing_summary.columns = [
    "Dataset",
    "Total Fields",
    "Fields >90% Missing",
    "Fields 50%-90% Missing",
    "Drop Recommendations",
    "Optional Fields for Review",
    "Dashboard Fields for Review",
]

display(
    missing_summary.style
    .hide(axis="index")
    .format(
        {
            "Total Fields": "{:,.0f}",
            "Fields >90% Missing": "{:,.0f}",
            "Fields 50%-90% Missing": "{:,.0f}",
            "Drop Recommendations": "{:,.0f}",
            "Optional Fields for Review": "{:,.0f}",
            "Dashboard Fields for Review": "{:,.0f}",
        }
    )
)
"""
    ),
    code(
        """
high_missing_residential = field_quality[
    field_quality["dataset"].isin(
        ["listings_residential", "sold_residential"]
    )
    & field_quality["over_90_percent_missing"]
][
    [
        "dataset",
        "column",
        "field_group",
        "dashboard_relevance",
        "is_core_analysis_field",
        "non_null_count",
        "missing_count",
        "missing_percent",
        "recommended_action",
    ]
].sort_values(["dataset", "missing_percent", "column"], ascending=[True, False, True])

display(HTML("<h3>Residential fields over 90% missing</h3>"))
display(
    high_missing_residential.style
    .hide(axis="index")
    .format(
        {
            "non_null_count": "{:,.0f}",
            "missing_count": "{:,.0f}",
            "missing_percent": "{:.2f}%",
        }
    )
)
"""
    ),
    code(
        """
recommendation_counts = (
    field_quality.groupby("recommended_action")
    .size()
    .reset_index(name="field_dataset_combinations")
    .sort_values("field_dataset_combinations", ascending=False)
)
recommendation_counts.columns = [
    "Recommendation",
    "Field-Dataset Combinations",
]

dashboard_missing_review = field_quality[
    field_quality["recommended_action"].isin(
        [
            "review_before_drop_dashboard_field",
            "retain_dashboard_field_review_missingness",
        ]
    )
][
    [
        "dataset",
        "column",
        "dashboard_relevance",
        "missing_percent",
        "recommended_action",
    ]
].sort_values(["dataset", "missing_percent"], ascending=[True, False])

display(HTML("<h3>All retain/drop recommendations</h3>"))
display(
    recommendation_counts.style
    .hide(axis="index")
    .format({"Field-Dataset Combinations": "{:,.0f}"})
)

display(HTML("<h3>Dashboard fields retained or reviewed despite missingness</h3>"))
display(
    dashboard_missing_review.style
    .hide(axis="index")
    .format({"missing_percent": "{:.2f}%"})
)
"""
    ),
    code(
        """
complete_field_review = field_quality[
    [
        "dataset",
        "column",
        "sample_dtype",
        "field_group",
        "field_category",
        "dashboard_relevance",
        "is_core_analysis_field",
        "non_null_count",
        "missing_count",
        "missing_percent",
        "over_90_percent_missing",
        "between_50_and_90_percent_missing",
        "at_or_over_50_percent_missing",
        "recommended_action",
    ]
].copy()

complete_field_review["missing_percent"] = complete_field_review[
    "missing_percent"
].map(lambda value: f"{value:.2f}%")
for count_column in ["non_null_count", "missing_count"]:
    complete_field_review[count_column] = complete_field_review[
        count_column
    ].map(lambda value: f"{value:,.0f}")

complete_field_html = complete_field_review.to_html(
    index=False,
    border=0,
    classes="complete-field-review",
)
display(
    HTML(
        "<details><summary><b>Open the complete per-column field-quality "
        "review</b></summary><div style='overflow-x:auto;max-height:650px;"
        "overflow-y:auto;margin-top:10px;'>"
        + complete_field_html
        + "</div></details>"
    )
)
"""
    ),
    markdown(
        """
## Week 2 Outputs

- Dataset rows, columns, data types, and property types were documented.
- Market-analysis fields were separated from metadata/review fields.
- Missing counts and percentages were calculated for every column.
- Fields over 90% missing were marked as drop recommendations when they do not
  support the Market Analysis or Competitive Analysis dashboards.
- Fields with 50% to 90% missing values were marked for usefulness review.
- Dashboard-relevant fields were retained or manually reviewed when partly
  missing.
- Residential listing and sold CSVs were saved for subsequent analysis.
- Numeric summaries were generated for the required MLS fields, including
  `ClosePrice`, `LivingArea`, and `DaysOnMarket`.
"""
    ),
    markdown("## Week 3: Executive Dashboard"),
    code(
        """
def market_value(metric, dataset="sold_residential"):
    match = market[
        market["metric"].eq(metric)
        & market["dataset"].eq(dataset)
    ]
    if match.empty:
        raise KeyError(f"Missing metric: {dataset}/{metric}")
    return float(match.iloc[0]["value"])


residential_listings = int(
    datasets.loc[datasets["dataset"].eq("listings_residential"), "rows"].iloc[0]
)
residential_sales = int(
    datasets.loc[datasets["dataset"].eq("sold_residential"), "rows"].iloc[0]
)
median_sale_price = market_value("median_close_price")
median_dom = market_value("median_days_on_market")

dashboard_html = f'''
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:8px 0 18px 0;">
  <div style="border-top:5px solid {COLORS["teal"]};padding:16px;background:#F7FAFA;">
    <div style="color:{COLORS["gray"]};font-size:13px;">Residential Listings</div>
    <div style="color:{COLORS["ink"]};font-size:28px;font-weight:700;">{residential_listings:,}</div>
  </div>
  <div style="border-top:5px solid {COLORS["blue"]};padding:16px;background:#F7F9FB;">
    <div style="color:{COLORS["gray"]};font-size:13px;">Residential Sales</div>
    <div style="color:{COLORS["ink"]};font-size:28px;font-weight:700;">{residential_sales:,}</div>
  </div>
  <div style="border-top:5px solid {COLORS["amber"]};padding:16px;background:#FFFBF3;">
    <div style="color:{COLORS["gray"]};font-size:13px;">Median Sale Price</div>
    <div style="color:{COLORS["ink"]};font-size:28px;font-weight:700;">${median_sale_price:,.0f}</div>
  </div>
  <div style="border-top:5px solid {COLORS["green"]};padding:16px;background:#F4FAF5;">
    <div style="color:{COLORS["gray"]};font-size:13px;">Median Days on Market</div>
    <div style="color:{COLORS["ink"]};font-size:28px;font-weight:700;">{median_dom:,.0f} days</div>
  </div>
</div>
'''
display(HTML(dashboard_html))
"""
    ),
    code(
        """
snapshot = pd.DataFrame(
    {
        "Metric": [
            "Average sale price",
            "Median sale price",
            "Residential share of listings",
            "Residential share of sold records",
            "Mortgage merge match rate",
        ],
        "Result": [
            f"${market_value('average_close_price'):,.0f}",
            f"${market_value('median_close_price'):,.0f}",
            f"{market_value('residential_share', 'listings_all'):.2f}%",
            f"{market_value('residential_share', 'sold_all'):.2f}%",
            f"{merge_validation['match_percentage'].min():.1f}%",
        ],
        "Interpretation": [
            "Before outlier cleaning",
            "More representative than the mean because prices are skewed",
            "Residential records retained for analysis",
            "Residential records retained for analysis",
            "No MLS rows are missing a monthly mortgage rate",
        ],
    }
)

display(
    snapshot.style
    .hide(axis="index")
    .set_properties(**{"text-align": "left", "padding": "7px"})
    .set_table_styles(
        [{"selector": "th", "props": [
            ("background-color", COLORS["ink"]),
            ("color", "white"),
            ("text-align", "left"),
            ("padding", "8px"),
        ]}]
    )
)
"""
    ),
    markdown(
        """
## Week 3: Handbook Questions Answered

The Week 3 exploratory-analysis questions are answered below from the
Residential data. Values are reported before final outlier and data-quality
adjustments.
"""
    ),
    code(
        """
dom_row = numeric[
    numeric["dataset"].eq("sold_residential")
    & numeric["field"].eq("DaysOnMarket")
].iloc[0]

top_three_counties = counties.head(3)
county_answer = "; ".join(
    f"{row.CountyOrParish}: ${row.median_close_price:,.0f}"
    for row in top_three_counties.itertuples()
)

questions_answered = pd.DataFrame(
    {
        "Handbook Question": [
            "What share of records are Residential versus other types?",
            "What are the median and average Residential ClosePrice?",
            "What is the Residential DaysOnMarket distribution?",
            "What percentage sold above, at, or below list price?",
            "Are the key transaction dates internally consistent?",
            "Which counties have the highest median sale prices?",
        ],
        "Answer": [
            (
                f"Listings: {market_value('residential_share', 'listings_all'):.2f}% "
                f"Residential and {100 - market_value('residential_share', 'listings_all'):.2f}% other. "
                f"Sold: {market_value('residential_share', 'sold_all'):.2f}% "
                f"Residential and {100 - market_value('residential_share', 'sold_all'):.2f}% other."
            ),
            (
                f"Median: ${market_value('median_close_price'):,.0f}; "
                f"average: ${market_value('average_close_price'):,.2f}."
            ),
            (
                f"Median: {market_value('median_days_on_market'):,.0f} days; "
                f"average: {market_value('average_days_on_market'):.2f} days; "
                f"95th percentile: {dom_row['p95']:,.0f} days. "
                f"{market_value('negative_days_on_market_records'):,.0f} negative records need review."
            ),
            (
                f"Above list: {market_value('sold_above_list_price'):.2f}%; "
                f"at list: {market_value('sold_at_list_price'):.2f}%; "
                f"below list: {market_value('sold_below_list_price'):.2f}%."
            ),
            (
                f"Mostly, but exceptions need review: "
                f"{market_value('listing_after_close_records'):,.0f} listing-after-close, "
                f"{market_value('purchase_after_close_records'):,.0f} purchase-after-close, and "
                f"{market_value('listing_after_purchase_records'):,.0f} listing-after-purchase records."
            ),
            county_answer,
        ],
    }
)

display(
    questions_answered.style
    .hide(axis="index")
    .set_properties(**{
        "text-align": "left",
        "white-space": "normal",
        "max-width": "650px",
        "padding": "8px",
    })
    .set_table_styles(
        [{"selector": "th", "props": [
            ("background-color", COLORS["ink"]),
            ("color", "white"),
            ("text-align", "left"),
            ("padding", "8px"),
        ]}]
    )
)
"""
    ),
    markdown(
        """
## Sale-to-List Performance

The market was relatively balanced: the share of homes selling below list price
was only slightly higher than the share selling above list price.
"""
    ),
    code(
        """
sale_metrics = {
    "Above list": market_value("sold_above_list_price"),
    "At list": market_value("sold_at_list_price"),
    "Below list": market_value("sold_below_list_price"),
}

figure, axis = plt.subplots(figsize=(9, 4.5))
bars = axis.bar(
    sale_metrics.keys(),
    sale_metrics.values(),
    color=[COLORS["teal"], COLORS["amber"], COLORS["blue"]],
)
axis.set_title("Residential Sales Compared with List Price", weight="bold")
axis.set_ylabel("Share of valid sales")
axis.set_ylim(0, 50)
axis.spines[["top", "right"]].set_visible(False)
axis.grid(axis="y", alpha=0.2)

for bar, value in zip(bars, sale_metrics.values()):
    axis.text(
        bar.get_x() + bar.get_width() / 2,
        value + 1,
        f"{value:.1f}%",
        ha="center",
        weight="bold",
    )

plt.show()
"""
    ),
    markdown(
        """
## Price and Market-Time Distributions

The charts below display the 1st through 99th percentile range so that the main
distribution remains readable. Full minimum and maximum values are documented
under each chart and in the numeric appendix.
"""
    ),
    code(
        """
display(
    Image(
        filename=str(
            ANALYSIS_DIR / "plots" / "sold_residential_ClosePrice.png"
        )
    )
)
"""
    ),
    code(
        """
display(
    Image(
        filename=str(
            ANALYSIS_DIR / "plots" / "sold_residential_DaysOnMarket.png"
        )
    )
)
"""
    ),
    markdown(
        """
## County Comparison

Counties are included only when they have at least 30 valid Residential sales.
This prevents very small groups from dominating the ranking.
"""
    ),
    code(
        """
top_counties = counties.head(10).sort_values("median_close_price")

figure, axis = plt.subplots(figsize=(10, 5.5))
bars = axis.barh(
    top_counties["CountyOrParish"],
    top_counties["median_close_price"],
    color=COLORS["teal"],
)
axis.set_title("Top 10 Counties by Median Residential Sale Price", weight="bold")
axis.set_xlabel("Median sale price")
axis.spines[["top", "right"]].set_visible(False)
axis.grid(axis="x", alpha=0.2)
axis.xaxis.set_major_formatter(
    lambda value, position: f"${value / 1_000_000:.1f}M"
)

for bar, value in zip(bars, top_counties["median_close_price"]):
    axis.text(
        value,
        bar.get_y() + bar.get_height() / 2,
        f"  ${value / 1_000_000:.2f}M",
        va="center",
        fontsize=9,
    )

plt.show()
"""
    ),
    markdown(
        """
## Mortgage-Rate Trend

Weekly FRED `MORTGAGE30US` observations were averaged by calendar month.
Listings were matched using `ListingContractDate`; sold records were matched
using `CloseDate`.
"""
    ),
    code(
        """
mortgage_period = mortgage[
    mortgage["year_month"].between("2024-01", "2026-05")
].copy()
mortgage_period["month"] = pd.to_datetime(
    mortgage_period["year_month"] + "-01"
)

figure, axis = plt.subplots(figsize=(11, 4.8))
axis.plot(
    mortgage_period["month"],
    mortgage_period["rate_30yr_fixed"],
    color=COLORS["blue"],
    linewidth=2.5,
)
axis.set_title("Average 30-Year Fixed Mortgage Rate", weight="bold")
axis.set_ylabel("Rate (%)")
axis.set_ylim(5.5, 7.5)
axis.spines[["top", "right"]].set_visible(False)
axis.grid(alpha=0.2)
figure.autofmt_xdate()
plt.show()

display(
    merge_validation[
        [
            "dataset",
            "rows",
            "matched_rate_rows",
            "unmatched_rate_rows",
            "match_percentage",
            "status",
        ]
    ].style.hide(axis="index").format(
        {
            "rows": "{:,.0f}",
            "matched_rate_rows": "{:,.0f}",
            "unmatched_rate_rows": "{:,.0f}",
            "match_percentage": "{:.1f}%",
        }
    )
)
"""
    ),
    markdown(
        """
## Data-Quality Findings

These checks identify records that may require correction or exclusion. No
records were removed during Weeks 2-3.
"""
    ),
    code(
        """
quality_checks = pd.DataFrame(
    {
        "Check": [
            "Nonpositive Close Price",
            "Negative Days on Market",
            "Listing Date After Close",
            "Purchase Date After Close",
            "Listing Date After Purchase",
            "Missing Mortgage Rate",
        ],
        "Records": [
            int(market_value("nonpositive_close_price_records")),
            int(market_value("negative_days_on_market_records")),
            int(market_value("listing_after_close_records")),
            int(market_value("purchase_after_close_records")),
            int(market_value("listing_after_purchase_records")),
            int(merge_validation["unmatched_rate_rows"].sum()),
        ],
        "Status": ["Review", "Review", "Review", "Review", "Review", "Pass"],
        "Recommended Treatment": [
            "Remove or correct",
            "Flag and investigate",
            "Add date-order flag",
            "Add date-order flag",
            "Add timeline flag",
            "No action needed",
        ],
    }
)

def status_color(value):
    if value == "Review":
        return "background-color: #FDECEC; color: #B91C1C; font-weight: bold"
    return "background-color: #EAF7EE; color: #15803D; font-weight: bold"

display(
    quality_checks.style
    .hide(axis="index")
    .format({"Records": "{:,.0f}"})
    .map(status_color, subset=["Status"])
    .set_properties(**{"text-align": "left", "padding": "7px"})
)
"""
    ),
    markdown(
        """
## Numeric Appendix

The IQR bounds identify potential outliers for review. They are screening
thresholds, not automatic deletion rules.
"""
    ),
    code(
        """
appendix_fields = ["ClosePrice", "LivingArea", "DaysOnMarket"]
appendix = numeric[
    numeric["dataset"].eq("sold_residential")
    & numeric["field"].isin(appendix_fields)
][
    [
        "field",
        "non_null_count",
        "min",
        "median",
        "mean",
        "p99",
        "max",
        "below_iqr_bound_count",
        "above_iqr_bound_count",
    ]
].copy()

display(
    appendix.style
    .hide(axis="index")
    .format(
        {
            "non_null_count": "{:,.0f}",
            "min": "{:,.1f}",
            "median": "{:,.1f}",
            "mean": "{:,.1f}",
            "p99": "{:,.1f}",
            "max": "{:,.1f}",
            "below_iqr_bound_count": "{:,.0f}",
            "above_iqr_bound_count": "{:,.0f}",
        }
    )
)
"""
    ),
    code(
        """
complete_numeric = numeric[
    [
        "dataset",
        "field",
        "non_null_count",
        "missing_or_non_numeric_count",
        "min",
        "p01",
        "p25",
        "median",
        "mean",
        "p75",
        "p99",
        "max",
        "below_iqr_bound_count",
        "above_iqr_bound_count",
    ]
].copy()

for count_column in [
    "non_null_count",
    "missing_or_non_numeric_count",
    "below_iqr_bound_count",
    "above_iqr_bound_count",
]:
    complete_numeric[count_column] = complete_numeric[count_column].map(
        lambda value: f"{value:,.0f}"
    )

for value_column in [
    "min",
    "p01",
    "p25",
    "median",
    "mean",
    "p75",
    "p99",
    "max",
]:
    complete_numeric[value_column] = complete_numeric[value_column].map(
        lambda value: "" if pd.isna(value) else f"{value:,.2f}"
    )

complete_numeric_html = complete_numeric.to_html(
    index=False,
    border=0,
    classes="complete-numeric-review",
)
display(
    HTML(
        "<details><summary><b>Open the complete numeric summary for all "
        "required fields</b></summary><div style='overflow-x:auto;"
        "max-height:650px;overflow-y:auto;margin-top:10px;'>"
        + complete_numeric_html
        + "</div></details>"
    )
)
"""
    ),
    markdown(
        """
## Complete Numeric Distribution Plot Appendix

The exploratory-analysis script produced a histogram and boxplot for each of
the nine required numeric fields in both Residential datasets. Each image shows
the readable 1st-to-99th-percentile range and documents the full range and IQR
outlier counts underneath.
"""
    ),
    code(
        """
plot_fields = [
    "ClosePrice",
    "ListPrice",
    "OriginalListPrice",
    "LivingArea",
    "LotSizeAcres",
    "BedroomsTotal",
    "BathroomsTotalInteger",
    "DaysOnMarket",
    "YearBuilt",
]

for dataset_name, dataset_label in [
    ("listings_residential", "Residential Listings"),
    ("sold_residential", "Residential Sold"),
]:
    display(HTML(f"<h3>{dataset_label}</h3>"))
    for field in plot_fields:
        display(HTML(f"<h4>{field}</h4>"))
        display(
            Image(
                filename=str(
                    ANALYSIS_DIR
                    / "plots"
                    / f"{dataset_name}_{field}.png"
                )
            )
        )
"""
    ),
    markdown(
        """
## Sources

- CRMLS monthly listing and sold files, January 2024 through June 2026
- Federal Reserve Bank of St. Louis `MORTGAGE30US` series
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

PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
for preview_file in PREVIEW_DIR.glob("*.png"):
    preview_file.unlink()

preview_count = 0
for cell_index, cell in enumerate(notebook["cells"]):
    if cell["cell_type"] != "code":
        continue
    for output_index, output in enumerate(cell.get("outputs", [])):
        image_data = output.get("data", {}).get("image/png")
        if not image_data:
            continue
        preview_path = PREVIEW_DIR / (
            f"cell_{cell_index:02d}_output_{output_index:02d}.png"
        )
        preview_path.write_bytes(base64.b64decode(image_data))
        preview_count += 1

exporter = HTMLExporter()
exporter.exclude_input_prompt = True
exporter.exclude_output_prompt = True
html, _ = exporter.from_notebook_node(notebook)
HTML_PATH.write_text(html, encoding="utf-8")

print(f"Saved {NOTEBOOK_PATH}")
print(f"Saved {HTML_PATH}")
print(f"Saved {preview_count} embedded chart previews to {PREVIEW_DIR}")
