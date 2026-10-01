import tempfile
import shutil
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from topics import (
    normalize_topic_name,
    load_catalog,
    save_catalog,
    get_or_create_topic_id,
    get_all_topics,
    CATALOG_PATH,
)


class TestTopicsCatalog:
    def setup_method(self):
        self.original_catalog_path = CATALOG_PATH
        self.temp_dir = tempfile.mkdtemp()
        self.test_catalog_path = Path(self.temp_dir) / "topics.json"
        import topics
        topics.CATALOG_PATH = self.test_catalog_path

    def teardown_method(self):
        import topics
        topics.CATALOG_PATH = self.original_catalog_path
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_normalize_topic_name(self):
        assert normalize_topic_name("array") == "Array"
        assert normalize_topic_name("ARRAY") == "Array"
        assert normalize_topic_name("Array") == "Array"
        assert normalize_topic_name("two pointers") == "Two Pointers"
        assert normalize_topic_name("Two Pointers") == "Two Pointers"
        assert normalize_topic_name("  dynamic programming  ") == "Dynamic Programming"

    def test_empty_catalog(self):
        catalog = load_catalog()
        assert catalog == []

    def test_new_topic_gets_id_1(self):
        topic_id = get_or_create_topic_id("Array")
        assert topic_id == 1

        catalog = load_catalog()
        assert len(catalog) == 1
        assert catalog[0] == {"id": 1, "name": "Array"}

    def test_existing_topic_returns_same_id(self):
        id1 = get_or_create_topic_id("Array")
        id2 = get_or_create_topic_id("Array")
        assert id1 == id2 == 1

        catalog = load_catalog()
        assert len(catalog) == 1

    def test_two_new_topics_get_sequential_ids(self):
        id1 = get_or_create_topic_id("Array")
        id2 = get_or_create_topic_id("String")
        assert id1 == 1
        assert id2 == 2

        catalog = load_catalog()
        assert len(catalog) == 2
        assert {item["name"]: item["id"] for item in catalog} == {"Array": 1, "String": 2}

    def test_repeated_execution_preserves_ids(self):
        get_or_create_topic_id("Array")
        get_or_create_topic_id("String")
        get_or_create_topic_id("Dynamic Programming")

        id1 = get_or_create_topic_id("Array")
        id2 = get_or_create_topic_id("String")
        id3 = get_or_create_topic_id("Dynamic Programming")

        assert id1 == 1
        assert id2 == 2
        assert id3 == 3

    def test_existing_ids_unchanged_when_adding_new(self):
        get_or_create_topic_id("Array")
        get_or_create_topic_id("String")

        id_array_before = get_or_create_topic_id("Array")
        id_string_before = get_or_create_topic_id("String")

        get_or_create_topic_id("Hash Table")
        get_or_create_topic_id("Tree")

        id_array_after = get_or_create_topic_id("Array")
        id_string_after = get_or_create_topic_id("String")

        assert id_array_before == id_array_after == 1
        assert id_string_before == id_string_after == 2

    def test_normalization_maps_to_same_id(self):
        id1 = get_or_create_topic_id("two pointers")
        id2 = get_or_create_topic_id("Two Pointers")
        id3 = get_or_create_topic_id("TWO POINTERS")
        id4 = get_or_create_topic_id("  Two Pointers  ")

        assert id1 == id2 == id3 == id4 == 1

    def test_get_all_topics_returns_mapping(self):
        get_or_create_topic_id("Array")
        get_or_create_topic_id("String")

        mapping = get_all_topics()
        assert mapping == {"Array": 1, "String": 2}

    def test_catalog_persisted_to_disk(self):
        get_or_create_topic_id("Array")
        get_or_create_topic_id("String")

        with self.test_catalog_path.open("r", encoding="utf-8") as f:
            import json
            data = json.load(f)

        assert data == [{"id": 1, "name": "Array"}, {"id": 2, "name": "String"}]


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])