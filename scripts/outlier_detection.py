"""Create Week 7 outlier flags and analysis-ready datasets.

The script preserves every feature-ready source row in a flagged dataset and
creates a separate filtered dataset for analysis. Core IQR fields determine
the filtered dataset at 1.5 IQR. Additional fields receive a 1.5 IQR review
flag and use only the more conservative 3.0 IQR fence for filtering.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = PROJECT_ROOT / "data" / "features"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "outliers"
CHUNK_SIZE = 50_000
IQR_MULTIPLIER = 1.5
EXTREME_IQR_MULTIPLIER = 3.0


@dataclass(frozen=True)
class MetricRule:
    field: str
    role: str
    valid_rule: str

    @property
    def flag_column(self) -> str:
        return f"{self.field}IQRFlag"


@dataclass(frozen=True)
class DatasetRule:
    name: str
    input_file: str
    flagged_file: str
    clean_file: str
    metrics: tuple[MetricRule, ...]


DATASETS = (
    DatasetRule(
        name="sold_residential",
        input_file="sold_residential_market_features.csv",
        flagged_file="sold_residential_outlier_flagged.csv",
        clean_file="sold_residential_analysis_clean.csv",
        metrics=(
            MetricRule("ClosePrice", "core_filter", "positive"),
            MetricRule("LivingArea", "core_filter", "positive"),
            MetricRule("DaysOnMarket", "core_filter", "nonnegative"),
            MetricRule("PricePerSqFt", "review_only", "positive"),
            MetricRule(
                "CloseToOriginalListRatio",
                "review_only",
                "positive",
            ),
        ),
    ),
    DatasetRule(
        name="listings_residential",
        input_file="listings_residential_features.csv",
        flagged_file="listings_residential_outlier_flagged.csv",
        clean_file="listings_residential_analysis_clean.csv",
        metrics=(
            MetricRule("ListPrice", "core_filter", "positive"),
            MetricRule("LivingArea", "core_filter", "positive"),
            MetricRule("DaysOnMarket", "core_filter", "nonnegative"),
            MetricRule("OriginalListPrice", "review_only", "positive"),
        ),
    ),
)

DATE_SEQUENCE_FIELDS = (
    "ListingToContractDays",
    "ContractToCloseDays",
)

def invalid_numeric_mask(series: pd.Series, valid_rule: str) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if valid_rule == "positive":
        return numeric.notna() & numeric.le(0)
    if valid_rule == "nonnegative":
        return numeric.notna() & numeric.lt(0)
    raise ValueError(f"Unknown numeric validity rule: {valid_rule}")


def append_reason(
    reasons: pd.Series,
    mask: pd.Series,
    label: str,
) -> None:
    matched = mask.fillna(False)
    if not matched.any():
        return
    current = reasons.loc[matched]
    reasons.loc[matched] = np.where(
        current.eq(""),
        label,
        current + "; " + label,
    )


def calculate_thresholds(
    input_path: Path,
    dataset_rule: DatasetRule,
) -> pd.DataFrame:
    fields = [metric.field for metric in dataset_rule.metrics]
    numeric_data = pd.read_csv(
        input_path,
        usecols=fields,
        low_memory=False,
    )
    rows: list[dict[str, object]] = []

    for metric in dataset_rule.metrics:
        numeric = pd.to_numeric(
            numeric_data[metric.field],
            errors="coerce",
        )
        invalid = invalid_numeric_mask(numeric, metric.valid_rule)
        valid = numeric[numeric.notna() & ~invalid]
        if valid.empty:
            raise ValueError(
                f"No valid values available for {dataset_rule.name} "
                f"{metric.field}"
            )

        q1 = float(valid.quantile(0.25))
        q3 = float(valid.quantile(0.75))
        iqr = q3 - q1
        lower = q1 - IQR_MULTIPLIER * iqr
        upper = q3 + IQR_MULTIPLIER * iqr
        extreme_lower = q1 - EXTREME_IQR_MULTIPLIER * iqr
        extreme_upper = q3 + EXTREME_IQR_MULTIPLIER * iqr
        outlier = valid.lt(lower) | valid.gt(upper)
        extreme_outlier = valid.lt(extreme_lower) | valid.gt(extreme_upper)

        rows.append(
            {
                "Dataset": dataset_rule.name,
                "Field": metric.field,
                "Role": metric.role,
                "ValidBusinessRule": metric.valid_rule,
                "Rows": len(numeric),
                "PopulatedRows": int(numeric.notna().sum()),
                "MissingRows": int(numeric.isna().sum()),
                "BusinessRuleInvalidRows": int(invalid.sum()),
                "ValidRowsUsedForIQR": len(valid),
                "Minimum": float(valid.min()),
                "P01": float(valid.quantile(0.01)),
                "P05": float(valid.quantile(0.05)),
                "Q1": q1,
                "Median": float(valid.median()),
                "Q3": q3,
                "P95": float(valid.quantile(0.95)),
                "P99": float(valid.quantile(0.99)),
                "Maximum": float(valid.max()),
                "IQR": iqr,
                "LowerBound": lower,
                "UpperBound": upper,
                "ExtremeLowerBound": extreme_lower,
                "ExtremeUpperBound": extreme_upper,
                "IQRFlaggedRows": int(outlier.sum()),
                "IQRFlaggedPercentOfValid": float(outlier.mean()),
                "ExtremeIQRFlaggedRows": int(extreme_outlier.sum()),
                "ExtremeIQRFlaggedPercentOfValid": float(
                    extreme_outlier.mean()
                ),
            }
        )
    return pd.DataFrame(rows)


def threshold_map(
    thresholds: pd.DataFrame,
) -> dict[str, tuple[float, float]]:
    return {
        row.Field: (float(row.LowerBound), float(row.UpperBound))
        for row in thresholds.itertuples(index=False)
    }


def process_dataset(
    input_path: Path,
    flagged_path: Path,
    clean_path: Path,
    dataset_rule: DatasetRule,
    thresholds: pd.DataFrame,
    chunk_size: int,
) -> tuple[
    dict[str, object],
    Counter[str],
    Counter[str],
    list[dict[str, object]],
]:
    required = {
        *(metric.field for metric in dataset_rule.metrics),
        *DATE_SEQUENCE_FIELDS,
    }
    input_columns = list(pd.read_csv(input_path, nrows=0).columns)
    missing = required - set(input_columns)
    if missing:
        raise ValueError(
            f"{input_path.name} is missing Week 7 fields: "
            + ", ".join(sorted(missing))
        )

    flagged_path.unlink(missing_ok=True)
    clean_path.unlink(missing_ok=True)

    bounds = threshold_map(thresholds)
    counters: dict[str, object] = {
        "Dataset": dataset_rule.name,
        "InputRows": 0,
        "FlaggedOutputRows": 0,
        "CleanOutputRows": 0,
        "BusinessRuleInvalidRows": 0,
        "DateSequenceInvalidRows": 0,
        "CoreIQRRows": 0,
        "ReviewIQRRows": 0,
        "ExtremeReviewIQRRows": 0,
        "AnyIQRRows": 0,
        "AnyOutlierRows": 0,
        "AnalysisExcludedRows": 0,
    }
    for metric in dataset_rule.metrics:
        counters[f"{metric.field}IQRRows"] = 0
        counters[f"{metric.field}ExtremeIQRRows"] = 0

    reason_counts: Counter[str] = Counter()
    exclusion_reason_counts: Counter[str] = Counter()
    samples: list[dict[str, object]] = []
    flagged_header = False
    clean_header = False

    for chunk in pd.read_csv(
        input_path,
        chunksize=chunk_size,
        low_memory=False,
    ):
        counters["InputRows"] += len(chunk)
        reasons = pd.Series("", index=chunk.index, dtype="string")
        exclusion_reasons = pd.Series(
            "",
            index=chunk.index,
            dtype="string",
        )
        business_invalid = pd.Series(False, index=chunk.index)
        core_iqr = pd.Series(False, index=chunk.index)
        review_iqr = pd.Series(False, index=chunk.index)
        extreme_review_iqr = pd.Series(False, index=chunk.index)
        flag_count = pd.Series(0, index=chunk.index, dtype="int16")

        for metric in dataset_rule.metrics:
            numeric = pd.to_numeric(chunk[metric.field], errors="coerce")
            invalid = invalid_numeric_mask(numeric, metric.valid_rule)
            lower, upper = bounds[metric.field]
            threshold_row = thresholds.loc[
                thresholds["Field"].eq(metric.field)
            ].iloc[0]
            extreme_lower = float(threshold_row["ExtremeLowerBound"])
            extreme_upper = float(threshold_row["ExtremeUpperBound"])
            iqr_flag = (
                numeric.notna()
                & ~invalid
                & (numeric.lt(lower) | numeric.gt(upper))
            )
            extreme_iqr_flag = (
                numeric.notna()
                & ~invalid
                & (
                    numeric.lt(extreme_lower)
                    | numeric.gt(extreme_upper)
                )
            )
            chunk[metric.flag_column] = iqr_flag
            chunk[f"{metric.field}ExtremeIQRFlag"] = extreme_iqr_flag
            counters[f"{metric.field}IQRRows"] += int(iqr_flag.sum())
            counters[f"{metric.field}ExtremeIQRRows"] += int(
                extreme_iqr_flag.sum()
            )
            flag_count += iqr_flag.astype("int16")

            invalid_label = (
                f"{metric.field} < 0"
                if metric.valid_rule == "nonnegative"
                else f"{metric.field} <= 0"
            )
            append_reason(reasons, invalid, invalid_label)
            append_reason(exclusion_reasons, invalid, invalid_label)
            business_invalid |= invalid

            outlier_label = f"{metric.field} outside 1.5 IQR"
            append_reason(reasons, iqr_flag, outlier_label)
            if metric.role == "core_filter":
                core_iqr |= iqr_flag
                append_reason(
                    exclusion_reasons,
                    iqr_flag,
                    outlier_label,
                )
            else:
                review_iqr |= iqr_flag
                extreme_review_iqr |= extreme_iqr_flag
                append_reason(
                    exclusion_reasons,
                    extreme_iqr_flag,
                    f"{metric.field} outside 3.0 IQR extreme fence",
                )

        date_invalid = pd.Series(False, index=chunk.index)
        for field in DATE_SEQUENCE_FIELDS:
            invalid_date = pd.to_numeric(
                chunk[field],
                errors="coerce",
            ).lt(0)
            label = f"{field} < 0"
            append_reason(reasons, invalid_date, label)
            append_reason(exclusion_reasons, invalid_date, label)
            date_invalid |= invalid_date

        any_iqr = core_iqr | review_iqr
        any_outlier = business_invalid | date_invalid | any_iqr
        analysis_exclude = (
            business_invalid
            | date_invalid
            | core_iqr
            | extreme_review_iqr
        )
        flag_count += business_invalid.astype("int16")
        flag_count += date_invalid.astype("int16")

        chunk["BusinessRuleInvalidFlag"] = business_invalid
        chunk["DateSequenceInvalidFlag"] = date_invalid
        chunk["CoreIQRFlag"] = core_iqr
        chunk["ReviewIQRFlag"] = review_iqr
        chunk["ExtremeReviewIQRFlag"] = extreme_review_iqr
        chunk["AnyIQRFlag"] = any_iqr
        chunk["AnyOutlierFlag"] = any_outlier
        chunk["AnalysisExcludeFlag"] = analysis_exclude
        chunk["OutlierFlagCount"] = flag_count
        chunk["OutlierReason"] = reasons.mask(reasons.eq(""), pd.NA)
        chunk["AnalysisExclusionReason"] = exclusion_reasons.mask(
            exclusion_reasons.eq(""),
            pd.NA,
        )

        counters["BusinessRuleInvalidRows"] += int(
            business_invalid.sum()
        )
        counters["DateSequenceInvalidRows"] += int(date_invalid.sum())
        counters["CoreIQRRows"] += int(core_iqr.sum())
        counters["ReviewIQRRows"] += int(review_iqr.sum())
        counters["ExtremeReviewIQRRows"] += int(
            extreme_review_iqr.sum()
        )
        counters["AnyIQRRows"] += int(any_iqr.sum())
        counters["AnyOutlierRows"] += int(any_outlier.sum())
        counters["AnalysisExcludedRows"] += int(analysis_exclude.sum())

        for reason, count in (
            chunk.loc[any_outlier, "OutlierReason"]
            .value_counts()
            .items()
        ):
            reason_counts[str(reason)] += int(count)
        for reason, count in (
            chunk.loc[analysis_exclude, "AnalysisExclusionReason"]
            .value_counts()
            .items()
        ):
            exclusion_reason_counts[str(reason)] += int(count)

        if len(samples) < 30:
            sample_fields = [
                field
                for field in (
                    "PropertyType",
                    "PropertySubType",
                    "CountyOrParish",
                    *(metric.field for metric in dataset_rule.metrics),
                    "OutlierFlagCount",
                    "AnalysisExcludeFlag",
                    "OutlierReason",
                )
                if field in chunk.columns
            ]
            candidates = (
                chunk.loc[any_outlier, sample_fields]
                .sort_values(
                    ["OutlierFlagCount"],
                    ascending=False,
                )
                .head(30 - len(samples))
                .copy()
            )
            candidates.insert(0, "Dataset", dataset_rule.name)
            samples.extend(candidates.to_dict("records"))

        chunk.to_csv(
            flagged_path,
            index=False,
            mode="a" if flagged_header else "w",
            header=not flagged_header,
        )
        flagged_header = True
        counters["FlaggedOutputRows"] += len(chunk)

        clean_chunk = chunk.loc[~analysis_exclude]
        clean_chunk.to_csv(
            clean_path,
            index=False,
            mode="a" if clean_header else "w",
            header=not clean_header,
        )
        clean_header = True
        counters["CleanOutputRows"] += len(clean_chunk)

    counters["FlaggedRowsPreserved"] = (
        counters["InputRows"] == counters["FlaggedOutputRows"]
    )
    counters["CleanPlusExcludedReconciles"] = (
        counters["CleanOutputRows"] + counters["AnalysisExcludedRows"]
        == counters["InputRows"]
    )
    counters["AnalysisExcludedPercent"] = (
        counters["AnalysisExcludedRows"] / counters["InputRows"]
    )
    return counters, reason_counts, exclusion_reason_counts, samples


def comparison_report(
    source_path: Path,
    clean_path: Path,
    dataset_rule: DatasetRule,
) -> pd.DataFrame:
    fields = [metric.field for metric in dataset_rule.metrics]
    before = pd.read_csv(source_path, usecols=fields, low_memory=False)
    after = pd.read_csv(clean_path, usecols=fields, low_memory=False)
    rows: list[dict[str, object]] = []

    for field in fields:
        before_values = pd.to_numeric(before[field], errors="coerce")
        after_values = pd.to_numeric(after[field], errors="coerce")
        before_median = float(before_values.median())
        after_median = float(after_values.median())
        before_mean = float(before_values.mean())
        after_mean = float(after_values.mean())
        rows.append(
            {
                "Dataset": dataset_rule.name,
                "Field": field,
                "BeforeRows": len(before),
                "AfterRows": len(after),
                "RowsRemoved": len(before) - len(after),
                "RowsRemovedPercent": (
                    (len(before) - len(after)) / len(before)
                ),
                "BeforePopulatedRows": int(before_values.notna().sum()),
                "AfterPopulatedRows": int(after_values.notna().sum()),
                "BeforeMedian": before_median,
                "AfterMedian": after_median,
                "MedianChange": after_median - before_median,
                "MedianChangePercent": (
                    (after_median - before_median) / before_median
                    if before_median
                    else np.nan
                ),
                "BeforeMean": before_mean,
                "AfterMean": after_mean,
                "MeanChange": after_mean - before_mean,
                "MeanChangePercent": (
                    (after_mean - before_mean) / before_mean
                    if before_mean
                    else np.nan
                ),
            }
        )

    return pd.DataFrame(rows)


def create_flag_summary(
    thresholds: pd.DataFrame,
    counters: list[dict[str, object]],
) -> pd.DataFrame:
    counter_map = {row["Dataset"]: row for row in counters}
    rows: list[dict[str, object]] = []
    for threshold in thresholds.itertuples(index=False):
        dataset_counter = counter_map[threshold.Dataset]
        rows.append(
            {
                "Dataset": threshold.Dataset,
                "FlagType": "IQR",
                "Field": threshold.Field,
                "Role": threshold.Role,
                "FlaggedRows": dataset_counter[
                    f"{threshold.Field}IQRRows"
                ],
                "DatasetRows": dataset_counter["InputRows"],
                "FlaggedPercent": (
                    dataset_counter[f"{threshold.Field}IQRRows"]
                    / dataset_counter["InputRows"]
                ),
                "UsedToExcludeFromCleanDataset": (
                    threshold.Role == "core_filter"
                ),
            }
        )
        if threshold.Role == "review_only":
            extreme_rows = dataset_counter[
                f"{threshold.Field}ExtremeIQRRows"
            ]
            rows.append(
                {
                    "Dataset": threshold.Dataset,
                    "FlagType": "Extreme IQR",
                    "Field": threshold.Field,
                    "Role": "extreme_review_filter",
                    "FlaggedRows": extreme_rows,
                    "DatasetRows": dataset_counter["InputRows"],
                    "FlaggedPercent": (
                        extreme_rows / dataset_counter["InputRows"]
                    ),
                    "UsedToExcludeFromCleanDataset": True,
                }
            )

    for dataset_counter in counters:
        for label, field in (
            ("Business Rule", "BusinessRuleInvalidRows"),
            ("Date Sequence", "DateSequenceInvalidRows"),
        ):
            rows.append(
                {
                    "Dataset": dataset_counter["Dataset"],
                    "FlagType": label,
                    "Field": label,
                    "Role": "always_exclude",
                    "FlaggedRows": dataset_counter[field],
                    "DatasetRows": dataset_counter["InputRows"],
                    "FlaggedPercent": (
                        dataset_counter[field]
                        / dataset_counter["InputRows"]
                    ),
                    "UsedToExcludeFromCleanDataset": True,
                }
            )
    return pd.DataFrame(rows)


def validation_report(
    source_path: Path,
    output_dir: Path,
    dataset_rule: DatasetRule,
    counters: dict[str, object],
    chunk_size: int,
) -> dict[str, object]:
    flagged_path = output_dir / dataset_rule.flagged_file
    clean_path = output_dir / dataset_rule.clean_file
    flagged_rows = 0
    clean_rows = 0
    flagged_source_errors = 0
    clean_exclusion_errors = 0

    source_reader = pd.read_csv(
        source_path,
        usecols=["ListingKey"],
        chunksize=chunk_size,
        low_memory=False,
    )
    flagged_reader = pd.read_csv(
        flagged_path,
        usecols=["ListingKey", "AnalysisExcludeFlag"],
        chunksize=chunk_size,
        low_memory=False,
    )
    for source, flagged in zip(source_reader, flagged_reader):
        flagged_rows += len(flagged)
        left = source["ListingKey"].fillna("").astype(str)
        right = flagged["ListingKey"].fillna("").astype(str)
        flagged_source_errors += int((left != right).sum())

    for clean in pd.read_csv(
        clean_path,
        usecols=["AnalysisExcludeFlag"],
        chunksize=chunk_size,
        low_memory=False,
    ):
        clean_rows += len(clean)
        clean_exclusion_errors += int(
            clean["AnalysisExcludeFlag"].astype(bool).sum()
        )

    return {
        "Dataset": dataset_rule.name,
        "ExpectedSourceRows": counters["InputRows"],
        "CheckedFlaggedRows": flagged_rows,
        "CheckedCleanRows": clean_rows,
        "FlaggedListingKeyOrderErrors": flagged_source_errors,
        "CleanRowsStillMarkedForExclusion": clean_exclusion_errors,
        "FlaggedRowsPreserved": (
            flagged_rows == counters["InputRows"]
            and flagged_source_errors == 0
        ),
        "CleanRowsCorrect": (
            clean_rows == counters["CleanOutputRows"]
            and clean_exclusion_errors == 0
        ),
        "CleanPlusExcludedReconciles": counters[
            "CleanPlusExcludedReconciles"
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create Week 7 flagged and IQR-filtered datasets."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Folder containing Week 6 feature-ready datasets.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Folder where Week 7 datasets and reports are saved.",
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
    output_dir.mkdir(parents=True, exist_ok=True)

    all_thresholds: list[pd.DataFrame] = []
    all_counters: list[dict[str, object]] = []
    all_comparisons: list[pd.DataFrame] = []
    all_reason_rows: list[dict[str, object]] = []
    all_exclusion_reason_rows: list[dict[str, object]] = []
    all_samples: list[dict[str, object]] = []

    for dataset_rule in DATASETS:
        input_path = input_dir / dataset_rule.input_file
        flagged_path = output_dir / dataset_rule.flagged_file
        clean_path = output_dir / dataset_rule.clean_file
        print(f"\nProfiling {dataset_rule.name}")
        thresholds = calculate_thresholds(input_path, dataset_rule)
        all_thresholds.append(thresholds)

        print(f"Flagging {input_path.name}")
        (
            counters,
            reason_counts,
            exclusion_reason_counts,
            samples,
        ) = process_dataset(
            input_path=input_path,
            flagged_path=flagged_path,
            clean_path=clean_path,
            dataset_rule=dataset_rule,
            thresholds=thresholds,
            chunk_size=args.chunk_size,
        )
        all_counters.append(counters)
        all_samples.extend(samples)
        all_reason_rows.extend(
            {
                "Dataset": dataset_rule.name,
                "OutlierReasonCombination": reason,
                "Rows": count,
            }
            for reason, count in reason_counts.most_common()
        )
        all_exclusion_reason_rows.extend(
            {
                "Dataset": dataset_rule.name,
                "AnalysisExclusionReasonCombination": reason,
                "Rows": count,
            }
            for reason, count in exclusion_reason_counts.most_common()
        )

        print(
            f"Preserved {counters['FlaggedOutputRows']:,} flagged rows; "
            f"saved {counters['CleanOutputRows']:,} clean rows"
        )
        all_comparisons.append(
            comparison_report(input_path, clean_path, dataset_rule)
        )

    thresholds_report = pd.concat(all_thresholds, ignore_index=True)
    thresholds_report.to_csv(
        output_dir / "week7_iqr_thresholds.csv",
        index=False,
    )

    dataset_summary = pd.DataFrame(all_counters)
    dataset_summary.to_csv(
        output_dir / "week7_dataset_summary.csv",
        index=False,
    )

    comparison = pd.concat(all_comparisons, ignore_index=True)
    comparison.to_csv(
        output_dir / "week7_before_after_comparison.csv",
        index=False,
    )

    flag_summary = create_flag_summary(
        thresholds_report,
        all_counters,
    )
    flag_summary.to_csv(
        output_dir / "week7_flag_summary.csv",
        index=False,
    )

    pd.DataFrame(all_reason_rows).to_csv(
        output_dir / "week7_reason_combinations.csv",
        index=False,
    )
    pd.DataFrame(all_exclusion_reason_rows).to_csv(
        output_dir / "week7_exclusion_reason_combinations.csv",
        index=False,
    )
    pd.DataFrame(all_samples).to_csv(
        output_dir / "week7_anonymized_flagged_sample.csv",
        index=False,
    )

    validations = [
        validation_report(
            source_path=input_dir / dataset_rule.input_file,
            output_dir=output_dir,
            dataset_rule=dataset_rule,
            counters=counters,
            chunk_size=args.chunk_size,
        )
        for dataset_rule, counters in zip(DATASETS, all_counters)
    ]
    validation = pd.DataFrame(validations)
    validation.to_csv(
        output_dir / "week7_validation_summary.csv",
        index=False,
    )

    if not (
        validation["FlaggedRowsPreserved"].all()
        and validation["CleanRowsCorrect"].all()
        and validation["CleanPlusExcludedReconciles"].all()
    ):
        raise RuntimeError("Week 7 validation failed.")

    print(f"\nWeek 7 outputs saved to {output_dir}")


if __name__ == "__main__":
    main()
