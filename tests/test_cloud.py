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

    def make_app(self, submit, monthly_limit=2):
        return create_app(jobs=self.jobs, usage=self.usage, submit=submit,
                          refresh=lambda: None, commit=lambda: self.commits.append(True),
                          username="studio", password="test-password", monthly_limit=monthly_limit)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.temp.cleanup()

    def test_auth_protects_generation_and_gallery(self):
        client = TestClient(self.app)
        for method, path in [("get", "/api/library"), ("post", "/api/generate"), ("get", "/library/x.png")]:
            self.assertEqual(getattr(client, method)(path).status_code, 401)
        self.assertEqual(len(self.submissions), 0)

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
        self.assertEqual(len(data["models"]), 4)
        self.assertEqual(len(data["loras"]), 3)
        self.assertEqual(self.client.get("/api/jobs/missing").status_code, 404)
        self.assertEqual(len(self.submissions), 0)

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
            modal_app.generate_image.local("test-job", self.payload)
        job = self.jobs["test-job"]
        self.assertEqual(job["status"], "completed")
        image = job["result"]["images"][0]
        self.assertNotIn("image_base64", image)
        self.assertEqual(self.client.get(image["url"]).status_code, 200)
        items = self.client.get("/api/library").json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(self.client.delete(f'/api/library/{image["id"]}').status_code, 200)
        self.assertEqual(self.client.get(image["url"]).status_code, 404)
        self.assertEqual(self.client.get("/api/library").json()["items"], [])
        self.assertEqual(len(self.commits), 1)

    def test_worker_failure_visible_after_gateway_restart(self):
        import modal_app
        from unittest.mock import Mock
        self.jobs["test-job"] = {"id": "test-job", "status": "queued", "logs": []}
        with patch.object(modal_app, "jobs", self.jobs), patch.object(modal_app, "models", Mock()), patch.object(modal_app, "outputs", Mock()), patch("app_runtime.core.generate", side_effect=RuntimeError("model unavailable")):
            with self.assertRaisesRegex(RuntimeError, "model unavailable"):
                modal_app.generate_image.local("test-job", self.payload)
        self.assertEqual(self.jobs["test-job"]["status"], "failed")
        self.assertIn("model unavailable", self.jobs["test-job"]["error"]["detail"])

    def test_incremental_images_visible_while_running_without_duplicate_saves(self):
        import modal_app
        from unittest.mock import Mock
        self.jobs["stream-job"] = {"id": "stream-job", "status": "queued", "logs": []}
        image = {"image_base64": self.payload["image_base64"], "width": 64, "height": 64, "format": "png"}
        meta = {"model_id": "tuymans_sdxl", "lora_id": "none", "demo_mode": False}
        def fake_generate(payload, progress_callback, image_callback):
            for count in (1, 2):
                image_callback(image, meta)
                live = self.jobs["stream-job"]
                self.assertEqual(live["status"], "running")
                self.assertEqual(len(live["partial_images"]), count)
                self.assertEqual(self.client.get(live["partial_images"][-1]["url"]).status_code, 200)
            return {"images": [image, image], "meta": meta}
        with patch.object(modal_app, "jobs", self.jobs), patch.object(modal_app, "models", Mock()), patch.object(modal_app, "outputs", Mock()), patch("app_runtime.core.generate", side_effect=fake_generate):
            modal_app.generate_image.local("stream-job", self.payload)
        self.assertEqual(self.jobs["stream-job"]["status"], "completed")
        self.assertEqual(len(self.jobs["stream-job"]["result"]["images"]), 2)
        self.assertEqual(len(self.client.get("/api/library").json()["items"]), 2)

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
        client = TestClient(self.make_app(lambda key, payload: self.submissions.append((key, payload)), monthly_limit=None))
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


if __name__ == "__main__":
    unittest.main()
