
import requests
import pandas as pd
from pathlib import Path

URL = (
    "https://services5.arcgis.com/i9cBEDR6pGnaWUlL/"
    "ArcGIS/rest/services/WaterMainBreaks/FeatureServer/0/query"
)

records = []
offset = 0
batch_size = 1000

while True:
    params = {
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "false",
        "resultOffset": offset,
        "resultRecordCount": batch_size,
        "orderByFields": "OBJECTID ASC",
        "f": "json",
    }

    response = requests.get(URL, params=params, timeout=60)
    response.raise_for_status()
    payload = response.json()

    if "error" in payload:
        raise RuntimeError(payload["error"])

    batch = [x["attributes"] for x in payload["features"]]
    records.extend(batch)
    print(f"Downloaded {len(records)} records")

    if len(batch) < batch_size:
        break

    offset += len(batch)

Path("data").mkdir(exist_ok=True)
df = pd.DataFrame(records)
df.to_csv("data/massachusetts_water_breaks.csv", index=False)

print("Saved:", len(df), "rows")
print("Columns:", df.columns.tolist())
