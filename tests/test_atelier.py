import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PIL import Image
from app_runtime import core, server
from app_runtime.atelier import subject_for
from test_generation import Generator, Pipeline


class TextPipeline:
    def __init__(self):
        self.calls = []
    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        self.num_timesteps = kwargs['num_inference_steps']
        for index in range(self.num_timesteps):
            kwargs['callback_on_step_end'](self, index, None, {})
        return SimpleNamespace(images=[Image.new('RGB', (kwargs['width'], kwargs['height']), '#b5b2a1')])


class AtelierTests(unittest.TestCase):
    def setUp(self):
        self.payload = {'generation_type': 'atelier', 'model_id': 'tuymans_modal_2400',
            'atelier_mode': 'noise', 'seed': 231020, 'cfg': .5, 'steps': 28,
            'width': 512, 'height': 512, 'scale': 2}

    def test_atelier_requires_no_input_and_preserves_half_cfg(self):
        parsed = core.parse_input(self.payload)
        self.assertEqual(parsed.image_base64, '')
        self.assertEqual(parsed.cfg, .5)
        for invalid in ({'generation_type':'img2img'}, {'model_id':'sdxl_base'},
                        {'atelier_mode':'unknown'}, {'atelier_theme':'unknown'},
                        {'width':513}, {'width':2048}, {'height':True}, {'render_mode':'detail'}):
            with self.assertRaises(ValueError):
                core.parse_input({**self.payload, **invalid})

    def run_study(self, **overrides):
        text = TextPipeline(); painting = Pipeline(); base = Pipeline()
        ensure = Mock(side_effect=lambda model: base if model == 'sdxl_base' else painting)
        updates, emitted = [], []
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(server, 'OUTPUTS_DIR', Path(tmp)), \
             patch.object(core, 'use_demo_mode', return_value=False), \
             patch.object(core, 'get_torch', return_value=SimpleNamespace(Generator=Generator)), \
             patch.object(core, 'get_diffusers', return_value={'text_pipeline': SimpleNamespace(from_pipe=lambda pipe: text)}), \
             patch.object(core, 'ensure_pipeline', ensure), \
             patch.object(core, 'ensure_lora'), \
             patch.object(core, 'make_scheduler', return_value=SimpleNamespace(config={})):
            result = core.generate({**self.payload, **overrides}, lambda value,msg: updates.append(value),
                lambda image,meta: emitted.append(meta))
            sources = list(Path(tmp).glob('source_atelier_*.png'))
        return text, painting, ensure, result, updates, emitted, sources

    def test_hofmann_supports_autonomous_subjects_without_tuymans_trigger(self):
        text, painting, ensure, result, updates, emitted, sources = self.run_study(model_id="hofmann_sdxl", atelier_mode="subject")
        self.assertEqual(ensure.call_args.args[0], "hofmann_sdxl")
        self.assertEqual(emitted[0]["model_id"], "hofmann_sdxl")
        self.assertEqual(text.calls[0]["prompt"], emitted[0]["subject_text"])
        self.assertNotIn("mvhpaint", text.calls[0]["prompt"])

    def test_noise_is_true_text_to_image_with_empty_prompt_and_lossless_metadata(self):
        text, painting, ensure, result, updates, emitted, sources = self.run_study(num_images=2)
        self.assertEqual(len(painting.calls), 0)
        self.assertEqual([call['generator'].seed for call in text.calls], [231020,231021])
        self.assertTrue(all(call['prompt'] == '' and 'image' not in call and 'strength' not in call for call in text.calls))
        self.assertEqual(len(result['images']), 2)
        self.assertTrue(all(meta['actual_steps']==28 and meta['subject_origin']=='none' for meta in emitted))
        self.assertEqual(updates, sorted(updates))
        im = Image.open(io.BytesIO(base64.b64decode(result['images'][0]['image_base64'])))
        self.assertEqual(im.size, (1024,1024))
        self.assertEqual(json.loads(im.info['sdxl_studio'])['generation_type'], 'atelier')
        self.assertEqual(sources, [])

    def test_subject_is_repeatable_and_uses_learned_caption_prefix(self):
        text, _, _, _, _, emitted, _ = self.run_study(atelier_mode='subject', atelier_theme='face')
        self.assertTrue(text.calls[0]['prompt'].startswith('mvhpaint, '))
        self.assertEqual(emitted[0]['subject_title'], subject_for(231020, 'face')[1])
        self.assertEqual(emitted[0]['subject_origin'], 'curated-starter-v1')

    def test_atelier_allows_requested_high_denoise_without_changing_defaults(self):
        from app_runtime.core import parse_input
        for mode in ("photo", "archive"):
            spec = parse_input({"generation_type":"atelier", "atelier_mode":mode, "model_id":"tuymans_modal_2400", "denoise":.99})
            self.assertEqual(spec.denoise, .99)
            capped = parse_input({"generation_type":"atelier", "atelier_mode":mode, "model_id":"tuymans_modal_2400", "denoise":1})
            self.assertEqual(capped.denoise, .99)

    def test_photo_is_separate_base_generation_then_single_paint_pass(self):
        text, painting, ensure, _, updates, emitted, sources = self.run_study(atelier_mode='photo', denoise=.9)
        self.assertEqual([call.args[0] for call in ensure.call_args_list], ['sdxl_base','tuymans_modal_2400'])
        self.assertEqual(len(text.calls),1);self.assertEqual(len(painting.calls),1)
        self.assertTrue(text.calls[0]['prompt'].startswith('An ordinary documentary photograph'))
        self.assertEqual(painting.calls[0]['prompt'],'')
        self.assertEqual(painting.calls[0]['strength'],.9)
        self.assertEqual(len(sources),1)
        self.assertTrue(emitted[0]['source_url'].startswith('/library/source_atelier_'))
        self.assertEqual(updates, sorted(updates))
    def test_structure_mode_uses_edge_map_and_never_passes_the_painting_colours(self):
        from PIL import Image
        from app_runtime import core
        source = Image.new("RGB", (64, 64), (200, 30, 30))
        for x in range(64):
            source.putpixel((x, 32), (0, 0, 0))
        edges = core.structure_map(source)
        self.assertEqual(edges.mode, "L")
        # A flat red field must not survive as colour information in the edge map.
        self.assertLessEqual(len(set(edges.getdata())), 256)
        self.assertEqual(core.parse_input({"generation_type": "atelier", "atelier_mode": "structure",
                                           "model_id": "tuymans_modal_2400", "controlnet_scale": 0.8}).controlnet_scale, 0.8)
        with self.assertRaises(ValueError):
            core.parse_input({"generation_type": "atelier", "atelier_mode": "structure",
                              "model_id": "tuymans_modal_2400", "controlnet_id": "missing"})

    def test_structure_study_sends_only_edges_and_records_provenance(self):
        import hashlib, json, tempfile
        from pathlib import Path
        from unittest.mock import patch
        from PIL import Image
        from app_runtime import archives, atelier, core, server
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = root / "ref.png"
            Image.new("RGB", (96, 64), (10, 120, 200)).save(reference)
            manifest = {"archives": [{"id": "hofmann", "name": "Julius Hofmann", "count": 1, "items": [
                {"id": "hofmann-0001", "filename": "ref.png", "path": "ref.png",
                 "sha256": hashlib.sha256(reference.read_bytes()).hexdigest()}]}]}
            (root / "manifest.json").write_text(json.dumps(manifest))
            spec = core.parse_input({"generation_type": "atelier", "atelier_mode": "structure",
                                     "atelier_archive": "hofmann", "model_id": "tuymans_modal_2400",
                                     "seed": 5, "width": 512, "height": 512, "controlnet_scale": 0.7})
            seen, emitted = [], []
            class FakeGenerator:
                def manual_seed(self, _seed):
                    return self
            class FakeTorch:
                @staticmethod
                def Generator(**_kwargs):
                    return FakeGenerator()
            class FakePipe:
                scheduler = type("S", (), {"config": {}})()
                num_timesteps = 7
                def __call__(self, **kwargs):
                    seen.append(kwargs)
                    return type("R", (), {"images": [kwargs["image"].convert("RGB")]})()
            with patch.object(archives, "archive_root", return_value=root), \
                 patch.object(core, "get_torch", return_value=FakeTorch()), \
                 patch.object(core, "ensure_controlnet_pipeline", return_value=FakePipe()), \
                 patch.object(core, "ensure_lora"), \
                 patch.object(core, "make_scheduler", return_value=None), \
                 patch.object(server, "OUTPUTS_DIR", root):
                result = atelier.generate_study(spec, None, lambda image, meta: emitted.append(meta))
            call = seen[0]
            self.assertEqual(call["prompt"], "")
            self.assertIn("control_image", call)
            self.assertEqual(call["control_image"].mode, "L")
            self.assertEqual(call["controlnet_conditioning_scale"], 0.7)
            self.assertEqual(emitted[0]["atelier_mode"], "structure")
            self.assertEqual(emitted[0]["controlnet_scale"], 0.7)
            self.assertTrue(emitted[0]["structure_url"].startswith("/library/source_structure_"))
            self.assertTrue(emitted[0]["source_url"].startswith("/library/source_structure_"))
            self.assertEqual(len(result["images"]), 1)

    def test_structure_mode_is_offered_in_ui_and_documented(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        studio = (root / "frontend" / "src" / "StudioView.jsx").read_text()
        app = (root / "frontend" / "src" / "App.jsx").read_text()
        readme = (root / "README.md").read_text()
        self.assertIn('id: "structure"', studio)
        self.assertIn("SÍLA OBYSU", studio)
        self.assertIn("Archiv → struktura", studio)
        self.assertIn("controlnet_scale", app)
        self.assertIn("Archiv → struktura", readme)

    def test_controlnet_is_configurable_and_downloaded_on_modal_only(self):
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        config = json.loads((root / "config" / "models.json").read_text())
        entry = next(i for i in config["controlnets"] if i["id"] == "canny_sdxl")
        self.assertEqual(entry["path"], "/models/controlnet/canny_sdxl")
        self.assertRegex(entry["revision"], r"^[0-9a-f]{40}$")
        script = (root / "scripts" / "download_controlnet.py").read_text()
        self.assertIn("snapshot_download", script)
        self.assertIn("allow_patterns", script)
        self.assertNotIn("local_dir_use_symlinks", script)
        # Weights are fetched inside Modal, never onto the Mac.
        self.assertIn("def download", script)
        self.assertIn("volume.commit()", script)

