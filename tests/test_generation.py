import base64
import io
import json
import math
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image
from app_runtime import core


class Generator:
    def __init__(self, device):
        self.device = device

    def manual_seed(self, seed):
        self.seed = seed
        return self


class Pipeline:
    def __init__(self):
        self.scheduler = SimpleNamespace(config={})
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        self.num_timesteps = int(kwargs['num_inference_steps'] * kwargs['strength'])
        callback = kwargs['callback_on_step_end']
        if callback:
            for i in range(self.num_timesteps):
                callback(self, i, None, {})
        return SimpleNamespace(images=[kwargs['image'].copy()])


class GenerationTests(unittest.TestCase):
    def setUp(self):
        buf = io.BytesIO()
        Image.new('RGB', (128, 96), 'red').save(buf, format='PNG')
        self.payload = {'image_base64': base64.b64encode(buf.getvalue()).decode(),
                        'model_id': 'tuymans_sdxl', 'seed': 42, 'steps': 25,
                        'denoise': .45, 'scale': 2, 'render_mode': 'faithful'}

    def run_generation(self, **overrides):
        pipe = Pipeline()
        updates, emitted = [], []
        with patch.object(core, 'use_demo_mode', return_value=False), \
             patch.object(core, 'get_torch', return_value=SimpleNamespace(Generator=Generator)), \
             patch.object(core, 'ensure_pipeline', return_value=pipe), \
             patch.object(core, 'make_scheduler', return_value=SimpleNamespace(config={})), \
             patch.object(core, 'ensure_lora'):
            result = core.generate({**self.payload, **overrides},
                progress_callback=lambda value, message: updates.append((value, message)),
                image_callback=lambda image, meta: emitted.append(meta))
        return pipe, result, updates, emitted

    def test_actual_step_budget_is_preserved_across_strengths(self):
        for steps in (1, 15, 25, 80, 150):
            for strength in (.05, .1, .25, .35, .45, .6, .99, 1):
                total, effective = core.inference_schedule(steps, strength, True)
                self.assertEqual(math.floor(total * effective), steps)
                self.assertLessEqual(abs(effective - strength), 1 / total + 1e-6)

    def test_detail_reencodes_upscaled_image_and_preserves_per_image_seed(self):
        pipe, result, updates, emitted = self.run_generation(render_mode='detail', num_images=2)
        self.assertEqual(len(pipe.calls), 4)
        self.assertEqual([call['image'].size for call in pipe.calls], [(128, 96), (256, 192)] * 2)
        self.assertEqual([meta['seed'] for meta in emitted], [42, 43])
        self.assertTrue(all(meta['actual_steps'] == 25 and meta['actual_detail_steps'] == 15 for meta in emitted))
        self.assertIsNone(pipe.calls[0]['negative_prompt'])
        self.assertEqual([u[0] for u in updates], sorted(u[0] for u in updates))
        im = Image.open(io.BytesIO(base64.b64decode(result['images'][0]['image_base64'])))
        self.assertEqual(json.loads(im.info['sdxl_studio'])['seed'], 42)
        self.assertIn('Seed: 42', im.info['parameters'])
        self.assertEqual(result['images'][1]['generation_meta']['seed'], 43)

    def test_conditioning_is_independent_of_render_mode(self):
        for mode in ('quick', 'faithful', 'detail'):
            for conditioning, negative, expected in (
                ('style', '', None), ('encoded', '', ''), ('style', 'blur', 'blur')):
                pipe, result, _, _ = self.run_generation(render_mode=mode,
                    conditioning_mode=conditioning, negative_prompt=negative)
                self.assertTrue(all(call['negative_prompt'] == expected for call in pipe.calls))
                self.assertEqual(result['meta']['conditioning_mode'], conditioning)

    def test_quick_always_has_at_least_one_denoising_step(self):
        for strength in (.05, .1, .35, .45, 1):
            total, effective = core.inference_schedule(1, strength, False)
            self.assertGreaterEqual(math.floor(total * effective), 1)

    def test_quick_keeps_fractional_steps_without_second_inference(self):
        pipe, result, _, _ = self.run_generation(render_mode='quick')
        self.assertEqual(len(pipe.calls), 1)
        self.assertEqual(result['meta']['actual_steps'], 11)
        self.assertEqual(result['meta']['upscaler'], 'lanczos')
        self.assertIsNone(pipe.calls[0]['negative_prompt'])

    def test_original_enlargement_only_resizes_completed_image(self):
        small_pipe, small, _, _ = self.run_generation(render_mode='quick', scale=1, sampler='dpmpp_2m_sde')
        large_pipe, large, _, _ = self.run_generation(render_mode='quick', scale=2, sampler='dpmpp_2m_sde')
        self.assertEqual(len(large_pipe.calls), 1)
        for key in ('strength', 'num_inference_steps', 'prompt', 'negative_prompt', 'guidance_scale'):
            self.assertEqual(small_pipe.calls[0][key], large_pipe.calls[0][key])
        self.assertEqual(small_pipe.calls[0]['image'].tobytes(), large_pipe.calls[0]['image'].tobytes())
        decode = lambda result: Image.open(io.BytesIO(base64.b64decode(result['images'][0]['image_base64'])))
        expected = decode(small).resize((256, 192), Image.Resampling.LANCZOS)
        self.assertEqual(expected.tobytes(), decode(large).tobytes())

    def test_ode_and_sde_are_distinct_and_order_is_explicit(self):
        scheduler = Mock()
        with patch.object(core, 'get_diffusers', return_value={'scheduler': scheduler}):
            core.make_scheduler({}, 'dpmpp_2m', 'karras')
            self.assertEqual(scheduler.from_config.call_args.kwargs,
                {'algorithm_type': 'dpmsolver++', 'solver_order': 2, 'use_karras_sigmas': True})
            core.make_scheduler({}, 'dpmpp_2m_sde', 'normal')
            self.assertEqual(scheduler.from_config.call_args.kwargs['algorithm_type'], 'sde-dpmsolver++')
            self.assertFalse(scheduler.from_config.call_args.kwargs['use_karras_sigmas'])

    def test_invalid_settings_rejected_and_unsupported_karras_normalized(self):
        for override in ({'seed': -2}, {'seed': 1.2}, {'seed': 2**32}, {'seed': True},
                         {'conditioning_mode': 'missing'}, {'render_mode': 'missing'}, {'render_mode': 'detail', 'scale': 4}):
            with self.assertRaises(ValueError):
                core.parse_input({**self.payload, **override})
        self.assertEqual(core.parse_input({**self.payload, 'sampler': 'euler_a'}).schedule, 'normal')

    def test_detail_size_aligns_to_latent_grid(self):
        self.assertEqual(core.detail_dimensions((1016, 768), 1.35), (1368, 1040))
        self.assertEqual(core.normalize_dimensions(Image.new('RGB', (2200, 1800)), 1024).size, (1024, 832))
