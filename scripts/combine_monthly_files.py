from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

import pandas as pd


START_MONTH = "202401"


def previous_month() -> str:
    today = date.today()
    year = today.year
    month = today.month - 1
    if month == 0:
        year -= 1
        month = 12
    return f"{year}{month:02d}"


def month_range(start: str, end: str) -> list[str]:
    start_year, start_month = int(start[:4]), int(start[4:])
    end_year, end_month = int(end[:4]), int(end[4:])
    months: list[str] = []

    year = start_year
    month = start_month
    while (year, month) <= (end_year, end_month):
        months.append(f"{year}{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1

    return months


def select_monthly_files(input_dir: Path, prefix: str) -> tuple[list[Path], list[str]]:
    pattern = re.compile(rf"^{re.escape(prefix)}(?P<month>\d{{6}})(?P<filled>_filled)?\.csv$", re.IGNORECASE)
    by_month: dict[str, list[Path]] = {}

    for path in sorted(input_dir.glob(f"{prefix}*.csv")):
        match = pattern.match(path.name)
        if not match:
            continue
        by_month.setdefault(match.group("month"), []).append(path)

    selected: list[Path] = []
    notes: list[str] = []

    for month, files in sorted(by_month.items()):
        filled = [path for path in files if "_filled" in path.stem.lower()]
        plain = [path for path in files if "_filled" not in path.stem.lower()]
        chosen = sorted(filled or plain)[0]
        selected.append(chosen)

        skipped = sorted(path.name for path in files if path != chosen)
        if skipped:
            notes.append(f"{prefix}{month}: using {chosen.name}, skipping {', '.join(skipped)}")

    return selected, notes


def combine_group(files: list[Path], output_path: Path, report_path: Path, label: str) -> None:
    if not files:
        raise ValueError(f"No {label} files found.")

    report_rows: list[dict[str, object]] = []
    total_residential_rows = 0
    wrote_header = False

    print(f"\n{label.upper()} FILES")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists():
        output_path.unlink()

    for path in files:
        rows_before = 0
        rows_after = 0

        for chunk in pd.read_csv(path, low_memory=False, chunksize=100_000):
            rows_before += len(chunk)

            if "PropertyType" not in chunk.columns:
                raise ValueError(f"{path.name} does not have a PropertyType column.")

            residential = chunk[chunk["PropertyType"].astype(str).str.strip().eq("Residential")].copy()
            rows_after += len(residential)

            residential.to_csv(output_path, index=False, mode="a", header=not wrote_header)
            wrote_header = True

        print(f"{path.name}: {rows_before:,} rows -> {rows_after:,} Residential rows")
        report_rows.append(
            {
                "group": label,
                "file": path.name,
                "rows_before_residential_filter": rows_before,
                "rows_after_residential_filter": rows_after,
                "rows_removed": rows_before - rows_after,
            }
        )
        total_residential_rows += rows_after

    report = pd.DataFrame(report_rows)
    report.to_csv(report_path, index=False)

    print(f"Saved {total_residential_rows:,} total Residential rows to {output_path}")
    print(f"Saved row-count report to {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Combine monthly CRMLS Listing and Sold CSV files into two Residential-only datasets."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path.home() / "Downloads",
        help="Folder containing the monthly CRMLS CSV files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data") / "processed",
        help="Folder where combined output CSVs should be saved.",
    )
    parser.add_argument("--start-month", default=START_MONTH, help="Expected first month, formatted YYYYMM.")
    parser.add_argument("--end-month", default=previous_month(), help="Expected final month, formatted YYYYMM.")
    args = parser.parse_args()

    input_dir = args.input_dir.expanduser().resolve()
    output_dir = args.output_dir

    listings, listing_notes = select_monthly_files(input_dir, "CRMLSListing")
    sold, sold_notes = select_monthly_files(input_dir, "CRMLSSold")

    print(f"Input folder: {input_dir}")
    print(f"Found {len(listings)} listing monthly files.")
    print(f"Found {len(sold)} sold monthly files.")

    for note in listing_notes + sold_notes:
        print(f"Note: {note}")

    expected = set(month_range(args.start_month, args.end_month))
    listing_months = {re.search(r"(\d{6})", path.name).group(1) for path in listings}
    sold_months = {re.search(r"(\d{6})", path.name).group(1) for path in sold}
    missing_listings = sorted(expected - listing_months)
    missing_sold = sorted(expected - sold_months)

    if missing_listings:
        print(f"Warning: missing listing months: {', '.join(missing_listings)}")
    if missing_sold:
        print(f"Warning: missing sold months: {', '.join(missing_sold)}")

    combine_group(
        listings,
        output_dir / "combined_listings_residential.csv",
        output_dir / "combined_listings_row_counts.csv",
        "listings",
    )
    combine_group(
        sold,
        output_dir / "combined_sold_residential.csv",
        output_dir / "combined_sold_row_counts.csv",
        "sold",
    )


if __name__ == "__main__":
    main()
