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
        ensure = Mock(side_effect=lambda model, resident=1: base if model == 'sdxl_base' else painting)
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
        text, painting, ensure, result, updates, emitted, sources = self.run_study(model_id="hofmann_sdxl", atelier_mode="subject", atelier_color_level=0)
        self.assertEqual(ensure.call_args.args[0], "hofmann_sdxl")
        self.assertEqual(emitted[0]["model_id"], "hofmann_sdxl")
        self.assertEqual(text.calls[0]["prompt"], emitted[0]["subject_text"])
        self.assertNotIn("mvhpaint", text.calls[0]["prompt"])

    def test_noise_is_true_text_to_image_with_empty_prompt_and_lossless_metadata(self):
        text, painting, ensure, result, updates, emitted, sources = self.run_study(num_images=2, atelier_color_level=0)
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
        text, _, _, _, _, emitted, _ = self.run_study(atelier_mode='subject', atelier_theme='face', atelier_color_level=0)
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


class ColourHintTests(AtelierTests):
    def test_colour_hint_replaces_the_empty_prompt_and_lifts_cfg_only_where_text_acts(self):
        text, _, _, _, _, emitted, _ = self.run_study(num_images=3, atelier_color_level=1)
        for call, meta in zip(text.calls, emitted):
            self.assertTrue(call['prompt'].startswith('mvhpaint, '))
            self.assertEqual(call['prompt'], 'mvhpaint, ' + meta['color_hint'])
            self.assertEqual(call['guidance_scale'], 3.0)
            self.assertEqual((meta['cfg'], meta['requested_cfg']), (3.0, .5))
        self.assertEqual(len({meta['color_hint'] for meta in emitted}) > 1, True)  # different studies, different palettes
        _, _, _, _, _, emitted, _ = self.run_study(cfg=5.0, atelier_color_level=1)
        self.assertEqual(emitted[0]['cfg'], 5.0)  # a higher requested CFG is never lowered
        text, _, _, _, _, emitted, _ = self.run_study()  # the default is the vivid level: stronger text pull
        self.assertEqual((text.calls[0]['guidance_scale'], emitted[0]['color_level']), (4.5, 2))
        self.assertNotRegex(emitted[0]['color_hint'], r'\b(pale|muted)\b')

    def test_subject_keeps_its_subject_and_adds_the_colour_hint(self):
        text, _, _, _, _, emitted, _ = self.run_study(atelier_mode='subject', atelier_theme='face')
        self.assertEqual(text.calls[0]['prompt'], 'mvhpaint, ' + emitted[0]['color_hint'] + ', ' + emitted[0]['subject_text'])

    def test_photo_and_opt_out_are_untouched(self):
        text, painting, _, _, _, emitted, _ = self.run_study(atelier_mode='photo', denoise=.9)
        self.assertEqual(painting.calls[0]['prompt'], '')
        self.assertEqual(emitted[0]['cfg'], .5)
        self.assertIsNone(emitted[0]['color_hint'])
        text, _, _, _, _, emitted, _ = self.run_study(atelier_color_level=0)
        self.assertEqual((text.calls[0]['prompt'], text.calls[0]['guidance_scale']), ('', .5))

    def test_manual_colour_text_overrides_the_archive_choice(self):
        text, _, _, _, _, emitted, _ = self.run_study(atelier_color_text='deep blue and ochre')
        self.assertEqual(text.calls[0]['prompt'], 'mvhpaint, deep blue and ochre')
        self.assertEqual(emitted[0]['color_hint'], 'deep blue and ochre')

    def test_palette_phrase_follows_the_dominant_colours_of_a_painting(self):
        from app_runtime import atelier
        def phrase(*blocks):
            image = Image.new('RGB', (48, 48))
            width = 48 // len(blocks)
            for index, colour in enumerate(blocks):
                image.paste(Image.new('RGB', (width + 1, 48), colour), (index * width, 0))
            return atelier.color_phrase_from_image(image)
        self.assertEqual(phrase('#2a60c8'), 'blue')
        self.assertEqual(phrase('#bcd0e8', '#8a8a86'), 'pale blue and grey')
        self.assertEqual(phrase('#c83020', '#101010'), 'red and black')
        self.assertIn('pink', phrase('#f0b0c0', '#f0f0f0'))
        self.assertEqual(atelier.color_name(0.58, 0.8, 0.8), 'blue')
        self.assertEqual(atelier.color_name(0.3, 0.8, 0.8), 'green')
        self.assertEqual(atelier.color_name(0.0, 0.0, 0.9), 'white')

    def test_hint_comes_from_a_real_archive_painting_when_the_model_has_one(self):
        from app_runtime import atelier
        with tempfile.TemporaryDirectory() as tmp:
            Image.new('RGB', (64, 64), '#2a60c8').save(Path(tmp) / 'one.png')
            import hashlib
            digest = hashlib.sha256((Path(tmp) / 'one.png').read_bytes()).hexdigest()
            manifest = {'archives': [{'id': 'tuymans', 'name': 'T', 'count': 1, 'items': [{'path': 'one.png', 'sha256': digest, 'filename': 'one.png'}]}]}
            with patch.dict('os.environ', {'ARCHIVE_ROOT': tmp}):
                (Path(tmp) / 'manifest.json').write_text(json.dumps(manifest))
                phrase, source = atelier.color_hint('tuymans_modal_2400', 7)
                self.assertEqual((phrase, source), ('blue', 'one.png'))
                self.assertEqual(atelier.color_archive_for('mix:tuymans_sdxl=50,hofmann_sdxl=50'), 'tuymans')
                self.assertEqual(atelier.color_archive_for('mulen_mara'), None)


class MulenMaraModelTests(unittest.TestCase):
    def test_mulen_mara_is_an_atelier_model_with_its_own_trigger(self):
        from app_runtime import atelier
        self.assertTrue(atelier.is_atelier_model("mulen_mara"))
        self.assertEqual(atelier.painting_prompt("mulen_mara", "a pale deer"), "mulpaint, a pale deer")
        self.assertEqual(atelier.painting_prompt("mulen_mara", ""), "mulpaint, ")
        self.assertEqual(atelier.painting_prompt("hofmann_sdxl", "a pale deer"), "a pale deer")
        self.assertEqual(atelier.painting_prompt("tuymans_modal_2400", "x"), "mvhpaint, x")
