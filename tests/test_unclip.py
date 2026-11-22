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


class MetamorphPipeline:
    """Explicit signature of StableDiffusionXLImg2ImgPipeline.__call__ in diffusers 0.32.2."""

    def __init__(self):
        self.calls, self.scales = [], []

    def set_ip_adapter_scale(self, scale):
        self.scales.append(scale)

    def __call__(self, prompt=None, prompt_2=None, image=None, strength=0.3, num_inference_steps=50, timesteps=None, sigmas=None,
                 denoising_start=None, denoising_end=None, guidance_scale=5.0, negative_prompt=None, negative_prompt_2=None,
                 num_images_per_prompt=1, eta=0.0, generator=None, latents=None, prompt_embeds=None, negative_prompt_embeds=None,
                 pooled_prompt_embeds=None, negative_pooled_prompt_embeds=None, ip_adapter_image=None, ip_adapter_image_embeds=None,
                 output_type='pil', return_dict=True, cross_attention_kwargs=None, guidance_rescale=0.0, original_size=None,
                 crops_coords_top_left=(0, 0), target_size=None, negative_original_size=None, negative_crops_coords_top_left=(0, 0),
                 negative_target_size=None, aesthetic_score=6.0, negative_aesthetic_score=2.5, clip_skip=None,
                 callback_on_step_end=None, callback_on_step_end_tensor_inputs=['latents']):
        self.calls.append(dict(image=image, strength=strength, ip_adapter_image=ip_adapter_image, guidance_scale=guidance_scale,
                               num_inference_steps=num_inference_steps, generator=generator, prompt=prompt))
        self.num_timesteps = int(num_inference_steps * strength)
        if callback_on_step_end:
            for i in range(self.num_timesteps):
                callback_on_step_end(self, i, None, {})
        return SimpleNamespace(images=[image.copy()])


class MetamorphTests(unittest.TestCase):
    def test_fields_are_validated_and_default_to_unclip(self):
        spec = core.parse_input({'generation_type': 'reimagine', 'image_base64': 'x'})
        self.assertEqual((spec.reimagine_mode, spec.ip_variant, spec.long_side), ('unclip', 'plus', 768))
        spec = core.parse_input({'generation_type': 'reimagine', 'image_base64': 'x', 'reimagine_mode': 'metamorph',
                                 'ip_variant': 'plain', 'ip_scale': 9, 'long_side': 1024})
        self.assertEqual((spec.reimagine_mode, spec.ip_variant, spec.ip_scale, spec.long_side), ('metamorph', 'plain', 1.5, 1024))
        for bad in ({'reimagine_mode': 'x'}, {'ip_variant': 'face'}, {'long_side': 900}):
            with self.assertRaises(ValueError):
                core.parse_input({'generation_type': 'reimagine', 'image_base64': 'x', **bad})

    def test_size_is_about_one_megapixel_in_the_source_ratio(self):
        width, height = unclip.metamorph_size(736, 999)
        self.assertEqual((width % 64, height % 64), (0, 0))
        self.assertAlmostEqual(width / height, 736 / 999, delta=0.05)
        self.assertAlmostEqual(width * height / 2**20, 1, delta=0.1)

    def test_only_the_chosen_adapter_is_active(self):
        self.assertEqual(unclip.adapter_scales('plus', .7), [0.0, .7])
        self.assertEqual(unclip.adapter_scales('plain', .5), [.5, 0.0])

    def test_metamorph_runs_sdxl_img2img_with_the_whole_picture_as_reference(self):
        pipe = MetamorphPipeline()
        payload = {'generation_type': 'reimagine', 'reimagine_mode': 'metamorph', 'image_base64': png_base64((300, 400)),
                   'num_images': 2, 'seed': 4, 'steps': 30, 'cfg': 5.5, 'denoise': .75, 'ip_scale': .8}
        with patch.object(core, 'use_demo_mode', return_value=False), \
             patch.object(core, 'get_torch', return_value=SimpleNamespace(Generator=Generator)), \
             patch.object(unclip, 'ensure_metamorph_pipeline', return_value=pipe), \
             patch.object(unclip, 'ensure_unclip_pipeline') as unclip_pipe:
            result = core.generate(payload)
        unclip_pipe.assert_not_called()
        self.assertEqual(pipe.scales, [[0.0, .8]])
        self.assertEqual(len(pipe.calls), 2)
        call = pipe.calls[0]
        self.assertEqual((call['strength'], call['guidance_scale'], call['num_inference_steps']), (.75, 5.5, 30))
        self.assertEqual([image.size for image in call['ip_adapter_image']], [(768, 768), (768, 768)])
        self.assertEqual([c['generator'].seed for c in pipe.calls], [4, 5])
        self.assertEqual(result['meta']['reimagine_mode'], 'metamorph')
        self.assertEqual(result['meta']['actual_steps'], 22)

    def test_missing_metamorph_weights_name_the_download_scripts(self):
        unclip._PIPELINE.pop('metamorph', None)
        with patch.dict('os.environ', {'IPADAPTER_DIR': '/nonexistent'}):
            with self.assertRaisesRegex(RuntimeError, 'download_ipadapter'):
                unclip.ensure_metamorph_pipeline()


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
