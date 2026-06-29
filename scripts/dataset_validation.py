"""Validate combined MLS datasets and create four readable quality reports.

Outputs:
- dataset_summary.csv: dataset size and Residential row counts
- property_type_counts.csv: property type breakdown before/after filtering
- field_quality_report.csv: column types, missing values, and review/drop guidance
- numeric_summary.csv: numeric distributions for price, size, and timing fields
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = PROJECT_ROOT / "data" / "processed"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "validation"
CHUNK_SIZE = 100_000
# Team guidance: review non-core fields when at least half their values are missing.
MISSING_DROP_REVIEW_THRESHOLD = 50.0

DATASET_FILES = {
    "listings_all": "combined_listings_all.csv",
    "sold_all": "combined_sold_all.csv",
    "listings_residential": "filtered_listings_residential.csv",
    "sold_residential": "filtered_sold_residential.csv",
}

CORE_ANALYSIS_FIELDS = {
    "PropertyType",
    "PropertySubType",
    "MlsStatus",
    "OriginalListPrice",
    "ListPrice",
    "ClosePrice",
    "LivingArea",
    "LotSizeAcres",
    "LotSizeSquareFeet",
    "BedroomsTotal",
    "BathroomsTotalInteger",
    "DaysOnMarket",
    "YearBuilt",
    "ListingContractDate",
    "PurchaseContractDate",
    "ContractStatusChangeDate",
    "CloseDate",
    "CountyOrParish",
    "City",
    "PostalCode",
    "StateOrProvince",
    "MLSAreaMajor",
    "Latitude",
    "Longitude",
    "ListOfficeName",
    "BuyerOfficeName",
    "ListAgentFullName",
    "BuyerAgentFullName",
}

NUMERIC_FIELDS = [
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

PRICE_FIELDS = {"ClosePrice", "ListPrice", "OriginalListPrice", "TaxAnnualAmount", "AssociationFee"}
DATE_FIELDS = {"CloseDate", "ListingContractDate", "PurchaseContractDate", "ContractStatusChangeDate"}
LOCATION_FIELDS = {
    "CountyOrParish",
    "City",
    "PostalCode",
    "StateOrProvince",
    "MLSAreaMajor",
    "Latitude",
    "Longitude",
    "UnparsedAddress",
    "StreetNumberNumeric",
}
PROPERTY_DETAIL_FIELDS = {
    "PropertyType",
    "PropertySubType",
    "LivingArea",
    "LotSizeAcres",
    "LotSizeSquareFeet",
    "LotSizeArea",
    "BedroomsTotal",
    "BathroomsTotalInteger",
    "YearBuilt",
    "Stories",
    "Levels",
    "GarageSpaces",
    "ParkingTotal",
    "FireplacesTotal",
    "NewConstructionYN",
    "PoolPrivateYN",
    "WaterfrontYN",
    "ViewYN",
    "BasementYN",
    "AttachedGarageYN",
}
AGENT_OFFICE_FIELDS = {
    "ListOfficeName",
    "BuyerOfficeName",
    "CoListOfficeName",
    "ListAgentFullName",
    "BuyerAgentFullName",
    "ListAgentFirstName",
    "ListAgentLastName",
    "BuyerAgentFirstName",
    "BuyerAgentLastName",
}
METADATA_NAMES = {
    "ListingKey",
    "ListingKeyNumeric",
    "ListingId",
    "BuyerAgentMlsId",
    "OriginatingSystemName",
    "OriginatingSystemSubName",
    "ListAgentEmail",
    "BuyerOfficeAOR",
    "BuyerAgentAOR",
    "ListAgentAOR",
    "BuyerAgencyCompensation",
    "BuyerAgencyCompensationType",
}


def base_column_name(column: str) -> str:
    """Remove pandas duplicate suffixes like .1 so duplicate source fields group together."""
    return re.sub(r"\.\d+$", "", column)


def classify_column(column: str) -> tuple[str, str]:
    base = base_column_name(column)
    lower = base.lower()

    if base in PRICE_FIELDS:
        return "market_analysis", "price"
    if base in DATE_FIELDS:
        return "market_analysis", "date"
    if base in LOCATION_FIELDS:
        return "market_analysis", "location"
    if base in PROPERTY_DETAIL_FIELDS:
        return "market_analysis", "property_detail"
    if base in AGENT_OFFICE_FIELDS:
        return "market_analysis", "agent_office"
    if base in CORE_ANALYSIS_FIELDS:
        return "market_analysis", "core_analysis"
    if (
        base in METADATA_NAMES
        or lower.endswith("key")
        or lower.endswith("id")
        or lower.endswith("email")
        or lower.endswith("aor")
        or lower.startswith("originating")
        or "compensation" in lower
    ):
        return "metadata_admin", "system_or_identifier"

    return "review", "needs_manual_review"


def recommendation(base_column: str, field_group: str, missing_percent: float) -> str:
    is_core = base_column in CORE_ANALYSIS_FIELDS
    meets_missing_threshold = missing_percent >= MISSING_DROP_REVIEW_THRESHOLD

    if meets_missing_threshold and is_core:
        return "retain_core_field_review_missingness"
    if meets_missing_threshold:
        return "review_drop_candidate"
    if is_core:
        return "retain_core_field"
    if field_group == "metadata_admin":
        return "retain_if_needed_for_traceability"

    return "retain_for_now"


def property_type_counts(chunk: pd.DataFrame) -> pd.Series:
    if "PropertyType" not in chunk.columns:
        return pd.Series(dtype="int64")

    values = (
        chunk["PropertyType"]
        .astype("string")
        .fillna("[missing]")
        .str.strip()
        .replace("", "[blank]")
    )
    return values.value_counts(dropna=False)


def summarize_numeric_field(dataset_name: str, field: str, values: pd.Series, total_rows: int) -> dict[str, object]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    row: dict[str, object] = {
        "dataset": dataset_name,
        "field": field,
        "non_null_count": int(clean.size),
        "missing_or_non_numeric_count": int(total_rows - clean.size),
    }

    if clean.empty:
        row.update(
            {
                "min": "",
                "p01": "",
                "p05": "",
                "p25": "",
                "median": "",
                "mean": "",
                "p75": "",
                "p95": "",
                "p99": "",
                "max": "",
            }
        )
        return row

    quantiles = clean.quantile([0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99])
    row.update(
        {
            "min": round(float(clean.min()), 3),
            "p01": round(float(quantiles.loc[0.01]), 3),
            "p05": round(float(quantiles.loc[0.05]), 3),
            "p25": round(float(quantiles.loc[0.25]), 3),
            "median": round(float(quantiles.loc[0.5]), 3),
            "mean": round(float(clean.mean()), 3),
            "p75": round(float(quantiles.loc[0.75]), 3),
            "p95": round(float(quantiles.loc[0.95]), 3),
            "p99": round(float(quantiles.loc[0.99]), 3),
            "max": round(float(clean.max()), 3),
        }
    )
    return row


def analyze_dataset(dataset_name: str, csv_path: Path, chunk_size: int) -> dict[str, list[dict[str, object]]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing input file: {csv_path}")

    header = pd.read_csv(csv_path, nrows=0)
    columns = list(header.columns)
    sample = pd.read_csv(csv_path, nrows=10_000, low_memory=False)
    sample_dtypes = {column: str(dtype) for column, dtype in sample.dtypes.items()}

    missing_counts = pd.Series(0, index=columns, dtype="int64")
    property_counts = pd.Series(dtype="int64")
    numeric_values: dict[str, list[pd.Series]] = {
        field: [] for field in NUMERIC_FIELDS if field in columns
    }
    total_rows = 0

    print(f"Analyzing {dataset_name}: {csv_path.name}")
    for chunk in pd.read_csv(csv_path, chunksize=chunk_size, low_memory=False):
        total_rows += len(chunk)
        missing_counts = missing_counts.add(chunk.isna().sum(), fill_value=0).astype("int64")

        counts = property_type_counts(chunk)
        if not counts.empty:
            property_counts = property_counts.add(counts, fill_value=0).astype("int64")

        for field in numeric_values:
            numeric_values[field].append(pd.to_numeric(chunk[field], errors="coerce"))

    duplicate_base_columns = sum(
        1 for column in columns if re.search(r"\.\d+$", column)
    )
    residential_rows = int(property_counts.get("Residential", 0)) if not property_counts.empty else ""

    dataset_summary = [
        {
            "dataset": dataset_name,
            "source_file": csv_path.name,
            "rows": total_rows,
            "columns": len(columns),
            "duplicate_base_columns": duplicate_base_columns,
            "property_type_column_found": "PropertyType" in columns,
            "residential_rows": residential_rows,
        }
    ]

    column_profile: list[dict[str, object]] = []
    for column in columns:
        base = base_column_name(column)
        field_group, field_category = classify_column(column)
        missing_count = int(missing_counts[column])
        missing_percent = round((missing_count / total_rows) * 100, 2) if total_rows else 0.0

        column_profile.append(
            {
                "dataset": dataset_name,
                "column": column,
                "base_column": base,
                "sample_dtype": sample_dtypes.get(column, ""),
                "field_group": field_group,
                "field_category": field_category,
                "is_core_analysis_field": base in CORE_ANALYSIS_FIELDS,
                "non_null_count": int(total_rows - missing_count),
                "missing_count": missing_count,
                "missing_percent": missing_percent,
                "over_90_percent_missing": missing_percent > 90,
                "at_or_over_50_percent_missing": (
                    missing_percent >= MISSING_DROP_REVIEW_THRESHOLD
                ),
                "recommended_action": recommendation(base, field_group, missing_percent),
            }
        )

    property_type_report = [
        {
            "dataset": dataset_name,
            "PropertyType": property_type,
            "rows": int(rows),
            "percent_of_dataset": round((int(rows) / total_rows) * 100, 2) if total_rows else 0.0,
        }
        for property_type, rows in property_counts.sort_values(ascending=False).items()
    ]

    numeric_summary: list[dict[str, object]] = []
    for field, series_parts in numeric_values.items():
        all_values = pd.concat(series_parts, ignore_index=True) if series_parts else pd.Series(dtype="float64")
        numeric_summary.append(summarize_numeric_field(dataset_name, field, all_values, total_rows))

    return {
        "dataset_summary": dataset_summary,
        "column_profile": column_profile,
        "property_type_report": property_type_report,
        "numeric_summary": numeric_summary,
    }


def write_report(rows: list[dict[str, object]], output_path: Path, sort_by: list[str] | None = None) -> None:
    frame = pd.DataFrame(rows)
    if sort_by and not frame.empty:
        frame = frame.sort_values(sort_by)
    frame.to_csv(output_path, index=False)
    print(f"Saved {output_path}")


def sort_field_quality_report(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        rows,
        key=lambda row: (
            str(row["dataset"]),
            not bool(row["at_or_over_50_percent_missing"]),
            -float(row["missing_percent"]),
            str(row["field_group"]),
            str(row["column"]),
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create four readable dataset validation reports."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Folder containing the combined and Residential-filtered CSV files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Folder where dataset validation reports should be saved.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=CHUNK_SIZE,
        help="Number of rows to process at a time.",
    )
    args = parser.parse_args()

    input_dir = args.input_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    all_dataset_summary: list[dict[str, object]] = []
    all_column_profiles: list[dict[str, object]] = []
    all_property_type_reports: list[dict[str, object]] = []
    all_numeric_summaries: list[dict[str, object]] = []

    for dataset_name, filename in DATASET_FILES.items():
        reports = analyze_dataset(dataset_name, input_dir / filename, args.chunk_size)
        all_dataset_summary.extend(reports["dataset_summary"])
        all_column_profiles.extend(reports["column_profile"])
        all_property_type_reports.extend(reports["property_type_report"])
        all_numeric_summaries.extend(reports["numeric_summary"])

    field_quality_report = sort_field_quality_report(all_column_profiles)

    write_report(
        all_dataset_summary,
        output_dir / "dataset_summary.csv",
        sort_by=["dataset"],
    )
    write_report(
        field_quality_report,
        output_dir / "field_quality_report.csv",
    )
    write_report(
        all_property_type_reports,
        output_dir / "property_type_counts.csv",
        sort_by=["dataset", "PropertyType"],
    )
    write_report(
        all_numeric_summaries,
        output_dir / "numeric_summary.csv",
        sort_by=["dataset", "field"],
    )

    print("\nDataset validation reports are complete.")
    print(f"Output folder: {output_dir}")


if __name__ == "__main__":
    main()
