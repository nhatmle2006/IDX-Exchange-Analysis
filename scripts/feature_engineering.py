"""Create Week 6 market metrics and school-district features.

The script reads the cleaned California Residential datasets, preserves every
row, adds dashboard-ready fields, and saves validation and segment summaries.
Source files are never overwritten.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from shapely import points
from shapely.geometry import shape
from shapely.strtree import STRtree


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = PROJECT_ROOT / "data" / "cleaned"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "features"
DEFAULT_DISTRICT_FILE = (
    PROJECT_ROOT / "reference" / "school_district_areas_2024_25.geojson"
)
CHUNK_SIZE = 50_000

DATASETS = {
    "listings_residential": {
        "input_file": "listings_residential_california_clean.csv",
        "output_file": "listings_residential_features.csv",
    },
    "sold_residential": {
        "input_file": "sold_residential_california_clean.csv",
        "output_file": "sold_residential_market_features.csv",
    },
}

DISTRICT_TYPES = {
    "Elementary": "CDEElementarySchoolDistrict",
    "High": "CDEHighSchoolDistrict",
    "Unified": "CDEUnifiedSchoolDistrict",
}

METRIC_FIELDS = [
    "PriceRatio",
    "PricePerSqFt",
    "DaysOnMarket",
    "Year",
    "Month",
    "YrMo",
    "CloseToOriginalListRatio",
    "ListingToContractDays",
    "ContractToCloseDays",
]


@dataclass
class DistrictLookup:
    district_type: str
    tree: STRtree
    names: np.ndarray
    codes: np.ndarray


def load_district_lookups(path: Path) -> dict[str, DistrictLookup]:
    """Load one spatial index for each overlapping school-district type."""
    if not path.exists():
        raise FileNotFoundError(
            "Missing school-district boundary file. Download the 2024-25 "
            f"CDE GeoJSON to {path}"
        )

    data = json.loads(path.read_text(encoding="utf-8"))
    grouped: dict[str, list[tuple[object, str, str]]] = {
        district_type: [] for district_type in DISTRICT_TYPES
    }

    for feature in data.get("features", []):
        properties = feature.get("properties") or {}
        district_type = properties.get("DistrictType")
        geometry = feature.get("geometry")
        if district_type not in grouped or not geometry:
            continue

        grouped[district_type].append(
            (
                shape(geometry),
                str(properties.get("DistrictName") or "").strip(),
                str(properties.get("CDCode") or "").strip(),
            )
        )

    lookups: dict[str, DistrictLookup] = {}
    for district_type, records in grouped.items():
        if not records:
            raise ValueError(f"No {district_type} district polygons were found.")
        geometries, names, codes = zip(*records)
        lookups[district_type] = DistrictLookup(
            district_type=district_type,
            tree=STRtree(list(geometries)),
            names=np.asarray(names, dtype=object),
            codes=np.asarray(codes, dtype=object),
        )

    return lookups


def safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Divide positive numeric values and leave invalid denominators missing."""
    numerator_numeric = pd.to_numeric(numerator, errors="coerce")
    denominator_numeric = pd.to_numeric(denominator, errors="coerce")
    valid = numerator_numeric.gt(0) & denominator_numeric.gt(0)
    result = pd.Series(np.nan, index=numerator.index, dtype="float64")
    result.loc[valid] = (
        numerator_numeric.loc[valid] / denominator_numeric.loc[valid]
    )
    return result


def engineer_market_metrics(chunk: pd.DataFrame) -> None:
    """Add the market fields required by the Week 6 handbook."""
    close_date = pd.to_datetime(chunk["CloseDate"], errors="coerce")
    purchase_date = pd.to_datetime(
        chunk["PurchaseContractDate"], errors="coerce"
    )
    listing_date = pd.to_datetime(
        chunk["ListingContractDate"], errors="coerce"
    )

    price_ratio = safe_ratio(
        chunk["ClosePrice"],
        chunk["OriginalListPrice"],
    )
    chunk["PriceRatio"] = price_ratio
    chunk["CloseToOriginalListRatio"] = price_ratio.copy()
    chunk["PricePerSqFt"] = safe_ratio(
        chunk["ClosePrice"],
        chunk["LivingArea"],
    )
    chunk["DaysOnMarket"] = pd.to_numeric(
        chunk["DaysOnMarket"], errors="coerce"
    )
    chunk["Year"] = close_date.dt.year.astype("Int64")
    chunk["Month"] = close_date.dt.month.astype("Int64")
    chunk["YrMo"] = close_date.dt.strftime("%Y-%m").astype("string")
    chunk["ListingToContractDays"] = (
        purchase_date - listing_date
    ).dt.days.astype("Int64")
    chunk["ContractToCloseDays"] = (
        close_date - purchase_date
    ).dt.days.astype("Int64")


def join_matches(
    chunk: pd.DataFrame,
    valid_positions: np.ndarray,
    point_geometries: np.ndarray,
    lookup: DistrictLookup,
) -> None:
    """Assign district names and codes without duplicating property rows."""
    district_column = DISTRICT_TYPES[lookup.district_type]
    code_column = f"{district_column}Code"
    count_column = f"{district_column}MatchCount"

    chunk[district_column] = pd.Series(
        pd.NA, index=chunk.index, dtype="string"
    )
    chunk[code_column] = pd.Series(pd.NA, index=chunk.index, dtype="string")
    chunk[count_column] = pd.Series(0, index=chunk.index, dtype="Int64")
    if not len(point_geometries):
        return

    matches = lookup.tree.query(point_geometries, predicate="intersects")
    if matches.size == 0:
        return

    local_point_indices = matches[0]
    polygon_indices = matches[1]
    matched = pd.DataFrame(
        {
            "position": valid_positions[local_point_indices],
            "name": lookup.names[polygon_indices],
            "code": lookup.codes[polygon_indices],
        }
    )
    grouped = matched.groupby("position", sort=False)
    names = grouped["name"].agg(
        lambda values: " | ".join(sorted(set(value for value in values if value)))
    )
    codes = grouped["code"].agg(
        lambda values: " | ".join(sorted(set(value for value in values if value)))
    )
    counts = grouped.size()

    positions = names.index.to_numpy(dtype=int)
    row_labels = chunk.index.to_numpy()[positions]
    chunk.loc[row_labels, district_column] = names.to_numpy()
    chunk.loc[row_labels, code_column] = codes.reindex(names.index).to_numpy()
    chunk.loc[row_labels, count_column] = counts.reindex(names.index).to_numpy()


def add_school_districts(
    chunk: pd.DataFrame,
    lookups: dict[str, DistrictLookup],
) -> None:
    latitude = pd.to_numeric(chunk["Latitude"], errors="coerce")
    longitude = pd.to_numeric(chunk["Longitude"], errors="coerce")
    valid = (
        latitude.notna()
        & longitude.notna()
        & latitude.between(-90, 90)
        & longitude.between(-180, 180)
    )
    valid_positions = np.flatnonzero(valid.to_numpy())
    point_geometries = points(
        longitude.iloc[valid_positions].to_numpy(),
        latitude.iloc[valid_positions].to_numpy(),
    )

    for district_type in DISTRICT_TYPES:
        join_matches(
            chunk,
            valid_positions,
            point_geometries,
            lookups[district_type],
        )


def required_input_columns(path: Path) -> list[str]:
    columns = list(pd.read_csv(path, nrows=0).columns)
    required = {
        "ClosePrice",
        "OriginalListPrice",
        "LivingArea",
        "DaysOnMarket",
        "CloseDate",
        "PurchaseContractDate",
        "ListingContractDate",
        "Latitude",
        "Longitude",
    }
    missing = required - set(columns)
    if missing:
        raise ValueError(
            f"{path.name} is missing required Week 6 fields: "
            + ", ".join(sorted(missing))
        )
    return columns


def process_dataset(
    dataset_name: str,
    input_path: Path,
    output_path: Path,
    lookups: dict[str, DistrictLookup],
    chunk_size: int,
) -> dict[str, object]:
    """Create one feature-ready CSV and return validation metrics."""
    input_columns = required_input_columns(input_path)
    if output_path.exists():
        output_path.unlink()

    counters = {
        "dataset": dataset_name,
        "input_rows": 0,
        "output_rows": 0,
        "input_columns": len(input_columns),
        "output_columns": 0,
        "price_ratio_populated": 0,
        "price_per_sq_ft_populated": 0,
        "yrmo_populated": 0,
        "listing_to_contract_days_populated": 0,
        "contract_to_close_days_populated": 0,
        "listing_to_contract_negative": 0,
        "contract_to_close_negative": 0,
        "valid_coordinate_rows": 0,
        "any_cde_district_populated": 0,
        "cde_district_unmatched_with_coordinates": 0,
        "cde_elementary_and_high_overlap": 0,
        "cde_elementary_and_unified_overlap": 0,
        "original_mls_high_school_district_populated": 0,
    }
    for district_column in DISTRICT_TYPES.values():
        counters[f"{district_column}_populated"] = 0
        counters[f"{district_column}_multiple_matches"] = 0

    wrote_header = False
    for chunk in pd.read_csv(
        input_path,
        chunksize=chunk_size,
        low_memory=False,
    ):
        counters["input_rows"] += len(chunk)
        engineer_market_metrics(chunk)
        add_school_districts(chunk, lookups)

        counters["price_ratio_populated"] += int(chunk["PriceRatio"].notna().sum())
        counters["price_per_sq_ft_populated"] += int(
            chunk["PricePerSqFt"].notna().sum()
        )
        counters["yrmo_populated"] += int(chunk["YrMo"].notna().sum())
        counters["listing_to_contract_days_populated"] += int(
            chunk["ListingToContractDays"].notna().sum()
        )
        counters["contract_to_close_days_populated"] += int(
            chunk["ContractToCloseDays"].notna().sum()
        )
        counters["listing_to_contract_negative"] += int(
            chunk["ListingToContractDays"].lt(0).fillna(False).sum()
        )
        counters["contract_to_close_negative"] += int(
            chunk["ContractToCloseDays"].lt(0).fillna(False).sum()
        )

        for district_column in DISTRICT_TYPES.values():
            counters[f"{district_column}_populated"] += int(
                chunk[district_column].notna().sum()
            )
            counters[f"{district_column}_multiple_matches"] += int(
                chunk[f"{district_column}MatchCount"].gt(1).sum()
            )

        valid_coordinates = chunk["Latitude"].notna() & chunk["Longitude"].notna()
        elementary_match = chunk["CDEElementarySchoolDistrict"].notna()
        high_match = chunk["CDEHighSchoolDistrict"].notna()
        unified_match = chunk["CDEUnifiedSchoolDistrict"].notna()
        any_district_match = elementary_match | high_match | unified_match
        counters["valid_coordinate_rows"] += int(valid_coordinates.sum())
        counters["any_cde_district_populated"] += int(any_district_match.sum())
        counters["cde_district_unmatched_with_coordinates"] += int(
            (valid_coordinates & ~any_district_match).sum()
        )
        counters["cde_elementary_and_high_overlap"] += int(
            (elementary_match & high_match).sum()
        )
        counters["cde_elementary_and_unified_overlap"] += int(
            (elementary_match & unified_match).sum()
        )
        if "HighSchoolDistrict" in chunk.columns:
            counters["original_mls_high_school_district_populated"] += int(
                chunk["HighSchoolDistrict"].notna().sum()
            )

        chunk.to_csv(
            output_path,
            index=False,
            mode="a" if wrote_header else "w",
            header=not wrote_header,
            date_format="%Y-%m-%d",
        )
        wrote_header = True
        counters["output_rows"] += len(chunk)

    counters["output_columns"] = len(pd.read_csv(output_path, nrows=0).columns)
    counters["rows_preserved"] = (
        counters["input_rows"] == counters["output_rows"]
    )
    return counters


def segment_summary(
    frame: pd.DataFrame,
    group_column: str,
) -> pd.DataFrame:
    source = frame.copy()
    source[group_column] = (
        source[group_column].astype("string").fillna("Missing")
    )
    summary = (
        source.groupby(group_column, dropna=False)
        .agg(
            ClosedSales=("ListingKey", "size"),
            MedianClosePrice=("ClosePrice", "median"),
            MedianPricePerSqFt=("PricePerSqFt", "median"),
            MedianDaysOnMarket=("DaysOnMarket", "median"),
            MedianCloseToOriginalListRatio=(
                "CloseToOriginalListRatio",
                "median",
            ),
            MedianListingToContractDays=(
                "ListingToContractDays",
                "median",
            ),
            MedianContractToCloseDays=("ContractToCloseDays", "median"),
        )
        .reset_index()
        .sort_values(["ClosedSales", group_column], ascending=[False, True])
    )
    return summary


def office_summary(
    frame: pd.DataFrame,
    source_column: str,
    role: str,
) -> pd.DataFrame:
    summary = segment_summary(frame, source_column).rename(
        columns={source_column: "OfficeName"}
    )
    summary.insert(0, "OfficeRole", role)
    return summary


def district_summary(
    frame: pd.DataFrame,
    district_column: str,
    district_type: str,
) -> pd.DataFrame:
    matched = frame[frame[district_column].notna()].copy()
    summary = segment_summary(matched, district_column).rename(
        columns={district_column: "SchoolDistrict"}
    )
    summary.insert(0, "DistrictType", district_type)
    return summary


def create_reports(
    output_dir: Path,
    validations: list[dict[str, object]],
) -> None:
    sold_path = output_dir / DATASETS["sold_residential"]["output_file"]
    report_fields = [
        "ListingKey",
        "ListingId",
        "PropertyType",
        "PropertySubType",
        "CountyOrParish",
        "MLSAreaMajor",
        "ListOfficeName",
        "BuyerOfficeName",
        "ClosePrice",
        "OriginalListPrice",
        "LivingArea",
        "DaysOnMarket",
        "CloseDate",
        "PriceRatio",
        "PricePerSqFt",
        "Year",
        "Month",
        "YrMo",
        "CloseToOriginalListRatio",
        "ListingToContractDays",
        "ContractToCloseDays",
        "HighSchoolDistrict",
        "CDEElementarySchoolDistrict",
        "CDEHighSchoolDistrict",
        "CDEUnifiedSchoolDistrict",
    ]
    sold = pd.read_csv(sold_path, usecols=report_fields, low_memory=False)

    populated = sold[
        sold[
            [
                "PriceRatio",
                "PricePerSqFt",
                "YrMo",
                "ListingToContractDays",
                "ContractToCloseDays",
            ]
        ]
        .notna()
        .all(axis=1)
    ].copy()
    sample = populated.sort_values(
        ["CloseDate", "ListingId"],
        ascending=[False, True],
    ).head(25)
    sample.to_csv(output_dir / "week6_feature_sample.csv", index=False)

    county = segment_summary(sold, "CountyOrParish")
    county.to_csv(output_dir / "week6_county_summary.csv", index=False)

    mls_area = segment_summary(sold, "MLSAreaMajor")
    mls_area.to_csv(output_dir / "week6_mls_area_summary.csv", index=False)

    property_type = segment_summary(sold, "PropertyType")
    property_type.to_csv(
        output_dir / "week6_property_type_summary.csv",
        index=False,
    )

    subtype = segment_summary(sold, "PropertySubType")
    subtype.to_csv(
        output_dir / "week6_property_subtype_summary.csv",
        index=False,
    )

    offices = pd.concat(
        [
            office_summary(sold, "ListOfficeName", "Listing Office"),
            office_summary(sold, "BuyerOfficeName", "Buyer Office"),
        ],
        ignore_index=True,
    )
    offices.to_csv(output_dir / "week6_office_summary.csv", index=False)

    districts = pd.concat(
        [
            district_summary(sold, district_column, district_type)
            for district_type, district_column in DISTRICT_TYPES.items()
        ],
        ignore_index=True,
    )
    districts.to_csv(
        output_dir / "week6_school_district_summary.csv",
        index=False,
    )

    validation = pd.DataFrame(validations)
    validation["price_ratio_columns_equal"] = True
    for dataset_name, settings in DATASETS.items():
        path = output_dir / settings["output_file"]
        equal = True
        for chunk in pd.read_csv(
            path,
            usecols=["PriceRatio", "CloseToOriginalListRatio"],
            chunksize=100_000,
        ):
            equal &= bool(
                (
                    chunk["PriceRatio"].eq(chunk["CloseToOriginalListRatio"])
                    | (
                        chunk["PriceRatio"].isna()
                        & chunk["CloseToOriginalListRatio"].isna()
                    )
                ).all()
            )
        validation.loc[
            validation["dataset"].eq(dataset_name),
            "price_ratio_columns_equal",
        ] = equal

    validation.to_csv(output_dir / "week6_validation_summary.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create Week 6 market metrics and school-district features."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Folder containing the cleaned California Residential CSVs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Folder where Week 6 feature datasets and reports are saved.",
    )
    parser.add_argument(
        "--district-file",
        type=Path,
        default=DEFAULT_DISTRICT_FILE,
        help="Official CDE 2024-25 school-district GeoJSON.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=CHUNK_SIZE,
        help="Rows processed per chunk.",
    )
    args = parser.parse_args()

    input_dir = args.input_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    district_file = args.district_file.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading school districts from {district_file.name}")
    lookups = load_district_lookups(district_file)
    for district_type, lookup in lookups.items():
        print(f"{district_type}: {len(lookup.names):,} polygons")

    validations: list[dict[str, object]] = []
    for dataset_name, settings in DATASETS.items():
        input_path = input_dir / settings["input_file"]
        output_path = output_dir / settings["output_file"]
        print(f"\nEngineering {dataset_name}: {input_path.name}")
        validation = process_dataset(
            dataset_name=dataset_name,
            input_path=input_path,
            output_path=output_path,
            lookups=lookups,
            chunk_size=args.chunk_size,
        )
        validations.append(validation)
        print(
            f"Saved {validation['output_rows']:,} rows to {output_path.name}"
        )

    print("\nCreating Week 6 sample and segment summaries")
    create_reports(output_dir, validations)
    print(f"Week 6 outputs saved to {output_dir}")


if __name__ == "__main__":
    main()
