import base64
import io
import json
import unittest
from unittest.mock import patch

import httpx
from PIL import Image

from app_runtime import core
from app_runtime.vari import providers, run


def png(color=(120, 60, 200), size=(64, 48)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def source_base64():
    return base64.b64encode(png((10, 90, 160), (300, 200))).decode()


class FakeInternet:
    """Routes every provider call to canned answers and records what was sent."""

    def __init__(self, replicate_statuses=("succeeded",)):
        self.calls = []
        self.replicate_statuses = list(replicate_statuses)

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        body = json.loads(request.content) if request.headers.get("content-type", "").startswith("application/json") and request.content else None
        self.calls.append((request.method, url, body, dict(request.headers)))
        if "rest.alpha.fal.ai/storage/upload/initiate" in url:
            return httpx.Response(200, json={"upload_url": "https://upload.test/put", "file_url": "https://cdn.test/source.png"})
        if url == "https://upload.test/put":
            return httpx.Response(200)
        if url.startswith("https://queue.fal.run/"):
            return httpx.Response(200, json={"request_id": "r1", "status_url": "https://queue.test/status", "response_url": "https://queue.test/result",
                                             "cancel_url": "https://queue.test/cancel"})
        if url == "https://queue.test/status":
            return httpx.Response(200, json={"status": "COMPLETED"})
        if url == "https://queue.test/result":
            return httpx.Response(200, json={"images": [{"url": "https://cdn.test/out1.png"}, {"url": "https://cdn.test/out2.png"}]})
        if url == "https://api.replicate.com/v1/predictions":
            return httpx.Response(201, json={"id": "p1", "status": "starting"})
        if url == "https://api.replicate.com/v1/predictions/p1":
            status = self.replicate_statuses.pop(0) if len(self.replicate_statuses) > 1 else self.replicate_statuses[0]
            output = ["https://cdn.test/rep1.png", "https://cdn.test/rep2.png"] if status == "succeeded" else None
            return httpx.Response(200, json={"id": "p1", "status": status, "output": output, "error": "boom" if status == "failed" else None})
        if url.startswith("https://cdn.test/"):
            return httpx.Response(200, content=png())
        if url == "https://api.openai.com/v1/responses":
            return httpx.Response(200, json={"output_text": json.dumps({"subject": "a ghost", "immutable_elements": ["ghost"], "variable_elements": []})})
        if url == "https://api.openai.com/v1/images/edits":
            return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(png()).decode()}]})
        return httpx.Response(404, json={"detail": f"unexpected {url}"})

    def client(self):
        return httpx.Client(transport=httpx.MockTransport(self.handler), headers={"User-Agent": providers.USER_AGENT})


class ProviderTests(unittest.TestCase):
    def test_fal_queue_flow_returns_the_image_urls(self):
        net = FakeInternet()
        with patch.dict("os.environ", {"FAL_KEY": "k"}):
            images = providers.run_fal(net.client(), {"_model_id": "fal-ai/z-image/turbo/image-to-image", "prompt": "p", "num_images": 2})
        self.assertEqual([i["url"] for i in images], ["https://cdn.test/out1.png", "https://cdn.test/out2.png"])
        submit = next(call for call in net.calls if call[1].startswith("https://queue.fal.run/"))
        self.assertEqual(submit[2], {"prompt": "p", "num_images": 2})  # the _model_id never reaches the provider body
        self.assertEqual(submit[3]["authorization"], "Key k")

    def test_replicate_polls_until_succeeded_and_sends_user_agent(self):
        net = FakeInternet(replicate_statuses=("starting", "processing", "succeeded"))
        with patch.dict("os.environ", {"REPLICATE_API_TOKEN": "t"}):
            images = providers.run_replicate(net.client(), {"version": "v", "input": {"a": 1}}, poll=0)
        self.assertEqual(len(images), 2)
        create = next(call for call in net.calls if call[0] == "POST")
        self.assertEqual(create[2], {"version": "v", "input": {"a": 1}})
        self.assertEqual(create[3]["user-agent"], providers.USER_AGENT)

    def test_replicate_throttling_is_retried_after_the_announced_wait(self):
        responses = [httpx.Response(429, json={"detail": "throttled", "retry_after": 7}), httpx.Response(429, json={"retry_after": 3}),
                     httpx.Response(201, json={"id": "p9", "status": "starting"})]
        waits = []
        client = httpx.Client(transport=httpx.MockTransport(lambda request: responses.pop(0)))
        with patch.dict("os.environ", {"REPLICATE_API_TOKEN": "t"}):
            self.assertEqual(providers.create_replicate_prediction(client, {"version": "v", "input": {}}, sleep=waits.append), "p9")
        self.assertEqual(len(waits), 2)
        self.assertTrue(7 <= waits[0] <= 12 and 3 <= waits[1] <= 14)

    def test_replicate_gives_up_after_the_last_attempt(self):
        client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(429, json={"detail": "Request was throttled.", "retry_after": 1})))
        with patch.dict("os.environ", {"REPLICATE_API_TOKEN": "t"}), self.assertRaisesRegex(providers.ProviderError, "throttled"):
            providers.create_replicate_prediction(client, {"version": "v", "input": {}}, attempts=2, sleep=lambda s: None)

    def test_replicate_failure_surfaces_the_providers_message(self):
        net = FakeInternet(replicate_statuses=("failed",))
        with patch.dict("os.environ", {"REPLICATE_API_TOKEN": "t"}), self.assertRaisesRegex(providers.ProviderError, "boom"):
            providers.run_replicate(net.client(), {"version": "v", "input": {}}, poll=0)

    def test_cancel_stops_polling_and_cancels_the_prediction(self):
        net = FakeInternet(replicate_statuses=("processing",))
        with patch.dict("os.environ", {"REPLICATE_API_TOKEN": "t"}), self.assertRaises(providers.Cancelled):
            providers.run_replicate(net.client(), {"version": "v", "input": {}}, poll=0, cancelled=lambda: True)
        self.assertTrue(any(call[1].endswith("/p1/cancel") for call in net.calls))

    def test_a_missing_key_has_a_clear_message(self):
        with patch.dict("os.environ", {}, clear=True), self.assertRaisesRegex(providers.ProviderError, "FAL_KEY"):
            providers.fal_headers()

    def test_upload_falls_back_to_a_data_uri_without_a_key(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertTrue(providers.fal_upload(FakeInternet().client(), b"abc").startswith("data:image/png;base64,"))

    def test_error_text_prefers_the_providers_own_message(self):
        response = httpx.Response(401, json={"error": {"message": "Incorrect API key"}})
        self.assertEqual(providers._error_text(response, "x"), "Incorrect API key")
        self.assertEqual(providers.gemini_aspect_ratio(1000, 1000), "1:1")
        self.assertEqual([providers.gemini_aspect_ratio(*s) for s in ((2000, 1000), (1600, 1000), (1300, 1000), (1100, 1000), (1000, 2000), (1000, 1500), (1000, 1300), (1000, 1100))],
                         ["21:9", "16:9", "4:3", "3:2", "9:16", "2:3", "3:4", "4:5"])


class ParseTests(unittest.TestCase):
    def test_vari_input_is_validated(self):
        spec = core.parse_input({"generation_type": "vari", "image_base64": "x", "vari_engine": "z-image", "vari_distance": "looser",
                                 "vari_tuning": {"z_image_creativity": 0.6}, "num_images": 3})
        self.assertEqual((spec.vari_engine, spec.vari_distance, spec.vari_tuning, spec.model_id), ("z-image", "looser", {"z_image_creativity": 0.6}, "vari_z-image"))
        for bad in ({"vari_engine": "nope"}, {"vari_distance": "far"}, {"vari_tuning": {"evil": 1}}, {"vari_tuning": {"fofr_cfg": "3"}}, {"vari_tuning": {"fofr_cfg": True}}, {"vari_tuning": []}):
            with self.assertRaises(ValueError):
                core.parse_input({"generation_type": "vari", "image_base64": "x", **bad})
        with self.assertRaises(ValueError):
            core.parse_input({"generation_type": "vari"})


class GenerateTests(unittest.TestCase):
    def run_engine(self, engine, net=None, **extra):
        net = net or FakeInternet()
        updates, emitted = [], []
        payload = {"generation_type": "vari", "image_base64": source_base64(), "vari_engine": engine, "vari_distance": "sibling", "num_images": 2, **extra}
        with patch.object(core, "use_demo_mode", return_value=False), patch.object(providers, "new_client", net.client), \
             patch.dict("os.environ", {"FAL_KEY": "f", "REPLICATE_API_TOKEN": "r", "OPENAI_API_KEY": "o", "GEMINI_API_KEY": "g"}):
            result = core.generate(payload, progress_callback=lambda v, m: updates.append((v, m)), image_callback=lambda image, meta: emitted.append(meta))
        return net, result, updates, emitted

    def test_a_fal_engine_end_to_end(self):
        net, result, updates, emitted = self.run_engine("z-image")
        self.assertEqual(len(result["images"]), 2)
        self.assertEqual(len(emitted), 2)
        self.assertEqual(result["meta"]["generation_type"], "vari")
        self.assertEqual((result["meta"]["vari_engine"], result["meta"]["model_name"]), ("z-image", "Vari · Z-Image"))
        submit = next(call for call in net.calls if call[1].startswith("https://queue.fal.run/fal-ai/z-image"))
        self.assertEqual(submit[2]["image_url"], "https://cdn.test/source.png")
        self.assertEqual(submit[2]["num_images"], 2)
        self.assertEqual(updates[-1][0], 1.0)
        self.assertTrue(all(a[0] <= b[0] + 1e-9 for a, b in zip(updates, updates[1:])))

    def test_a_replicate_engine_with_tuning(self):
        net, result, _, _ = self.run_engine("sd-variation", vari_tuning={"sd_variation_steps": 31.6, "sd_variation_guidance": 4})
        create = next(call for call in net.calls if call[1] == "https://api.replicate.com/v1/predictions" and call[0] == "POST")
        self.assertEqual(create[2]["input"]["num_inference_steps"], 32)
        self.assertEqual(create[2]["input"]["guidance_scale"], 4)
        self.assertEqual(len(result["images"]), 2)

    def test_an_openai_engine_analyzes_first_and_then_edits(self):
        net, result, _, _ = self.run_engine("gpt-image-2")
        order = [call[1] for call in net.calls if call[1].startswith("https://api.openai.com")]
        self.assertEqual(order, ["https://api.openai.com/v1/responses", "https://api.openai.com/v1/images/edits"])
        self.assertEqual(len(result["images"]), 1)

    def test_comfy_gets_a_square_reference(self):
        net, _, _, _ = self.run_engine("comfy-unclip")
        uploads = [call for call in net.calls if "storage/upload/initiate" in call[1]]
        self.assertEqual(len(uploads), 2)  # the source and the square reference

    def test_demo_mode_refuses_vari(self):
        with patch.object(core, "use_demo_mode", return_value=True), self.assertRaises(ValueError):
            core.generate({"generation_type": "vari", "image_base64": source_base64()})

    def test_square_reference_is_square_and_keeps_the_picture_in_the_middle(self):
        image = Image.new("RGB", (200, 100), (250, 0, 0))
        reference = run.square_reference(image)
        self.assertEqual(reference.size, (200, 200))
        self.assertEqual(reference.getpixel((100, 100)), (250, 0, 0))


if __name__ == "__main__":
    unittest.main()
