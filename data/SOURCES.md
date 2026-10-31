# Data sources

Everything about the street NETWORK is real (geometry, street name, length, road class, jurisdiction, neighborhood).
Everything about what is UNDER and ON the streets (pipe material, install year, breaks, pavement condition, last paved,
traffic, customers, costs) is SIMULATED by `sim/city.py` with a seeded generator. ALL ASSET DATA SIMULATED.

Built by `python3 -m sim.fetch_streets` (raw downloads cached in `data/raw/`, git-ignored; the committed output
`data/boston_streets.geojson` makes every run offline). Download dates are in `data/build_info.json` (all 2026-10-31).

| Dataset | Used for | Source | Terms |
|---|---|---|---|
| Boston Street Segments (SAM System) | geometry, street name, segment id, address ranges, CFCC, owner, speed limit | Analyze Boston, https://data.boston.gov/dataset/boston-street-segments-sam-system (19,440 segments) | Open Data Commons Public Domain Dedication and License (PDDL) |
| MassDOT Road Inventory (City = Boston, 20,385 arcs), the source dataset of MassGIS "MassDOT Roads" (EOTROADS_ARC) | federal functional class, jurisdiction, access control, facility type | https://gis.massdot.state.ma.us/arcgis/rest/services/Roads/RoadInventory/FeatureServer/0 | MassGIS / MassDOT public data, no use restrictions; credit MassDOT Office of Transportation Planning |
| Boston Neighborhood Boundaries (26) | neighborhood by segment midpoint | Analyze Boston, https://data.boston.gov/dataset/bpda-neighborhood-boundaries | Open Data Commons PDDL |
| OpenStreetMap basemap tiles (demo only) | background map in the demo, never used for simulation | https://www.openstreetmap.org/copyright | ODbL, attribution shown on the map |

Not downloaded: the MassGIS shapefile bundle (`eotroads.zip` on the MassGIS download site) was not reachable at a
stable URL, so the MassDOT Road Inventory feature service (same attributes, same agency) was used. The osmnx fallback
(`--osm`) is implemented but untested, because both primary downloads worked.

## Processing
- SAM segments dropped (counts in the README): limited-access highways and ramps (CFCC A1x, A6x), alleys, walkways,
  stairs and private roads (A7x), ownership other than Boston Public Works Department (private, state, DCR, Massport,
  parks, housing), other municipalities, MassDOT interstate/freeway class, likely paper streets (no address range and no
  MassDOT line), segments under 10 ft.
- MassDOT join: nearest MassDOT line to the segment midpoint within 15 m and within 35 degrees of the same direction
  (the MassDOT file has no street names to compare). Unmatched segments fall back to the SAM CFCC class; the list is in
  `data/unmatched_segments.csv`. `class_source` records which was used.
- Classes: MassDOT functional class 3-4 -> arterial, 5-6 -> collector, 7 -> local (CFCC A2x/A3x/A4x when unmatched).
- Geometry: WGS84 for the map; lengths computed in EPSG:26986 (MA State Plane, metres) and stored in feet; simplified
  with a 1.5 m tolerance; segments longer than 250 m are cut into equal pieces.
- 333 segments are "City Public Works" in SAM but "unaccepted by city" in MassDOT; they are kept and labeled.
