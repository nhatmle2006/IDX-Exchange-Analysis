"""Build the Week 8 Market Analysis Tableau worksheets from a saved template.

The template must contain the completed Monthly Median Close Price worksheet.
The script preserves the packaged Hyper extract, adds the four remaining
required worksheets, and writes a separate TWBX. Dashboard layout is completed
and saved in Tableau Public so Tableau owns the workbook layout metadata.
"""

from __future__ import annotations

import argparse
import copy
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = (
    PROJECT_ROOT / "tableau" / "templates" / "market_analysis_template.twbx"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "tableau" / "market_analysis_week8.twbx"
TEMPLATE_SHEET = "Monthly Median Close Price"
DATASOURCE_NAME = "federated.0s467ss1v4p1wl10x67uc0gn590i"

FILTER_FIELDS = (
    ("City", "City", "string", "nominal"),
    ("CountyOrParish", "County Or Parish", "string", "nominal"),
    ("PostalCode", "Postal Code", "integer", "ordinal"),
    ("PropertySubType", "Property Sub Type", "string", "nominal"),
)


@dataclass(frozen=True)
class WorksheetConfig:
    name: str
    field: str
    caption: str
    derivation: str
    token: str
    activity_type: str
    default_format: str | None = None


WORKSHEETS = (
    WorksheetConfig(
        name="Average Days on Market",
        field="SoldDaysOnMarket",
        caption="Sold Days on Market",
        derivation="Avg",
        token="avg",
        activity_type="Closed Sale",
    ),
    WorksheetConfig(
        name="Average Close-to-Original-List Ratio",
        field="CloseToOriginalListRatio",
        caption="Close to Original List Ratio",
        derivation="Avg",
        token="avg",
        activity_type="Closed Sale",
        default_format="p2",
    ),
    WorksheetConfig(
        name="New Listings",
        field="NewListings",
        caption="New Listings",
        derivation="Sum",
        token="sum",
        activity_type="New Listing",
    ),
    WorksheetConfig(
        name="Closed Sales",
        field="ClosedSales",
        caption="Closed Sales",
        derivation="Sum",
        token="sum",
        activity_type="Closed Sale",
    ),
)


def new_uuid() -> str:
    return "{" + str(uuid.uuid4()).upper() + "}"


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


def clone_worksheet(
    template: etree._Element,
    config: WorksheetConfig,
) -> etree._Element:
    worksheet = copy.deepcopy(template)
    replacements = {
        TEMPLATE_SHEET: config.name,
        "med:ClosePrice:qk": f"{config.token}:{config.field}:qk",
        "Close Price": config.caption,
        "ClosePrice": config.field,
        "Median": config.derivation,
        "Closed Sale": config.activity_type,
    }
    replace_tokens(worksheet, replacements)
    worksheet.attrib["name"] = config.name

    for simple_id in worksheet.xpath(".//simple-id"):
        simple_id.attrib["uuid"] = new_uuid()

    if config.default_format:
        target_name = f"[{config.field}]"
        for column in worksheet.xpath(".//datasource-dependencies/column"):
            if column.attrib.get("name") == target_name:
                column.attrib["default-format"] = config.default_format

    return worksheet


def clone_window(
    template: etree._Element,
    config: WorksheetConfig,
) -> etree._Element:
    window = copy.deepcopy(template)
    replacements = {
        TEMPLATE_SHEET: config.name,
        "med:ClosePrice:qk": f"{config.token}:{config.field}:qk",
        "ClosePrice": config.field,
        "Median": config.derivation,
        "Closed Sale": config.activity_type,
        "yr:AnalysisMonth:ok": "tmn:AnalysisMonth:qk",
    }
    replace_tokens(window, replacements)
    window.attrib["name"] = config.name
    for simple_id in window.xpath(".//simple-id"):
        simple_id.attrib["uuid"] = new_uuid()
    return window


def add_shared_filters(worksheet: etree._Element) -> None:
    view = worksheet.find("./table/view")
    if view is None:
        raise ValueError(f"Worksheet {worksheet.attrib['name']!r} has no view.")
    dependencies = view.find(f"datasource-dependencies[@datasource='{DATASOURCE_NAME}']")
    slices = view.find("slices")
    if dependencies is None or slices is None:
        raise ValueError("Worksheet template is missing dependencies or slices.")

    existing_instances = {
        instance.attrib.get("name")
        for instance in dependencies.findall("column-instance")
    }
    existing_columns = {
        column.attrib.get("name") for column in dependencies.findall("column")
    }
    existing_filters = {
        node.attrib.get("column") for node in view.findall("filter")
    }
    existing_slices = {node.text for node in slices.findall("column")}

    slices_index = list(view).index(slices)
    for field, caption, datatype, field_type in FILTER_FIELDS:
        column_name = f"[{field}]"
        instance_name = f"[none:{field}:nk]"
        qualified_instance = f"[{DATASOURCE_NAME}].{instance_name}"

        if column_name not in existing_columns:
            column_attributes = {
                "caption": caption,
                "datatype": datatype,
                "name": column_name,
                "role": "dimension",
                "type": field_type,
            }
            if field == "PostalCode":
                column_attributes["default-format"] = "*00000"
            dependencies.append(etree.Element("column", **column_attributes))

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

        if qualified_instance not in existing_filters:
            filter_node = etree.Element(
                "filter",
                **{
                    "class": "categorical",
                    "column": qualified_instance,
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

        if qualified_instance not in existing_slices:
            etree.SubElement(slices, "column").text = qualified_instance


def build_workbook(
    template_path: Path,
    output_path: Path,
) -> None:
    if not template_path.exists():
        raise FileNotFoundError(f"Template workbook not found: {template_path}")

    with tempfile.TemporaryDirectory(prefix="tableau_week8_") as temporary:
        build_dir = Path(temporary)
        with zipfile.ZipFile(template_path) as archive:
            archive.extractall(build_dir)

        workbook_files = list(build_dir.glob("*.twb"))
        if len(workbook_files) != 1:
            raise ValueError("Expected exactly one TWB inside the template package.")
        workbook_path = workbook_files[0]

        parser = etree.XMLParser(remove_blank_text=False)
        tree = etree.parse(str(workbook_path), parser)
        root = tree.getroot()
        worksheets = root.find("worksheets")
        windows = root.find("windows")
        if worksheets is None or windows is None:
            raise ValueError("Template is missing worksheets or windows.")

        template_sheet = worksheets.find(f"worksheet[@name='{TEMPLATE_SHEET}']")
        template_window = windows.find(f"window[@name='{TEMPLATE_SHEET}']")
        if template_sheet is None or template_window is None:
            raise ValueError(
                f"Template must contain a worksheet named {TEMPLATE_SHEET!r}."
            )

        existing_names = {sheet.attrib["name"] for sheet in worksheets}
        for config in WORKSHEETS:
            if config.name not in existing_names:
                worksheets.append(clone_worksheet(template_sheet, config))
                windows.append(clone_window(template_window, config))

        for worksheet in worksheets.findall("worksheet"):
            add_shared_filters(worksheet)

        thumbnails = root.find("thumbnails")
        if thumbnails is not None:
            root.remove(thumbnails)

        tree.write(
            str(workbook_path),
            encoding="utf-8",
            xml_declaration=True,
            pretty_print=True,
        )

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the Week 8 Market Analysis Tableau workbook."
    )
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_workbook(args.template, args.output)
    print(f"Created Tableau workbook: {args.output}")


if __name__ == "__main__":
    main()
