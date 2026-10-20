"""Feature-owned collection matching, recursive bounds and atomic per-file batches."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from features.comics.mobile.collection import (
    matches,
    suggestions,
    scan_comics,
    CollectionBatch,
)
from commonUtils.runtime.local_files import LocalFiles


class CollectionTests(unittest.TestCase):
    def test_comic_metadata_snapshot_bounds_values_and_preserves_mixed_dispatch(self):
        from features.comics.collection.metadata import metadata_fields
        from features.books.library.metadata import metadata_fields as mixed_fields
        from features.comics.mobile.collection import metadata_fields as legacy_fields

        class Info:
            FIELDS = ("Title", "Writer", "Count", "Invalid")

            def get_field(self, key):
                if key == "Invalid":
                    raise ValueError("Invalid legacy field")
                return {"Title": "x" * 5000, "Writer": "Alice", "Count": 3}[key]

        document = SimpleNamespace(info=Info())
        expected = {"Title": "x" * 4096, "Writer": "Alice", "Count": "3"}
        self.assertEqual(metadata_fields(document), expected)
        reader = SimpleNamespace(document=document)
        self.assertEqual(metadata_fields(reader), expected)
        self.assertEqual(mixed_fields("comic", reader), expected)
        self.assertEqual(legacy_fields("comic", reader), expected)

    def test_metadata_search_and_shared_suggestion_semantics(self):
        fields = {
            "Writer": "Alice, Bob\nAlice",
            "Tags": "Space, Adventure",
            "Publisher": "  One  Press ",
        }
        self.assertTrue(matches("Book.cbz", fields, "bob space"))
        self.assertFalse(matches("Book.cbz", fields, "bob crime"))
        result = suggestions([fields])
        self.assertEqual(result["Writer"], ["Alice", "Bob"])
        self.assertEqual(result["Publisher"], ["One Press"])

    def test_recursive_selection_natural_order_and_preflight_before_publication(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "child").mkdir()
            for name in ["10.cbz", "2.cbz", "child/1.zip", "ignored.txt"]:
                (root / name).write_bytes(b"fixture")
            provider = LocalFiles(root)
            rows = scan_comics(provider, "")
            self.assertEqual(
                [r["path"] for r in rows], ["2.cbz", "10.cbz", "child/1.zip"]
            )
            written = []

            class Document:
                def prepare_metadata(self, changes):
                    pass

            plan = CollectionBatch(
                rows,
                open_document=lambda path: Document(),
                revision=lambda path: provider.entry(path)["revision"],
                publish=lambda *args: written.append(args),
            )
            (root / "10.cbz").write_bytes(b"changed")
            with self.assertRaises(ValueError):
                plan.apply({"Title": "New"})
            self.assertEqual(written, [])

    def test_provider_escaping_row_is_rejected(self):
        class Provider:
            def relative(self, path):
                return path

            def list(self, path):
                return [dict(path="outside.cbz", name="outside.cbz", directory=False)]

        with self.assertRaises(ValueError):
            scan_comics(Provider(), "inside")
