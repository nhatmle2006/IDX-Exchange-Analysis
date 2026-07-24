# Geographic Reference Data

`california_boundary_2025.geojson` is the U.S. Census Bureau TIGERweb state
boundary for California (state FIPS code `06`), January 1, 2025 vintage. It is
stored locally so the cleaning script can run without downloading data.

Source: https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/0

`school_district_areas_2024_25.geojson` is the California Department of
Education school-district area layer for the 2024-25 academic year. It contains
overlapping elementary, high, and unified district boundaries. The file is
downloaded locally and ignored by Git because it is approximately 45 MB.

Source: https://services3.arcgis.com/fdvHcZVgB2QSRNkL/arcgis/rest/services/SchoolDistrictAreas2425/FeatureServer/0
