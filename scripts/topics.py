import json
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "topics.json"


def normalize_topic_name(name: str) -> str:
    """Normalize topic name deterministically."""
    return name.strip().title()


def load_catalog() -> list[dict]:
    """Load topic catalog from disk. Returns empty list if file doesn't exist."""
    if not CATALOG_PATH.exists():
        return []
    with CATALOG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_catalog(catalog: list[dict]) -> None:
    """Save topic catalog to disk atomically."""
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = CATALOG_PATH.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    temp_path.replace(CATALOG_PATH)


def get_next_id(catalog: list[dict]) -> int:
    """Get next available ID (max + 1, or 1 if empty)."""
    if not catalog:
        return 1
    return max(item["id"] for item in catalog) + 1


def get_or_create_topic_id(name: str) -> int:
    """Get existing topic ID or create new one."""
    normalized = normalize_topic_name(name)
    catalog = load_catalog()

    for item in catalog:
        if item["name"] == normalized:
            return item["id"]

    new_id = get_next_id(catalog)
    catalog.append({"id": new_id, "name": normalized})
    save_catalog(catalog)
    return new_id


def get_all_topics() -> dict[str, int]:
    """Return all topics as {name: id} mapping."""
    return {item["name"]: item["id"] for item in load_catalog()}