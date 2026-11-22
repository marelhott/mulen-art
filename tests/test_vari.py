import json
import unittest
from pathlib import Path

from app_runtime.vari import catalog

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "vari_payloads.json").read_text())
CAMEL_TO_SNAKE = {
    "comfyNoise": "comfy_noise", "comfyStrength": "comfy_strength", "ipAdapterScale": "ip_adapter_scale",
    "ipAdapterSteps": "ip_adapter_steps", "chigoScale": "chigo_scale", "chigoSteps": "chigo_steps",
    "sdxlGuidance": "sdxl_guidance", "sdxlStrength": "sdxl_strength", "sdxlSteps": "sdxl_steps",
    "stableGuidance": "stable_guidance", "stableStrength": "stable_strength", "stableSteps": "stable_steps",
    "sdVariationGuidance": "sd_variation_guidance", "sdVariationSteps": "sd_variation_steps",
    "fofrCfg": "fofr_cfg", "fofrSteps": "fofr_steps", "fofrIpWeight": "fofr_ip_weight", "zImageCreativity": "z_image_creativity",
}
TUNING = [{}, {k: v for k, v in zip(CAMEL_TO_SNAKE, [0.3, 0.5, 0.7, 33.6, 0.6, 51.4, 4.1, 0.77, 29.5, 4.4, 0.55, 21.2, 3.9, 17.7, 3.3, 37.5, 0.7, 0.42])},
          {"comfyNoise": 0.9, "comfyStrength": 0.1}]


def normalized(value):
    return json.loads(json.dumps(catalog.clean(value)))


class ParityWithTheTypeScriptOriginal(unittest.TestCase):
    def test_every_provider_payload_matches_the_original_builders(self):
        checked = 0
        for entry in FIXTURE["payloads"]:
            tuning = {CAMEL_TO_SNAKE[k]: v for k, v in TUNING[entry["tuningIndex"]].items()}
            ctx = {"source_url": "https://example.test/source.png", "comfy_reference_url": "https://example.test/ref.png",
                   "image_info": FIXTURE["images"][entry["imageIndex"]], "distance": entry["distance"], "count": entry["count"], **tuning}
            actual = normalized(catalog.build_payload(entry["engine"], ctx, rng=lambda: 0.5))
            self.assertEqual(actual, entry["payload"], f"{entry['engine']} / {entry['distance']} / count {entry['count']} / image {entry['imageIndex']} / tuning {entry['tuningIndex']}")
            checked += 1
        self.assertEqual(checked, len(FIXTURE["payloads"]))
        self.assertGreater(checked, 2000)

    def test_workflow_json_strings_are_byte_identical(self):
        # workflow_json is compared as a string by the tests above only after parsing; check the raw text once more
        for entry in FIXTURE["payloads"]:
            if entry["engine"] in ("comfy-unclip", "fofr-any-comfyui-workflow") and entry["tuningIndex"] == 1:
                tuning = {CAMEL_TO_SNAKE[k]: v for k, v in TUNING[1].items()}
                ctx = {"source_url": "https://example.test/source.png", "comfy_reference_url": "https://example.test/ref.png",
                       "image_info": FIXTURE["images"][entry["imageIndex"]], "distance": entry["distance"], "count": entry["count"], **tuning}
                payload = catalog.build_payload(entry["engine"], ctx, rng=lambda: 0.5)
                self.assertEqual(catalog.js_json(json.loads(payload["input"]["workflow_json"])), entry["payload"]["input"]["workflow_json"])
                self.assertEqual(payload["input"]["workflow_json"], entry["payload"]["input"]["workflow_json"])

    def test_prompts_and_helpers_match(self):
        for distance, expected in FIXTURE["prompts"].items():
            prompt, negative = catalog.build_prompt(distance)
            self.assertEqual([prompt, negative], [expected["base"]["prompt"], expected["base"]["negativePrompt"]])
            self.assertEqual(catalog.build_gpt_image2_prompt(distance, FIXTURE["analysis"]), expected["gpt"])
            self.assertEqual(catalog.build_vision_remix_prompt(distance, FIXTURE["analysis"]), expected["remix"])
        helpers = FIXTURE["helpers"]
        for index, image in enumerate(FIXTURE["images"]):
            self.assertEqual(catalog.image_info(image["width"], image["height"]), image)
            self.assertEqual(catalog.fal_image_size(image), helpers["falImageSize"][index])
            self.assertEqual([catalog.snapped_dimensions(image, side) for side in (1024, 1280, 1344)], helpers["snapped"][index])

    def test_js_round_goes_half_up(self):
        self.assertEqual([catalog.js_round(v) for v in (0.5, 1.5, 2.5, 29.5, 37.5, 33.6, -0.4)], [1, 2, 3, 30, 38, 34, 0])


class AvailabilityTests(unittest.TestCase):
    def test_an_engine_is_available_only_when_all_its_keys_exist(self):
        result = catalog.availability({"FAL_KEY": "x", "REPLICATE_API_TOKEN": "y", "GEMINI_API_KEY": "z"})
        self.assertTrue(result["z-image"]["available"] and result["sd-variation"]["available"] and result["comfy-unclip"]["available"])
        self.assertFalse(result["gpt-image-2"]["available"])
        self.assertEqual(result["gemini-3-pro"]["missing"], ["OPENAI_API_KEY"])
        self.assertEqual(set(catalog.availability({})) , set(catalog.ENGINES))
        retired = catalog.availability({"FAL_KEY": "x"})["stable"]
        self.assertFalse(retired["available"])  # the fal endpoint is gone, whatever keys exist
        self.assertIn("endpoint", retired["note"])
        self.assertTrue(all(not item["available"] for item in catalog.availability({}).values()))


if __name__ == "__main__":
    unittest.main()
