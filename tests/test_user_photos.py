import hashlib, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from app_runtime import archives, user_photos


def photo_id(n):
    return hashlib.sha256(str(n).encode()).hexdigest()


class UserPhotosTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = self.base / "user-photos"
        self.root.mkdir()
        items = []
        for n in range(3):
            path = self.root / f"{n}.jpg"
            Image.new("RGB", (64, 48), (n * 60, 10, 10)).save(path)
            thumb = self.root / f"{n}-t.jpg"
            Image.new("RGB", (16, 12)).save(thumb)
            items.append({"id": photo_id(n), "filename": f"{n}.jpg", "album": "A", "width": 64, "height": 48,
                          "path": f"user-photos/{n}.jpg", "thumb_path": f"user-photos/{n}-t.jpg",
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        self.items = items
        self.write({"version": 1, "collections": [{"id": "malba", "name": "Malba", "count": 3, "items": items}]})
        self.patch = patch.object(archives, "archive_root", return_value=self.base)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def write(self, manifest):
        (self.root / "manifest.json").write_text(json.dumps(manifest))
        user_photos._load_manifest.cache_clear()

    def test_missing_manifest_is_an_empty_catalog(self):
        (self.root / "manifest.json").unlink()
        self.assertEqual(user_photos.collection_options(), [])

    def test_listing_paginates_and_hides_internal_paths(self):
        page = user_photos.list_photos("malba", offset=1, limit=1)
        self.assertEqual([item["id"] for item in page["items"]], [photo_id(1)])
        self.assertTrue(page["has_more"])
        self.assertNotIn("path", page["items"][0])
        self.assertTrue(page["items"][0]["image_url"].endswith(photo_id(1)))
        self.assertFalse(user_photos.list_photos("malba", offset=2)["has_more"])
        with self.assertRaises(ValueError):
            user_photos.list_photos("unknown")

    def test_pick_is_repeatable_and_honours_an_explicit_id(self):
        self.assertEqual(user_photos.pick_photo("malba", 7)[1], user_photos.pick_photo("malba", 7)[1])
        self.assertEqual(user_photos.pick_photo("malba", 7, photo_id(2))[1]["id"], photo_id(2))
        with self.assertRaises(ValueError):
            user_photos.pick_photo("malba", 1, "f" * 64)

    def test_photo_for_checks_integrity(self):
        _c, item, source, _t = user_photos.photo_for("malba", 0, photo_id(0))
        self.assertEqual(item["id"], photo_id(0))
        source.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "integrity"):
            user_photos.photo_for("malba", 0, photo_id(0))

    def test_photo_path_rejects_bad_ids_and_escapes(self):
        self.assertTrue(user_photos.photo_path(photo_id(1)).is_file())
        self.assertTrue(user_photos.photo_path(photo_id(1), thumbnail=True).name.endswith("-t.jpg"))
        for bad in ("../etc/passwd", "x" * 64, 5, ""):
            with self.assertRaises(ValueError):
                user_photos.photo_path(bad)
        with self.assertRaises(FileNotFoundError):
            user_photos.photo_path("a" * 64)
        escaping = json.loads((self.root / "manifest.json").read_text())
        escaping["collections"][0]["items"][0]["path"] = "../../outside.jpg"
        self.write(escaping)
        with self.assertRaises(FileNotFoundError):
            user_photos.photo_path(photo_id(0))


if __name__ == "__main__":
    unittest.main()
