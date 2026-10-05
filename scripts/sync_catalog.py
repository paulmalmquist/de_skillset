"""After a reviewed Markdown edit, refresh the packaged catalog; tests catch drift."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
path=ROOT/"flightcheck/data/catalog.json"
catalog=json.loads(path.read_text())
for item in catalog["skills"]+catalog["protocols"]:
    item["content"]=(ROOT/item["path"]).read_text()
path.write_text(json.dumps(catalog,indent=2)+"\n")
print("Catalog content refreshed. Review metadata, then run scripts/check_catalog.py.")
