"""Create streamlined Week 8 data sources for Tableau.

The Week 7 flagged datasets contain more than 100 columns. Tableau only needs a
smaller set of market, geography, office, agent, and school-district fields for
the required dashboards. Dashboard rows are filtered with the 3.0 IQR extreme
fences, along with the existing business and date-validity rules. The latest
eligible source version of each ListingKey is retained so transaction counts
and sales volume are not duplicated in Tableau.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = PROJECT_ROOT / "data" / "outliers"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "tableau"
CHUNK_SIZE = 50_000
MARKET_OUTPUT_FILE = "market_analysis_tableau.csv"

IDENTIFIER_FIELDS = (
    "ListingKey",
    "PostalCode",
)

FILTER_FIELDS = (
    "PropertySubType",
    "City",
    "CountyOrParish",
    "PostalCode",
)

DIMENSION_FIELDS = (
    "MLSAreaMajor",
    "ListAgentFullName",
    "ListOfficeName",
    "BuyerOfficeName",
    "CDEElementarySchoolDistrict",
    "CDEHighSchoolDistrict",
    "CDEUnifiedSchoolDistrict",
)

GEOGRAPHIC_FIELDS = (
    "Latitude",
    "Longitude",
)


@dataclass(frozen=True)
class TableauDataset:
    name: str
    input_file: str
    output_file: str
    analysis_date: str
    metric_fields: tuple[str, ...]
    date_fields: tuple[str, ...]
    extreme_iqr_fields: tuple[str, ...]

    @property
    def tableau_fields(self) -> tuple[str, ...]:
        fields = (
            *IDENTIFIER_FIELDS,
            *self.date_fields,
            *self.metric_fields,
            *FILTER_FIELDS,
            *DIMENSION_FIELDS,
            *GEOGRAPHIC_FIELDS,
            "rate_30yr_fixed",
        )
        return tuple(dict.fromkeys(fields))

    @property
    def eligibility_fields(self) -> tuple[str, ...]:
        return (
            "BusinessRuleInvalidFlag",
            "DateSequenceInvalidFlag",
            *(f"{field}ExtremeIQRFlag" for field in self.extreme_iqr_fields),
        )

    @property
    def source_fields(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys((*self.tableau_fields, *self.eligibility_fields))
        )


DATASETS = (
    TableauDataset(
        name="sold_residential",
        input_file="sold_residential_outlier_flagged.csv",
        output_file="sold_tableau.csv",
        analysis_date="CloseDate",
        date_fields=(
            "CloseDate",
            "ListingContractDate",
            "PurchaseContractDate",
            "ContractStatusChangeDate",
        ),
        metric_fields=(
            "ClosePrice",
            "ListPrice",
            "OriginalListPrice",
            "LivingArea",
            "DaysOnMarket",
            "CloseToOriginalListRatio",
            "PricePerSqFt",
            "ListingToContractDays",
            "ContractToCloseDays",
        ),
        extreme_iqr_fields=(
            "ClosePrice",
            "LivingArea",
            "DaysOnMarket",
            "PricePerSqFt",
            "CloseToOriginalListRatio",
        ),
    ),
    TableauDataset(
        name="listings_residential",
        input_file="listings_residential_outlier_flagged.csv",
        output_file="listings_tableau.csv",
        analysis_date="ListingContractDate",
        date_fields=(
            "ListingContractDate",
            "ContractStatusChangeDate",
        ),
        metric_fields=(
            "ListPrice",
            "OriginalListPrice",
            "ListToOriginalListRatio",
            "LivingArea",
            "DaysOnMarket",
        ),
        extreme_iqr_fields=(
            "ListPrice",
            "LivingArea",
            "DaysOnMarket",
            "OriginalListPrice",
        ),
    ),
)


def clean_text(series: pd.Series) -> pd.Series:
    cleaned = series.astype("string").str.strip()
    return cleaned.mask(cleaned.eq(""))


def true_flag(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.astype("string").str.strip().str.lower().eq("true")


def dashboard_eligible_mask(
    frame: pd.DataFrame,
    dataset: TableauDataset,
) -> pd.Series:
    excluded = pd.Series(False, index=frame.index)
    for field in dataset.eligibility_fields:
        excluded |= true_flag(frame[field])
    return ~excluded


def validate_source_columns(path: Path, dataset: TableauDataset) -> None:
    available = set(pd.read_csv(path, nrows=0).columns)
    missing = sorted(set(dataset.source_fields) - available)
    if missing:
        raise ValueError(f"{path.name} is missing required fields: {missing}")


def select_primary_rows(
    path: Path,
    dataset: TableauDataset,
    chunk_size: int,
) -> tuple[set[int], int, int, int]:
    """Select the latest 3.0-IQR-eligible row for each ListingKey."""
    primary_by_key: dict[str, tuple[tuple[int, int, int], int]] = {}
    missing_key_rows: set[int] = set()
    row_offset = 0
    eligible_rows = 0

    reader = pd.read_csv(
        path,
        usecols=list(
            dict.fromkeys(
                (
                    "ListingKey",
                    dataset.analysis_date,
                    "ContractStatusChangeDate",
                    *dataset.eligibility_fields,
                )
            )
        ),
        dtype={"ListingKey": "string"},
        low_memory=False,
        chunksize=chunk_size,
    )

    for chunk in reader:
        eligible = dashboard_eligible_mask(chunk, dataset)
        eligible_rows += int(eligible.sum())
        keys = clean_text(chunk["ListingKey"])
        analysis_dates = pd.to_datetime(
            chunk[dataset.analysis_date],
            errors="coerce",
        )
        status_dates = pd.to_datetime(
            chunk["ContractStatusChangeDate"],
            errors="coerce",
        ).fillna(analysis_dates)

        for local_position, (key, status_date, analysis_date, is_eligible) in enumerate(
            zip(keys, status_dates, analysis_dates, eligible)
        ):
            source_position = row_offset + local_position
            if not is_eligible:
                continue
            if pd.isna(key):
                missing_key_rows.add(source_position)
                continue

            status_rank = status_date.value if pd.notna(status_date) else -1
            analysis_rank = analysis_date.value if pd.notna(analysis_date) else -1
            rank = (status_rank, analysis_rank, source_position)
            existing = primary_by_key.get(str(key))
            if existing is None or rank > existing[0]:
                primary_by_key[str(key)] = (rank, source_position)

        row_offset += len(chunk)

    selected_rows = missing_key_rows | {
        source_position for _, source_position in primary_by_key.values()
    }
    return selected_rows, row_offset, len(primary_by_key), eligible_rows


def prepare_dataset(
    dataset: TableauDataset,
    input_dir: Path,
    output_dir: Path,
    chunk_size: int,
) -> dict[str, object]:
    input_path = input_dir / dataset.input_file
    output_path = output_dir / dataset.output_file
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    validate_source_columns(input_path, dataset)
    output_path.unlink(missing_ok=True)

    selected_rows, source_rows, unique_keys, eligible_rows = select_primary_rows(
        input_path,
        dataset,
        chunk_size,
    )
    rule_excluded_rows = source_rows - eligible_rows
    duplicate_key_rows = eligible_rows - len(selected_rows)

    text_fields = set(IDENTIFIER_FIELDS + FILTER_FIELDS + DIMENSION_FIELDS)
    dtypes = {field: "string" for field in text_fields}

    output_rows = 0
    dated_rows = 0
    missing_filter_counts = {field: 0 for field in FILTER_FIELDS}
    minimum_month: pd.Timestamp | None = None
    maximum_month: pd.Timestamp | None = None
    row_offset = 0

    reader = pd.read_csv(
        input_path,
        usecols=list(dataset.source_fields),
        dtype=dtypes,
        low_memory=False,
        chunksize=chunk_size,
    )

    for chunk_number, chunk in enumerate(reader):
        source_positions = range(row_offset, row_offset + len(chunk))
        selected_mask = pd.Series(
            [position in selected_rows for position in source_positions],
            index=chunk.index,
        )
        eligible_mask = dashboard_eligible_mask(chunk, dataset)
        row_offset += len(chunk)
        chunk = chunk.loc[selected_mask & eligible_mask].copy()
        chunk = chunk.loc[:, dataset.tableau_fields]

        for field in text_fields:
            chunk[field] = clean_text(chunk[field])

        for field in dataset.date_fields:
            parsed = pd.to_datetime(chunk[field], errors="coerce")
            chunk[field] = parsed.dt.strftime("%Y-%m-%d")

        analysis_dates = pd.to_datetime(
            chunk[dataset.analysis_date],
            errors="coerce",
        )
        analysis_month = analysis_dates.dt.to_period("M").dt.to_timestamp()
        chunk.insert(1, "AnalysisMonth", analysis_month.dt.strftime("%Y-%m-%d"))
        chunk.insert(2, "AnalysisYrMo", analysis_month.dt.strftime("%Y%m"))
        chunk.insert(3, "Dataset", dataset.name)

        valid_months = analysis_month.dropna()
        dated_rows += len(valid_months)
        if not valid_months.empty:
            chunk_minimum = valid_months.min()
            chunk_maximum = valid_months.max()
            minimum_month = (
                chunk_minimum
                if minimum_month is None
                else min(minimum_month, chunk_minimum)
            )
            maximum_month = (
                chunk_maximum
                if maximum_month is None
                else max(maximum_month, chunk_maximum)
            )

        for field in FILTER_FIELDS:
            missing_filter_counts[field] += int(chunk[field].isna().sum())

        chunk.to_csv(
            output_path,
            mode="a",
            header=chunk_number == 0,
            index=False,
        )
        output_rows += len(chunk)

    output_columns = len(pd.read_csv(output_path, nrows=0).columns)
    return {
        "Dataset": dataset.name,
        "SourceFile": dataset.input_file,
        "TableauFile": dataset.output_file,
        "SourceRows": source_rows,
        "IQRRule": "3.0 extreme fence",
        "RowsEligibleAfter3IQR": eligible_rows,
        "RowsExcludedBy3IQRAndValidityRules": rule_excluded_rows,
        "TableauRows": output_rows,
        "DuplicateVersionsRemoved": duplicate_key_rows,
        "RowsReconciled": (
            source_rows
            == output_rows + duplicate_key_rows + rule_excluded_rows
        ),
        "TableauColumns": output_columns,
        "AnalysisDateField": dataset.analysis_date,
        "RowsWithAnalysisMonth": dated_rows,
        "StartMonth": minimum_month.strftime("%Y-%m") if minimum_month else "",
        "EndMonth": maximum_month.strftime("%Y-%m") if maximum_month else "",
        "UniqueListingKeys": unique_keys,
        "MissingCity": missing_filter_counts["City"],
        "MissingCounty": missing_filter_counts["CountyOrParish"],
        "MissingPostalCode": missing_filter_counts["PostalCode"],
        "MissingPropertySubType": missing_filter_counts["PropertySubType"],
        "PrivateContactFieldsIncluded": False,
    }


def build_market_analysis_source(
    output_dir: Path,
    chunk_size: int,
) -> dict[str, object]:
    """Combine listing and sold activity for one filterable market workbook."""
    output_path = output_dir / MARKET_OUTPUT_FILE
    output_path.unlink(missing_ok=True)

    market_fields = (
        "ActivityKey",
        "ListingKey",
        "ActivityType",
        "AnalysisMonth",
        "AnalysisYrMo",
        "NewListings",
        "ClosedSales",
        "ClosePrice",
        "ListPrice",
        "OriginalListPrice",
        "ListToOriginalListRatio",
        "LivingArea",
        "SoldDaysOnMarket",
        "ListingDaysOnMarket",
        "CloseToOriginalListRatio",
        "PricePerSqFt",
        "ListingToContractDays",
        "ContractToCloseDays",
        *FILTER_FIELDS,
        "MLSAreaMajor",
        *GEOGRAPHIC_FIELDS,
        "rate_30yr_fixed",
        "CDEElementarySchoolDistrict",
        "CDEHighSchoolDistrict",
        "CDEUnifiedSchoolDistrict",
    )

    inputs = (
        ("sold_tableau.csv", "Closed Sale"),
        ("listings_tableau.csv", "New Listing"),
    )
    total_rows = 0
    dated_rows = 0
    written_chunks = 0
    activity_counts: dict[str, int] = {}
    minimum_month: pd.Timestamp | None = None
    maximum_month: pd.Timestamp | None = None

    for input_file, activity_type in inputs:
        input_path = output_dir / input_file
        activity_rows = 0
        for chunk in pd.read_csv(input_path, chunksize=chunk_size, low_memory=False):
            is_sold = activity_type == "Closed Sale"
            market = pd.DataFrame(index=chunk.index)
            market["ActivityKey"] = activity_type + "|" + chunk["ListingKey"].astype("string")
            market["ListingKey"] = chunk["ListingKey"]
            market["ActivityType"] = activity_type
            market["AnalysisMonth"] = chunk["AnalysisMonth"]
            market["AnalysisYrMo"] = chunk["AnalysisYrMo"]
            market["NewListings"] = 0 if is_sold else 1
            market["ClosedSales"] = 1 if is_sold else 0

            for field in (
                "ClosePrice",
                "ListPrice",
                "OriginalListPrice",
                "ListToOriginalListRatio",
                "LivingArea",
                "CloseToOriginalListRatio",
                "PricePerSqFt",
                "ListingToContractDays",
                "ContractToCloseDays",
                *FILTER_FIELDS,
                "MLSAreaMajor",
                *GEOGRAPHIC_FIELDS,
                "rate_30yr_fixed",
                "CDEElementarySchoolDistrict",
                "CDEHighSchoolDistrict",
                "CDEUnifiedSchoolDistrict",
            ):
                market[field] = chunk[field] if field in chunk else pd.NA

            market["SoldDaysOnMarket"] = chunk["DaysOnMarket"] if is_sold else pd.NA
            market["ListingDaysOnMarket"] = (
                pd.NA if is_sold else chunk["DaysOnMarket"]
            )

            analysis_months = pd.to_datetime(
                market["AnalysisMonth"],
                errors="coerce",
            )
            valid_months = analysis_months.dropna()
            dated_rows += len(valid_months)
            if not valid_months.empty:
                chunk_minimum = valid_months.min()
                chunk_maximum = valid_months.max()
                minimum_month = (
                    chunk_minimum
                    if minimum_month is None
                    else min(minimum_month, chunk_minimum)
                )
                maximum_month = (
                    chunk_maximum
                    if maximum_month is None
                    else max(maximum_month, chunk_maximum)
                )

            market = market.loc[:, market_fields]
            market.to_csv(
                output_path,
                mode="a",
                header=written_chunks == 0,
                index=False,
            )
            written_chunks += 1
            activity_rows += len(market)
            total_rows += len(market)

        activity_counts[activity_type] = activity_rows

    return {
        "Dataset": "market_analysis",
        "SourceFile": "sold_tableau.csv + listings_tableau.csv",
        "TableauFile": MARKET_OUTPUT_FILE,
        "SourceRows": total_rows,
        "IQRRule": "3.0 extreme fence",
        "RowsEligibleAfter3IQR": total_rows,
        "RowsExcludedBy3IQRAndValidityRules": 0,
        "TableauRows": total_rows,
        "DuplicateVersionsRemoved": 0,
        "RowsReconciled": True,
        "TableauColumns": len(market_fields),
        "AnalysisDateField": "AnalysisMonth",
        "RowsWithAnalysisMonth": dated_rows,
        "StartMonth": minimum_month.strftime("%Y-%m") if minimum_month else "",
        "EndMonth": maximum_month.strftime("%Y-%m") if maximum_month else "",
        "UniqueListingKeys": "",
        "MissingCity": "",
        "MissingCounty": "",
        "MissingPostalCode": "",
        "MissingPropertySubType": "",
        "PrivateContactFieldsIncluded": False,
        "NewListingRows": activity_counts["New Listing"],
        "ClosedSaleRows": activity_counts["Closed Sale"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create streamlined Residential CSV files for Tableau."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Directory containing the Week 7 outlier-flagged CSV files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for Tableau-ready CSV files.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=CHUNK_SIZE,
        help="Rows processed at a time.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    summaries = [
        prepare_dataset(
            dataset,
            args.input_dir,
            args.output_dir,
            args.chunk_size,
        )
        for dataset in DATASETS
    ]
    summaries.append(build_market_analysis_source(args.output_dir, args.chunk_size))

    summary = pd.DataFrame(summaries)
    summary_path = args.output_dir / "week8_tableau_validation.csv"
    summary.to_csv(summary_path, index=False)

    print("Week 8 Tableau data preparation complete")
    print(summary.to_string(index=False))
    print(f"Validation summary: {summary_path}")


if __name__ == "__main__":
    main()
