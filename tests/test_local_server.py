import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta, UTC
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from app_runtime import server


class LocalServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.output = Path(self.temp.name)
        self.patches = [patch.object(server, "OUTPUTS_DIR", self.output), patch.object(server, "THUMBS_DIR", self.output / "thumbs")]
        for p in self.patches:
            p.start()
        server._RECORD_CACHE.clear()
        server._LISTING_CACHE.clear()
        self.client = TestClient(server.app)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.temp.cleanup()
        server.JOBS.clear()

    def add_image(self, stem, **extra):
        Image.new("RGB", (16, 16), "red").save(self.output / f"{stem}.png")
        record = {"id": stem, "filename": f"{stem}.png", "saved_to_library": True, **extra}
        (self.output / f"{stem}.json").write_text(json.dumps(record))

    def test_cors_allows_the_local_dev_frontend_but_not_arbitrary_websites(self):
        for origin, allowed in (("http://localhost:5173", True), ("http://127.0.0.1:8000", True), ("https://evil.example", False)):
            response = self.client.get("/health", headers={"Origin": origin})
            self.assertEqual(response.headers.get("access-control-allow-origin") == origin, allowed, origin)

    def test_library_route_serves_only_images_not_metadata_or_archives(self):
        self.add_image("a")
        (self.output / "secret.json").write_text("{}")
        (self.output / "atelier-archives").mkdir()
        (self.output / "atelier-archives" / "manifest.json").write_text("{}")
        self.assertEqual(self.client.get("/library/a.png").status_code, 200)
        self.assertIn("private", self.client.get("/library/a.png").headers["cache-control"])
        for path in ("/library/a.json", "/library/secret.json", "/library/atelier-archives/manifest.json", "/library/..%2Fa.png", "/library/missing.png"):
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_library_order_endpoint_exists_validates_and_writes_atomically(self):
        for stem in ("a", "b"):
            self.add_image(stem)
        response = self.client.put("/api/library/order", json={"ids": ["b", "a"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads((self.output / "library-order.json").read_text()), ["b", "a"])
        self.assertEqual(self.client.put("/api/library/order", json={"ids": ["b", "b"]}).status_code, 400)
        self.assertEqual(self.client.put("/api/library/order", json={"ids": "nope"}).status_code, 400)
        self.assertEqual(list(self.output.glob("*.tmp")), [])
        self.assertEqual([item["id"] for item in self.client.get("/api/library").json()["items"]], ["b", "a"])

    def test_records_with_path_like_filenames_are_ignored(self):
        self.add_image("good")
        (self.output / "evil.json").write_text(json.dumps({"id": "evil", "filename": "../good.png"}))
        (self.output / "dots.json").write_text(json.dumps({"id": "dots", "filename": ".."}))
        self.assertEqual([item["id"] for item in server.load_history_items()], ["good"])
        self.assertEqual(self.client.post("/api/library/evil").status_code, 404)

    def test_finished_jobs_are_pruned_and_status_is_a_snapshot(self):
        old = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        with server.JOBS_LOCK:
            server.JOBS["old"] = {"status": "completed", "updated_at": old, "logs": []}
            server.JOBS["live"] = {"status": "running", "updated_at": old, "logs": []}
            server.prune_jobs()
        self.assertNotIn("old", server.JOBS)
        self.assertIn("live", server.JOBS)  # running jobs are never dropped, however old
        snapshot = self.client.get("/api/jobs/live").json()
        snapshot["logs"].append("x")
        self.assertEqual(server.JOBS["live"]["logs"], [])

    def test_completed_local_jobs_do_not_keep_image_bytes_in_memory(self):
        result = {"images": [{"image_base64": "AAAA" * 1000, "format": "png", "width": 1, "height": 1}], "meta": {"model_id": "m"}}
        buffer_png = __import__("io").BytesIO(); Image.new("RGB", (4, 4)).save(buffer_png, "PNG")
        result["images"][0]["image_base64"] = __import__("base64").b64encode(buffer_png.getvalue()).decode()
        with patch.object(server, "generate", return_value=result):
            server.JOBS["j"] = {"id": "j", "status": "queued", "progress": 0, "message": "", "logs": [], "result": None, "error": None,
                                "created_at": server.now_iso(), "updated_at": server.now_iso()}
            server.run_job("j", {})
        stored = server.JOBS["j"]["result"]
        self.assertNotIn("image_base64", json.dumps(stored))
        self.assertTrue(stored["images"][0]["url"].startswith("/library/"))

    def test_exif_rotated_portrait_thumbnail_is_not_regenerated_on_every_request(self):
        path = self.output / "rot.png"
        image = Image.new("RGB", (1600, 800), "blue")
        exif = image.getexif(); exif[0x0112] = 6  # rotate 90: displayed as 800 x 1600
        image.save(path, exif=exif)
        with patch.object(server, "THUMB_WIDTH", 400):
            first = server.ensure_thumbnail("rot.png")
            stamp = first.stat().st_mtime_ns
            time.sleep(0.01)
            self.assertEqual(server.ensure_thumbnail("rot.png").stat().st_mtime_ns, stamp)

    def test_unreferenced_old_sources_are_purged_but_referenced_and_recent_ones_stay(self):
        now = time.time()
        old = now - 20 * 86400
        for name in ("source_used.png", "source_orphan.png", "source_fresh.png"):
            Image.new("RGB", (8, 8)).save(self.output / name)
        import os
        for name in ("source_used.png", "source_orphan.png"):
            os.utime(self.output / name, (old, old))
        self.add_image("out", source_url="/library/source_used.png")
        self.assertEqual(server.purge_orphan_sources(14, now=now), 1)
        self.assertFalse((self.output / "source_orphan.png").exists())
        self.assertTrue((self.output / "source_used.png").exists())
        self.assertTrue((self.output / "source_fresh.png").exists())

    def test_slim_payload_loads_only_a_well_formed_stored_source_name(self):
        name = "source_" + "a" * 64 + ".png"
        Image.new("RGB", (8, 8), "red").save(self.output / name)
        loaded = server.materialize_source({"source_file": name, "image_base64": ""})
        self.assertTrue(loaded["image_base64"])
        self.assertEqual(server.materialize_source({"image_base64": "keep", "source_file": name})["image_base64"], "keep")
        for bad in ("../secret.png", "source_x.png", "a/" + name, "source_" + "A" * 64 + ".png"):
            with self.assertRaises(ValueError):
                server.materialize_source({"source_file": bad, "image_base64": ""})


if __name__ == "__main__":
    unittest.main()
