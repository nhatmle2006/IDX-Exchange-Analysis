"""Merge monthly FRED 30-year mortgage rates onto Residential MLS datasets."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = PROJECT_ROOT / "data" / "processed"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "enriched"
FRED_MORTGAGE_URL = (
    "https://fred.stlouisfed.org/graph/fredgraph.csv?id=MORTGAGE30US"
)
CHUNK_SIZE = 100_000

DATASETS = {
    "listings_residential": {
        "input_file": "filtered_listings_residential.csv",
        "date_field": "ListingContractDate",
        "output_file": "listings_residential_with_mortgage_rates.csv",
    },
    "sold_residential": {
        "input_file": "filtered_sold_residential.csv",
        "date_field": "CloseDate",
        "output_file": "sold_residential_with_mortgage_rates.csv",
    },
}


def load_monthly_mortgage_rates(source: str | Path) -> pd.DataFrame:
    print(f"Loading mortgage rates from {source}")
    mortgage = pd.read_csv(source)

    required_columns = {"observation_date", "MORTGAGE30US"}
    missing_columns = required_columns - set(mortgage.columns)
    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))
        raise ValueError(f"Mortgage file is missing columns: {missing_text}")

    mortgage["observation_date"] = pd.to_datetime(
        mortgage["observation_date"],
        errors="coerce",
    )
    mortgage["MORTGAGE30US"] = pd.to_numeric(
        mortgage["MORTGAGE30US"],
        errors="coerce",
    )
    mortgage = mortgage.dropna(subset=["observation_date", "MORTGAGE30US"]).copy()
    if mortgage.empty:
        raise ValueError("Mortgage source does not contain any valid observations.")

    mortgage["year_month"] = (
        mortgage["observation_date"].dt.to_period("M").astype(str)
    )
    monthly = (
        mortgage.groupby("year_month", as_index=False)
        .agg(
            rate_30yr_fixed=("MORTGAGE30US", "mean"),
            weekly_observation_count=("MORTGAGE30US", "count"),
            first_observation_date=("observation_date", "min"),
            last_observation_date=("observation_date", "max"),
        )
        .sort_values("year_month")
    )
    monthly["rate_30yr_fixed"] = monthly["rate_30yr_fixed"].round(3)
    monthly["first_observation_date"] = monthly[
        "first_observation_date"
    ].dt.strftime("%Y-%m-%d")
    monthly["last_observation_date"] = monthly[
        "last_observation_date"
    ].dt.strftime("%Y-%m-%d")
    return monthly


def enrich_dataset(
    dataset_name: str,
    input_path: Path,
    output_path: Path,
    date_field: str,
    monthly_rates: pd.DataFrame,
    chunk_size: int,
) -> dict[str, object]:
    if not input_path.exists():
        raise FileNotFoundError(f"Missing input file: {input_path}")

    columns = list(pd.read_csv(input_path, nrows=0).columns)
    if date_field not in columns:
        raise ValueError(f"{input_path.name} does not contain {date_field}.")

    total_rows = 0
    missing_date_rows = 0
    unmatched_rate_rows = 0
    first_month = ""
    last_month = ""
    wrote_header = False

    print(f"Enriching {dataset_name}: {input_path.name}")
    for chunk in pd.read_csv(
        input_path,
        chunksize=chunk_size,
        low_memory=False,
    ):
        parsed_date = pd.to_datetime(chunk[date_field], errors="coerce")
        chunk["year_month"] = parsed_date.dt.to_period("M").astype("string")
        chunk = chunk.merge(
            monthly_rates[["year_month", "rate_30yr_fixed"]],
            on="year_month",
            how="left",
            validate="many_to_one",
        )

        total_rows += len(chunk)
        missing_date_rows += int(parsed_date.isna().sum())
        unmatched_rate_rows += int(chunk["rate_30yr_fixed"].isna().sum())

        valid_months = chunk["year_month"].dropna()
        if not valid_months.empty:
            chunk_first_month = str(valid_months.min())
            chunk_last_month = str(valid_months.max())
            first_month = (
                min(first_month, chunk_first_month)
                if first_month
                else chunk_first_month
            )
            last_month = (
                max(last_month, chunk_last_month)
                if last_month
                else chunk_last_month
            )

        chunk.to_csv(
            output_path,
            index=False,
            mode="a" if wrote_header else "w",
            header=not wrote_header,
        )
        wrote_header = True

    matched_rate_rows = total_rows - unmatched_rate_rows
    match_percentage = (
        round((matched_rate_rows / total_rows) * 100, 4) if total_rows else 0.0
    )
    return {
        "dataset": dataset_name,
        "input_file": input_path.name,
        "output_file": output_path.name,
        "date_field": date_field,
        "rows": total_rows,
        "valid_date_rows": total_rows - missing_date_rows,
        "missing_date_rows": missing_date_rows,
        "matched_rate_rows": matched_rate_rows,
        "unmatched_rate_rows": unmatched_rate_rows,
        "match_percentage": match_percentage,
        "first_year_month": first_month,
        "last_year_month": last_month,
        "status": "PASS" if unmatched_rate_rows == 0 else "REVIEW",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add monthly FRED 30-year mortgage rates to Residential MLS data."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Folder containing the Residential listing and sold datasets.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Folder where enriched datasets and validation files are saved.",
    )
    parser.add_argument(
        "--mortgage-csv",
        type=Path,
        help="Optional downloaded MORTGAGE30US CSV. FRED is used when omitted.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=CHUNK_SIZE,
        help="Number of MLS rows to process at a time.",
    )
    args = parser.parse_args()

    input_dir = args.input_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    mortgage_source: str | Path
    if args.mortgage_csv:
        mortgage_source = args.mortgage_csv.expanduser().resolve()
        if not mortgage_source.exists():
            raise FileNotFoundError(f"Missing mortgage file: {mortgage_source}")
    else:
        mortgage_source = FRED_MORTGAGE_URL

    monthly_rates = load_monthly_mortgage_rates(mortgage_source)
    monthly_path = output_dir / "mortgage_monthly_rates.csv"
    monthly_rates.to_csv(monthly_path, index=False)
    print(f"Saved {monthly_path}")

    validation_rows: list[dict[str, object]] = []
    for dataset_name, settings in DATASETS.items():
        validation_rows.append(
            enrich_dataset(
                dataset_name=dataset_name,
                input_path=input_dir / settings["input_file"],
                output_path=output_dir / settings["output_file"],
                date_field=settings["date_field"],
                monthly_rates=monthly_rates,
                chunk_size=args.chunk_size,
            )
        )

    validation = pd.DataFrame(validation_rows)
    validation_path = output_dir / "mortgage_merge_validation.csv"
    validation.to_csv(validation_path, index=False)
    print(f"Saved {validation_path}")

    unmatched_total = int(validation["unmatched_rate_rows"].sum())
    if unmatched_total:
        raise ValueError(
            f"Mortgage enrichment left {unmatched_total:,} rows without a rate. "
            f"Review {validation_path}."
        )

    print("\nMortgage-rate enrichment is complete.")
    print("All MLS rows matched to a monthly mortgage rate.")


if __name__ == "__main__":
    main()
