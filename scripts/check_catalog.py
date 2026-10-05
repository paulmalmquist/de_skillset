"""Validate repo-local Claude skills and ensure the UI catalog matches their source files."""
import json
import re
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1]
catalog=json.loads((ROOT/"flightcheck/data/catalog.json").read_text())
errors=[]
for item in catalog["skills"]:
    path=ROOT/item["path"]
    content=path.read_text()
    if content!=item["content"]:errors.append(f"Stale catalog content: {path}")
    front=yaml.safe_load(content.split("---",2)[1])
    if front.get("name")!=path.parent.name or not re.fullmatch(r"[a-z0-9-]{1,64}",front.get("name","")):errors.append(f"Invalid skill name: {path}")
    if len(front.get("description",""))<25:errors.append(f"Missing skill trigger: {path}")
    for target in re.findall(r"\]\(([^)]+)\)",content):
        if not target.startswith("http") and not (path.parent/target).resolve().is_file():errors.append(f"Broken reference: {path}: {target}")
for item in catalog["protocols"]:
    if (ROOT/item["path"]).read_text()!=item["content"]:errors.append(f"Stale protocol catalog: {item['path']}")
actual={p.parent.name for p in (ROOT/".claude/skills").glob("*/SKILL.md")}
if actual!={i["id"] for i in catalog["skills"]}:errors.append("Skill catalog does not match available skills")
if errors:
    raise SystemExit("\n".join(errors))
print(f"Validated {len(actual)} skills, {len(catalog['protocols'])} protocols and their UI catalog.")
