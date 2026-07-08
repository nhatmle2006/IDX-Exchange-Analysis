"""Create Week 3 exploratory analysis summaries and numeric distribution plots."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import matplotlib
import pandas as pd


matplotlib.use("Agg")
import matplotlib.pyplot as plt


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = PROJECT_ROOT / "data" / "processed"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "analysis"
PLOT_SAMPLE_SIZE = 100_000

DATASET_FILES = {
    "listings_residential": "filtered_listings_residential.csv",
    "sold_residential": "filtered_sold_residential.csv",
}

ALL_DATASET_FILES = {
    "listings_all": "combined_listings_all.csv",
    "sold_all": "combined_sold_all.csv",
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

SOLD_DETAIL_FIELDS = [
    "ClosePrice",
    "ListPrice",
    "DaysOnMarket",
    "ListingContractDate",
    "PurchaseContractDate",
    "CloseDate",
    "CountyOrParish",
]


def load_residential_dataset(path: Path, include_sold_details: bool = False) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing input file: {path}")

    available = set(pd.read_csv(path, nrows=0).columns)
    requested = list(NUMERIC_FIELDS)
    if include_sold_details:
        requested.extend(SOLD_DETAIL_FIELDS)

    usecols = list(dict.fromkeys(field for field in requested if field in available))
    return pd.read_csv(path, usecols=usecols, low_memory=False)


def residential_share(path: Path, chunk_size: int) -> tuple[int, int, float]:
    if not path.exists():
        raise FileNotFoundError(f"Missing input file: {path}")

    total_rows = 0
    residential_rows = 0

    for chunk in pd.read_csv(
        path,
        usecols=["PropertyType"],
        chunksize=chunk_size,
        low_memory=False,
    ):
        property_type = chunk["PropertyType"].astype("string").str.strip()
        total_rows += len(chunk)
        residential_rows += int(property_type.eq("Residential").sum())

    percentage = round((residential_rows / total_rows) * 100, 2) if total_rows else 0.0
    return total_rows, residential_rows, percentage


def numeric_distribution_rows(dataset_name: str, frame: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    for field in NUMERIC_FIELDS:
        if field not in frame.columns:
            continue

        clean = pd.to_numeric(frame[field], errors="coerce").dropna()
        if clean.empty:
            continue

        quantiles = clean.quantile([0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99])
        q1 = float(quantiles.loc[0.25])
        q3 = float(quantiles.loc[0.75])
        iqr = q3 - q1
        lower_bound = q1 - (1.5 * iqr)
        upper_bound = q3 + (1.5 * iqr)

        rows.append(
            {
                "dataset": dataset_name,
                "field": field,
                "non_null_count": int(clean.size),
                "missing_or_non_numeric_count": int(len(frame) - clean.size),
                "min": round(float(clean.min()), 3),
                "p01": round(float(quantiles.loc[0.01]), 3),
                "p05": round(float(quantiles.loc[0.05]), 3),
                "p25": round(q1, 3),
                "median": round(float(quantiles.loc[0.5]), 3),
                "mean": round(float(clean.mean()), 3),
                "p75": round(q3, 3),
                "p95": round(float(quantiles.loc[0.95]), 3),
                "p99": round(float(quantiles.loc[0.99]), 3),
                "max": round(float(clean.max()), 3),
                "iqr_lower_bound": round(lower_bound, 3),
                "iqr_upper_bound": round(upper_bound, 3),
                "below_iqr_bound_count": int(clean.lt(lower_bound).sum()),
                "above_iqr_bound_count": int(clean.gt(upper_bound).sum()),
            }
        )

    return rows


def save_distribution_plot(
    dataset_name: str,
    field: str,
    values: pd.Series,
    output_path: Path,
) -> None:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return

    p01 = float(clean.quantile(0.01))
    p99 = float(clean.quantile(0.99))
    visible = clean[clean.between(p01, p99)]
    if visible.empty:
        visible = clean
    if len(visible) > PLOT_SAMPLE_SIZE:
        visible = visible.sample(PLOT_SAMPLE_SIZE, random_state=42)

    figure, axes = plt.subplots(
        2,
        1,
        figsize=(10, 7),
        gridspec_kw={"height_ratios": [3, 1]},
    )
    figure.subplots_adjust(
        left=0.09,
        right=0.98,
        top=0.88,
        bottom=0.16,
        hspace=0.35,
    )
    readable_dataset = dataset_name.replace("_", " ").title()
    readable_field = re.sub(r"(?<!^)(?=[A-Z])", " ", field)

    axes[0].hist(visible, bins=50, color="#197278", edgecolor="white", linewidth=0.4)
    axes[0].axvline(clean.median(), color="#D1495B", linewidth=2, label="Median")
    axes[0].set_ylabel("Records")
    axes[0].legend(frameon=False)
    axes[0].grid(axis="y", alpha=0.2)

    axes[1].boxplot(
        visible,
        orientation="horizontal",
        patch_artist=True,
        boxprops={"facecolor": "#EDAE49", "edgecolor": "#333333"},
        medianprops={"color": "#D1495B", "linewidth": 2},
        whiskerprops={"color": "#333333"},
        capprops={"color": "#333333"},
        flierprops={"marker": ".", "markersize": 2, "alpha": 0.3},
    )
    axes[1].set_xlabel(readable_field, labelpad=8)
    axes[1].set_yticks([])
    axes[1].grid(axis="x", alpha=0.2)

    figure.suptitle(
        f"{readable_dataset}: {readable_field}",
        fontsize=15,
        fontweight="bold",
    )
    figure.text(
        0.5,
        0.025,
        (
            f"Chart displays the 1st-99th percentile range. "
            f"Full minimum: {clean.min():,.2f}; full maximum: {clean.max():,.2f}."
        ),
        ha="center",
        fontsize=9,
        color="#555555",
    )
    figure.savefig(output_path, dpi=150, facecolor="white")
    plt.close(figure)


def market_summary_rows(
    input_dir: Path,
    sold: pd.DataFrame,
    chunk_size: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    for dataset_name, filename in ALL_DATASET_FILES.items():
        total, residential, percentage = residential_share(input_dir / filename, chunk_size)
        rows.append(
            {
                "dataset": dataset_name,
                "category": "property_type",
                "metric": "residential_share",
                "value": percentage,
                "unit": "percent",
                "notes": f"{residential:,} of {total:,} records",
            }
        )

    close_price = pd.to_numeric(sold["ClosePrice"], errors="coerce").dropna()
    valid_close_price = close_price[close_price.gt(0)]
    rows.extend(
        [
            {
                "dataset": "sold_residential",
                "category": "price",
                "metric": "average_close_price",
                "value": round(float(close_price.mean()), 2),
                "unit": "dollars",
                "notes": "Before outlier cleaning",
            },
            {
                "dataset": "sold_residential",
                "category": "price",
                "metric": "median_close_price",
                "value": round(float(close_price.median()), 2),
                "unit": "dollars",
                "notes": "Before outlier cleaning",
            },
            {
                "dataset": "sold_residential",
                "category": "price",
                "metric": "nonpositive_close_price_records",
                "value": int(close_price.le(0).sum()),
                "unit": "records",
                "notes": "Flag for later cleaning",
            },
        ]
    )

    days_on_market = pd.to_numeric(sold["DaysOnMarket"], errors="coerce").dropna()
    rows.extend(
        [
            {
                "dataset": "sold_residential",
                "category": "days_on_market",
                "metric": "median_days_on_market",
                "value": round(float(days_on_market.median()), 2),
                "unit": "days",
                "notes": "Before outlier cleaning",
            },
            {
                "dataset": "sold_residential",
                "category": "days_on_market",
                "metric": "average_days_on_market",
                "value": round(float(days_on_market.mean()), 2),
                "unit": "days",
                "notes": "Before outlier cleaning",
            },
            {
                "dataset": "sold_residential",
                "category": "days_on_market",
                "metric": "negative_days_on_market_records",
                "value": int(days_on_market.lt(0).sum()),
                "unit": "records",
                "notes": "Flag for later cleaning",
            },
        ]
    )

    list_price = pd.to_numeric(sold["ListPrice"], errors="coerce")
    close_price_for_comparison = pd.to_numeric(sold["ClosePrice"], errors="coerce")
    valid_comparison = list_price.gt(0) & close_price_for_comparison.gt(0)
    comparison_total = int(valid_comparison.sum())

    comparisons = {
        "sold_above_list_price": close_price_for_comparison.gt(list_price),
        "sold_at_list_price": close_price_for_comparison.eq(list_price),
        "sold_below_list_price": close_price_for_comparison.lt(list_price),
    }
    for metric, condition in comparisons.items():
        count = int((valid_comparison & condition).sum())
        percentage = round((count / comparison_total) * 100, 2) if comparison_total else 0.0
        rows.append(
            {
                "dataset": "sold_residential",
                "category": "sale_to_list",
                "metric": metric,
                "value": percentage,
                "unit": "percent",
                "notes": f"{count:,} of {comparison_total:,} valid comparisons",
            }
        )

    listing_date = pd.to_datetime(sold["ListingContractDate"], errors="coerce")
    purchase_date = pd.to_datetime(sold["PurchaseContractDate"], errors="coerce")
    close_date = pd.to_datetime(sold["CloseDate"], errors="coerce")
    date_checks = {
        "listing_after_close_records": listing_date.gt(close_date),
        "purchase_after_close_records": purchase_date.gt(close_date),
        "listing_after_purchase_records": listing_date.gt(purchase_date),
    }
    for metric, condition in date_checks.items():
        rows.append(
            {
                "dataset": "sold_residential",
                "category": "date_consistency",
                "metric": metric,
                "value": int(condition.sum()),
                "unit": "records",
                "notes": "Flag for later cleaning",
            }
        )

    rows.append(
        {
            "dataset": "sold_residential",
            "category": "price",
            "metric": "valid_positive_close_price_records",
            "value": int(valid_close_price.size),
            "unit": "records",
            "notes": "Used for county price summary",
        }
    )
    return rows


def county_price_summary(sold: pd.DataFrame) -> pd.DataFrame:
    county = sold["CountyOrParish"].astype("string").str.strip()
    close_price = pd.to_numeric(sold["ClosePrice"], errors="coerce")
    valid = county.notna() & county.ne("") & close_price.gt(0)

    frame = pd.DataFrame(
        {
            "CountyOrParish": county[valid],
            "ClosePrice": close_price[valid],
        }
    )
    summary = (
        frame.groupby("CountyOrParish")["ClosePrice"]
        .agg(
            sales_count="count",
            median_close_price="median",
            average_close_price="mean",
            minimum_close_price="min",
            maximum_close_price="max",
        )
        .reset_index()
    )
    summary = summary[summary["sales_count"].ge(30)].copy()
    summary["median_price_rank"] = summary["median_close_price"].rank(
        method="min",
        ascending=False,
    )
    summary = summary.sort_values(
        ["median_close_price", "sales_count"],
        ascending=[False, False],
    )

    money_columns = [
        "median_close_price",
        "average_close_price",
        "minimum_close_price",
        "maximum_close_price",
    ]
    summary[money_columns] = summary[money_columns].round(2)
    summary["median_price_rank"] = summary["median_price_rank"].astype(int)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create Week 3 exploratory analysis summaries and plots."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Folder containing the processed MLS datasets.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Folder where Week 3 analysis outputs should be saved.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=100_000,
        help="Rows to process at a time for property-type counts.",
    )
    args = parser.parse_args()

    input_dir = args.input_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    frames: dict[str, pd.DataFrame] = {}
    numeric_rows: list[dict[str, object]] = []

    for dataset_name, filename in DATASET_FILES.items():
        print(f"Loading {dataset_name}: {filename}")
        frame = load_residential_dataset(
            input_dir / filename,
            include_sold_details=dataset_name == "sold_residential",
        )
        frames[dataset_name] = frame
        numeric_rows.extend(numeric_distribution_rows(dataset_name, frame))

        for field in NUMERIC_FIELDS:
            if field not in frame.columns:
                continue
            output_path = plots_dir / f"{dataset_name}_{field}.png"
            save_distribution_plot(dataset_name, field, frame[field], output_path)
            print(f"Saved {output_path}")

    numeric_summary = pd.DataFrame(numeric_rows).sort_values(["dataset", "field"])
    numeric_path = output_dir / "numeric_distribution_summary.csv"
    numeric_summary.to_csv(numeric_path, index=False)

    sold = frames["sold_residential"]
    market_summary = pd.DataFrame(
        market_summary_rows(input_dir, sold, args.chunk_size)
    )
    market_path = output_dir / "market_summary.csv"
    market_summary.to_csv(market_path, index=False)

    county_summary = county_price_summary(sold)
    county_path = output_dir / "county_price_summary.csv"
    county_summary.to_csv(county_path, index=False)

    print(f"Saved {numeric_path}")
    print(f"Saved {market_path}")
    print(f"Saved {county_path}")
    print("\nExploratory analysis is complete.")


if __name__ == "__main__":
    main()
