"""Build Dashboard 1: California Market Pulse.

The workbook uses the Tableau-ready Residential market file, the 3.0 IQR
dashboard population, and the latest available analysis month. Running this
script replaces only the generated California Market Pulse workbook.
"""

from __future__ import annotations

import argparse
import copy
import csv
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
from lxml import etree


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = PROJECT_ROOT / "data" / "tableau" / "market_analysis_tableau.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "tableau" / "california_market_pulse_final.twbx"
DEFAULT_TEMPLATE = (
    PROJECT_ROOT / "tableau" / "templates" / "market_analysis_template.twbx"
)
TEMPLATE_SHEET = "Monthly Median Close Price"
DASHBOARD_NAME = "California Market Pulse"

COLORS = {
    "navy": "#17324D",
    "teal": "#0B6E69",
    "gold": "#D79B2E",
    "blue": "#3B6FB6",
    "ink": "#25313C",
    "muted": "#65727E",
    "border": "#D8E0E7",
    "white": "#FFFFFF",
}

SHARED_FILTERS = (
    ("CountyOrParish", "County", "string", "nominal", "10"),
    ("City", "City", "string", "nominal", "11"),
    ("PropertySubType", "Property Subtype", "string", "nominal", "12"),
)


@dataclass(frozen=True)
class Metric:
    sheet_name: str
    field: str
    caption: str
    derivation: str
    token: str
    activity_type: str
    number_format: str
    display_formula: str | None = None


KPI_METRICS = (
    Metric(
        "KPI Median Close Price",
        "ClosePrice",
        "Median Close Price",
        "Median",
        "med",
        "Closed Sale",
        '"$"#,##0',
        'IF ISNULL(MEDIAN([ClosePrice])) THEN "No data" ELSE "$" + '
        'STR(ROUND(MEDIAN([ClosePrice]) / 1000, 0)) + "K" END',
    ),
    Metric(
        "KPI New Listings",
        "NewListings",
        "New Listings",
        "Sum",
        "sum",
        "New Listing",
        "#,##0",
    ),
    Metric(
        "KPI Closed Sales",
        "ClosedSales",
        "Closed Sales",
        "Sum",
        "sum",
        "Closed Sale",
        "#,##0",
    ),
    Metric(
        "KPI Average DOM",
        "SoldDaysOnMarket",
        "Average Days on Market",
        "Avg",
        "avg",
        "Closed Sale",
        "0.0",
        'IF ISNULL(AVG([SoldDaysOnMarket])) THEN "No data" ELSE '
        'STR(ROUND(AVG([SoldDaysOnMarket]), 1)) END',
    ),
    Metric(
        "KPI Sale to Original",
        "CloseToOriginalListRatio",
        "Sale to Original List",
        "Avg",
        "avg",
        "Closed Sale",
        "p1",
        'IF ISNULL(AVG([CloseToOriginalListRatio])) THEN "No data" ELSE '
        'STR(ROUND(AVG([CloseToOriginalListRatio]) * 100, 1)) + "%" END',
    ),
)

HYPER_COLUMNS = (
    ("ActivityKey", "text"),
    ("ListingKey", "big_int"),
    ("ActivityType", "text"),
    ("AnalysisMonth", "date"),
    ("AnalysisYrMo", "big_int"),
    ("NewListings", "big_int"),
    ("ClosedSales", "big_int"),
    ("ClosePrice", "double"),
    ("ListPrice", "double"),
    ("OriginalListPrice", "double"),
    ("LivingArea", "double"),
    ("SoldDaysOnMarket", "double"),
    ("ListingDaysOnMarket", "text"),
    ("CloseToOriginalListRatio", "double"),
    ("PricePerSqFt", "double"),
    ("ListingToContractDays", "double"),
    ("ContractToCloseDays", "double"),
    ("PropertySubType", "text"),
    ("City", "text"),
    ("CountyOrParish", "text"),
    ("PostalCode", "text"),
    ("MLSAreaMajor", "text"),
    ("Latitude", "double"),
    ("Longitude", "double"),
    ("rate_30yr_fixed", "double"),
    ("CDEElementarySchoolDistrict", "text"),
    ("CDEHighSchoolDistrict", "text"),
    ("CDEUnifiedSchoolDistrict", "text"),
)


def new_uuid() -> str:
    return "{" + str(uuid.uuid4()).upper() + "}"


def qualified(datasource: str, instance: str) -> str:
    return f"[{datasource}].[{instance}]"


def replace_tokens(element: etree._Element, replacements: dict[str, str]) -> None:
    ordered = sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True)
    for node in element.iter():
        for attribute, value in list(node.attrib.items()):
            updated = value
            for old, new in ordered:
                updated = updated.replace(old, new)
            node.attrib[attribute] = updated
        if node.text:
            updated = node.text
            for old, new in ordered:
                updated = updated.replace(old, new)
            node.text = updated


def latest_month(data_path: Path) -> pd.Timestamp:
    months = pd.read_csv(data_path, usecols=["AnalysisMonth"])["AnalysisMonth"]
    parsed = pd.to_datetime(months, errors="coerce")
    if parsed.notna().sum() == 0:
        raise ValueError(f"No valid AnalysisMonth values found in {data_path}")
    return parsed.max().to_period("M").to_timestamp()


def source_header(data_path: Path) -> list[str]:
    with data_path.open("r", encoding="utf-8-sig", newline="") as source:
        header = next(csv.reader(source))
    expected = [name for name, _ in HYPER_COLUMNS]
    missing = [name for name in expected if name not in header]
    if missing:
        raise ValueError(
            "The Tableau CSV is missing required dashboard columns: "
            f"{missing}."
        )
    return header


def sql_type(kind: str):
    from tableauhyperapi import SqlType

    return {
        "text": SqlType.text(),
        "big_int": SqlType.big_int(),
        "date": SqlType.date(),
        "double": SqlType.double(),
    }[kind]


def build_hyper_extract(data_path: Path, extract_path: Path) -> None:
    try:
        from tableauhyperapi import (
            Connection,
            CreateMode,
            HyperProcess,
            Inserter,
            TableDefinition,
            TableName,
            Telemetry,
        )
    except ImportError as error:
        raise RuntimeError(
            "tableauhyperapi is required to refresh the packaged Tableau data."
        ) from error

    table = TableName("Extract", "Extract")
    definition = TableDefinition(
        table,
        [
            TableDefinition.Column(name, sql_type(kind))
            for name, kind in HYPER_COLUMNS
        ],
    )
    extract_path.parent.mkdir(parents=True, exist_ok=True)

    dtype = {
        name: "string"
        for name, kind in HYPER_COLUMNS
        if kind in {"text", "date"}
    }
    with HyperProcess(
        Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU,
        parameters={"log_config": ""},
    ) as hyper:
        with Connection(
            hyper.endpoint,
            str(extract_path),
            CreateMode.CREATE_AND_REPLACE,
        ) as connection:
            connection.catalog.create_schema("Extract")
            connection.catalog.create_table(definition)
            for chunk in pd.read_csv(
                data_path,
                usecols=[name for name, _ in HYPER_COLUMNS],
                dtype=dtype,
                low_memory=False,
                chunksize=25_000,
            ):
                rows: list[tuple[object, ...]] = []
                for record in chunk.itertuples(index=False, name=None):
                    cleaned: list[object] = []
                    for value, (_, kind) in zip(record, HYPER_COLUMNS):
                        if pd.isna(value):
                            cleaned.append(None)
                        elif kind == "date":
                            cleaned.append(datetime.strptime(str(value), "%Y-%m-%d").date())
                        elif kind == "big_int":
                            cleaned.append(int(value))
                        elif kind == "double":
                            cleaned.append(float(value))
                        else:
                            cleaned.append(str(value))
                    rows.append(tuple(cleaned))
                with Inserter(connection, definition) as inserter:
                    inserter.add_rows(rows)
                    inserter.execute()


def update_source_schema(datasource: etree._Element, header: list[str]) -> None:
    source_ordinals = {name: index for index, name in enumerate(header)}
    extract_ordinals = {
        name: index for index, (name, _) in enumerate(HYPER_COLUMNS)
    }
    tableau_types = {
        "text": "string",
        "big_int": "integer",
        "date": "date",
        "double": "real",
    }
    kinds = {name: kind for name, kind in HYPER_COLUMNS}
    relations = datasource.xpath("./connection/relation")
    if len(relations) != 1:
        raise ValueError("Expected one Tableau source relation.")
    relation = relations[0]
    columns = relation.find("columns")
    if columns is None:
        raise ValueError("The Tableau source relation has no column list.")

    for column in list(columns.findall("column")):
        name = column.attrib.get("name")
        if name not in extract_ordinals:
            columns.remove(column)
            continue
        if name in source_ordinals:
            column.attrib["ordinal"] = str(source_ordinals[name])
            column.attrib["datatype"] = tableau_types[kinds[name]]

    metadata_sets = [
        (metadata, source_ordinals)
        for metadata in relation.xpath("./metadata-records")
    ]
    extract = datasource.find("extract")
    if extract is not None:
        metadata_sets.extend(
            (metadata, extract_ordinals)
            for metadata in extract.xpath("./connection/metadata-records")
        )

    for metadata, ordinals in metadata_sets:
        for record in list(metadata.findall("metadata-record")):
            if record.attrib.get("class") != "column":
                continue
            name = record.findtext("remote-name")
            if name not in extract_ordinals:
                metadata.remove(record)
                continue
            ordinal = record.find("ordinal")
            if name in ordinals and ordinal is not None:
                ordinal.text = str(ordinals[name])
            if name == "PostalCode":
                record.find("remote-type").text = "129"
                record.find("local-type").text = "string"
                record.find("aggregation").text = "Count"

    for column in list(datasource.findall("column")):
        field_name = column.attrib.get("name", "").strip("[]")
        if field_name not in extract_ordinals:
            datasource.remove(column)
    postal_column = datasource.find("column[@name='[PostalCode]']")
    if postal_column is not None:
        postal_column.attrib["datatype"] = "string"
        postal_column.attrib["role"] = "dimension"
        postal_column.attrib["type"] = "nominal"


def point_extract_to(datasource: etree._Element, package_path: str) -> None:
    extract = datasource.find("extract")
    if extract is None:
        raise ValueError("The Tableau template has no extract definition.")
    connection = extract.find("connection")
    if connection is None:
        raise ValueError("The Tableau extract has no connection.")
    connection.attrib["dbname"] = package_path.replace("\\", "/")
    connection.attrib["update-time"] = datetime.now().strftime("%m/%d/%Y %I:%M:%S %p")


def set_sheet_title(worksheet: etree._Element, title: str) -> None:
    layout = worksheet.find("layout-options")
    if layout is None:
        layout = etree.Element("layout-options")
        worksheet.insert(0, layout)
    title_node = layout.find("title")
    if title_node is None:
        title_node = etree.SubElement(layout, "title")
    title_node.clear()
    formatted = etree.SubElement(title_node, "formatted-text")
    etree.SubElement(
        formatted,
        "run",
        bold="true",
        fontcolor=COLORS["ink"],
        fontsize="12",
    ).text = title


def set_default_format(
    worksheet: etree._Element,
    field: str,
    number_format: str,
) -> None:
    dependency = worksheet.find(
        f"./table/view/datasource-dependencies/column[@name='[{field}]']"
    )
    if dependency is not None:
        dependency.attrib["default-format"] = number_format


def set_datasource_default_format(
    datasource: etree._Element,
    field: str,
    number_format: str,
) -> None:
    column = datasource.find(f"column[@name='[{field}]']")
    if column is None:
        raise ValueError(f"Datasource field {field!r} was not found.")
    column.attrib["default-format"] = number_format


def set_axis_title(
    worksheet: etree._Element,
    datasource: str,
    instance: str,
    scope: str,
    title: str,
) -> etree._Element:
    table = worksheet.find("table")
    if table is None:
        raise ValueError(f"Worksheet {worksheet.attrib['name']!r} has no table.")
    style = table.find("style")
    if style is None:
        style = etree.Element("style")
        table.insert(1, style)
    axis_rule = style.find("style-rule[@element='axis']")
    if axis_rule is None:
        axis_rule = etree.SubElement(style, "style-rule", element="axis")
    field = qualified(datasource, instance)
    etree.SubElement(
        axis_rule,
        "format",
        attr="title",
        **{"class": "0", "field": field, "scope": scope, "value": title},
    )
    return axis_rule


def exclude_zero_from_axis(
    worksheet: etree._Element,
    datasource: str,
    instance: str,
) -> None:
    table = worksheet.find("table")
    if table is None:
        raise ValueError(f"Worksheet {worksheet.attrib['name']!r} has no table.")
    style = table.find("style")
    if style is None:
        style = etree.Element("style")
        table.insert(1, style)
    axis_rule = style.find("style-rule[@element='axis']")
    if axis_rule is None:
        axis_rule = etree.SubElement(style, "style-rule", element="axis")
    field = qualified(datasource, instance)
    encoding = axis_rule.find(
        f"encoding[@attr='space'][@field='{field}'][@scope='rows']"
    )
    if encoding is None:
        encoding = etree.Element(
            "encoding",
            attr="space",
            **{
                "class": "0",
                "domain-expand": "false",
                "field": field,
                "field-type": "quantitative",
                "scope": "rows",
                "type": "space",
            },
        )
        axis_rule.insert(0, encoding)
    else:
        encoding.attrib["domain-expand"] = "false"


def shared_filter_references(datasource: str) -> set[str]:
    return {
        qualified(datasource, f"none:{field}:nk")
        for field, _, _, _, _ in SHARED_FILTERS
    } | {qualified(datasource, "none:PostalCode:nk")}


def add_shared_filters(worksheet: etree._Element, datasource: str) -> None:
    view = worksheet.find("./table/view")
    if view is None:
        raise ValueError(f"Worksheet {worksheet.attrib['name']!r} has no view.")
    dependencies = view.find(f"datasource-dependencies[@datasource='{datasource}']")
    slices = view.find("slices")
    if dependencies is None or slices is None:
        raise ValueError("Worksheet is missing dependencies or slices.")

    removable = shared_filter_references(datasource)
    for filter_node in list(view.findall("filter")):
        if filter_node.attrib.get("column") in removable:
            view.remove(filter_node)
    for slice_node in list(slices.findall("column")):
        if slice_node.text in removable:
            slices.remove(slice_node)

    existing_columns = {
        column.attrib.get("name") for column in dependencies.findall("column")
    }
    existing_instances = {
        instance.attrib.get("name")
        for instance in dependencies.findall("column-instance")
    }
    slices_index = list(view).index(slices)

    for field, caption, datatype, field_type, group in SHARED_FILTERS:
        column_name = f"[{field}]"
        instance_name = f"[none:{field}:nk]"
        reference = qualified(datasource, f"none:{field}:nk")
        if column_name not in existing_columns:
            dependencies.append(
                etree.Element(
                    "column",
                    caption=caption,
                    datatype=datatype,
                    name=column_name,
                    role="dimension",
                    type=field_type,
                )
            )
        if instance_name not in existing_instances:
            dependencies.append(
                etree.Element(
                    "column-instance",
                    column=column_name,
                    derivation="None",
                    name=instance_name,
                    pivot="key",
                    type=field_type,
                )
            )
        filter_node = etree.Element(
            "filter",
            **{
                "class": "categorical",
                "column": reference,
                "filter-group": group,
            },
        )
        etree.SubElement(
            filter_node,
            "groupfilter",
            function="level-members",
            level=instance_name,
        )
        view.insert(slices_index, filter_node)
        slices_index += 1
        etree.SubElement(slices, "column").text = reference


def clone_metric_sheet(
    template: etree._Element,
    metric: Metric,
) -> etree._Element:
    worksheet = copy.deepcopy(template)
    replacements = {
        TEMPLATE_SHEET: metric.sheet_name,
        "med:ClosePrice:qk": f"{metric.token}:{metric.field}:qk",
        "Close Price": metric.caption,
        "ClosePrice": metric.field,
        "Median": metric.derivation,
        "Closed Sale": metric.activity_type,
    }
    replace_tokens(worksheet, replacements)
    worksheet.attrib["name"] = metric.sheet_name
    for simple_id in worksheet.xpath(".//simple-id"):
        simple_id.attrib["uuid"] = new_uuid()
    return worksheet


def add_latest_month_filter(
    worksheet: etree._Element,
    datasource: str,
    month: pd.Timestamp,
) -> None:
    view = worksheet.find("./table/view")
    slices = view.find("slices") if view is not None else None
    if view is None or slices is None:
        raise ValueError("KPI sheet is missing its Tableau view.")
    month_reference = qualified(datasource, "tmn:AnalysisMonth:qk")
    filter_node = etree.Element(
        "filter",
        **{
            "class": "quantitative",
            "column": month_reference,
            "included-values": "in-range",
        },
    )
    date_literal = f"#{month:%Y-%m-%d}#"
    etree.SubElement(filter_node, "min").text = date_literal
    etree.SubElement(filter_node, "max").text = date_literal
    view.insert(list(view).index(slices), filter_node)
    etree.SubElement(slices, "column").text = month_reference


def add_kpi_display_calculation(
    worksheet: etree._Element,
    metric: Metric,
    datasource: str,
) -> str:
    dependencies = worksheet.find(
        f"./table/view/datasource-dependencies[@datasource='{datasource}']"
    )
    if dependencies is None or metric.display_formula is None:
        raise ValueError("KPI display calculation dependencies are missing.")

    display_name = f"KPIDisplay{metric.field}"
    column_name = f"[{display_name}]"
    instance_name = f"[usr:{display_name}:nk]"
    column = etree.Element(
        "column",
        caption=f"{metric.caption} Display",
        datatype="string",
        name=column_name,
        role="dimension",
        type="nominal",
    )
    etree.SubElement(
        column,
        "calculation",
        **{"class": "tableau", "formula": metric.display_formula},
    )
    dependencies.append(column)
    dependencies.append(
        etree.Element(
            "column-instance",
            column=column_name,
            derivation="User",
            name=instance_name,
            pivot="key",
            type="nominal",
        )
    )
    return qualified(datasource, f"usr:{display_name}:nk")


def make_kpi_sheet(
    template: etree._Element,
    metric: Metric,
    datasource: str,
    month: pd.Timestamp,
) -> etree._Element:
    worksheet = clone_metric_sheet(template, metric)
    set_sheet_title(worksheet, metric.caption)
    set_default_format(worksheet, metric.field, metric.number_format)
    add_latest_month_filter(worksheet, datasource, month)

    table = worksheet.find("table")
    pane = worksheet.find("./table/panes/pane")
    if table is None or pane is None:
        raise ValueError("KPI template is missing table or pane elements.")
    measure_reference = qualified(datasource, f"{metric.token}:{metric.field}:qk")
    display_reference = measure_reference
    if metric.display_formula is not None:
        display_reference = add_kpi_display_calculation(
            worksheet,
            metric,
            datasource,
        )
    table.find("rows").text = None
    table.find("cols").text = None

    for child_name in ("encodings", "customized-label", "style"):
        child = pane.find(child_name)
        if child is not None:
            pane.remove(child)
    encodings = etree.SubElement(pane, "encodings")
    etree.SubElement(encodings, "text", column=display_reference)
    label = etree.SubElement(pane, "customized-label")
    formatted = etree.SubElement(label, "formatted-text")
    value_run = etree.SubElement(
        formatted,
        "run",
        bold="true",
        fontcolor=COLORS["navy"],
        fontsize="22",
    )
    value_run.text = f"<{display_reference}>"
    etree.SubElement(formatted, "run").text = "\n"
    etree.SubElement(
        formatted,
        "run",
        fontcolor=COLORS["muted"],
        fontsize="10",
    ).text = metric.caption.upper()

    pane_style = etree.SubElement(pane, "style")
    cell_rule = etree.SubElement(pane_style, "style-rule", element="cell")
    etree.SubElement(cell_rule, "format", attr="text-align", value="center")
    mark_rule = etree.SubElement(pane_style, "style-rule", element="mark")
    etree.SubElement(mark_rule, "format", attr="mark-labels-show", value="true")
    etree.SubElement(mark_rule, "format", attr="size", value="1")

    table_style = table.find("style")
    if table_style is None:
        table_style = etree.Element("style")
        table.insert(1, table_style)
    number_rule = etree.SubElement(table_style, "style-rule", element="cell")
    etree.SubElement(
        number_rule,
        "format",
        attr="text-format",
        field=measure_reference,
        value=metric.number_format,
    )
    return worksheet


def make_mortgage_sheet(
    template: etree._Element,
    datasource: str,
) -> etree._Element:
    metric = Metric(
        "Mortgage Rate Trend",
        "rate_30yr_fixed",
        "30-Year Fixed Mortgage Rate",
        "Avg",
        "avg",
        "Closed Sale",
        '0.00"%"',
    )
    worksheet = clone_metric_sheet(template, metric)
    set_sheet_title(worksheet, metric.caption)
    set_default_format(worksheet, metric.field, metric.number_format)
    return worksheet


def make_activity_sheet(
    template: etree._Element,
    datasource: str,
) -> etree._Element:
    worksheet = copy.deepcopy(template)
    replace_tokens(
        worksheet,
        {
            TEMPLATE_SHEET: "Monthly Market Activity",
            "med:ClosePrice:qk": "sum:MarketActivityCount:qk",
            "Close Price": "Market Activity",
            "ClosePrice": "MarketActivityCount",
            "Median": "Sum",
        },
    )
    worksheet.attrib["name"] = "Monthly Market Activity"
    set_sheet_title(worksheet, "New Listings and Closed Sales")
    for simple_id in worksheet.xpath(".//simple-id"):
        simple_id.attrib["uuid"] = new_uuid()

    view = worksheet.find("./table/view")
    dependencies = view.find(
        f"datasource-dependencies[@datasource='{datasource}']"
    ) if view is not None else None
    slices = view.find("slices") if view is not None else None
    pane = worksheet.find("./table/panes/pane")
    if view is None or dependencies is None or slices is None or pane is None:
        raise ValueError("Activity worksheet template is incomplete.")

    activity_filter = qualified(datasource, "none:ActivityType:nk")
    for filter_node in list(view.findall("filter")):
        if filter_node.attrib.get("column") == activity_filter:
            view.remove(filter_node)
    for slice_node in list(slices.findall("column")):
        if slice_node.text == activity_filter:
            slices.remove(slice_node)

    calculation = dependencies.find("column[@name='[MarketActivityCount]']")
    if calculation is None:
        raise ValueError("Market activity calculation column was not cloned.")
    calculation.attrib["caption"] = "Market Activity"
    calculation.append(
        etree.Element(
            "calculation",
            **{
                "class": "tableau",
                "formula": "ZN([NewListings]) + ZN([ClosedSales])",
            },
        )
    )
    for field in ("NewListings", "ClosedSales"):
        if dependencies.find(f"column[@name='[{field}]']") is None:
            dependencies.append(
                etree.Element(
                    "column",
                    datatype="integer",
                    name=f"[{field}]",
                    role="measure",
                    type="quantitative",
                )
            )

    encodings = pane.find("encodings")
    if encodings is None:
        encodings = etree.SubElement(pane, "encodings")
    etree.SubElement(encodings, "color", column=activity_filter)
    return worksheet


def standard_window(name: str) -> etree._Element:
    window = etree.Element(
        "window",
        **{"class": "worksheet", "maximized": "true", "name": name},
    )
    cards = etree.SubElement(window, "cards")
    left = etree.SubElement(cards, "edge", name="left")
    strip = etree.SubElement(left, "strip", size="160")
    for card_type in ("pages", "filters", "marks"):
        etree.SubElement(strip, "card", type=card_type)
    top = etree.SubElement(cards, "edge", name="top")
    for card_type in ("columns", "rows"):
        strip = etree.SubElement(top, "strip", size="2147483647")
        etree.SubElement(strip, "card", type=card_type)
    strip = etree.SubElement(top, "strip", size="30")
    etree.SubElement(strip, "card", type="title")
    etree.SubElement(window, "viewpoint")
    etree.SubElement(window, "simple-id", uuid=new_uuid())
    return window


def zone_style(
    border: str = COLORS["border"],
    border_width: str = "1",
    margin: str = "4",
) -> etree._Element:
    style = etree.Element("zone-style")
    for attribute, value in (
        ("border-color", border),
        ("border-style", "solid" if border_width != "0" else "none"),
        ("border-width", border_width),
        ("margin", margin),
    ):
        etree.SubElement(style, "format", attr=attribute, value=value)
    return style


def text_zone(
    parent: etree._Element,
    zone_id: int,
    x: int,
    y: int,
    width: int,
    height: int,
    title: str,
    subtitle: str = "",
) -> None:
    zone = etree.SubElement(
        parent,
        "zone",
        h=str(height),
        id=str(zone_id),
        **{"type-v2": "text", "w": str(width), "x": str(x), "y": str(y)},
    )
    formatted = etree.SubElement(zone, "formatted-text")
    etree.SubElement(
        formatted,
        "run",
        bold="true",
        fontcolor=COLORS["navy"],
        fontsize="24",
    ).text = title
    if subtitle:
        etree.SubElement(formatted, "run").text = "\n"
        etree.SubElement(
            formatted,
            "run",
            fontcolor=COLORS["muted"],
            fontsize="10",
        ).text = subtitle
    zone.append(zone_style(border_width="0", margin="8"))


def note_zone(
    parent: etree._Element,
    zone_id: int,
    x: int,
    y: int,
    width: int,
    height: int,
    text: str,
    font_size: str = "10",
) -> None:
    zone = etree.SubElement(
        parent,
        "zone",
        h=str(height),
        id=str(zone_id),
        **{"type-v2": "text", "w": str(width), "x": str(x), "y": str(y)},
    )
    formatted = etree.SubElement(zone, "formatted-text")
    etree.SubElement(
        formatted,
        "run",
        fontcolor=COLORS["muted"],
        fontsize=font_size,
    ).text = text
    zone.append(zone_style(border_width="0", margin="4"))


def worksheet_zone(
    parent: etree._Element,
    zone_id: int,
    name: str,
    x: int,
    y: int,
    width: int,
    height: int,
    show_title: bool,
) -> None:
    zone = etree.SubElement(
        parent,
        "zone",
        h=str(height),
        id=str(zone_id),
        name=name,
        **{
            "show-title": str(show_title).lower(),
            "w": str(width),
            "x": str(x),
            "y": str(y),
        },
    )
    etree.SubElement(zone, "layout-cache", **{"type-h": "cell", "type-w": "cell"})
    zone.append(zone_style(margin="5"))


def filter_zone(
    parent: etree._Element,
    zone_id: int,
    datasource: str,
    field: str,
    x: int,
    width: int,
) -> None:
    zone = etree.SubElement(
        parent,
        "zone",
        h="9000",
        id=str(zone_id),
        mode="checkdropdown",
        name=TEMPLATE_SHEET,
        param=qualified(datasource, f"none:{field}:nk"),
        **{
            "type-v2": "filter",
            "values": "relevant",
            "w": str(width),
            "x": str(x),
            "y": "9000",
        },
    )
    zone.append(zone_style(margin="4"))


def color_legend_zone(
    parent: etree._Element,
    zone_id: int,
    datasource: str,
    x: int,
    y: int,
    width: int,
    height: int,
) -> None:
    zone = etree.SubElement(
        parent,
        "zone",
        h=str(height),
        id=str(zone_id),
        name="Monthly Market Activity",
        param=qualified(datasource, "none:ActivityType:nk"),
        **{
            "show-title": "false",
            "type-v2": "color",
            "w": str(width),
            "x": str(x),
            "y": str(y),
        },
    )
    zone.append(zone_style(border_width="0", margin="2"))


def dashboard_dependencies(datasource: str) -> etree._Element:
    dependencies = etree.Element("datasource-dependencies", datasource=datasource)
    for field, caption, datatype, field_type, _ in SHARED_FILTERS:
        etree.SubElement(
            dependencies,
            "column",
            caption=caption,
            datatype=datatype,
            name=f"[{field}]",
            role="dimension",
            type=field_type,
        )
        etree.SubElement(
            dependencies,
            "column-instance",
            column=f"[{field}]",
            derivation="None",
            name=f"[none:{field}:nk]",
            pivot="key",
            type=field_type,
        )
    return dependencies


def create_dashboard(
    datasource: str,
    latest: pd.Timestamp,
    start: pd.Timestamp,
) -> etree._Element:
    dashboard = etree.Element("dashboard", name=DASHBOARD_NAME)
    etree.SubElement(dashboard, "style")
    etree.SubElement(dashboard, "size", **{"sizing-mode": "automatic"})
    datasources = etree.SubElement(dashboard, "datasources")
    etree.SubElement(
        datasources,
        "datasource",
        caption="market_analysis_tableau",
        name=datasource,
    )
    dashboard.append(dashboard_dependencies(datasource))
    zones = etree.SubElement(dashboard, "zones")
    root = etree.SubElement(
        zones,
        "zone",
        h="100000",
        id="1",
        **{"type-v2": "layout-basic", "w": "100000", "x": "0", "y": "0"},
    )

    subtitle = (
        f"California Residential Market | {start:%B %Y}-{latest:%B %Y} | "
        f"Latest month: {latest:%B %Y}"
    )
    text_zone(root, 2, 0, 0, 100000, 5200, DASHBOARD_NAME)
    note_zone(root, 16, 0, 5200, 100000, 3800, subtitle, "10")

    filter_widths = (33333, 33333, 33334)
    x = 0
    for zone_id, ((field, _, _, _, _), width) in enumerate(
        zip(SHARED_FILTERS, filter_widths),
        start=3,
    ):
        filter_zone(root, zone_id, datasource, field, x, width)
        x += width

    kpi_widths = (20000, 20000, 20000, 20000, 20000)
    x = 0
    for zone_id, (metric, width) in enumerate(zip(KPI_METRICS, kpi_widths), start=6):
        worksheet_zone(root, zone_id, metric.sheet_name, x, 18000, width, 15000, False)
        x += width

    worksheet_zone(
        root,
        11,
        TEMPLATE_SHEET,
        0,
        33000,
        56000,
        38000,
        True,
    )
    color_legend_zone(root, 17, datasource, 78500, 34000, 20500, 5200)
    worksheet_zone(
        root,
        12,
        "Monthly Market Activity",
        56000,
        33000,
        44000,
        38000,
        True,
    )
    bottom = (
        ("Average Days on Market", 0, 34000),
        ("Average Close-to-Original-List Ratio", 34000, 33000),
        ("Mortgage Rate Trend", 67000, 33000),
    )
    for zone_id, (name, x, width) in enumerate(bottom, start=13):
        worksheet_zone(root, zone_id, name, x, 71000, width, 26000, True)

    methodology = (
        "Sources: CRMLS and Freddie Mac | California residential records | "
        "Extreme-value filter: 3.0 IQR"
    )
    note_zone(root, 18, 0, 97000, 100000, 3000, methodology, "8")

    root.append(zone_style(border_width="0", margin="8"))
    etree.SubElement(dashboard, "simple-id", uuid=new_uuid())
    return dashboard


def create_dashboard_window(sheet_names: list[str]) -> etree._Element:
    window = etree.Element(
        "window",
        **{"class": "dashboard", "maximized": "true", "name": DASHBOARD_NAME},
    )
    viewpoints = etree.SubElement(window, "viewpoints")
    for name in sheet_names:
        viewpoint = etree.SubElement(viewpoints, "viewpoint", name=name)
        etree.SubElement(viewpoint, "zoom", type="entire-view")
    etree.SubElement(window, "active", id="11")
    etree.SubElement(window, "simple-id", uuid=new_uuid())
    return window


def replace_dashboard(root: etree._Element, dashboard: etree._Element) -> None:
    windows = root.find("windows")
    if windows is None:
        raise ValueError("The Tableau workbook has no windows section.")
    dashboards = root.find("dashboards")
    if dashboards is None:
        dashboards = etree.Element("dashboards")
        root.insert(root.index(windows), dashboards)
    for existing in dashboards.findall(f"dashboard[@name='{DASHBOARD_NAME}']"):
        dashboards.remove(existing)
    dashboards.append(dashboard)
    for existing in windows.findall(f"window[@name='{DASHBOARD_NAME}']"):
        windows.remove(existing)


def validate_packaged_workbook(output_path: Path, data_path: Path) -> dict[str, object]:
    from tableauhyperapi import Connection, HyperProcess, Telemetry

    with tempfile.TemporaryDirectory(prefix="market_pulse_validation_") as temporary:
        check_dir = Path(temporary)
        with zipfile.ZipFile(output_path) as archive:
            archive.extractall(check_dir)

        workbook_files = list(check_dir.glob("*.twb"))
        extract_files = list(check_dir.rglob("*.hyper"))
        if len(workbook_files) != 1 or len(extract_files) != 1:
            raise ValueError("The packaged workbook must contain one TWB and one Hyper extract.")

        root = etree.parse(str(workbook_files[0])).getroot()
        dashboard = root.find(f"./dashboards/dashboard[@name='{DASHBOARD_NAME}']")
        dashboard_window = root.find(
            f"./windows/window[@class='dashboard'][@name='{DASHBOARD_NAME}']"
        )
        if dashboard is None or dashboard_window is None:
            raise ValueError("The California Market Pulse dashboard is missing.")

        sheet_names = {
            worksheet.attrib["name"]
            for worksheet in root.findall("./worksheets/worksheet")
        }
        zone_names = {
            zone.attrib["name"]
            for zone in dashboard.findall(".//zone[@name]")
            if zone.attrib.get("type-v2") != "filter"
        }
        missing_sheets = sorted(zone_names - sheet_names)
        if missing_sheets:
            raise ValueError(f"Dashboard zones reference missing sheets: {missing_sheets}")

        source = pd.read_csv(
            data_path,
            usecols=["ActivityKey", "AnalysisMonth", "NewListings", "ClosedSales"],
            low_memory=False,
        )
        expected = {
            "rows": len(source),
            "unique_keys": source["ActivityKey"].nunique(dropna=True),
            "start_month": pd.to_datetime(source["AnalysisMonth"]).min().date().isoformat(),
            "end_month": pd.to_datetime(source["AnalysisMonth"]).max().date().isoformat(),
            "new_listings": int(source["NewListings"].sum()),
            "closed_sales": int(source["ClosedSales"].sum()),
        }

        with HyperProcess(
            Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU,
            parameters={"log_config": ""},
        ) as hyper:
            with Connection(hyper.endpoint, str(extract_files[0])) as connection:
                result = connection.execute_list_query(
                    'SELECT COUNT(*), COUNT(DISTINCT "ActivityKey"), '
                    'MIN("AnalysisMonth"), MAX("AnalysisMonth"), '
                    'SUM("NewListings"), SUM("ClosedSales") '
                    'FROM "Extract"."Extract"'
                )[0]

        actual = {
            "rows": int(result[0]),
            "unique_keys": int(result[1]),
            "start_month": str(result[2]),
            "end_month": str(result[3]),
            "new_listings": int(result[4]),
            "closed_sales": int(result[5]),
        }
        if actual != expected:
            raise ValueError(
                f"Packaged extract does not match the Tableau CSV: {actual} != {expected}"
            )

        filter_groups = {
            group: len(root.findall(f".//filter[@filter-group='{group}']"))
            for *_, group in SHARED_FILTERS
        }
        if any(count != len(sheet_names) for count in filter_groups.values()):
            raise ValueError(f"Shared dashboard filters are incomplete: {filter_groups}")

    return {
        **actual,
        "worksheets": len(sheet_names),
        "dashboard_zones": len(zone_names),
        "filter_groups": len(filter_groups),
    }


def build_workbook(template_path: Path, data_path: Path, output_path: Path) -> None:
    if not template_path.exists():
        raise FileNotFoundError(f"Template workbook not found: {template_path}")
    if not data_path.exists():
        raise FileNotFoundError(f"Tableau data not found: {data_path}")

    header = source_header(data_path)
    latest = latest_month(data_path)
    months = pd.read_csv(data_path, usecols=["AnalysisMonth"])["AnalysisMonth"]
    start = pd.to_datetime(months, errors="coerce").min().to_period("M").to_timestamp()

    with tempfile.TemporaryDirectory(prefix="market_pulse_") as temporary:
        build_dir = Path(temporary)
        with zipfile.ZipFile(template_path) as archive:
            archive.extractall(build_dir)

        workbook_files = list(build_dir.glob("*.twb"))
        if len(workbook_files) != 1:
            raise ValueError("Expected exactly one TWB in the Tableau template.")
        workbook_path = workbook_files[0]
        tree = etree.parse(str(workbook_path), etree.XMLParser(remove_blank_text=False))
        root = tree.getroot()

        datasource = root.find("./datasources/datasource")
        worksheets = root.find("worksheets")
        windows = root.find("windows")
        if datasource is None or worksheets is None or windows is None:
            raise ValueError("The Tableau template is missing required workbook sections.")
        datasource_name = datasource.attrib["name"]
        update_source_schema(datasource, header)
        for field, number_format in (
            ("ClosePrice", '"$"#,##0'),
            ("SoldDaysOnMarket", "0.0"),
            ("CloseToOriginalListRatio", "p1"),
            ("rate_30yr_fixed", '0.0"%"'),
        ):
            set_datasource_default_format(datasource, field, number_format)

        template = worksheets.find(f"worksheet[@name='{TEMPLATE_SHEET}']")
        if template is None:
            raise ValueError(f"Template worksheet {TEMPLATE_SHEET!r} was not found.")

        generated_names = {
            *(metric.sheet_name for metric in KPI_METRICS),
            "Monthly Market Activity",
            "Mortgage Rate Trend",
        }
        for worksheet in list(worksheets.findall("worksheet")):
            if worksheet.attrib.get("name") in generated_names:
                worksheets.remove(worksheet)
        for window in list(windows.findall("window")):
            if window.attrib.get("name") in generated_names:
                windows.remove(window)

        generated = [
            make_kpi_sheet(template, metric, datasource_name, latest)
            for metric in KPI_METRICS
        ]
        generated.extend(
            [
                make_activity_sheet(template, datasource_name),
                make_mortgage_sheet(template, datasource_name),
            ]
        )
        for worksheet in generated:
            worksheets.append(worksheet)
            windows.append(standard_window(worksheet.attrib["name"]))

        title_by_sheet = {
            TEMPLATE_SHEET: "Monthly Median Close Price ($)",
            "Average Days on Market": "Average Days on Market",
            "Average Close-to-Original-List Ratio": "Sale to Original List (%)",
            "New Listings": "Monthly New Listings",
            "Closed Sales": "Monthly Closed Sales",
            "Monthly Market Activity": "Monthly New Listings and Closed Sales",
            "Mortgage Rate Trend": "30-Year Fixed Mortgage Rate (%)",
        }
        chart_formats = {
            TEMPLATE_SHEET: ("ClosePrice", "med:ClosePrice:qk", '"$"#,##0', "Median Close Price ($)"),
            "Monthly Market Activity": (
                "MarketActivityCount",
                "sum:MarketActivityCount:qk",
                "#,##0",
                "Listings and Closed Sales",
            ),
            "Average Days on Market": (
                "SoldDaysOnMarket",
                "avg:SoldDaysOnMarket:qk",
                "0.0",
                "Days on Market",
            ),
            "Average Close-to-Original-List Ratio": (
                "CloseToOriginalListRatio",
                "avg:CloseToOriginalListRatio:qk",
                "p1",
                "Sale to Original List (%)",
            ),
            "Mortgage Rate Trend": (
                "rate_30yr_fixed",
                "avg:rate_30yr_fixed:qk",
                '0.0"%"',
                "Mortgage Rate (%)",
            ),
        }
        for worksheet in worksheets.findall("worksheet"):
            worksheet_name = worksheet.attrib["name"]
            if worksheet_name in title_by_sheet:
                set_sheet_title(worksheet, title_by_sheet[worksheet_name])
            if worksheet_name in chart_formats:
                field, instance, number_format, axis_title = chart_formats[worksheet_name]
                set_default_format(worksheet, field, number_format)
                set_axis_title(worksheet, datasource_name, "tmn:AnalysisMonth:qk", "cols", "Month")
                set_axis_title(worksheet, datasource_name, instance, "rows", axis_title)
                exclude_zero_from_axis(worksheet, datasource_name, instance)
            add_shared_filters(worksheet, datasource_name)

        dashboard_sheets = [
            *(metric.sheet_name for metric in KPI_METRICS),
            TEMPLATE_SHEET,
            "Monthly Market Activity",
            "Average Days on Market",
            "Average Close-to-Original-List Ratio",
            "Mortgage Rate Trend",
        ]
        replace_dashboard(root, create_dashboard(datasource_name, latest, start))
        windows.append(create_dashboard_window(dashboard_sheets))

        thumbnails = root.find("thumbnails")
        if thumbnails is not None:
            root.remove(thumbnails)

        extract_relative = "Data/Extracts/california_market_pulse.hyper"
        for old_extract in build_dir.rglob("*.hyper"):
            old_extract.unlink()
        extract_path = build_dir / extract_relative
        build_hyper_extract(data_path, extract_path)
        point_extract_to(datasource, extract_relative)

        tree.write(
            str(workbook_path),
            encoding="utf-8",
            xml_declaration=True,
            pretty_print=True,
        )
        etree.parse(str(workbook_path))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.unlink(missing_ok=True)
        with zipfile.ZipFile(
            output_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            for file_path in build_dir.rglob("*"):
                if file_path.is_file():
                    archive.write(file_path, file_path.relative_to(build_dir))

    validation = validate_packaged_workbook(output_path, data_path)
    print(f"Created Tableau dashboard: {output_path}")
    print(f"Analysis period: {start:%B %Y} through {latest:%B %Y}")
    print(f"Latest KPI month: {latest:%B %Y}")
    print(
        "Validated extract: "
        f"{validation['rows']:,} rows, "
        f"{validation['new_listings']:,} listings, "
        f"{validation['closed_sales']:,} sales"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the California Market Pulse dashboard.")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the existing output workbook without rebuilding it.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.validate_only:
        validation = validate_packaged_workbook(args.output, args.data)
        print(f"Validated Tableau dashboard: {args.output}")
        print(
            f"Extract rows: {validation['rows']:,}; "
            f"new listings: {validation['new_listings']:,}; "
            f"closed sales: {validation['closed_sales']:,}"
        )
        return
    build_workbook(args.template, args.data, args.output)


if __name__ == "__main__":
    main()
