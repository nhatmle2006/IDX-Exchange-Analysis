"""Build and execute the Week 6 feature-engineering report."""

import os
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient
from nbconvert import HTMLExporter


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_DIR = ROOT / "notebooks"
NOTEBOOK_PATH = NOTEBOOK_DIR / "Week_6_Report.ipynb"
HTML_PATH = NOTEBOOK_DIR / "Week_6_Report.html"


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
        "version": "3.12",
    },
}

notebook["cells"] = [
    markdown(
        """
# Week 6 Feature Engineering and Market Metrics

**IDX Exchange Data Analyst Internship**<br>
**Analysis period:** January 2024 through June 2026

This report documents the market features added to the cleaned California
Residential datasets, the California Department of Education school-district
assignment, and the resulting market and competitive segments.

### Report Guide

1. **Engineered Market Fields** defines every metric and its exact formula.
2. **Populated Sample** shows those fields on real sold records.
3. **School-District Enrichment** explains the geographic assignment.
4. **Market Segmentation Fields** defines every field used to group results.
5. **Segment Results** compares property, geography, and office groups.
6. **Validation** confirms row preservation and identifies Week 7 review items.
"""
    ),
    code(
        """
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from IPython.display import HTML, display


ROOT = Path.cwd()
if ROOT.name == "notebooks":
    ROOT = ROOT.parent

FEATURE_DIR = ROOT / "data" / "features"

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
"""
    ),
    code(
        """
validation = pd.read_csv(FEATURE_DIR / "week6_validation_summary.csv")
sample = pd.read_csv(FEATURE_DIR / "week6_feature_sample.csv")
county = pd.read_csv(FEATURE_DIR / "week6_county_summary.csv")
mls_area = pd.read_csv(FEATURE_DIR / "week6_mls_area_summary.csv")
property_type = pd.read_csv(FEATURE_DIR / "week6_property_type_summary.csv")
subtype = pd.read_csv(FEATURE_DIR / "week6_property_subtype_summary.csv")
offices = pd.read_csv(FEATURE_DIR / "week6_office_summary.csv")
districts = pd.read_csv(FEATURE_DIR / "week6_school_district_summary.csv")

required_reports = {
    "validation": validation,
    "sample": sample,
    "county": county,
    "MLS area": mls_area,
    "property type": property_type,
    "property subtype": subtype,
    "offices": offices,
    "school districts": districts,
}
assert all(not report.empty for report in required_reports.values())


def validation_value(dataset, field):
    match = validation[validation["dataset"].eq(dataset)]
    if match.empty:
        raise KeyError(f"Missing validation row: {dataset}")
    return match.iloc[0][field]


print("Week 6 report inputs loaded successfully.")
"""
    ),
    markdown("## Completion Snapshot"),
    code(
        """
sold_rows = int(validation_value("sold_residential", "output_rows"))
ratio_rows = int(
    validation_value("sold_residential", "price_ratio_populated")
)
ppsf_rows = int(
    validation_value("sold_residential", "price_per_sq_ft_populated")
)
district_rows = int(
    validation_value("sold_residential", "any_cde_district_populated")
)

snapshot_html = f'''
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:8px 0 18px 0;">
  <div style="border-top:5px solid {COLORS["teal"]};padding:16px;background:#F7FAFA;">
    <div style="color:{COLORS["gray"]};font-size:13px;">Feature-Ready Sold Rows</div>
    <div style="color:{COLORS["ink"]};font-size:28px;font-weight:700;">{sold_rows:,}</div>
  </div>
  <div style="border-top:5px solid {COLORS["blue"]};padding:16px;background:#F7F9FB;">
    <div style="color:{COLORS["gray"]};font-size:13px;">Price Ratios Populated</div>
    <div style="color:{COLORS["ink"]};font-size:28px;font-weight:700;">{ratio_rows:,}</div>
  </div>
  <div style="border-top:5px solid {COLORS["amber"]};padding:16px;background:#FFFBF3;">
    <div style="color:{COLORS["gray"]};font-size:13px;">PPSF Values Populated</div>
    <div style="color:{COLORS["ink"]};font-size:28px;font-weight:700;">{ppsf_rows:,}</div>
  </div>
  <div style="border-top:5px solid {COLORS["green"]};padding:16px;background:#F5FAF6;">
    <div style="color:{COLORS["gray"]};font-size:13px;">CDE District Matches</div>
    <div style="color:{COLORS["ink"]};font-size:28px;font-weight:700;">{district_rows:,}</div>
  </div>
</div>
'''
display(HTML(snapshot_html))
"""
    ),
    markdown(
        """
## Engineered Market Fields: Quick Reference

Ratios are stored as decimals so Tableau can format them as percentages.
Invalid or missing denominators remain blank. Negative date intervals are
retained and counted for later data-quality review rather than silently
deleted.

**Important:** `PriceRatio` and `CloseToOriginalListRatio` use the same formula
because that is how both fields are defined in the internship handbook. They
are stored as separate columns for their different dashboard labels, but their
values are currently identical.
"""
    ),
    code(
        """
metric_definitions = pd.DataFrame(
    [
        {
            "Metric": "Price Ratio",
            "Saved Column": "PriceRatio",
            "Exact Calculation": "ClosePrice / OriginalListPrice",
            "What It Tells Us": "Measures negotiation strength",
            "Sold Rows Populated": validation_value(
                "sold_residential", "price_ratio_populated"
            ),
        },
        {
            "Metric": "Price Per Sq Ft",
            "Saved Column": "PricePerSqFt",
            "Exact Calculation": "ClosePrice / LivingArea",
            "What It Tells Us": "Normalizes price across property sizes",
            "Sold Rows Populated": validation_value(
                "sold_residential", "price_per_sq_ft_populated"
            ),
        },
        {
            "Metric": "Days on Market",
            "Saved Column": "DaysOnMarket",
            "Exact Calculation": "DaysOnMarket (raw MLS field)",
            "What It Tells Us": "Time-to-sell indicator",
            "Sold Rows Populated": sold_rows,
        },
        {
            "Metric": "Year / Month / YrMo",
            "Saved Column": "Year, Month, YrMo",
            "Exact Calculation": "Derived from CloseDate",
            "What It Tells Us": "Enables time-series analysis",
            "Sold Rows Populated": validation_value(
                "sold_residential", "yrmo_populated"
            ),
        },
        {
            "Metric": "Close to Original List Ratio",
            "Saved Column": "CloseToOriginalListRatio",
            "Exact Calculation": "ClosePrice / OriginalListPrice",
            "What It Tells Us": "Captures full price-reduction history",
            "Sold Rows Populated": validation_value(
                "sold_residential", "price_ratio_populated"
            ),
        },
        {
            "Metric": "Listing to Contract Days",
            "Saved Column": "ListingToContractDays",
            "Exact Calculation": (
                "PurchaseContractDate - ListingContractDate"
            ),
            "What It Tells Us": (
                "Measures time from listing to accepted offer"
            ),
            "Sold Rows Populated": validation_value(
                "sold_residential",
                "listing_to_contract_days_populated",
            ),
        },
        {
            "Metric": "Contract to Close Days",
            "Saved Column": "ContractToCloseDays",
            "Exact Calculation": "CloseDate - PurchaseContractDate",
            "What It Tells Us": "Escrow and closing period duration",
            "Sold Rows Populated": validation_value(
                "sold_residential",
                "contract_to_close_days_populated",
            ),
        },
    ]
)

display(
    metric_definitions.style
    .hide(axis="index")
    .format({"Sold Rows Populated": "{:,.0f}"})
)
"""
    ),
    markdown(
        """
### How to Read the Ratios

- **1.00** means the property closed at its original list price.
- **Above 1.00** means the property closed above its original list price.
- **Below 1.00** means the property closed below its original list price.

For example, a ratio of **0.97** means the closing price was 97% of the
original list price. A ratio of **1.03** means it closed 3% above the original
list price.
"""
    ),
    markdown("### Populated Sample"),
    code(
        """
sample_columns = [
    "ListingId",
    "CountyOrParish",
    "PropertySubType",
    "ClosePrice",
    "PriceRatio",
    "PricePerSqFt",
    "DaysOnMarket",
    "YrMo",
    "ListingToContractDays",
    "ContractToCloseDays",
    "CDEElementarySchoolDistrict",
    "CDEHighSchoolDistrict",
    "CDEUnifiedSchoolDistrict",
]
sample_display = sample[sample_columns].head(12)

display(
    sample_display.style
    .hide(axis="index")
    .format(
        {
            "ClosePrice": "${:,.0f}",
            "PriceRatio": "{:.3f}",
            "PricePerSqFt": "${:,.2f}",
            "DaysOnMarket": "{:,.0f}",
            "ListingToContractDays": "{:,.0f}",
            "ContractToCloseDays": "{:,.0f}",
        },
        na_rep="",
    )
)
"""
    ),
    markdown(
        """
## School-District Enrichment

The 2024-25 California Department of Education layer contains 937 polygons:
516 elementary, 76 high, and 345 unified districts. District types are stored
in separate CDE-prefixed columns because elementary and high service areas
overlap by design. The original MLS `HighSchoolDistrict` field remains
unchanged.
"""
    ),
    code(
        """
district_quality = pd.DataFrame(
    [
        {
            "Dataset": "Residential Listings",
            "Total Rows": validation_value(
                "listings_residential", "output_rows"
            ),
            "Coordinate Coverage": (
                validation_value(
                    "listings_residential", "valid_coordinate_rows"
                )
                / validation_value("listings_residential", "output_rows")
            ),
            "District Match Rate": (
                validation_value(
                    "listings_residential",
                    "any_cde_district_populated",
                )
                / validation_value(
                    "listings_residential", "valid_coordinate_rows"
                )
            ),
            "Coordinates Without Match": validation_value(
                "listings_residential", "valid_coordinate_rows"
            )
            - validation_value(
                "listings_residential",
                "any_cde_district_populated",
            ),
        },
        {
            "Dataset": "Residential Sold",
            "Total Rows": validation_value(
                "sold_residential", "output_rows"
            ),
            "Coordinate Coverage": (
                validation_value(
                    "sold_residential", "valid_coordinate_rows"
                )
                / validation_value("sold_residential", "output_rows")
            ),
            "District Match Rate": (
                validation_value(
                    "sold_residential", "any_cde_district_populated"
                )
                / validation_value(
                    "sold_residential", "valid_coordinate_rows"
                )
            ),
            "Coordinates Without Match": validation_value(
                "sold_residential", "valid_coordinate_rows"
            )
            - validation_value(
                "sold_residential",
                "any_cde_district_populated",
            ),
        },
    ]
)

display(HTML("<h3>School-district match coverage</h3>"))
display(
    district_quality.style
    .hide(axis="index")
    .format(
        {
            "Total Rows": "{:,.0f}",
            "Coordinate Coverage": "{:.2%}",
            "District Match Rate": "{:.2%}",
            "Coordinates Without Match": "{:,.0f}",
        }
    )
)
"""
    ),
    markdown(
        """
### District Boundary Overlap Review

- **Separate Elementary + High districts** is a normal structure: one district
  serves elementary grades and another serves high-school grades.
- **Elementary + Unified boundary overlap** is less common and is retained as a
  review flag. It does not create duplicate property rows.
"""
    ),
    code(
        """
district_overlap = pd.DataFrame(
    [
        {
            "Dataset": "Residential Listings",
            "Separate Elementary + High Districts": validation_value(
                "listings_residential",
                "cde_elementary_and_high_overlap",
            ),
            "Elementary + Unified Boundary Review": validation_value(
                "listings_residential",
                "cde_elementary_and_unified_overlap",
            ),
        },
        {
            "Dataset": "Residential Sold",
            "Separate Elementary + High Districts": validation_value(
                "sold_residential",
                "cde_elementary_and_high_overlap",
            ),
            "Elementary + Unified Boundary Review": validation_value(
                "sold_residential",
                "cde_elementary_and_unified_overlap",
            ),
        },
    ]
)

display(
    district_overlap.style
    .hide(axis="index")
    .format(
        {
            "Separate Elementary + High Districts": "{:,.0f}",
            "Elementary + Unified Boundary Review": "{:,.0f}",
        }
    )
)
"""
    ),
    code(
        """
district_top = (
    districts.sort_values(
        ["DistrictType", "ClosedSales"],
        ascending=[True, False],
    )
    .groupby("DistrictType", group_keys=False)
    .head(5)
)

display(HTML("<h3>Five largest sold segments by district type</h3>"))
display(
    district_top[
        [
            "DistrictType",
            "SchoolDistrict",
            "ClosedSales",
            "MedianClosePrice",
            "MedianPricePerSqFt",
            "MedianDaysOnMarket",
            "MedianCloseToOriginalListRatio",
        ]
    ]
    .style
    .hide(axis="index")
    .format(
        {
            "ClosedSales": "{:,.0f}",
            "MedianClosePrice": "${:,.0f}",
            "MedianPricePerSqFt": "${:,.2f}",
            "MedianDaysOnMarket": "{:,.0f}",
            "MedianCloseToOriginalListRatio": "{:.3f}",
        },
        na_rep="",
    )
)
"""
    ),
    markdown(
        """
## Market Segmentation Fields

These fields do not create new measurements. They divide the sold records into
groups so the same market metrics can be compared across property categories,
locations, and competing offices.
"""
    ),
    code(
        """
segment_definitions = pd.DataFrame(
    [
        {
            "Analysis Category": "Property",
            "Primary Field": "PropertyType",
            "Detailed Field": "PropertySubType",
            "What the Fields Identify": (
                "Broad property category and its more specific subtype"
            ),
            "Dashboard Use": (
                "Compare prices, market time, and sale-to-list performance "
                "across property categories"
            ),
        },
        {
            "Analysis Category": "Geography",
            "Primary Field": "CountyOrParish",
            "Detailed Field": "MLSAreaMajor",
            "What the Fields Identify": (
                "County-level market and the more detailed MLS market area"
            ),
            "Dashboard Use": (
                "Compare broader county trends with local-area performance"
            ),
        },
        {
            "Analysis Category": "Competitive Intelligence",
            "Primary Field": "ListOfficeName",
            "Detailed Field": "BuyerOfficeName",
            "What the Fields Identify": (
                "Office representing the seller and office representing "
                "the buyer"
            ),
            "Dashboard Use": (
                "Compare office transaction volume and performance on both "
                "sides of a sale"
            ),
        },
    ]
)

display(segment_definitions.style.hide(axis="index"))
"""
    ),
    markdown(
        """
## Segment Results

### Property: `PropertyType` and `PropertySubType`

`PropertyType` is the broad category. Because the approved analysis scope is
Residential only, it also confirms that non-residential records are excluded.
`PropertySubType` provides the useful detail, such as single-family residence,
condominium, or townhouse.
"""
    ),
    code(
        """
residential_sales = int(
    property_type.loc[
        property_type["PropertyType"].eq("Residential"),
        "ClosedSales",
    ].sum()
)
display(
    HTML(
        f'''
        <div style="border-left:5px solid {COLORS["teal"]};padding:12px 16px;background:#F7FAFA;margin:8px 0 18px 0;">
          <strong>PropertyType scope:</strong> Residential only
          <span style="color:{COLORS["gray"]};">({residential_sales:,} sold records)</span>
        </div>
        '''
    )
)

display(HTML("<h4>Largest PropertySubType segments</h4>"))
subtype_ranked = subtype[
    ~subtype["PropertySubType"].fillna("").str.strip().str.lower().isin(
        ["", "missing", "unknown", "n/a"]
    )
].head(12)
display(
    subtype_ranked.style
    .hide(axis="index")
    .format(
        {
            "ClosedSales": "{:,.0f}",
            "MedianClosePrice": "${:,.0f}",
            "MedianPricePerSqFt": "${:,.2f}",
            "MedianDaysOnMarket": "{:,.0f}",
            "MedianCloseToOriginalListRatio": "{:.3f}",
            "MedianListingToContractDays": "{:,.0f}",
            "MedianContractToCloseDays": "{:,.0f}",
        },
        na_rep="",
    )
)
"""
    ),
    markdown(
        """
### Geography: `CountyOrParish` and `MLSAreaMajor`

`CountyOrParish` supports broad regional comparisons. `MLSAreaMajor` provides
a more local market view within those larger regions.
"""
    ),
    code(
        """
county_top = county.head(12).copy()
display(HTML("<h4>Largest CountyOrParish sold segments</h4>"))
display(
    county_top.style
    .hide(axis="index")
    .format(
        {
            "ClosedSales": "{:,.0f}",
            "MedianClosePrice": "${:,.0f}",
            "MedianPricePerSqFt": "${:,.2f}",
            "MedianDaysOnMarket": "{:,.0f}",
            "MedianCloseToOriginalListRatio": "{:.3f}",
            "MedianListingToContractDays": "{:,.0f}",
            "MedianContractToCloseDays": "{:,.0f}",
        },
        na_rep="",
    )
)
"""
    ),
    code(
        """
chart = county_top.sort_values("MedianClosePrice")
fig, ax = plt.subplots(figsize=(10, 6))
ax.barh(
    chart["CountyOrParish"],
    chart["MedianClosePrice"],
    color=COLORS["teal"],
)
ax.set_title("Median Close Price - Largest County Segments")
ax.set_xlabel("Median Close Price")
ax.set_ylabel("")
ax.xaxis.set_major_formatter(
    plt.FuncFormatter(lambda value, _: f"${value / 1_000_000:.1f}M")
)
ax.grid(axis="x", alpha=0.2)
plt.tight_layout()
plt.show()
"""
    ),
    code(
        """
mls_area_labels = mls_area["MLSAreaMajor"].fillna("").str.strip()
undefined_area = (
    mls_area_labels.str.lower().isin(["", "missing", "unknown", "n/a"])
    | mls_area_labels.str.contains("not defined", case=False, na=False)
)
undefined_area_rows = int(mls_area.loc[undefined_area, "ClosedSales"].sum())
undefined_area_rate = undefined_area_rows / sold_rows
mls_area_ranked = mls_area.loc[~undefined_area].head(15)

display(
    HTML(
        f'''
        <div style="border-left:5px solid {COLORS["amber"]};padding:12px 16px;background:#FFFBF3;margin:8px 0 18px 0;">
          <strong>MLS-area quality note:</strong> {undefined_area_rows:,} sold records
          ({undefined_area_rate:.1%}) have a missing or undefined MLSAreaMajor.
          They remain in the dataset but are excluded from this ranking.
        </div>
        '''
    )
)
display(HTML("<h4>Largest defined MLSAreaMajor sold segments</h4>"))
display(
    mls_area_ranked.style
    .hide(axis="index")
    .format(
        {
            "ClosedSales": "{:,.0f}",
            "MedianClosePrice": "${:,.0f}",
            "MedianPricePerSqFt": "${:,.2f}",
            "MedianDaysOnMarket": "{:,.0f}",
            "MedianCloseToOriginalListRatio": "{:.3f}",
            "MedianListingToContractDays": "{:,.0f}",
            "MedianContractToCloseDays": "{:,.0f}",
        },
        na_rep="",
    )
)
"""
    ),
    markdown(
        """
### Competitive Intelligence: `ListOfficeName` and `BuyerOfficeName`

`ListOfficeName` identifies the office representing the seller.
`BuyerOfficeName` identifies the office representing the buyer. Comparing both
fields shows which offices are most active and how their transactions perform
on each side of the market.
"""
    ),
    code(
        """
office_labels = offices["OfficeName"].fillna("").str.strip()
undefined_office = office_labels.str.lower().isin(
    ["", "missing", "unknown", "n/a"]
)
undefined_office_rows = int(
    offices.loc[undefined_office, "ClosedSales"].sum()
)
office_top = (
    offices.loc[~undefined_office]
    .sort_values(
        ["OfficeRole", "ClosedSales"],
        ascending=[True, False],
    )
    .groupby("OfficeRole", group_keys=False)
    .head(10)
)

display(
    HTML(
        f'''
        <div style="border-left:5px solid {COLORS["amber"]};padding:12px 16px;background:#FFFBF3;margin:8px 0 18px 0;">
          <strong>Office quality note:</strong> {undefined_office_rows:,}
          office-side records have a missing or unknown office name.
          They remain in the dataset but are excluded from this ranking.
        </div>
        '''
    )
)
display(HTML("<h4>Largest listing-side and buyer-side office segments</h4>"))
display(
    office_top[
        [
            "OfficeRole",
            "OfficeName",
            "ClosedSales",
            "MedianClosePrice",
            "MedianDaysOnMarket",
            "MedianCloseToOriginalListRatio",
        ]
    ]
    .style
    .hide(axis="index")
    .format(
        {
            "ClosedSales": "{:,.0f}",
            "MedianClosePrice": "${:,.0f}",
            "MedianDaysOnMarket": "{:,.0f}",
            "MedianCloseToOriginalListRatio": "{:.3f}",
        },
        na_rep="",
    )
)
"""
    ),
    markdown(
        """
## Validation and Week 7 Carryover

No rows were removed during feature engineering. `PriceRatio` and
`CloseToOriginalListRatio` were verified as identical, as required by the
handbook formulas. Negative timeline intervals remain available for review.
Extreme price, PPSF, ratio, and days-on-market values remain unfiltered because
outlier treatment is the Week 7 task.
"""
    ),
    code(
        """
validation_display = validation[
    [
        "dataset",
        "input_rows",
        "output_rows",
        "rows_preserved",
        "price_ratio_columns_equal",
        "listing_to_contract_negative",
        "contract_to_close_negative",
    ]
].copy()
validation_display.columns = [
    "Dataset",
    "Input Rows",
    "Output Rows",
    "Rows Preserved",
    "Ratio Columns Equal",
    "Negative Listing-to-Contract",
    "Negative Contract-to-Close",
]

display(
    validation_display.style
    .hide(axis="index")
    .format(
        {
            "Input Rows": "{:,.0f}",
            "Output Rows": "{:,.0f}",
            "Negative Listing-to-Contract": "{:,.0f}",
            "Negative Contract-to-Close": "{:,.0f}",
        }
    )
)
"""
    ),
    markdown(
        """
## Week 6 Outputs

- `listings_residential_features.csv`
- `sold_residential_market_features.csv`
- `week6_feature_sample.csv`
- `week6_county_summary.csv`
- `week6_mls_area_summary.csv`
- `week6_property_type_summary.csv`
- `week6_property_subtype_summary.csv`
- `week6_office_summary.csv`
- `week6_school_district_summary.csv`
- `week6_validation_summary.csv`

The feature-ready datasets are prepared for Week 7 outlier review and later
Tableau dashboard construction.
"""
    ),
    markdown(
        """
## Sources

- Cleaned CRMLS California Residential listing and sold datasets
- California Department of Education, California School District Areas
  2024-25
"""
    ),
]

NOTEBOOK_DIR.mkdir(parents=True, exist_ok=True)
nbf.write(notebook, NOTEBOOK_PATH)

client = NotebookClient(
    notebook,
    timeout=600,
    kernel_name=os.environ.get("WEEK6_KERNEL_NAME", "python3"),
    resources={"metadata": {"path": str(ROOT)}},
)
client.execute()
nbf.write(notebook, NOTEBOOK_PATH)

exporter = HTMLExporter()
exporter.exclude_input = True
exporter.exclude_input_prompt = True
exporter.exclude_output_prompt = True
html, _ = exporter.from_notebook_node(notebook)
HTML_PATH.write_text(html, encoding="utf-8")

print(f"Saved {NOTEBOOK_PATH}")
print(f"Saved {HTML_PATH}")
