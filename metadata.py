import json
from pathlib import Path


def cap_tags(tags, budget=480):
    out, used = [], 0
    for t in tags:
        add = len(t) + (1 if out else 0)
        if used + add > budget:
            break
        out.append(t)
        used += add
    return out


def load_metadata(metadata_path, title, description, tags_csv):
    meta = {"title": "", "description": "", "tags": []}
    if metadata_path:
        p = Path(metadata_path).expanduser()
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            meta["title"] = (data.get("title") or "").strip()
            meta["description"] = data.get("description") or ""
            meta["tags"] = [t for t in (data.get("tags") or []) if t]
    if title:
        meta["title"] = title
    if description:
        meta["description"] = description
    if tags_csv:
        meta["tags"] = [t.strip() for t in tags_csv.split(",") if t.strip()]
    meta["title"] = meta["title"][:100]
    meta["tags"] = cap_tags(meta["tags"])
    return meta
