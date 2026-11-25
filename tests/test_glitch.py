import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from app_runtime import core, glitch
from test_atelier import AtelierBase


class Handle:
    def __init__(self, registry, hook):
        self.registry, self.hook = registry, hook

    def remove(self):
        self.registry.remove(self.hook)


class Hooked:
    """A module that records the hooks registered on it, like torch.nn.Module."""
    def __init__(self):
        self.hooks, self.pre_hooks = [], []
        self.resnets = [SimpleNamespace(out_channels=640)]

    def register_forward_hook(self, hook):
        self.hooks.append(hook)
        return Handle(self.hooks, hook)

    def register_forward_pre_hook(self, hook):
        self.pre_hooks.append(hook)
        return Handle(self.pre_hooks, hook)


class FakeUnet(Hooked):
    device = "cpu"

    def __init__(self):
        super().__init__()
        self.mid_block = Hooked()
        self.down_blocks = [Hooked(), Hooked()]
        self.up_blocks = [Hooked()]
        self.attn_processors = {"mid_block.attentions.0.transformer_blocks.0.attn1.processor": "mid-sa",
                                "mid_block.attentions.0.transformer_blocks.0.attn2.processor": "mid-xa",
                                "up_blocks.0.attentions.0.transformer_blocks.0.attn1.processor": "up-sa"}

    def set_attn_processor(self, processors):
        self.attn_processors = dict(processors)

    def all_hooks(self):
        blocks = [self, self.mid_block, *self.down_blocks, *self.up_blocks]
        return sum(len(block.hooks) + len(block.pre_hooks) for block in blocks)


class FakeTorch:
    class Generator:
        def __init__(self, device=None):
            self.seed = None

        def manual_seed(self, seed):
            self.seed = seed
            return self

    @staticmethod
    def randperm(count, generator=None, device=None):
        return list(range(count))


class ParseTests(unittest.TestCase):
    base = {"generation_type": "atelier", "model_id": "tuymans_modal_2400", "atelier_mode": "noise"}

    def test_the_glitch_is_off_by_default_and_validated(self):
        parsed = core.parse_input(self.base)
        self.assertEqual((parsed.glitch, parsed.glitch_until), ("", 0.3))
        parsed = core.parse_input({**self.base, "glitch": "top_suppress", "glitch_until": 0.45})
        self.assertEqual((parsed.glitch, parsed.glitch_until), ("top_suppress", 0.45))
        self.assertEqual(core.parse_input({**self.base, "glitch": "chan_drop", "glitch_until": 9}).glitch_until, 0.6)
        self.assertEqual(core.parse_input({**self.base, "glitch": "chan_drop", "glitch_until": 0}).glitch_until, 0.1)
        with self.assertRaises(ValueError):
            core.parse_input({**self.base, "glitch": "melt"})

    def test_unclip_takes_a_glitch_and_other_types_ignore_it(self):
        reimagine = {"generation_type": "reimagine", "image_base64": "x", "glitch": "sa_identity"}
        self.assertEqual(core.parse_input(reimagine).glitch, "sa_identity")
        self.assertEqual(core.parse_input({"generation_type": "img2img", "image_base64": "x", "glitch": "top_suppress"}).glitch, "")

    def test_the_vari_glitch_belongs_to_the_unclip_pre_stage(self):
        vari = {"generation_type": "vari", "image_base64": "x", "num_images": 3}
        parsed = core.parse_input({**vari, "pre_unclip": "loose", "pre_unclip_glitch": "top_suppress", "glitch_until": 0.4})
        self.assertEqual((parsed.pre_unclip_glitch, parsed.glitch_until, parsed.glitch), ("top_suppress", 0.4, ""))
        self.assertEqual(core.parse_input(vari).pre_unclip_glitch, "")
        with self.assertRaises(ValueError):  # no pre-stage, nothing to damage
            core.parse_input({**vari, "pre_unclip_glitch": "top_suppress"})
        with self.assertRaises(ValueError):
            core.parse_input({**vari, "pre_unclip": "free", "pre_unclip_glitch": "melt"})
        with self.assertRaises(ValueError):
            core.parse_input({"generation_type": "collage", "image_base64": "x", "pre_unclip_glitch": "top_suppress"})


class DamagedTests(unittest.TestCase):
    def pipe(self):
        return SimpleNamespace(unet=FakeUnet())

    def run_op(self, op, fail=False):
        pipe = self.pipe()
        original = dict(pipe.unet.attn_processors)
        with patch.object(core, "get_torch", return_value=FakeTorch):
            try:
                with glitch.damaged(pipe, op, 28, 0.3, 11) as info:
                    inside = (pipe.unet.all_hooks(), dict(pipe.unet.attn_processors))
                    for _ in range(3):
                        for hook in pipe.unet.pre_hooks:
                            hook(None, ())
                    if fail:
                        raise RuntimeError("boom")
            except RuntimeError:
                pass
        return pipe, original, inside, info

    def test_every_operation_hooks_in_and_always_cleans_up(self):
        for op in glitch.GLITCH_OPS:
            for fail in (False, True):
                pipe, original, inside, info = self.run_op(op, fail)
                if op == "sa_identity":  # works by replacing attention processors, not by a hook
                    self.assertNotEqual(inside[1], original)
                else:
                    self.assertGreater(inside[0], 1, op)  # the call counter plus at least one operation hook
                self.assertEqual(pipe.unet.all_hooks(), 0, f"{op} left hooks behind")
                self.assertEqual(pipe.unet.attn_processors, original, f"{op} left attention processors replaced")
                self.assertEqual(info["glitch_calls"], 3)

    def test_sa_identity_replaces_only_the_mid_block_self_attention(self):
        _, original, inside, _ = self.run_op("sa_identity")
        changed = {name for name, proc in inside[1].items() if proc != original[name]}
        self.assertEqual(changed, {"mid_block.attentions.0.transformer_blocks.0.attn1.processor"})

    def test_off_does_nothing_and_unknown_is_refused(self):
        pipe = self.pipe()
        with glitch.damaged(pipe, "", 28, 0.3, 1) as info:
            self.assertEqual(pipe.unet.all_hooks(), 0)
        self.assertEqual(info["glitch"], "")
        with patch.object(core, "get_torch", return_value=FakeTorch), self.assertRaises(ValueError):
            with glitch.damaged(pipe, "melt", 28, 0.3, 1):
                pass

    def test_the_healing_point_and_the_seed_are_stable(self):
        self.assertEqual(glitch.calls_before_healing(28, 0.3), 8)  # the value of the experiments (scripts/experiments/glitch_lab.py)
        self.assertEqual(glitch.calls_before_healing(3, 0.1), 1)
        self.assertEqual(glitch.seed_for(11, "top_suppress"), glitch.seed_for(11, "top_suppress"))
        self.assertNotEqual(glitch.seed_for(11, "top_suppress"), glitch.seed_for(11, "chan_drop"))


class AtelierGlitchTests(AtelierBase):
    def test_the_glitch_reaches_the_study_and_is_recorded(self):
        seen = []

        @contextmanager
        def fake(pipe, op, total_calls, until, seed):
            seen.append((op, total_calls, until))
            yield {"glitch": op, "glitch_until": until, "glitch_calls": 0}
        with patch("app_runtime.glitch.damaged", fake):
            _, _, _, result, _, emitted, _ = self.run_study(glitch="top_suppress", glitch_until=0.4)
            off = self.run_study()[5][0]
        self.assertEqual(seen[0], ("top_suppress", 28, 0.4))
        self.assertEqual((emitted[0]["glitch"], emitted[0]["glitch_until"]), ("top_suppress", 0.4))
        self.assertEqual(seen[1][0], "")  # off: still entered, but with nothing to do
        self.assertNotIn("glitch", off)


if __name__ == "__main__":
    unittest.main()
