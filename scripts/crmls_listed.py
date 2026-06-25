import csv
from datetime import datetime
from pathlib import Path

import requests

from config import get_auth_endpoint


# CoreLogic Trestle Property endpoint.
url = "https://api-trestle.corelogic.com/trestle/odata/Property"

auth_endpoint = get_auth_endpoint()
response = requests.get(auth_endpoint, timeout=30)
response.raise_for_status()

token = response.json().get("access_token")

fieldnames = [
    "OriginalListPrice",
    "ListingKey",
    "CloseDate",
    "ClosePrice",
    "ListAgentFirstName",
    "ListAgentLastName",
    "Latitude",
    "Longitude",
    "UnparsedAddress",
    "PropertyType",
    "LivingArea",
    "ListPrice",
    "DaysOnMarket",
    "ListOfficeName",
    "BuyerOfficeName",
    "CoListOfficeName",
    "ListAgentFullName",
    "CoListAgentFirstName",
    "CoListAgentLastName",
    "BuyerAgentMlsId",
    "BuyerAgentFirstName",
    "BuyerAgentLastName",
    "FireplacesTotal",
    "AssociationFeeFrequency",
    "AboveGradeFinishedArea",
    "ListingKeyNumeric",
    "MLSAreaMajor",
    "TaxAnnualAmount",
    "CountyOrParish",
    "MlsStatus",
    "ElementarySchool",
    "AttachedGarageYN",
    "ParkingTotal",
    "BuilderName",
    "PropertySubType",
    "LotSizeAcres",
    "SubdivisionName",
    "BuyerOfficeAOR",
    "YearBuilt",
    "StreetNumberNumeric",
    "ListingId",
    "BathroomsTotalInteger",
    "City",
    "TaxYear",
    "BuildingAreaTotal",
    "BedroomsTotal",
    "ContractStatusChangeDate",
    "ElementarySchoolDistrict",
    "CoBuyerAgentFirstName",
    "PurchaseContractDate",
    "ListingContractDate",
    "BelowGradeFinishedArea",
    "BusinessType",
    "StateOrProvince",
    "CoveredSpaces",
    "MiddleOrJuniorSchool",
    "FireplaceYN",
    "Stories",
    "HighSchool",
    "Levels",
    "LotSizeDimensions",
    "LotSizeArea",
    "MainLevelBedrooms",
    "NewConstructionYN",
    "GarageSpaces",
    "HighSchoolDistrict",
    "PostalCode",
    "AssociationFee",
    "LotSizeSquareFeet",
    "MiddleOrJuniorSchoolDistrict",
]

if token:
    headers = {"Authorization": f"Bearer {token}"}

    params = {
        "$select": ",".join(fieldnames),
        "$filter": (
            f"ListingContractDate ge {datetime(2026, 2, 1).isoformat(timespec='milliseconds')}Z "
            f"and ListingContractDate lt {datetime(2026, 3, 1).isoformat(timespec='milliseconds')}Z"
        ),
        "$top": 1000,
    }

    total_records = 0
    output_dir = Path("data") / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_file = output_dir / "CRMLSListing202602.csv"

    with csv_file.open(mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        while True:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                observations = data.get("value", [])

                for observation in observations:
                    writer.writerow({field: observation.get(field, "") for field in fieldnames})
                    total_records += 1

                if "@odata.nextLink" in data:
                    url = data["@odata.nextLink"]
                    params = None
                else:
                    break
            else:
                print(f"Error: {response.status_code}")
                print(f"Error Message: {response.text}")
                break

    print(f"Total {total_records} records exported to {csv_file}")
else:
    print("Error retrieving token: access_token not found")
