import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sync_images  # noqa: E402


class FakeVolume:
    def __init__(self):
        self.files = {}  # name -> (bytes, mtime)

    def put(self, name, data, mtime):
        self.files[name] = (data if isinstance(data, bytes) else json.dumps(data).encode(), mtime)

    def listdir(self, _path):
        from modal.volume import FileEntryType
        return [SimpleNamespace(path="/" + name, type=FileEntryType.FILE, mtime=mtime) for name, (_, mtime) in self.files.items()]

    def read_file(self, path):
        yield self.files[path.lstrip("/")][0]


def record(filename, kind="img2img", **extra):
    return {"id": filename.split(".")[0], "filename": filename, "created_at": "2026-10-21T10:00:00+00:00",
            "settings": {"generation_type": kind}, **extra}


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dest = Path(self.tmp.name) / "Mulen art"
        self.trashed = []
        self.volume = FakeVolume()

    def tearDown(self):
        self.tmp.cleanup()

    def run_sync(self):
        return sync_images.sync(self.dest, self.volume, trash=lambda path: (self.trashed.append(path.name), path.unlink()))

    def test_new_images_land_in_the_right_folder_and_are_downloaded_once(self):
        self.volume.put("a.png", b"canvas", 1); self.volume.put("a.json", record("a.png"), 1)
        self.volume.put("b.png", b"studio", 2); self.volume.put("b.json", record("b.png", "atelier"), 2)
        self.assertEqual(self.run_sync()["downloaded"], 2)
        self.assertEqual((self.dest / "Plátno" / "a.png").read_bytes(), b"canvas")
        self.assertEqual((self.dest / "Atelier" / "b.png").read_bytes(), b"studio")
        self.assertEqual(self.run_sync(), {"downloaded": 0, "removed": 0, "checked": 0})  # nothing to do the second time

    def test_deleting_in_the_app_moves_the_file_to_the_trash_and_restoring_brings_it_back(self):
        self.volume.put("a.png", b"canvas", 1); self.volume.put("a.json", record("a.png"), 1)
        self.run_sync()
        self.volume.put("a.json", record("a.png", deleted=True), 5)  # the app rewrites the record on delete
        self.assertEqual(self.run_sync()["removed"], 1)
        self.assertEqual(self.trashed, ["a.png"])
        self.assertFalse((self.dest / "Plátno" / "a.png").exists())
        self.assertEqual(self.run_sync()["removed"], 0)  # and it is not removed twice
        self.volume.put("a.json", record("a.png", deleted=False), 9)  # restored in the app
        self.assertEqual(self.run_sync()["downloaded"], 1)
        self.assertTrue((self.dest / "Plátno" / "a.png").exists())

    def test_images_the_user_removed_locally_stay_removed_and_deleted_records_are_never_downloaded(self):
        self.volume.put("a.png", b"canvas", 1); self.volume.put("a.json", record("a.png"), 1)
        self.volume.put("d.png", b"gone", 1); self.volume.put("d.json", record("d.png", deleted=True), 1)
        self.run_sync()
        self.assertFalse((self.dest / "Plátno" / "d.png").exists())
        (self.dest / "Plátno" / "a.png").unlink()  # the user cleans their own folder
        self.run_sync()
        self.assertFalse((self.dest / "Plátno" / "a.png").exists())

    def test_an_image_that_arrives_after_its_record_is_picked_up_later_and_old_state_files_migrate(self):
        self.volume.put("c.json", record("c.png"), 3)
        self.assertEqual(self.run_sync()["downloaded"], 0)
        self.volume.put("c.png", b"late", 4); self.volume.put("c.json", record("c.png"), 4)
        self.assertEqual(self.run_sync()["downloaded"], 1)
        old = {"x.json": "Plátno/x.png", "y.json": "not-a-record"}
        self.assertEqual(sync_images.migrate(old)["x.json"]["status"], "downloaded")
        self.assertEqual(sync_images.migrate(old)["y.json"]["status"], "skip")


if __name__ == "__main__":
    unittest.main()
