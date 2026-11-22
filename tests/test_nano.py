import base64
import io
import json
import unittest
from unittest import mock

import httpx
from PIL import Image

from app_runtime import core
from app_runtime.nano import models, plans, providers, run


def png_data_url(size=(64, 48), color=(200, 90, 40)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


class PlanTests(unittest.TestCase):
    def test_default_prompt_gets_at_most_one_distance_sentence(self):
        base = plans.build_variants_prompt("", "middle")
        self.assertEqual(base, plans.GENERAL_PROMPT)
        self.assertTrue(plans.build_variants_prompt("", "near").endswith(plans.DISTANCE_SUFFIX["near"]))
        self.assertEqual(plans.build_variants_prompt("  my own  ", "middle"), "my own")

    def test_qwen_gets_a_short_edit_instruction_that_differs_per_variant(self):
        prompts = [plans.build_prompt_for_model("venice/qwen-image-2-1-pro-edit", "", "far", i) for i in range(6)]
        self.assertEqual(len(set(prompts[:5])), 5)
        self.assertEqual(prompts[0], prompts[5])  # directives repeat after five
        self.assertTrue(all(item.endswith(plans.EDIT_KEEP_SUFFIX) for item in prompts))
        self.assertEqual(plans.build_prompt_for_model("openai/gpt-image-2.5-sunburst", "", "middle", 3), plans.GENERAL_PROMPT)

    def test_nearest_aspect_ratio_and_rotation(self):
        self.assertEqual(plans.nearest_aspect_ratio(1000, 1000), "1:1")
        self.assertEqual(plans.nearest_aspect_ratio(1920, 1080), "16:9")
        self.assertEqual(plans.nearest_aspect_ratio(0, 10), "Original")
        self.assertEqual(plans.rotate_inputs([1, 2, 3], 4), [2, 3, 1])
        self.assertEqual(plans.rotate_inputs([], 3), [])

    def test_fuse_directive_is_deterministic_and_varies_with_the_seed(self):
        self.assertEqual(plans.build_fuse_directive(7, 3), plans.build_fuse_directive(7, 3))
        self.assertEqual(plans.build_fuse_directive(7, 3)[0], 1)
        self.assertNotEqual(plans.build_fuse_directive(7, 3)[1], plans.build_fuse_directive(8, 3)[1])
        shift, prompt = plans.build_fuse_prompt("venice/qwen-edit-uncensored", "", 0, 3)
        self.assertTrue(prompt.startswith("Edit image 1 so that images 2 and 3 blend"))
        self.assertEqual(plans.build_fuse_prompt("google/gemini-3-pro-image", "mine", 0, 2)[1], "mine")  # custom prompt untouched
        self.assertIn("image 2 blends", plans.build_collage_edit_instruction(2))

    def test_input_checks_follow_the_model_limits(self):
        self.assertIn("vyžaduje", models.input_error(models.BY_ID["qwen-pro"], 0))
        self.assertIn("pouze generování", models.input_error(models.BY_ID["lustify"], 1))
        self.assertIn("nejvýše 1", models.input_error(models.BY_ID["recraft"], 2))
        self.assertIsNone(models.input_error(models.BY_ID["muse"], 10))

    def test_availability_names_the_missing_key_and_never_returns_a_value(self):
        items = {item["id"]: item for item in models.availability({"OPENROUTER_API_KEY": "secret-value"})}
        self.assertTrue(items["gpt"]["available"])
        self.assertEqual(items["qwen-pro"]["missing"], "VENICE_API_KEY")
        self.assertNotIn("secret-value", json.dumps(items))


class ProviderTests(unittest.TestCase):
    def client(self, handler):
        return httpx.Client(transport=httpx.MockTransport(handler))

    def test_openrouter_sends_references_and_decodes_a_data_url(self):
        seen = {}
        def handler(request):
            seen["body"] = json.loads(request.content)
            seen["auth"] = request.headers["authorization"]
            return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(b"IMG").decode()}]})
        with mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": '"k1"\\n'}):
            data = providers.openrouter_image(self.client(handler), "google/gemini-3-pro-image", "p", ["data:image/jpeg;base64,AA"], "16:9", "1K")
        self.assertEqual(data, b"IMG")
        self.assertEqual(seen["auth"], "Bearer k1")  # quotes and a trailing \n are stripped
        self.assertEqual(seen["body"]["input_references"], [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,AA"}}])
        self.assertEqual((seen["body"]["aspect_ratio"], seen["body"]["resolution"]), ("16:9", "1K"))

    def test_error_text_never_contains_the_key_or_image_data(self):
        def handler(request):
            return httpx.Response(402, json={"error": {"message": "no credit data:image/png;base64,AAAA", "metadata": {"provider_name": "OpenAI"}}})
        with mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": "sk-secret"}):
            with self.assertRaises(providers.ProviderError) as caught:
                providers.openrouter_image(self.client(handler), "m", "p", [], None, None)
        self.assertNotIn("sk-secret", str(caught.exception))
        self.assertNotIn("AAAA", str(caught.exception))
        self.assertIn("OpenAI", str(caught.exception))

    def test_venice_qwen_uses_multi_edit_for_several_images_and_returns_binary(self):
        seen = {}
        def handler(request):
            seen["url"], seen["body"] = str(request.url), json.loads(request.content)
            return httpx.Response(200, content=b"PNGDATA", headers={"content-type": "image/png"})
        with mock.patch.dict("os.environ", {"VENICE_API_KEY": "v"}):
            data = providers.venice_image(self.client(handler), "venice/qwen-image-2-1-pro-edit", "p", ["a", "b"], "4:5", "2K")
        self.assertEqual(data, b"PNGDATA")
        self.assertTrue(seen["url"].endswith("/image/multi-edit"))
        self.assertEqual((seen["body"]["modelId"], seen["body"]["aspect_ratio"], seen["body"]["resolution"]), ("qwen-image-2-1-pro-edit", "4:5", "2K"))

    def test_transient_failures_are_retried_but_a_rejection_is_not(self):
        calls = []
        def flaky(request):
            calls.append(1)
            if len(calls) < 3:
                return httpx.Response(503, json={"error": {"message": "busy"}})
            return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(b"OK").decode()}]})
        with mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": "k"}):
            self.assertEqual(providers.generate_image(self.client(flaky), "m", "p", [], None, None, sleep=lambda s: None), b"OK")
            self.assertEqual(len(calls), 3)
            rejected = []
            def refuse(request):
                rejected.append(1)
                return httpx.Response(400, json={"error": {"message": "bad"}})
            with self.assertRaises(providers.ProviderError):
                providers.generate_image(self.client(refuse), "m", "p", [], None, None, sleep=lambda s: None)
            self.assertEqual(len(rejected), 1)

    def test_a_cancelled_job_starts_no_provider_call(self):
        with self.assertRaises(providers.Cancelled):
            providers.generate_image(self.client(lambda r: httpx.Response(200)), "m", "p", [], None, None, cancelled=lambda: True)


class RunTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        def fake(client, model, prompt, images, aspect, resolution, cancelled=None, **kwargs):
            self.calls.append({"model": model, "prompt": prompt, "images": images, "aspect": aspect, "resolution": resolution})
            buffer = io.BytesIO()
            Image.new("RGB", (32, 24), (10, 20, 30)).save(buffer, format="PNG")
            return buffer.getvalue()
        patches = [mock.patch.object(providers, "generate_image", fake), mock.patch.object(providers, "new_client", lambda: mock.Mock())]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def payload(self, **extra):
        return {"generation_type": "vari", "image_base64": png_data_url(), "num_images": 3, "nano_model": "gpt", "nano_distance": "far", **extra}

    def test_vari_makes_one_call_per_variant_and_reports_each_image(self):
        received = []
        result = core.generate(self.payload(), image_callback=lambda image, meta: received.append(meta))
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(len(result["images"]), 3)
        self.assertEqual(len(received), 3)
        self.assertEqual({call["model"] for call in self.calls}, {"openai/gpt-image-2.5-sunburst"})
        self.assertTrue(all(call["prompt"].endswith(plans.DISTANCE_SUFFIX["far"]) and len(call["images"]) == 1 and call["aspect"] is None for call in self.calls))
        self.assertEqual((result["meta"]["generation_type"], result["meta"]["model_name"]), ("vari", "Vari · GPT Image 2.5"))
        self.assertTrue(self.calls[0]["images"][0].startswith("data:image/jpeg;base64,"))

    def test_a_failed_variant_keeps_the_others_and_all_failing_raises(self):
        outcomes = iter([RuntimeError("boom"), None, None])
        original = providers.generate_image
        def flaky(*args, **kwargs):
            failure = next(outcomes)
            if failure:
                raise failure
            return original(*args, **kwargs)
        with mock.patch.object(providers, "generate_image", flaky):
            result = core.generate(self.payload())
        self.assertEqual((len(result["images"]), result["meta"]["failed_variants"]), (2, 1))
        with mock.patch.object(providers, "generate_image", side_effect=providers.ProviderError("nope")):
            with self.assertRaisesRegex(providers.ProviderError, "nope"):
                core.generate(self.payload())

    def test_collage_fuse_sends_all_inputs_rotated_with_the_nearest_aspect(self):
        extra = "a" * 64
        with mock.patch.object(run, "load_extra_sources", lambda ids: [Image.new("RGB", (40, 40), (1, 2, 3)), Image.new("RGB", (40, 40), (4, 5, 6))]):
            result = core.generate({"generation_type": "collage", "image_base64": png_data_url((160, 90)), "num_images": 1, "nano_model": "nano-pro",
                                    "collage_fuse": True, "extra_source_ids": [extra, "b" * 64], "seed": 7})
        self.assertEqual(len(self.calls), 1)
        self.assertEqual((len(self.calls[0]["images"]), self.calls[0]["aspect"], self.calls[0]["resolution"]), (3, "16:9", "1K"))
        self.assertEqual(result["meta"]["source_count"], 3)
        self.assertIn("This variant:", self.calls[0]["prompt"])

    def test_collage_single_input_makes_variants_with_different_techniques(self):
        core.generate({"generation_type": "collage", "image_base64": png_data_url(), "num_images": 3, "nano_model": "gemini", "collage_fuse": False, "seed": 0})
        self.assertEqual(len({call["prompt"] for call in self.calls}), 3)

    def test_model_limits_are_enforced_before_any_call(self):
        with self.assertRaisesRegex(ValueError, "vyžaduje vstupní obrázek|nejvýše"):
            core.generate({"generation_type": "collage", "image_base64": png_data_url(), "num_images": 1, "nano_model": "recraft", "collage_fuse": True,
                           "extra_source_ids": ["a" * 64]}, )
        self.assertEqual(self.calls, [])

    def test_parse_rejects_bad_models_distances_and_source_ids(self):
        base = {"generation_type": "vari", "image_base64": png_data_url(), "num_images": 1}
        for bad in ({"nano_model": "nope"}, {"nano_distance": "sideways"}, {"extra_source_ids": ["a" * 64]}):
            with self.assertRaises(ValueError):
                core.parse_input({**base, **bad})
        with self.assertRaises(ValueError):
            core.parse_input({**base, "generation_type": "collage", "extra_source_ids": ["../etc/passwd"]})

    def test_prepare_input_stays_under_its_byte_budget(self):
        noisy = Image.effect_noise((2400, 1800), 90).convert("RGB")
        url = run.prepare_input(noisy, 400_000)
        self.assertLessEqual(len(base64.b64decode(url.split(",")[1])), 500_000)
        self.assertLessEqual(max(Image.open(io.BytesIO(base64.b64decode(url.split(",")[1]))).size), run.MAX_DIMENSION)


if __name__ == "__main__":
    unittest.main()
