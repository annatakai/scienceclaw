"""Download Boston main streets from OpenStreetMap (Overpass API) and cache them as data/boston_streets.json.
Street GEOMETRY is real (OSM, ODbL); every asset attribute built on top of it is SIMULATED.
Run: python3 -m sim.fetch_streets [south west north east]     (the cache is committed, so this is only needed to refresh)"""
import json
import math
import pathlib
import subprocess
import sys

BBOX = (42.330, -71.090, 42.372, -71.045)  # south, west, north, east: South End, Back Bay, Downtown
CLASSES = "trunk|primary|secondary|tertiary"
MAX_M, MIN_M = 200.0, 40.0
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "boston_streets.json"
URL = "https://overpass-api.de/api/interpreter"


def fetch(bbox):
    q = f'[out:json][timeout:90];way["highway"~"^({CLASSES})$"]({",".join(map(str, bbox))});out geom;'
    # curl rather than urllib: the macOS system Python's TLS stack fails the handshake with some servers
    out = subprocess.run(["curl", "-sf", "-m", "120", "-A", "dig-once-prototype/0.1", "-H", "Accept: application/json",
                          "--data-urlencode", f"data={q}", URL], capture_output=True, check=True).stdout
    return json.loads(out)["elements"]


def dist_m(a, b):
    dy = (b[0] - a[0]) * 111_320
    dx = (b[1] - a[1]) * 111_320 * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(dx, dy)


def line_m(pts):
    return sum(dist_m(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def point_at(pts, d):
    """Point d metres along the polyline."""
    for i in range(len(pts) - 1):
        L = dist_m(pts[i], pts[i + 1])
        if d <= L or i == len(pts) - 2:
            t = 0 if L == 0 else min(1, d / L)
            return [pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t], i
        d -= L


def cut(pts, a, b):
    """Sub-polyline between distances a and b along pts."""
    pa, ia = point_at(pts, a)
    pb, ib = point_at(pts, b)
    cum, c = [], 0.0
    for i in range(len(pts) - 1):
        cum.append(c)
        c += dist_m(pts[i], pts[i + 1])
    mid = [pts[i] for i in range(len(pts)) if a < (cum[i] if i < len(cum) else c) < b]
    return [pa] + mid + [pb]


def build(elements):
    ways = [e for e in elements if e["type"] == "way" and len(e.get("nodes", [])) == len(e.get("geometry", []))]
    use = {}
    for w in ways:
        for n in w["nodes"]:
            use[n] = use.get(n, 0) + 1
    edges = []  # (node_a, node_b, name, highway, pts)
    for w in ways:
        pts = [[g["lat"], g["lon"]] for g in w["geometry"]]
        start = 0
        for i in range(1, len(w["nodes"])):
            if use[w["nodes"][i]] > 1 or i == len(w["nodes"]) - 1:
                if w["nodes"][start] != w["nodes"][i]:
                    edges.append((w["nodes"][start], w["nodes"][i], w["tags"].get("name", "unnamed"),
                                  w["tags"]["highway"], pts[start:i + 1]))
                start = i
    # drop very short edges, then keep the largest connected component
    edges = [e for e in edges if line_m(e[4]) >= MIN_M]
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b, *_ in edges:
        parent[find(a)] = find(b)
    sizes = {}
    for a, *_ in edges:
        sizes[find(a)] = sizes.get(find(a), 0) + 1
    big = max(sizes, key=sizes.get)
    edges = [e for e in edges if find(e[0]) == big]
    # cut long edges into equal pieces of at most MAX_M (each piece is >= MIN_M since MAX_M > 2*MIN_M)
    segs = []
    for _, _, name, hw, pts in edges:
        L = line_m(pts)
        k = max(1, math.ceil(L / MAX_M))
        for j in range(k):
            sub = pts if k == 1 else cut(pts, L * j / k, L * (j + 1) / k)
            segs.append(dict(id=f"S{len(segs):03d}", street=name, highway=hw,
                             coords=[[round(p[0], 6), round(p[1], 6)] for p in sub],
                             length_ft=round(line_m(sub) * 3.28084)))
    return segs


if __name__ == "__main__":
    bbox = tuple(float(a) for a in sys.argv[1:5]) if len(sys.argv) >= 5 else BBOX
    segs = build(fetch(bbox))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(dict(source="OpenStreetMap contributors (ODbL), via Overpass API", bbox=bbox,
                                   segments=segs), separators=(",", ":")))
    by = {}
    for s in segs:
        by[s["highway"]] = by.get(s["highway"], 0) + 1
    print(f"wrote {OUT} with {len(segs)} segments {by}; "
          f"length ft min {min(s['length_ft'] for s in segs)} max {max(s['length_ft'] for s in segs)}")
