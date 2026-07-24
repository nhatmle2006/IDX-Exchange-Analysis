"""Clean the Residential MLS datasets for analysis and Tableau.

The script keeps California properties, standardizes analysis fields, removes
columns with more than 90% missing data, and records every cleaning decision in
small audit reports. Source files are never overwritten.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

import matplotlib.path as mpath
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = PROJECT_ROOT / "data" / "enriched"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "cleaned"
CHUNK_SIZE = 100_000
MISSING_DROP_THRESHOLD = 90.0
CALIFORNIA_BOUNDARY_PATH = (
    PROJECT_ROOT / "reference" / "california_boundary_2025.geojson"
)

DATASETS = {
    "listings_residential": {
        "input_file": "listings_residential_with_mortgage_rates.csv",
        "output_file": "listings_residential_california_clean.csv",
    },
    "sold_residential": {
        "input_file": "sold_residential_with_mortgage_rates.csv",
        "output_file": "sold_residential_california_clean.csv",
    },
}

DATE_FIELDS = [
    "CloseDate",
    "PurchaseContractDate",
    "ListingContractDate",
    "ContractStatusChangeDate",
]

NUMERIC_FIELDS = [
    "ClosePrice",
    "ListPrice",
    "OriginalListPrice",
    "LivingArea",
    "LotSizeAcres",
    "LotSizeSquareFeet",
    "BedroomsTotal",
    "BathroomsTotalInteger",
    "DaysOnMarket",
    "YearBuilt",
    "Latitude",
    "Longitude",
    "rate_30yr_fixed",
]

INVALID_VALUE_RULES = {
    "ClosePrice": ("close_price_nonpositive_flag", "nonpositive"),
    "LivingArea": ("living_area_nonpositive_flag", "nonpositive"),
    "DaysOnMarket": ("days_on_market_negative_flag", "negative"),
    "BedroomsTotal": ("bedrooms_negative_flag", "negative"),
    "BathroomsTotalInteger": ("bathrooms_negative_flag", "negative"),
}

@lru_cache(maxsize=1)
def california_boundary_paths() -> tuple[
    tuple[mpath.Path, tuple[mpath.Path, ...]], ...
]:
    """Load the official Census California boundary once per script run."""
    if not CALIFORNIA_BOUNDARY_PATH.exists():
        raise FileNotFoundError(
            f"Missing California boundary file: {CALIFORNIA_BOUNDARY_PATH}"
        )

    boundary_data = json.loads(
        CALIFORNIA_BOUNDARY_PATH.read_text(encoding="utf-8")
    )
    geometry = boundary_data["features"][0]["geometry"]
    polygons = (
        geometry["coordinates"]
        if geometry["type"] == "MultiPolygon"
        else [geometry["coordinates"]]
    )

    paths: list[tuple[mpath.Path, tuple[mpath.Path, ...]]] = []
    for polygon in polygons:
        exterior = mpath.Path(np.asarray(polygon[0], dtype=float))
        holes = tuple(
            mpath.Path(np.asarray(ring, dtype=float)) for ring in polygon[1:]
        )
        paths.append((exterior, holes))
    return tuple(paths)


def points_in_california(longitude: pd.Series, latitude: pd.Series) -> pd.Series:
    """Return True for coordinates inside the official California boundary."""
    x = pd.to_numeric(longitude, errors="coerce")
    y = pd.to_numeric(latitude, errors="coerce")
    x_values = x.to_numpy(dtype=float)
    y_values = y.to_numpy(dtype=float)
    points = np.column_stack([x_values, y_values])
    usable = np.isfinite(x_values) & np.isfinite(y_values)
    inside = np.zeros(len(points), dtype=bool)

    for exterior, holes in california_boundary_paths():
        polygon_inside = exterior.contains_points(points, radius=1e-10)
        for hole in holes:
            polygon_inside &= ~hole.contains_points(points, radius=-1e-10)
        inside |= polygon_inside

    inside &= usable
    return pd.Series(inside, index=x.index)


def normalized_state(values: pd.Series) -> pd.Series:
    return values.astype("string").str.strip().str.upper().fillna("")


def profile_columns(
    input_path: Path,
    chunk_size: int,
) -> tuple[list[str], int, pd.Series]:
    """Count rows and missing values before deciding which columns to remove."""
    columns = list(pd.read_csv(input_path, nrows=0).columns)
    missing_counts = pd.Series(0, index=columns, dtype="int64")
    total_rows = 0

    for chunk in pd.read_csv(input_path, chunksize=chunk_size, low_memory=False):
        total_rows += len(chunk)
        missing_counts = missing_counts.add(
            chunk.isna().sum(),
            fill_value=0,
        ).astype("int64")

    return columns, total_rows, missing_counts


def columns_to_remove(
    columns: list[str],
    total_rows: int,
    missing_counts: pd.Series,
) -> tuple[set[str], list[dict[str, object]]]:
    removed: set[str] = set()
    report_rows: list[dict[str, object]] = []

    for column in columns:
        missing_count = int(missing_counts[column])
        missing_percent = (
            round(missing_count / total_rows * 100, 2) if total_rows else 0.0
        )
        base_column = re.sub(r"\.\d+$", "", column)
        duplicate_column = base_column != column and base_column in columns
        high_missing = missing_percent > MISSING_DROP_THRESHOLD

        if duplicate_column:
            reason = "redundant duplicate column"
        elif high_missing:
            reason = "more than 90% missing"
        else:
            continue

        removed.add(column)
        report_rows.append(
            {
                "column": column,
                "reason": reason,
                "missing_count": missing_count,
                "missing_percent": missing_percent,
            }
        )

    return removed, report_rows


def invalid_value_mask(values: pd.Series, rule: str) -> pd.Series:
    if rule == "nonpositive":
        return values.le(0).fillna(False)
    return values.lt(0).fillna(False)


def add_timeline_flags(chunk: pd.DataFrame) -> None:
    listing_date = chunk.get(
        "ListingContractDate",
        pd.Series(pd.NaT, index=chunk.index),
    )
    purchase_date = chunk.get(
        "PurchaseContractDate",
        pd.Series(pd.NaT, index=chunk.index),
    )
    close_date = chunk.get(
        "CloseDate",
        pd.Series(pd.NaT, index=chunk.index),
    )

    chunk["listing_after_close_flag"] = listing_date.gt(close_date).fillna(False)
    chunk["purchase_after_close_flag"] = purchase_date.gt(close_date).fillna(False)
    listing_after_purchase = listing_date.gt(purchase_date).fillna(False)
    chunk["negative_timeline_flag"] = (
        chunk["listing_after_close_flag"]
        | chunk["purchase_after_close_flag"]
        | listing_after_purchase
    )


def clean_dataset(
    dataset_name: str,
    input_path: Path,
    output_path: Path,
    chunk_size: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    if not input_path.exists():
        raise FileNotFoundError(f"Missing input file: {input_path}")

    columns, source_rows, missing_counts = profile_columns(input_path, chunk_size)
    required_geo_fields = {"StateOrProvince", "Latitude", "Longitude"}
    missing_geo_fields = required_geo_fields - set(columns)
    if missing_geo_fields:
        fields = ", ".join(sorted(missing_geo_fields))
        raise ValueError(f"{input_path.name} is missing geographic fields: {fields}")

    removed_columns, column_report = columns_to_remove(
        columns,
        source_rows,
        missing_counts,
    )
    for row in column_report:
        row["dataset"] = dataset_name

    counters: Counter[str] = Counter()
    removed_states: Counter[str] = Counter()
    parse_failures: Counter[str] = Counter()
    flag_counts: Counter[str] = Counter()
    output_rows = 0
    wrote_header = False

    print(f"Cleaning {dataset_name}: {input_path.name}")
    print(f"Dropping {len(removed_columns)} columns")

    for chunk in pd.read_csv(input_path, chunksize=chunk_size, low_memory=False):
        chunk = chunk.drop(columns=list(removed_columns), errors="ignore")
        counters["source_rows"] += len(chunk)

        original_state = chunk["StateOrProvince"].copy()
        state = normalized_state(original_state)

        for field in DATE_FIELDS:
            if field not in chunk.columns:
                continue
            source_not_blank = (
                chunk[field].notna()
                & chunk[field].astype("string").str.strip().ne("")
            )
            parsed = pd.to_datetime(chunk[field], errors="coerce")
            parse_failures[field] += int((source_not_blank & parsed.isna()).sum())
            chunk[field] = parsed

        for field in NUMERIC_FIELDS:
            if field not in chunk.columns:
                continue
            source_not_blank = (
                chunk[field].notna()
                & chunk[field].astype("string").str.strip().ne("")
            )
            parsed = pd.to_numeric(chunk[field], errors="coerce")
            parse_failures[field] += int((source_not_blank & parsed.isna()).sum())
            chunk[field] = parsed.astype("float64")

        add_timeline_flags(chunk)

        for field, (flag_name, rule) in INVALID_VALUE_RULES.items():
            if field not in chunk.columns:
                chunk[flag_name] = False
                continue
            invalid = invalid_value_mask(chunk[field], rule)
            chunk[flag_name] = invalid
            chunk.loc[invalid, field] = pd.NA

        latitude = chunk["Latitude"]
        longitude = chunk["Longitude"]
        has_coordinates = latitude.notna() & longitude.notna()
        in_california = points_in_california(longitude, latitude)
        state_fallback = ~has_coordinates & state.eq("CA")
        keep = in_california | state_fallback

        zero_coordinates = has_coordinates & (latitude.eq(0) | longitude.eq(0))
        positive_longitude = has_coordinates & longitude.gt(0)
        coordinate_state_corrections = in_california & state.ne("CA")
        outside_coordinates = has_coordinates & ~in_california
        removed_missing_coordinates = ~has_coordinates & ~state.eq("CA")

        counters["rows_with_coordinates"] += int(has_coordinates.sum())
        counters["rows_missing_coordinates"] += int((~has_coordinates).sum())
        counters["rows_inside_california_boundary"] += int(in_california.sum())
        counters["rows_kept_by_ca_state_fallback"] += int(state_fallback.sum())
        counters["rows_removed_outside_california"] += int(outside_coordinates.sum())
        counters["rows_removed_missing_coordinates_non_ca_state"] += int(
            removed_missing_coordinates.sum()
        )
        counters["state_labels_corrected_from_coordinates"] += int(
            coordinate_state_corrections.sum()
        )
        counters["zero_coordinate_rows"] += int(zero_coordinates.sum())
        counters["positive_longitude_rows"] += int(positive_longitude.sum())

        removed_state_values = state.where(state.ne(""), "MISSING")[~keep]
        removed_states.update(removed_state_values.tolist())

        cleaned = chunk.loc[keep].copy()
        cleaned["StateOrProvinceOriginal"] = original_state.loc[keep]
        cleaned["StateOrProvince"] = "CA"
        cleaned["missing_coordinates_flag"] = ~has_coordinates.loc[keep]
        cleaned["california_filter_method"] = "coordinates"
        cleaned.loc[
            state_fallback.loc[keep],
            "california_filter_method",
        ] = "state_fallback_missing_coordinates"

        for flag_name in [
            "listing_after_close_flag",
            "purchase_after_close_flag",
            "negative_timeline_flag",
            "close_price_nonpositive_flag",
            "living_area_nonpositive_flag",
            "days_on_market_negative_flag",
            "bedrooms_negative_flag",
            "bathrooms_negative_flag",
            "missing_coordinates_flag",
        ]:
            flag_counts[flag_name] += int(cleaned[flag_name].sum())

        output_rows += len(cleaned)
        cleaned.to_csv(
            output_path,
            index=False,
            mode="a" if wrote_header else "w",
            header=not wrote_header,
            date_format="%Y-%m-%d",
        )
        wrote_header = True

    counters["output_rows"] = output_rows
    counters["rows_removed_total"] = source_rows - output_rows
    counters["source_columns"] = len(columns)
    counters["columns_removed"] = len(removed_columns)
    counters["output_columns"] = (
        len(pd.read_csv(output_path, nrows=0).columns) if output_path.exists() else 0
    )

    summary_rows: list[dict[str, object]] = []
    metric_details = {
        "source_rows": ("row_count", "Residential rows before cleaning"),
        "output_rows": ("row_count", "California-only rows after cleaning"),
        "rows_removed_total": ("row_count", "Rows excluded by the California rule"),
        "source_columns": ("column_count", "Columns before cleaning"),
        "columns_removed": ("column_count", "Redundant or >90% missing columns removed"),
        "output_columns": ("column_count", "Columns after cleaning and adding quality flags"),
        "rows_with_coordinates": ("geographic_quality", "Rows with usable latitude and longitude"),
        "rows_missing_coordinates": ("geographic_quality", "Rows missing latitude or longitude"),
        "rows_inside_california_boundary": ("geographic_quality", "Rows kept using the official Census California boundary"),
        "rows_kept_by_ca_state_fallback": ("geographic_quality", "Missing-coordinate rows kept because state was CA"),
        "rows_removed_outside_california": ("geographic_quality", "Rows with present coordinates that are invalid or outside the official California boundary"),
        "rows_removed_missing_coordinates_non_ca_state": ("geographic_quality", "Rows without coordinates and without a CA state label"),
        "state_labels_corrected_from_coordinates": ("geographic_quality", "Rows inside California whose original state label was not CA"),
        "zero_coordinate_rows": ("geographic_quality", "Rows with latitude or longitude equal to zero"),
        "positive_longitude_rows": ("geographic_quality", "Rows with an invalid positive longitude"),
    }
    for metric, (category, notes) in metric_details.items():
        summary_rows.append(
            {
                "dataset": dataset_name,
                "category": category,
                "metric": metric,
                "value": counters[metric],
                "notes": notes,
            }
        )

    flag_notes = {
        "listing_after_close_flag": "Timeline issue in the final California dataset; row retained for review",
        "purchase_after_close_flag": "Timeline issue in the final California dataset; row retained for review",
        "negative_timeline_flag": "Any out-of-order listing, purchase, or close date in the final California dataset",
        "missing_coordinates_flag": "Row retained because its state label was CA",
    }
    for flag_name, count in sorted(flag_counts.items()):
        summary_rows.append(
            {
                "dataset": dataset_name,
                "category": "quality_flag",
                "metric": flag_name,
                "value": count,
                "notes": flag_notes.get(
                    flag_name,
                    "Invalid value count in the final California dataset; value changed to missing",
                ),
            }
        )

    for state_name, count in sorted(removed_states.items()):
        summary_rows.append(
            {
                "dataset": dataset_name,
                "category": "removed_state_label",
                "metric": state_name,
                "value": count,
                "notes": "Original state labels among rows excluded by the California rule",
            }
        )

    data_type_rows: list[dict[str, object]] = []
    for field in DATE_FIELDS:
        if field in columns and field not in removed_columns:
            data_type_rows.append(
                {
                    "dataset": dataset_name,
                    "column": field,
                    "cleaning_type": "datetime64[ns]",
                    "csv_format": "YYYY-MM-DD",
                    "nonblank_values_that_failed_conversion": parse_failures[field],
                }
            )
    for field in NUMERIC_FIELDS:
        if field in columns and field not in removed_columns:
            data_type_rows.append(
                {
                    "dataset": dataset_name,
                    "column": field,
                    "cleaning_type": "float64",
                    "csv_format": "numeric",
                    "nonblank_values_that_failed_conversion": parse_failures[field],
                }
            )

    return summary_rows, column_report, data_type_rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create California-only, analysis-ready Residential MLS datasets."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Folder containing the mortgage-enriched Residential CSV files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Folder where cleaned datasets and audit reports are saved.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=CHUNK_SIZE,
        help="Number of rows processed at a time.",
    )
    args = parser.parse_args()

    input_dir = args.input_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    all_summary_rows: list[dict[str, object]] = []
    all_column_rows: list[dict[str, object]] = []
    all_type_rows: list[dict[str, object]] = []

    for dataset_name, settings in DATASETS.items():
        summary_rows, column_rows, type_rows = clean_dataset(
            dataset_name=dataset_name,
            input_path=input_dir / settings["input_file"],
            output_path=output_dir / settings["output_file"],
            chunk_size=args.chunk_size,
        )
        all_summary_rows.extend(summary_rows)
        all_column_rows.extend(column_rows)
        all_type_rows.extend(type_rows)

    pd.DataFrame(all_summary_rows).to_csv(
        output_dir / "cleaning_summary.csv",
        index=False,
    )
    column_report = pd.DataFrame(all_column_rows)[
        ["dataset", "column", "reason", "missing_count", "missing_percent"]
    ].sort_values(
        ["dataset", "reason", "missing_percent"],
        ascending=[True, True, False],
    )
    column_report.to_csv(output_dir / "column_removal_report.csv", index=False)
    pd.DataFrame(all_type_rows).sort_values(
        ["dataset", "column"]
    ).to_csv(output_dir / "data_type_report.csv", index=False)

    print("\nData cleaning is complete.")
    print(f"Output folder: {output_dir}")


if __name__ == "__main__":
    main()
