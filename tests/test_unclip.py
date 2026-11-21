import base64
import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
from app_runtime import core, unclip
from test_generation import Generator


class UnclipPipeline:
    """Explicit signature copied from StableUnCLIPImg2ImgPipeline.__call__ in diffusers 0.32.2 (legacy callback API),
    so a keyword the real pipeline lacks fails here instead of on the GPU."""

    def __init__(self):
        self.calls = []
        self.scheduler = SimpleNamespace(set_timesteps=lambda count, device=None: None, timesteps=[])

    def __call__(self, image=None, prompt=None, height=None, width=None, num_inference_steps=20, guidance_scale=10,
                 negative_prompt=None, num_images_per_prompt=1, eta=0.0, generator=None, latents=None, prompt_embeds=None,
                 negative_prompt_embeds=None, output_type='pil', return_dict=True, callback=None, callback_steps=1,
                 cross_attention_kwargs=None, noise_level=0, image_embeds=None, clip_skip=None):
        self.calls.append(dict(image=image, prompt=prompt, height=height, width=width, num_inference_steps=num_inference_steps,
                               guidance_scale=guidance_scale, negative_prompt=negative_prompt, generator=generator,
                               noise_level=noise_level, callback=callback, callback_steps=callback_steps, latents=latents))
        if callback:
            for i in range(num_inference_steps):
                callback(i, None, None)
        return SimpleNamespace(images=[image.copy()])


def png_base64(size=(300, 200)):
    buf = io.BytesIO()
    Image.new('RGB', size, 'red').save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


class ReimagineTests(unittest.TestCase):
    def test_reimagine_is_accepted_without_a_checkpoint_entry_and_needs_an_image(self):
        spec = core.parse_input({'generation_type': 'reimagine', 'image_base64': 'x', 'model_id': 'does-not-exist',
                                 'lora_id': 'whatever', 'noise_level': 120})
        self.assertEqual((spec.generation_type, spec.model_id, spec.lora_id, spec.noise_level),
                         ('reimagine', 'sd21_unclip', 'none', 120))
        with self.assertRaises(ValueError):
            core.parse_input({'generation_type': 'reimagine'})

    def test_noise_level_is_clamped_and_other_types_unchanged(self):
        self.assertEqual(core.parse_input({'generation_type': 'reimagine', 'image_base64': 'x', 'noise_level': 9999}).noise_level, 500)
        self.assertEqual(core.parse_input({'generation_type': 'reimagine', 'image_base64': 'x', 'noise_level': -5}).noise_level, 0)
        with self.assertRaises(ValueError):
            core.parse_input({'generation_type': 'nonsense', 'image_base64': 'x'})
        with self.assertRaises(ValueError):  # SDXL checkpoint rules still apply to img2img
            core.parse_input({'image_base64': 'x', 'model_id': 'does-not-exist'})

    def test_output_size_keeps_aspect_ratio_in_multiples_of_eight(self):
        self.assertEqual(unclip.output_size(1000, 500), (768, 384))
        self.assertEqual(unclip.output_size(500, 1000), (384, 768))
        width, height = unclip.output_size(1234, 987)
        self.assertEqual((width % 8, height % 8, max(width, height)), (0, 0, 768))

    def test_generate_runs_the_unclip_pipeline_once_per_variation(self):
        pipe = UnclipPipeline()
        updates, emitted = [], []
        payload = {'generation_type': 'reimagine', 'image_base64': png_base64(), 'num_images': 3, 'seed': 10,
                   'steps': 4, 'cfg': 9, 'noise_level': 200}
        with patch.object(core, 'use_demo_mode', return_value=False), \
             patch.object(core, 'get_torch', return_value=SimpleNamespace(Generator=Generator)), \
             patch.object(unclip, 'ensure_unclip_pipeline', return_value=pipe), \
             patch.object(unclip, 'prepare_init_latents', return_value=(None, 0)), \
             patch.object(core, 'ensure_pipeline') as sdxl:
            result = core.generate(payload, progress_callback=lambda v, m: updates.append((v, m)),
                                   image_callback=lambda image, meta: emitted.append(meta))
        sdxl.assert_not_called()
        self.assertEqual(len(pipe.calls), 3)
        self.assertEqual([call['generator'].seed for call in pipe.calls], [10, 11, 12])
        for call in pipe.calls:
            self.assertEqual((call['noise_level'], call['guidance_scale'], call['num_inference_steps']), (200, 9, 4))
            self.assertEqual((call['width'], call['height']), (768, 512))
            self.assertIsNone(call['prompt'])
        self.assertEqual(len(result['images']), 3)
        self.assertEqual(len(emitted), 3)
        self.assertEqual(result['meta']['generation_type'], 'reimagine')
        self.assertEqual(result['meta']['model_id'], 'sd21_unclip')
        self.assertEqual(result['meta']['noise_level'], 200)
        self.assertEqual(updates[-1][0], 1.0)
        self.assertTrue(all(a[0] <= b[0] + 1e-9 for a, b in zip(updates, updates[1:])))

    def test_source_latents_keep_the_composition_and_shorten_the_schedule(self):
        pipe = UnclipPipeline()
        payload = {'generation_type': 'reimagine', 'image_base64': png_base64((200, 300)), 'num_images': 1, 'steps': 20, 'denoise': .6}
        with patch.object(core, 'use_demo_mode', return_value=False), \
             patch.object(core, 'get_torch', return_value=SimpleNamespace(Generator=Generator)), \
             patch.object(unclip, 'ensure_unclip_pipeline', return_value=pipe), \
             patch.object(unclip, 'prepare_init_latents', return_value=('LATENTS', 8)) as prepare:
            result = core.generate(payload)
        self.assertEqual(prepare.call_args.args[2:4], (.6, 20))
        self.assertEqual(pipe.calls[0]['latents'], 'LATENTS')
        self.assertEqual(result['meta']['actual_steps'], 12)
        self.assertEqual(result['meta']['denoise'], .6)

    def test_the_clip_encoder_sees_the_whole_picture_not_a_centre_crop(self):
        tall = Image.new('RGB', (384, 512))
        self.assertEqual(unclip.embedding_image(tall).size, (768, 768))

    def test_start_index_follows_strength(self):
        self.assertEqual([unclip.start_index(20, s) for s in (1.0, .7, .5, .05)], [0, 6, 10, 19])
        self.assertEqual(core.parse_input({'generation_type': 'reimagine', 'image_base64': 'x'}).denoise, .6)
        self.assertEqual(core.parse_input({'generation_type': 'reimagine', 'image_base64': 'x', 'denoise': 1}).denoise, 1.0)

    def test_demo_mode_refuses_reimagine(self):
        with patch.object(core, 'use_demo_mode', return_value=True):
            with self.assertRaises(ValueError):
                core.generate({'generation_type': 'reimagine', 'image_base64': png_base64()})

    def test_missing_weights_give_an_actionable_error(self):
        unclip._PIPELINE.clear()
        with patch.dict('os.environ', {'UNCLIP_DIR': '/nonexistent/unclip'}):
            with self.assertRaisesRegex(RuntimeError, 'download_unclip'):
                unclip.ensure_unclip_pipeline()


if __name__ == '__main__':
    unittest.main()
