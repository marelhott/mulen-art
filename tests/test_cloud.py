import base64
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from PIL import Image

from app_runtime.cloud_server import create_app
from app_runtime import cloud_server, server


class CloudFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.output = Path(self.temp.name)
        self.patches = [patch.object(cloud_server, "OUTPUTS_DIR", self.output),
                        patch.object(server, "OUTPUTS_DIR", self.output)]
        for p in self.patches:
            p.start()
        self.jobs, self.usage, self.submissions = {}, {}, []
        self.commits = []
        self.app = self.make_app(lambda key, payload: self.submissions.append((key, payload)))
        self.client = TestClient(self.app)
        self.client.auth = ("studio", "test-password")
        buffer = io.BytesIO()
        Image.new("RGB", (64, 64), "red").save(buffer, format="PNG")
        self.payload = {"image_base64": base64.b64encode(buffer.getvalue()).decode(),
                        "model_id": "tuymans_sdxl", "lora_id": "none", "num_images": 1}

    def make_app(self, submit, monthly_limit=2, **options):
        return create_app(jobs=self.jobs, usage=self.usage, submit=submit,
                          refresh=lambda: None, commit=lambda: self.commits.append(True),
                          username="studio", password="test-password", monthly_limit=monthly_limit, **options)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.temp.cleanup()

    def test_auth_protects_generation_and_gallery(self):
        client = TestClient(self.app)
        for method, path in [("get", "/api/library"), ("post", "/api/generate"), ("get", "/library/x.png")]:
            self.assertEqual(getattr(client, method)(path).status_code, 401)
        self.assertEqual(len(self.submissions), 0)

    def test_unauthenticated_writes_are_rejected_but_health_and_login_stay_public(self):
        client = TestClient(self.app)
        source = {"image_base64": self.payload["image_base64"]}
        writes = [("post", "/api/generate-batch", {"json": {"inputs": [source]}}),
                  ("post", "/api/atelier-batch", {"json": {"model_ids": ["tuymans_modal_800"], "count": 1}}),
                  ("post", "/api/library/x", {}), ("delete", "/api/library/x", {}),
                  ("put", "/api/library/order", {"json": {"ids": []}})]
        for method, path, kwargs in writes:
            self.assertEqual(getattr(client, method)(path, **kwargs).status_code, 401, path)
        client.auth = ("studio", "wrong")
        self.assertEqual(client.post("/api/generate-batch", json={"inputs": [source]}).status_code, 401)
        self.assertEqual(self.submissions, [])
        self.assertEqual(self.usage, {})
        public = TestClient(self.app)
        self.assertEqual(public.get("/health").status_code, 200)
        self.assertEqual(public.get("/login").status_code, 200)

    def test_enabled_auth_refuses_to_start_without_credentials(self):
        for username, password in ((None, None), ("studio", ""), ("", "secret")):
            with self.assertRaises(ValueError):
                create_app(jobs={}, usage={}, submit=lambda *_: None, refresh=lambda: None,
                           commit=lambda: None, username=username, password=password)

    def test_monthly_limit_and_job_cap_come_from_optional_env(self):
        from app_runtime.cloud_server import optional_int_env
        with patch.dict("os.environ", {"MONTHLY_IMAGE_LIMIT": ""}):
            self.assertIsNone(optional_int_env("MONTHLY_IMAGE_LIMIT"))
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(optional_int_env("MAX_JOBS_PER_REQUEST", 64), 64)
        with patch.dict("os.environ", {"MONTHLY_IMAGE_LIMIT": "300"}):
            self.assertEqual(optional_int_env("MONTHLY_IMAGE_LIMIT"), 300)
        for bad in ("0", "-5", "many"):
            with patch.dict("os.environ", {"MONTHLY_IMAGE_LIMIT": bad}), self.assertRaises(ValueError):
                optional_int_env("MONTHLY_IMAGE_LIMIT")

    def test_monthly_limit_returns_429_for_atelier_without_submitting(self):
        response = self.client.post("/api/atelier-batch", json={"model_ids": ["tuymans_modal_800"], "count": 3,
            "settings": {"atelier_mode": "subject", "atelier_theme": "face", "seed": 1}})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(self.submissions, [])
        self.assertEqual(self.usage, {})

    def test_per_request_job_cap_rejects_oversized_batches_before_gpu(self):
        client = TestClient(self.make_app(lambda key, payload: self.submissions.append((key, payload)),
                                          monthly_limit=None, max_jobs_per_request=4))
        client.auth = self.client.auth
        source = {"image_base64": self.payload["image_base64"]}
        self.assertEqual(client.post("/api/generate-batch", json={"inputs": [source] * 5}).status_code, 413)
        self.assertEqual(client.post("/api/generate-batch", json={"inputs": [source] * 2, "settings": {"num_images": 3}}).status_code, 413)
        atelier = {"atelier_mode": "subject", "atelier_theme": "face", "seed": 1}
        self.assertEqual(client.post("/api/atelier-batch", json={"model_ids": ["tuymans_modal_800", "tuymans_modal_2400"],
                                                                  "count": 3, "settings": atelier}).status_code, 413)
        self.assertEqual(self.submissions, [])
        self.assertEqual(self.usage, {})
        self.assertEqual(client.post("/api/generate-batch", json={"inputs": [source] * 2, "settings": {"num_images": 2}}).status_code, 200)
        self.assertEqual(len(self.submissions), 4)

    def test_login_cookie_and_tamper_rejection(self):
        client = TestClient(self.app, base_url="https://studio.test")
        self.assertEqual(client.get("/login").status_code, 200)
        bad = client.post("/login", data={"username": "studio", "password": "wrong"})
        self.assertEqual(bad.status_code, 401)
        good = client.post("/login", data={"username": "studio", "password": "test-password"}, follow_redirects=False)
        self.assertEqual(good.status_code, 303)
        self.assertIn("HttpOnly", good.headers["set-cookie"])
        self.assertIn("Secure", good.headers["set-cookie"])
        self.assertEqual(client.get("/api/options").status_code, 200)
        client.cookies.set("studio_session", "0.tampered")
        self.assertEqual(client.get("/api/options").status_code, 401)

    def test_monthly_usage_persists_independently_of_job_dict(self):
        from app_runtime.cloud_server import VolumeUsage
        from unittest.mock import Mock
        path = self.output / "usage.json"
        ledger = VolumeUsage(path, Mock())
        ledger["2026-10"] = 100
        self.assertEqual(VolumeUsage(path, Mock()).get("2026-10"), 100)

    def test_public_frontend_refresh_never_reuses_equal_size_build(self):
        import os
        frontend = self.output / "frontend"
        frontend.mkdir()
        index = frontend / "index.html"
        index.write_text('<html>build-one</html>')
        os.utime(index, (1000, 1000))
        app = create_app(jobs={}, usage={}, submit=lambda *_: None, refresh=lambda: None,
                         commit=lambda: None, username=None, password=None,
                         auth_enabled=False, frontend_dir=str(frontend))
        client = TestClient(app)
        first = client.get("/")
        self.assertEqual(first.headers["cache-control"], "no-store")
        index.write_text('<html>build-two</html>')
        os.utime(index, (1000, 1000))
        second = client.get("/", headers={"if-none-match": "*", "if-modified-since": "Wed, 21 Oct 2037 07:28:00 GMT"})
        self.assertEqual(second.status_code, 200)
        self.assertIn('build-two', second.text)
        self.assertNotIn('etag', second.headers)

    def test_options_and_polling_do_not_submit_gpu(self):
        data = self.client.get("/api/options").json()
        self.assertTrue({"tuymans_sdxl", "tuy_small", "hofmann_sdxl", "sdxl_base", "tuymans_modal_800", "tuymans_modal_1600", "tuymans_modal_2400"}.issubset({item["id"] for item in data["models"]}))
        self.assertEqual(len(data["loras"]), 3)
        self.assertEqual(self.client.get("/api/jobs/missing").status_code, 404)
        self.assertEqual(len(self.submissions), 0)

    def test_multiple_checkpoints_keep_inputs_separate_and_seeds_comparable(self):
        client = TestClient(self.make_app(lambda key, payload: self.submissions.append((key, payload)), monthly_limit=None))
        client.auth = ("studio", "test-password")
        for model in ("tuymans_modal_800", "tuymans_modal_1600", "tuymans_modal_2400"):
            response = client.post("/api/generate-batch", json={
                "inputs": [{"name": name, "image_base64": self.payload["image_base64"]} for name in ("first.png", "second.png")],
                "settings": {"model_id": model, "num_images": 2, "seed": 4294967295},
            })
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(len(response.json()["jobs"]), 4)
        self.assertEqual(len(self.submissions), 12)
        for model in ("tuymans_modal_800", "tuymans_modal_1600", "tuymans_modal_2400"):
            for name in ("first.png", "second.png"):
                payloads = [payload for _, payload in self.submissions if payload["model_id"] == model and payload["source_name"] == name]
                self.assertEqual([payload["seed"] for payload in payloads], [4294967295, 0])
                self.assertTrue(all(payload["num_images"] == 1 for payload in payloads))

    def test_atelier_queues_no_source_files_and_compares_all_models_on_same_studies(self):
        client = TestClient(self.make_app(lambda key, payload: self.submissions.append((key, payload)), monthly_limit=None))
        client.auth = ("studio", "test-password")
        response = client.post("/api/atelier-batch", json={"model_ids": ["tuymans_modal_800", "tuymans_modal_2400"], "count": 3,
            "settings": {"atelier_mode": "subject", "atelier_theme": "face", "seed": 231020, "cfg": .5, "steps": 28}})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()["jobs"]), 6)
        self.assertEqual(list(self.output.glob('source_*')), [])
        for index in range(3):
            pair = [payload for _,payload in self.submissions if payload["seed"] == 231020+index]
            self.assertEqual(len(pair),2)
            self.assertEqual(pair[0]["source_name"],pair[1]["source_name"])
            self.assertTrue(all(payload["cfg"]==.5 and not payload["image_base64"] and payload["source_url"] is None for payload in pair))
        for invalid in ({"model_ids":["sdxl_base"]}, {"count":9}, {"settings":{"atelier_mode":"missing"}}):
            rejected = client.post("/api/atelier-batch", json={"model_ids":["tuymans_modal_800"], "count":1, **invalid})
            self.assertEqual(rejected.status_code,422)
        self.assertEqual(len(self.submissions),6)

    def test_archive_fusion_validates_source_before_submitting_and_keeps_models_independent(self):
        client = TestClient(self.make_app(lambda key, payload: self.submissions.append((key, payload)), monthly_limit=None))
        client.auth = ("studio", "test-password")
        request = {"model_ids": ["tuymans_modal_2400", "hofmann_sdxl"], "count": 1,
                   "settings": {"atelier_mode": "archive", "atelier_archive": "hofmann", "seed": 123,
                                "denoise": .55, "cfg": .5, "steps": 28}}
        with patch("app_runtime.archives.reference_for", side_effect=ValueError("Missing reference")):
            self.assertEqual(client.post("/api/atelier-batch", json=request).status_code, 422)
        self.assertEqual(self.submissions, [])
        with patch("app_runtime.archives.reference_for", return_value=({"name":"Julius Hofmann"}, {"filename":"painting.png"}, Path("painting.png"))):
            response = client.post("/api/atelier-batch", json=request)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(self.submissions), 2)
        pair = [payload for _, payload in self.submissions]
        self.assertEqual([p["model_id"] for p in pair], request["model_ids"])
        self.assertTrue(all(p["atelier_archive"] == "hofmann" and p["seed"] == 123 and p["steps"] == 28 and p["denoise"] == .55 for p in pair))
        self.assertEqual(pair[0]["source_name"], pair[1]["source_name"])

    def test_random_ratios_are_varied_reproducible_and_shared_between_models(self):
        client = TestClient(self.make_app(lambda key, payload: self.submissions.append((key, payload)), monthly_limit=None))
        client.auth = ("studio", "test-password")
        request = {"model_ids": ["tuymans_modal_2400", "hofmann_sdxl"], "count": 8,
                   "settings": {"atelier_mode":"noise", "atelier_ratio":"random", "seed":20261020}}
        self.assertEqual(client.post("/api/atelier-batch", json=request).status_code, 200)
        first = [p for _,p in self.submissions]
        self.assertGreater(len({(p["width"],p["height"]) for p in first}), 1)
        for i in range(0,16,2):
            self.assertEqual((first[i]["width"],first[i]["height"]), (first[i+1]["width"],first[i+1]["height"]))
        self.assertEqual(client.post("/api/atelier-batch", json=request).status_code, 200)
        self.assertEqual([(p["width"],p["height"]) for p in first], [(p["width"],p["height"]) for _,p in self.submissions[16:]])
        request["settings"]["atelier_ratio"] = "bad"
        self.assertEqual(client.post("/api/atelier-batch", json=request).status_code, 422)

    def test_batch_variant_seeds_and_engine_options_survive_gateway(self):
        settings = {**self.payload, "num_images": 3, "seed": 4294967295,
                    "render_mode": "detail", "detail_steps": 8, "scale": 2}
        self.app = self.make_app(lambda key, payload: self.submissions.append((key, payload)), monthly_limit=None)
        self.client = TestClient(self.app); self.client.auth = ("studio", "test-password")
        response = self.client.post("/api/generate-batch", json={
            "inputs": [{"image_base64": self.payload["image_base64"], "name": "test.png"}], "settings": settings})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([p["seed"] for _, p in self.submissions], [4294967295, 0, 1])
        self.assertTrue(all(p["render_mode"] == "detail" and p["detail_steps"] == 8 for _, p in self.submissions))

    def test_invalid_input_does_not_allocate_gpu_or_quota(self):
        for payload in [{}, {**self.payload, "model_id": "missing"}, {**self.payload, "image_base64": "invalid"}]:
            self.assertEqual(self.client.post("/api/generate", json=payload).status_code, 422)
        self.assertEqual(self.usage, {})
        self.assertEqual(self.submissions, [])

    def test_modes_reject_mixed_checkpoint_lora_before_gpu(self):
        invalid = [
            {**self.payload, "lora_id": "lora_tuymans_sdxl"},
            {**self.payload, "model_id": "sdxl_base", "lora_id": "none"},
        ]
        for payload in invalid:
            self.assertEqual(self.client.post("/api/generate", json=payload).status_code, 422)
        self.assertEqual(self.submissions, [])
        valid = {**self.payload, "model_id": "sdxl_base", "lora_id": "lora_hofmann_sdxl"}
        self.assertEqual(self.client.post("/api/generate", json=valid).status_code, 200)
        self.assertEqual(self.submissions[0][1]["model_id"], "sdxl_base")
        self.assertEqual(self.submissions[0][1]["lora_id"], "lora_hofmann_sdxl")

    def test_quota_and_shared_job_survive_new_gateway(self):
        first = self.client.post("/api/generate", json={**self.payload, "num_images": 2})
        self.assertEqual(first.status_code, 200)
        job_id = first.json()["job_id"]
        client = TestClient(self.make_app(lambda *_: None))
        client.auth = self.client.auth
        self.assertEqual(client.get(f"/api/jobs/{job_id}").json()["status"], "queued")
        self.assertEqual(client.post("/api/generate", json=self.payload).status_code, 429)
        self.assertEqual(len(self.submissions), 1)

    def test_submission_failure_rolls_back_quota(self):
        def fail(*_):
            raise RuntimeError("offline")
        client = TestClient(self.make_app(fail)); client.auth = self.client.auth
        self.assertEqual(client.post("/api/generate", json=self.payload).status_code, 503)
        self.assertEqual(sum(self.usage.values()), 0)
        self.assertEqual(self.jobs, {})

    def test_worker_persists_gallery_without_inline_base64(self):
        import modal_app
        from unittest.mock import Mock
        self.jobs["test-job"] = {"id": "test-job", "status": "queued", "logs": []}
        with patch.object(modal_app, "jobs", self.jobs), patch.object(modal_app, "models", Mock()), patch.object(modal_app, "outputs", Mock()), patch.dict("os.environ", {"IMG2IMG_DEMO_MODE": "true"}):
            modal_app.generate_job("test-job", self.payload)
        job = self.jobs["test-job"]
        self.assertEqual(job["status"], "completed")
        image = job["result"]["images"][0]
        self.assertNotIn("image_base64", image)
        self.assertEqual(self.client.get(image["url"]).status_code, 200)
        self.assertEqual(len(self.client.get("/api/history").json()["items"]), 1)
        # New outputs start on the canvas only; they enter the library after an explicit save.
        self.assertEqual(len(self.client.get("/api/library").json()["items"]), 0)
        self.assertEqual(self.client.post(f'/api/library/{image["id"]}').status_code, 200)
        self.assertEqual(len(self.client.get("/api/library").json()["items"]), 1)
        self.assertEqual(self.client.delete(f'/api/library/{image["id"]}').status_code, 200)
        self.assertEqual(self.client.get("/api/history").json()["items"], [])
        self.assertEqual(self.client.get("/api/library").json()["items"], [])
        self.assertEqual(self.client.post(f'/api/library/{image["id"]}').status_code, 200)
        self.assertEqual(len(self.client.get("/api/history").json()["items"]), 1)
        self.assertEqual(len(self.client.get("/api/library").json()["items"]), 1)
        self.assertEqual(len(self.commits), 3)

    def test_worker_failure_visible_after_gateway_restart(self):
        import modal_app
        from unittest.mock import Mock
        self.jobs["test-job"] = {"id": "test-job", "status": "queued", "logs": []}
        with patch.object(modal_app, "jobs", self.jobs), patch.object(modal_app, "models", Mock()), patch.object(modal_app, "outputs", Mock()), patch("app_runtime.core.generate", side_effect=RuntimeError("model unavailable")):
            with self.assertRaisesRegex(RuntimeError, "model unavailable"):
                modal_app.generate_job("test-job", self.payload)
        self.assertEqual(self.jobs["test-job"]["status"], "failed")
        self.assertIn("model unavailable", self.jobs["test-job"]["error"]["detail"])

    def test_incremental_images_visible_while_running_without_duplicate_saves(self):
        import modal_app
        from unittest.mock import Mock
        self.jobs["stream-job"] = {"id": "stream-job", "status": "queued", "logs": []}
        image = {"image_base64": self.payload["image_base64"], "width": 64, "height": 64, "format": "png"}
        meta = {"model_id": "tuymans_sdxl", "lora_id": "none", "demo_mode": False}
        volume = Mock()
        committed_files = set()
        def commit_files():
            self.assertNotEqual(self.jobs["stream-job"]["status"], "completed")
            committed_files.update(path.name for path in self.output.glob("*"))
        volume.commit.side_effect = commit_files
        def fake_generate(payload, progress_callback, image_callback):
            for count in (1, 2):
                image_callback(image, meta)
                live = self.jobs["stream-job"]
                self.assertEqual(live["status"], "running")
                self.assertEqual(len(live["partial_images"]), count)
                self.assertEqual(volume.commit.call_count, count)
                self.assertIn(live["partial_images"][-1]["filename"], committed_files)
                # Each saved image carries a real elapsed-time figure for the cost readout.
                # A stubbed generator finishes instantly, so only the type is asserted here.
                self.assertIsInstance(live["partial_images"][-1]["settings"]["worker_seconds"], float)
                self.assertEqual(self.client.get(live["partial_images"][-1]["url"]).status_code, 200)
            return {"images": [image, image], "meta": meta}
        with patch.object(modal_app, "jobs", self.jobs), patch.object(modal_app, "models", Mock()), patch.object(modal_app, "outputs", volume), patch("app_runtime.core.generate", side_effect=fake_generate):
            modal_app.generate_job("stream-job", self.payload)
        self.assertEqual(self.jobs["stream-job"]["status"], "completed")
        self.assertEqual(len(self.jobs["stream-job"]["result"]["images"]), 2)
        self.assertEqual(len(self.client.get("/api/history").json()["items"]), 2)
        self.assertEqual(len(self.client.get("/api/library").json()["items"]), 0)

    def test_source_is_committed_before_submission_and_commit_failure_does_not_enqueue(self):
        from unittest.mock import Mock
        committed_sources = set()
        def commit_sources():
            committed_sources.update(path.name for path in self.output.glob("source_*.png"))
        def submit(job_id, payload):
            self.assertIn(Path(payload["source_url"]).name, committed_sources)
            self.submissions.append((job_id, payload))
        commit = Mock(side_effect=commit_sources)
        app = create_app(jobs=self.jobs, usage=self.usage, submit=submit, refresh=lambda: None,
                         commit=commit, username=None, password=None, auth_enabled=False)
        client = TestClient(app)
        self.assertEqual(client.post("/api/generate", json=self.payload).status_code, 200)
        self.assertEqual(commit.call_count, 1)
        self.assertEqual(len(self.submissions), 1)
        # Reused sources are confirmed too, including retries after a failed commit.
        self.assertEqual(client.post("/api/generate", json=self.payload).status_code, 200)
        self.assertEqual(commit.call_count, 2)
        self.jobs.clear(); self.usage.clear(); self.submissions.clear()
        commit.side_effect = RuntimeError("storage unavailable")
        failed = TestClient(app, raise_server_exceptions=False).post("/api/generate", json=self.payload)
        self.assertEqual(failed.status_code, 500)
        self.assertEqual(self.jobs, {})
        self.assertEqual(self.usage, {})
        self.assertEqual(self.submissions, [])
        commit.side_effect = commit_sources
        self.assertEqual(client.post("/api/generate", json=self.payload).status_code, 200)
        self.assertEqual(commit.call_count, 4)
        self.assertEqual(len(self.submissions), 1)

    def test_worker_never_publishes_images_when_volume_commit_fails(self):
        import modal_app
        from unittest.mock import Mock
        self.jobs["failed-commit"] = {"id": "failed-commit", "status": "queued", "logs": []}
        image = {"image_base64": self.payload["image_base64"], "format": "png"}
        meta = {"model_id": "tuymans_sdxl"}
        volume = Mock()
        volume.commit.side_effect = RuntimeError("storage unavailable")
        for incremental in (True, False):
            self.jobs["failed-commit"] = {"id": "failed-commit", "status": "queued", "logs": []}
            def generate(payload, progress_callback, image_callback):
                if incremental:
                    image_callback(image, meta)
                return {"images": [image], "meta": meta}
            with patch.object(modal_app, "jobs", self.jobs), patch.object(modal_app, "models", Mock()), patch.object(modal_app, "outputs", volume), patch("app_runtime.core.generate", side_effect=generate):
                with self.assertRaisesRegex(RuntimeError, "storage unavailable"):
                    modal_app.generate_job("failed-commit", self.payload)
            self.assertEqual(self.jobs["failed-commit"]["status"], "failed")
            self.assertNotIn("partial_images", self.jobs["failed-commit"])
            self.assertNotIn("result", self.jobs["failed-commit"])

    def test_missing_cloud_asset_refreshes_even_within_polling_cache_interval(self):
        from unittest.mock import Mock
        def reveal_file():
            Image.new("RGB", (64, 64), "blue").save(self.output / "new.png")
        refresh = Mock()
        app = create_app(jobs={}, usage={}, submit=lambda *_: None, refresh=refresh,
                         commit=lambda: None, username=None, password=None, auth_enabled=False)
        client = TestClient(app)
        client.get("/api/history")
        refresh.side_effect = reveal_file
        self.assertEqual(client.get("/library/new.png").status_code, 200)
        self.assertEqual(refresh.call_count, 2)

    def test_local_thumbnail_route_returns_real_webp_and_supports_head(self):
        Image.new("RGB", (1200, 800), "red").save(self.output / "local.png")
        with patch.object(server, "THUMBS_DIR", self.output / "thumbs"):
            client = TestClient(server.app)
            response = client.get("/thumb/local.webp")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"], "image/webp")
            with Image.open(io.BytesIO(response.content)) as image:
                self.assertEqual(image.size, (server.THUMB_WIDTH, round(800 * server.THUMB_WIDTH / 1200)))
            head = client.head("/thumb/local.webp")
            self.assertEqual(head.status_code, 200)
            self.assertEqual(head.content, b"")
            self.assertEqual(int(head.headers["content-length"]), len(response.content))
            self.assertEqual(client.get("/thumb/missing.webp").status_code, 404)
            self.assertEqual(client.get("/thumb/local.png").status_code, 404)
            with patch("app_runtime.archives.archive_options", return_value=[]):
                self.assertEqual(client.get("/api/options").json()["archives"], [])

    def test_img2img_progress_uses_actual_denoising_steps(self):
        from app_runtime.core import build_step_callback
        from types import SimpleNamespace
        updates = []
        callback = build_step_callback(lambda value, message: updates.append((value, message)), 0.35, 2, 0, 25)
        state = {}
        self.assertIs(callback(SimpleNamespace(num_timesteps=11), 10, None, state), state)
        self.assertAlmostEqual(updates[-1][0], 0.625)
        self.assertEqual(updates[-1][1], "Image 1/2: step 11/11")

    def test_batch_ten_inputs_remain_independent_and_reserve_twenty_outputs(self):
        inputs = [{"name": f"source-{i}.png", "image_base64": self.payload["image_base64"]} for i in range(10)]
        buffer = io.BytesIO(); Image.new("RGB", (80, 64), "blue").save(buffer, format="PNG")
        inputs[1]["image_base64"] = base64.b64encode(buffer.getvalue()).decode()
        client = TestClient(self.make_app(lambda key, payload: self.submissions.append((key, payload)), monthly_limit=20))
        client.auth = self.client.auth
        settings = {"model_id": "tuymans_sdxl", "num_images": 2}
        response = client.post("/api/generate-batch", json={"inputs": inputs, "settings": settings})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["jobs"]), 20)
        self.assertEqual(len(self.submissions), 20)
        for index, (_, payload) in enumerate(self.submissions):
            self.assertEqual(payload["image_base64"], inputs[index // 2]["image_base64"])
            self.assertEqual(payload["source_name"], inputs[index // 2]["name"])
            self.assertEqual(payload["num_images"], 1)
        self.assertEqual(sum(self.usage.values()), 20)

    def test_batch_rejects_invalid_count_input_and_total_quota_before_gpu(self):
        source = {"image_base64": self.payload["image_base64"]}
        for inputs in ([], [source, {"image_base64": "invalid"}]):
            self.assertEqual(self.client.post("/api/generate-batch", json={"inputs": inputs}).status_code, 422)
        self.assertEqual(self.client.post("/api/generate-batch", json={"inputs": [source] * 2, "settings": {"num_images": 2}}).status_code, 429)
        self.assertEqual(self.submissions, [])
        self.assertEqual(self.usage, {})

    def test_unlimited_counts_split_variants_and_no_monthly_cap(self):
        client = TestClient(self.make_app(lambda key, payload: self.submissions.append((key, payload)),
                                          monthly_limit=None, max_jobs_per_request=None))
        client.auth = self.client.auth
        response = client.post("/api/generate-batch", json={"inputs": [
            {"name": f"source-{i}", "image_base64": self.payload["image_base64"]} for i in range(12)],
            "settings": {"num_images": 21}})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["jobs"]), 252)
        self.assertEqual(sum(self.usage.values()), 252)
        self.assertIsNone(client.get("/api/usage").json()["limit"])
        self.assertTrue(all(payload["num_images"] == 1 for _, payload in self.submissions))
        self.assertEqual({j["source_index"] for j in response.json()["jobs"]}, set(range(12)))

    def test_retained_source_is_private_and_survives_gateway_restart(self):
        response = self.client.post("/api/generate-batch", json={"inputs": [
            {"name": "original.png", "image_base64": self.payload["image_base64"]}]})
        job = self.jobs[response.json()["jobs"][0]["job_id"]]
        self.assertTrue(job["source_url"].startswith("/library/source_"))
        self.assertEqual(TestClient(self.app).get(job["source_url"]).status_code, 401)
        self.assertEqual(self.client.get(job["source_url"]).status_code, 200)
        client = TestClient(self.make_app(lambda *_: None)); client.auth = self.client.auth
        self.assertEqual(client.get(job["source_url"]).status_code, 200)
        self.assertEqual(client.get("/api/library").json()["items"], [])

    def test_waiting_queue_does_not_expire_based_on_submission_age(self):
        response = self.client.post("/api/generate", json=self.payload)
        job_id = response.json()["job_id"]
        self.jobs[job_id]["created_at"] = "2020-01-01T00:00:00+00:00"
        self.assertEqual(self.client.get(f"/api/jobs/{job_id}").json()["status"], "queued")

    def test_non_positive_and_fractional_variant_counts_are_rejected(self):
        for count in (0, -1, 1.5, True):
            self.assertEqual(self.client.post("/api/generate", json={**self.payload, "num_images": count}).status_code, 422)
        self.assertFalse(self.submissions)

    def test_batch_partial_submission_failure_keeps_successful_job_and_refunds_failed(self):
        def submit(key, payload):
            if payload["source_name"] == "bad": raise RuntimeError("offline")
            self.submissions.append((key, payload))
        client = TestClient(self.make_app(submit)); client.auth = self.client.auth
        response = client.post("/api/generate-batch", json={"inputs": [
            {"name": name, "image_base64": self.payload["image_base64"]} for name in ("bad", "good")]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["jobs"]), 1)
        self.assertEqual(response.json()["jobs"][0]["source_index"], 1)
        self.assertEqual(len(response.json()["errors"]), 1)
        self.assertEqual(sum(self.usage.values()), 1)
        self.assertEqual(len(self.jobs), 1)

    def test_legacy_records_without_saved_flag_stay_in_library_but_unsaved_ones_leave(self):
        from app_runtime import server
        import json
        def write(stem, saved):
            record = {"id": stem, "filename": f"{stem}.png", "url": f"/library/{stem}.png",
                      "width": 8, "height": 8, "format": "png", "created_at": "2026-10-19T00:00:00+00:00",
                      "model_id": "tuymans_sdxl", "lora_id": "none", "settings": {}}
            if saved is not None:
                record["saved_to_library"] = saved
            (self.output / f"{stem}.png").write_bytes(b"stub")
            (self.output / f"{stem}.json").write_text(json.dumps(record))
        write("legacy-no-flag", None)
        write("explicitly-saved", True)
        write("explicitly-unsaved", False)
        ids = {item["id"] for item in server.load_library_items()}
        self.assertEqual(ids, {"legacy-no-flag", "explicitly-saved"})
        self.assertEqual({item["id"] for item in server.load_history_items()}, {"legacy-no-flag", "explicitly-saved", "explicitly-unsaved"})

    def test_thumbnails_are_generated_small_cached_and_served_with_cache_headers(self):
        from app_runtime import server
        from PIL import Image
        Image.new("RGB", (1200, 800), (10, 20, 30)).save(self.output / "big.png")
        target = server.ensure_thumbnail("big.png")
        self.assertIsNotNone(target)
        with Image.open(target) as thumb:
            self.assertEqual(thumb.width, server.THUMB_WIDTH)
            self.assertEqual(thumb.format, "WEBP")
        self.assertLess(target.stat().st_size, (self.output / "big.png").stat().st_size)
        again = server.ensure_thumbnail("big.png")
        self.assertEqual(again, target)

    def test_narrow_sources_keep_their_size_and_missing_sources_return_none(self):
        from app_runtime import server
        from PIL import Image
        Image.new("RGB", (120, 90), (5, 5, 5)).save(self.output / "small.png")
        target = server.ensure_thumbnail("small.png")
        with Image.open(target) as thumb:
            self.assertEqual(thumb.size, (120, 90))
        self.assertIsNone(server.ensure_thumbnail("does-not-exist.png"))

    def test_image_assets_support_head_and_immutable_caching(self):
        from PIL import Image
        Image.new("RGB", (32, 32), (1, 2, 3)).save(self.output / "asset.png")
        head = self.client.head("/library/asset.png")
        self.assertEqual(head.status_code, 200)
        self.assertEqual(int(head.headers["content-length"]), (self.output / "asset.png").stat().st_size)
        self.assertIn("immutable", head.headers["cache-control"])
        get = self.client.get("/library/asset.png")
        self.assertEqual(get.status_code, 200)
        self.assertIn("immutable", get.headers["cache-control"])
        self.assertEqual(self.client.head("/library/missing.png").status_code, 404)

    def test_bulk_status_returns_many_jobs_in_one_request_and_null_for_unknown(self):
        self.jobs["aaa"] = {"id": "aaa", "status": "queued", "progress": 0}
        self.jobs["bbb"] = {"id": "bbb", "status": "completed", "progress": 1}
        data = self.client.get("/api/jobs", params={"ids": "aaa,bbb,missing,bad id!"}).json()
        self.assertEqual(data["jobs"]["aaa"]["status"], "queued")
        self.assertEqual(data["jobs"]["bbb"]["status"], "completed")
        self.assertIsNone(data["jobs"]["missing"])
        self.assertNotIn("bad id!", data["jobs"])
        self.assertEqual(self.client.get("/api/jobs").status_code, 422)
        self.assertEqual(self.client.get("/api/jobs", params={"ids": ",".join(f"j{i}" for i in range(201))}).status_code, 422)

    def test_cancel_stops_the_cloud_call_and_keeps_finished_jobs_untouched(self):
        cancelled = []
        app = self.make_app(lambda key, payload: f"fc-{key}", monthly_limit=None, cancel=cancelled.append)
        client = TestClient(app)
        client.auth = ("studio", "test-password")
        job_id = client.post("/api/generate", json=self.payload).json()["job_id"]
        self.assertEqual(self.jobs[f"call:{job_id}"], f"fc-{job_id}")
        result = client.post(f"/api/jobs/{job_id}/cancel").json()
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(cancelled, [f"fc-{job_id}"])
        self.jobs["done"] = {"id": "done", "status": "completed"}
        self.assertEqual(client.post("/api/jobs/done/cancel").json()["status"], "completed")
        self.assertEqual(cancelled, [f"fc-{job_id}"])
        self.assertEqual(client.post("/api/jobs/missing/cancel").status_code, 404)
        self.assertEqual(self.client.post(f"/api/jobs/{job_id}/cancel").status_code, 501)

    def test_source_uploaded_once_can_back_many_batches_without_resending_bytes(self):
        app = self.make_app(lambda key, payload: self.submissions.append((key, payload)), monthly_limit=None)
        client = TestClient(app)
        client.auth = ("studio", "test-password")
        upload = client.post("/api/sources", json={"image_base64": self.payload["image_base64"]})
        self.assertEqual(upload.status_code, 200)
        source_id = upload.json()["source_id"]
        self.assertEqual(len(list(self.output.glob("source_*.png"))), 1)
        for model_id in ("tuymans_sdxl", "tuy_small"):
            response = client.post("/api/generate-batch", json={
                "inputs": [{"name": "a.png", "source_id": source_id}], "settings": {"model_id": model_id}})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.submissions), 2)
        # The stored file is reused; no duplicate source is written per batch.
        self.assertEqual(len(list(self.output.glob("source_*.png"))), 1)
        self.assertTrue(all(p["source_url"] == f"/library/source_{source_id}.png" for _, p in self.submissions))
        for bad in ("../x", "0" * 64, None):
            response = client.post("/api/generate-batch", json={"inputs": [{"source_id": bad}], "settings": {}})
            self.assertEqual(response.status_code, 422)
        self.assertEqual(client.post("/api/sources", json={"image_base64": "invalid"}).status_code, 422)
        self.assertEqual(TestClient(app).post("/api/sources", json={}).status_code, 401)

    def test_worker_does_not_overwrite_a_cancelled_job(self):
        import modal_app
        from unittest.mock import Mock
        self.jobs["test-job"] = {"id": "test-job", "status": "cancelled", "logs": []}
        with patch.object(modal_app, "jobs", self.jobs), patch.object(modal_app, "models", Mock()), patch.object(modal_app, "outputs", Mock()), patch.dict("os.environ", {"IMG2IMG_DEMO_MODE": "true"}):
            modal_app.generate_job("test-job", self.payload)
        self.assertEqual(self.jobs["test-job"]["status"], "cancelled")

    def test_record_cache_sees_same_size_same_mtime_rewrites(self):
        import json, os
        path = self.output / "rec.json"
        path.write_text(json.dumps({"state": "aaaa"}))
        before = path.stat()
        self.assertEqual(server.read_record(path), {"state": "aaaa"})
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"state": "bbbb"}))
        os.utime(temporary, ns=(before.st_atime_ns, before.st_mtime_ns))
        temporary.replace(path)
        self.assertEqual(path.stat().st_size, before.st_size)
        self.assertEqual(server.read_record(path), {"state": "bbbb"})

    def test_gpu_cap_is_global_across_models_and_expires_leaked_slots(self):
        import modal_app
        slots = {}
        for index in range(3):
            modal_app.acquire_slot(slots, f"j{index}", cap=3, now=100)
        with self.assertRaisesRegex(RuntimeError, "backlog"):
            modal_app.acquire_slot(slots, "j3", cap=3, now=101)
        modal_app.release_slot(slots, "j0")
        modal_app.release_slot(slots, "j0")  # idempotent
        modal_app.acquire_slot(slots, "j3", cap=3, now=102)
        # A crashed worker never releases; its slot is reclaimed after the TTL.
        modal_app.acquire_slot(slots, "j4", cap=3, ttl=50, now=1000)
        self.assertEqual(list(slots), ["j4"])

    def test_spawn_routes_to_model_pool_returns_call_id_and_cancel_releases_slot(self):
        import modal_app
        from unittest.mock import Mock
        slots, worker = {}, Mock()
        worker.return_value.run.spawn.return_value.object_id = "fc-123"
        with patch.object(modal_app, "slots", slots), patch.object(modal_app, "ImageWorker", worker), \
                patch.object(modal_app.modal.FunctionCall, "from_id") as from_id:
            self.assertEqual(modal_app.spawn_job("job", {"model_id": "hofmann_sdxl"}), "fc-123")
            worker.assert_called_once_with(model_id="hofmann_sdxl")
            self.assertEqual(slots["job"]["call_id"], "fc-123")
            modal_app.cancel_call("fc-123")
            from_id.assert_called_once_with("fc-123")
            from_id.return_value.cancel.assert_called_once()
        self.assertEqual(slots, {})

    def test_spawn_failure_releases_slot(self):
        import modal_app
        from unittest.mock import Mock
        slots, worker = {}, Mock()
        worker.return_value.run.spawn.side_effect = RuntimeError("offline")
        with patch.object(modal_app, "slots", slots), patch.object(modal_app, "ImageWorker", worker):
            with self.assertRaises(RuntimeError):
                modal_app.spawn_job("job", {"model_id": "tuymans_sdxl"})
        self.assertEqual(slots, {})

    def test_worker_is_parameterized_by_model_and_releases_slot(self):
        import modal_app
        from unittest.mock import Mock
        slots = {"test-job": {"ts": 1, "call_id": None}}
        self.jobs["test-job"] = {"id": "test-job", "status": "queued", "logs": []}
        with patch.object(modal_app, "jobs", self.jobs), patch.object(modal_app, "slots", slots), patch.object(modal_app, "models", Mock()), patch.object(modal_app, "outputs", Mock()), patch.dict("os.environ", {"IMG2IMG_DEMO_MODE": "true"}):
            modal_app.ImageWorker(model_id="tuymans_sdxl").run.local("test-job", self.payload)
        self.assertEqual(self.jobs["test-job"]["status"], "completed")
        self.assertEqual(slots, {})


if __name__ == "__main__":
    unittest.main()
