import unittest
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from app_runtime import core
from app_runtime.repaint import repaint, DEFAULT_REPAINT_DENOISE
from test_generation import Generator, Pipeline


class RepaintTests(unittest.TestCase):
    def test_artist_tokens_and_full_steps_without_leaking_source_prompt(self):
        for model, token in [('tuymans_modal_2400', 'mvhpaint'), ('mulen_mara', 'mulpaint'),
                             ('hofmann_sdxl', ''), ('tuymans_sdxl', 'tuypaint')]:
            with self.subTest(model=model):
                spec = core.parse_input({'generation_type': 'atelier', 'atelier_mode': 'photo',
                    'model_id': model, 'steps': 28, 'cfg': .5, 'denoise': .52,
                    'prompt': 'a documentary photograph'})
                pipe = Pipeline()
                with patch.object(core, 'ensure_pipeline', return_value=pipe) as ensure, \
                     patch.object(core, 'ensure_lora'), \
                     patch.object(core, 'make_scheduler', return_value=SimpleNamespace(config={})), \
                     patch.object(core, 'get_torch', return_value=SimpleNamespace(Generator=Generator)):
                    source = Image.new('RGB', (512, 512))
                    _, meta = repaint(source, spec, 42, None)
                ensure.assert_called_once_with(model, resident=2)
                self.assertEqual(pipe.calls[0]['prompt'], token)
                self.assertIs(pipe.calls[0]['image'], source)
                self.assertEqual(meta['actual_steps'], 28)
                self.assertEqual(meta['requested_cfg'], .5)
                self.assertEqual(meta['cfg'], 3.0 if token else .5)
                self.assertEqual(pipe.calls[0]['generator'].seed, 42)

    def test_strong_default_is_scoped_to_atelier_repainting_and_explicit_choice_survives(self):
        for mode in ['photo', 'archive']:
            payload = {'generation_type': 'atelier', 'atelier_mode': mode, 'model_id': 'hofmann_sdxl'}
            self.assertEqual(core.parse_input(payload).denoise, DEFAULT_REPAINT_DENOISE)
            self.assertEqual(core.parse_input({**payload, 'denoise': .2}).denoise, .2)
        self.assertEqual(core.parse_input({'image_base64': 'x', 'model_id': 'hofmann_sdxl'}).denoise, .35)
