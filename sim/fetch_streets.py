"""Build the Boston street network: REAL geometry, names, length and road class; no asset data.

Sources (see data/SOURCES.md):
  1. Boston Street Segments (SAM System), Analyze Boston: geometry, names, address ranges, CFCC, owner. PDDL.
  2. MassDOT Road Inventory (the source of MassGIS EOTROADS_ARC), City = Boston: federal functional class,
     jurisdiction, access control. Spatially joined to SAM (see match_massdot).
  3. Analyze Boston neighborhood boundaries (26 neighborhoods): neighborhood by segment midpoint.
Fallback when a download fails: OSM drive network via osmnx (--osm).

Run: python3 -m sim.fetch_streets [--refresh] [--osm]       Output: data/boston_streets.geojson (committed)
Raw downloads are cached in data/raw/ (git-ignored); with the cache present nothing is downloaded.
ALL PIPE, PAVEMENT, BREAK AND COST DATA IS SIMULATED elsewhere (sim/city.py).
"""
import datetime
import json
import pathlib
import subprocess
import sys
from collections import Counter

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString
from shapely.ops import substring

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "boston_streets.geojson"
SAM_URL = ("https://data.boston.gov/dataset/b9b8b634-f28a-410f-9727-b53d0d006308/resource/"
           "e850cfd2-2c6e-4af6-9ac4-e03019412d1e/download/boston_street_segments_sam_system.geojson")
NBHD_URL = ("https://data.boston.gov/dataset/bf1a7b50-4c72-4637-b0fa-11d632e3aff1/resource/"
            "e5849875-a6f6-4c9c-9d8a-5048b0fbd03e/download/boston_neighborhood_boundaries.geojson")
MASSDOT_URL = "https://gis.massdot.state.ma.us/arcgis/rest/services/Roads/RoadInventory/FeatureServer/0/query"
MASSDOT_FIELDS = "Rd_Seg_ID,Route_System,Route_Number,Facility,F_F_Class,Jurisdictn,Control,City,Speed_Lim,Surface_Wd,Num_Lanes"
BOSTON_CITY_CODE = 35   # MassDOT city code for Boston

M2FT = 3.280839895
MATCH_TOL_M = 15.0      # midpoint-to-line tolerance for the SAM to MassDOT join
SIMPLIFY_M = 1.5        # light simplification (keeps corners, removes redundant vertices)
MAX_SEG_M = 250.0       # longer segments are cut into equal pieces
MIN_SEG_FT = 10.0       # shorter than this is dropped as effectively zero length
CRS_MAP, CRS_PROJ = "EPSG:4326", "EPSG:26986"   # WGS84 for the map; MA State Plane mainland (metres) for geometry work

# MassDOT federal functional class -> our three classes (1 Interstate, 2 freeway: excluded elsewhere)
FC_CLASS = {3: "arterial", 4: "arterial", 5: "collector", 6: "collector", 7: "local"}
JURIS = {"0": "Unaccepted by city", "1": "MassDOT", "2": "City accepted", "3": "DCR", "5": "Massport", "6": "State park",
         "7": "State institutional", "B": "State university", "E": "Federal institutional", "H": "Private"}
# CFCC (Census feature class) fallback when no MassDOT line matches
CFCC_CLASS = {"A2": "arterial", "A3": "collector", "A4": "local"}
OSM_CLASS = {"motorway": None, "motorway_link": None, "trunk": "arterial", "primary": "arterial",
             "secondary": "arterial", "tertiary": "collector", "unclassified": "local", "residential": "local",
             "living_street": "local", "trunk_link": None, "primary_link": None, "secondary_link": None,
             "tertiary_link": None}


def curl(url, dest, params=None, post=False):
    # curl rather than urllib: the macOS system Python 3.9 TLS stack fails the handshake with some servers
    cmd = ["curl", "-sfL", "-m", "300", "-A", "dig-once-prototype/0.2"]
    if params:
        cmd += ["-G"] + sum([["--data-urlencode", f"{k}={v}"] for k, v in params.items()], [])
    out = subprocess.run(cmd + [url], capture_output=True, check=True).stdout
    if dest:
        dest.write_bytes(out)
    return out


def download(refresh):
    RAW.mkdir(parents=True, exist_ok=True)
    stamp = {}
    for name, url in (("sam.geojson", SAM_URL), ("nbhd.geojson", NBHD_URL)):
        p = RAW / name
        if refresh or not p.exists():
            print("downloading", name)
            curl(url, p)
        stamp[name] = datetime.date.fromtimestamp(p.stat().st_mtime).isoformat()
    p = RAW / "massdot_roads_boston.geojson"
    if refresh or not p.exists():
        print("downloading MassDOT Road Inventory (City=Boston)")
        feats, off = [], 0
        while True:
            d = json.loads(curl(MASSDOT_URL, None, dict(where=f"City={BOSTON_CITY_CODE}", outFields=MASSDOT_FIELDS, outSR=4326,
                                                         resultOffset=off, resultRecordCount=2000, f="geojson")))
            feats += d["features"]
            if len(d["features"]) < 2000 and not d.get("exceededTransferLimit"):
                break
            off += len(d["features"])
        p.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    stamp["massdot_roads_boston.geojson"] = datetime.date.fromtimestamp(p.stat().st_mtime).isoformat()
    return stamp


def street_name(r):
    parts = [r.get("PRE_DIR"), r.get("ST_NAME"), r.get("ST_TYPE"), r.get("SUF_DIR")]
    return " ".join(str(x).strip() for x in parts if isinstance(x, str) and x.strip()).title()


def angle_diff(a, b):
    """Smallest angle between two undirected lines (degrees), using end-to-end bearings."""
    def brg(g):
        (x0, y0), (x1, y1) = g.coords[0], g.coords[-1]
        return np.degrees(np.arctan2(y1 - y0, x1 - x0)) % 180
    d = abs(brg(a) - brg(b))
    return min(d, 180 - d)


def match_massdot(sam, md):
    """Join each SAM segment to the MassDOT line nearest its midpoint within MATCH_TOL_M, preferring a similarly
    oriented line (so a cross street at an intersection is not chosen). Returns a frame indexed like sam."""
    mid = gpd.GeoDataFrame(geometry=sam.geometry.interpolate(0.5, normalized=True), index=sam.index, crs=sam.crs)
    j = gpd.sjoin_nearest(mid, md[["geometry", "F_F_Class", "Jurisdictn", "Control", "Facility", "Rd_Seg_ID"]],
                          how="left", max_distance=MATCH_TOL_M, distance_col="dist_m")
    j = j[~j.index.duplicated(keep="first")]
    ok = j["Rd_Seg_ID"].notna() | j["F_F_Class"].notna() | j["Jurisdictn"].notna()
    j["matched"] = j["index_right"].notna() & ok
    # reject a match whose orientation disagrees strongly with the SAM segment (cross street at a junction)
    md_geom = md.geometry
    bad = []
    for i, r in j[j.matched].iterrows():
        try:
            if angle_diff(sam.geometry[i], md_geom.loc[r["index_right"]]) > 35:
                bad.append(i)
        except Exception:
            pass
    j.loc[bad, "matched"] = False
    j.loc[~j.matched, ["F_F_Class", "Jurisdictn", "Control", "Facility", "Rd_Seg_ID", "dist_m"]] = np.nan
    return j


def cut(line, max_m):
    n = int(np.ceil(line.length / max_m))
    if n <= 1:
        return [line]
    return [substring(line, line.length * k / n, line.length * (k + 1) / n) for k in range(n)]


def build_primary(stamp):
    sam = gpd.read_file(RAW / "sam.geojson").set_index("SEGMENT_ID", drop=False)
    md = gpd.read_file(RAW / "massdot_roads_boston.geojson")
    nb = gpd.read_file(RAW / "nbhd.geojson")
    drops = Counter()
    n0 = len(sam)
    print(f"SAM segments downloaded: {n0}")
    sam = sam.to_crs(CRS_PROJ)
    md = md.to_crs(CRS_PROJ)
    sam["ownership"] = sam["ownership"].fillna("").str.strip()
    sam["street"] = [street_name(r) for r in sam.to_dict("records")]
    sam["cfcc"] = sam["CFCC"].fillna("").str.strip()

    def drop(mask, why):
        nonlocal sam
        drops[why] += int(mask.sum())
        sam = sam[~mask]

    # zero-length and non-Boston municipality
    drop(sam.geometry.length * M2FT < MIN_SEG_FT, f"zero or tiny length (< {MIN_SEG_FT:.0f} ft)")
    drop(sam["MUN_L"].fillna("BOSTON").ne("BOSTON") & sam["MUN_R"].fillna("BOSTON").ne("BOSTON"), "other municipality")
    # SAM feature class: limited access, ramps and special road features, alleys/walkways/stairs/private roads
    drop(sam.cfcc.str.startswith("A1"), "limited-access highway (CFCC A1x)")
    drop(sam.cfcc.str.startswith("A6"), "ramp, service drive or special feature (CFCC A6x)")
    drop(sam.cfcc.str.startswith("A7"), "alley, walkway, stairway or private road (CFCC A7x)")
    drop(sam.cfcc.eq(""), "no CFCC")
    # owner: only the City of Boston Public Works Department maintains the street
    drop(sam.ownership.eq("Private"), "private way (SAM ownership)")
    drop(sam.ownership.ne("Boston Public Works Department") & sam.ownership.ne(""),
         "not City of Boston Public Works (state, DCR, Massport, parks, housing)")
    drop(sam.ownership.eq(""), "ownership unknown")
    # MassDOT join
    j = match_massdot(sam, md)
    sam = sam.join(j[["F_F_Class", "Jurisdictn", "Control", "Facility", "dist_m", "matched"]])
    rate = sam.matched.mean()
    print(f"MassDOT class match rate (within {MATCH_TOL_M:.0f} m of segment midpoint): {rate:.1%} "
          f"({int(sam.matched.sum())} of {len(sam)} remaining segments)")
    um = sam[~sam.matched]
    print("unmatched by CFCC:", um.cfcc.value_counts().head(6).to_dict(), "| by neighborhood:", um.NBHD_L.value_counts().head(5).to_dict())
    print("sample unmatched segments:", [f"{r.street} ({r.SEGMENT_ID})" for r in um.head(12).itertuples()])
    um[["SEGMENT_ID", "street", "cfcc", "NBHD_L"]].to_csv(RAW.parent / "unmatched_segments.csv", index=False)
    drop(sam.matched & sam.F_F_Class.isin([1, 2]), "interstate or freeway (MassDOT functional class 1-2)")
    drop(sam.matched & sam.Control.eq(1), "full access control (MassDOT)")
    drop(sam.matched & sam.Facility.isin([7, 8, 9, 10, 11]), "ramp or collector-distributor (MassDOT)")
    drop(sam.matched & sam.Facility.isin([12, 14]), "bike/ped path or private way (MassDOT facility)")
    mj = lambda: sam.Jurisdictn.astype("string")
    drop(sam.matched & mj().notna() & mj().isin(["1", "3", "5", "6", "7", "B", "E", "H"]), "not city jurisdiction (MassDOT)")
    # "0" (unaccepted by the city) where SAM also says City Public Works: kept, flagged; counted for the report
    conflict = int((sam.matched & mj().eq("0").fillna(False)).sum())
    print(f"MassDOT says 'unaccepted by city' but SAM says City Public Works: {conflict} segments (kept, jurisdiction labeled)")
    # paper streets: no address range at all and no MassDOT line
    addr = sam[["L_F_ADD", "L_T_ADD", "R_F_ADD", "R_T_ADD"]].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
    drop((addr == 0) & ~sam.matched, "likely paper street (no address range, no MassDOT road)")

    # class: MassDOT functional class where matched, else CFCC
    cls_md = sam.F_F_Class.map(FC_CLASS)
    cls_cf = sam.cfcc.str[:2].map(CFCC_CLASS)
    sam["class"] = cls_md.where(sam.matched & cls_md.notna(), cls_cf)
    sam["class_source"] = np.where(sam.matched & cls_md.notna(), "MassDOT functional class", "SAM CFCC (no MassDOT match)")
    drop(sam["class"].isna(), "no usable road class")
    sam["jurisdiction"] = mj().map(JURIS).fillna("City Public Works (SAM; no MassDOT match)")

    # neighborhood by midpoint (Analyze Boston boundaries); nearest boundary for points just offshore
    nb = nb.to_crs(CRS_PROJ)
    mid = gpd.GeoDataFrame(geometry=sam.geometry.interpolate(0.5, normalized=True), index=sam.index, crs=CRS_PROJ)
    jn = gpd.sjoin(mid, nb[["name", "geometry"]], how="left", predicate="within")
    jn = jn[~jn.index.duplicated(keep="first")]
    miss = jn.name.isna()
    if miss.any():
        jm = gpd.sjoin_nearest(mid[miss.values], nb[["name", "geometry"]], how="left", max_distance=100)
        jm = jm[~jm.index.duplicated(keep="first")]
        jn.loc[jm.index, "name"] = jm["name"]
    sam["neighborhood"] = jn["name"].reindex(sam.index)
    drop(sam.neighborhood.isna(), "outside Boston neighborhood boundaries")

    # geometry: simplify lightly, cut long segments
    rows = []
    for r in sam.to_dict("records"):
        g = r["geometry"].simplify(SIMPLIFY_M, preserve_topology=True)
        parts = cut(g, MAX_SEG_M)
        for k, p in enumerate(parts):
            ft = p.length * M2FT
            if ft < MIN_SEG_FT:
                continue
            sp = r["SPEEDLIMIT"]
            rows.append(dict(segment_id=f"S{r['SEGMENT_ID']}" + (f".{k + 1}" if len(parts) > 1 else ""), sam_id=int(r["SEGMENT_ID"]),
                             street=r["street"], **{"class": r["class"]}, class_source=r["class_source"],
                             jurisdiction=r["jurisdiction"], neighborhood=r["neighborhood"], length_ft=round(ft, 1),
                             cfcc=r["cfcc"], addr_l=f"{r['L_F_ADD'] or ''}-{r['L_T_ADD'] or ''}", addr_r=f"{r['R_F_ADD'] or ''}-{r['R_T_ADD'] or ''}",
                             speed_limit=None if pd.isna(sp) else int(sp), geometry=p))
    out = gpd.GeoDataFrame(rows, crs=CRS_PROJ)
    cutn = len(out) - len(sam)
    print(f"segments cut at >{MAX_SEG_M:.0f} m: +{cutn} pieces")
    print(f"\nDROPPED (of {n0} SAM segments):")
    for k, v in drops.most_common():
        print(f"  {v:6d}  {k}")
    print(f"KEPT: {len(sam)} SAM segments -> {len(out)} simulation segments")
    return out, dict(n0=n0, drops=dict(drops), match_rate=float(rate), kept_sam=len(sam), conflict=conflict)


def build_osm():
    import osmnx as ox   # fallback only; pip install osmnx
    G = ox.graph_from_place("Boston, Massachusetts, USA", network_type="drive")
    edges = ox.graph_to_gdfs(G, nodes=False).reset_index()
    nb = gpd.read_file(RAW / "nbhd.geojson").to_crs(CRS_PROJ)
    edges["hw"] = edges["highway"].map(lambda h: h[0] if isinstance(h, list) else h)
    edges["class"] = edges["hw"].map(OSM_CLASS)
    edges = edges[edges["class"].notna()].to_crs(CRS_PROJ)
    edges["street"] = edges["name"].map(lambda n: (n[0] if isinstance(n, list) else n) or "Unnamed").astype(str)
    rows = []
    for r in edges.itertuples():
        for k, p in enumerate(cut(r.geometry.simplify(SIMPLIFY_M), MAX_SEG_M)):
            if p.length * M2FT >= MIN_SEG_FT:
                rows.append(dict(segment_id=f"O{r.osmid if not isinstance(r.osmid, list) else r.osmid[0]}.{k}", sam_id=None,
                                 street=r.street, **{"class": r._asdict()["class"]}, class_source="OSM highway tag", jurisdiction="unknown (OSM)",
                                 neighborhood=None, length_ft=round(p.length * M2FT, 1), cfcc="", addr_l="", addr_r="", speed_limit=None, geometry=p))
    out = gpd.GeoDataFrame(rows, crs=CRS_PROJ)
    nbm = gpd.sjoin(gpd.GeoDataFrame(geometry=out.geometry.interpolate(0.5, normalized=True), crs=CRS_PROJ), nb[["name", "geometry"]], how="left", predicate="within")
    out["neighborhood"] = nbm[~nbm.index.duplicated()]["name"].values
    return out, dict(fallback="osmnx")


def write(out):
    g = out.to_crs(CRS_MAP)
    feats = []
    for r in g.to_dict("records"):
        geom = r.pop("geometry")
        coords = [[round(x, 6), round(y, 6)] for x, y in geom.coords]
        props = {k: (None if (isinstance(v, float) and np.isnan(v)) else v) for k, v in r.items()}
        feats.append(dict(type="Feature", properties=props, geometry=dict(type="LineString", coordinates=coords)))
    OUT.write_text(json.dumps(dict(type="FeatureCollection", features=feats), separators=(",", ":")))
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


def summary(out):
    out = out.copy()
    out["miles"] = out.length_ft / 5280
    print(f"\nTOTAL segments {len(out)}, total miles {out.miles.sum():.1f}")
    print(out.groupby("class").agg(segments=("miles", "size"), miles=("miles", "sum")).round(1).to_string())
    print(out.groupby("neighborhood").agg(segments=("miles", "size"), miles=("miles", "sum")).round(1).sort_values("miles", ascending=False).to_string())


if __name__ == "__main__":
    stamp = download("--refresh" in sys.argv)
    if "--osm" in sys.argv:
        out, info = build_osm()
    else:
        out, info = build_primary(stamp)
    summary(out)
    write(out)
    (ROOT / "data" / "build_info.json").write_text(json.dumps(dict(downloaded=stamp, **info), indent=1))
