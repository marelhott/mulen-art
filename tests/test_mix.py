import contextlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app_runtime import atelier, core


class FakeTensor:
    """Just enough of torch.Tensor for the blending arithmetic."""
    dtype = "fp16"

    def __init__(self, values):
        self.values = list(values)

    def is_floating_point(self):
        return True

    def float(self):
        return self

    def to(self, _dtype):
        return self

    def __mul__(self, factor):
        return FakeTensor(v * factor for v in self.values)

    def __add__(self, other):
        return FakeTensor(a + b for a, b in zip(self.values, other.values))

    def copy_(self, other):
        self.values = list(other.values)


def fake_pipe(base):
    def module(offset):
        state = {"w": FakeTensor([base + offset, 2 * base + offset])}  # like torch, state_dict() returns the live tensors
        return SimpleNamespace(state_dict=lambda: state)
    return SimpleNamespace(unet=module(0), text_encoder=module(1), text_encoder_2=module(2))


class MixTests(unittest.TestCase):
    def test_mix_ids_are_validated(self):
        self.assertEqual(core.parse_mix_id("mix:hofmann_sdxl=60,tuymans_modal_2400=40"), [("hofmann_sdxl", 60), ("tuymans_modal_2400", 40)])
        for bad in ("mix:hofmann_sdxl=100", "mix:hofmann_sdxl=50,hofmann_sdxl=50", "mix:tuymans_sdxl=70,hofmann_sdxl=40",
                    "mix:tuymans_sdxl=0,hofmann_sdxl=100", "mix:sdxl_base=50,hofmann_sdxl=50", "mix:nope=50,hofmann_sdxl=50",
                    "mix:a=20,b=20,c=20,d=20,e=20", "mix:../x=50,hofmann_sdxl=50", "mulen_mara"):
            with self.assertRaises(ValueError, msg=bad):
                core.parse_mix_id(bad)

    def test_a_mix_behaves_like_any_model_id(self):
        mix = "mix:tuymans_sdxl=60,tuymans_modal_2400=40"
        item = core.get_config_item("models", mix)
        self.assertEqual(item["name"], "Fúze: Tuymans SDXL 60 % + Tuymans Modal — 2400 kroků 40 %")
        self.assertTrue(atelier.is_atelier_model(mix))
        self.assertTrue(atelier.is_atelier_model("mix:hofmann_sdxl=50,tuymans_sdxl=50"))
        self.assertEqual(atelier.painting_prompt(mix, "a pale deer"), "tuypaint, mvhpaint, a pale deer")
        self.assertEqual(atelier.painting_prompt(mix, ""), "tuypaint, mvhpaint")
        self.assertEqual(atelier.painting_prompt("mix:hofmann_sdxl=50,tuymans_modal_2400=50", "x"), "mvhpaint, x")
        parsed = core.parse_input({"generation_type": "atelier", "atelier_mode": "noise", "model_id": mix})
        self.assertEqual(parsed.model_id, mix)
        with self.assertRaises(ValueError):
            core.parse_input({"generation_type": "atelier", "atelier_mode": "noise", "model_id": "mix:tuymans_sdxl=50,hofmann_sdxl=40"})

    def test_weights_are_blended_per_tensor_and_vae_stays_with_the_first(self):
        pipes = {"a": fake_pipe(1.0), "b": fake_pipe(5.0)}
        with patch.object(core, "get_torch", return_value=SimpleNamespace(no_grad=contextlib.nullcontext)), \
             patch.object(core, "load_checkpoint_pipeline", side_effect=lambda model_id, path: pipes[model_id]), \
             patch.object(core, "get_config_item", return_value={"path": "x"}):
            result = core.build_mixed_pipeline([("a", 75), ("b", 25)])
        self.assertIs(result, pipes["a"])
        self.assertEqual([round(v, 6) for v in result.unet.state_dict()["w"].values], [round(1 * .75 + 5 * .25, 6), round(2 * .75 + 10 * .25, 6)])
        self.assertEqual([round(v, 6) for v in result.text_encoder.state_dict()["w"].values][0], round(2 * .75 + 6 * .25, 6))

    def test_incompatible_checkpoints_are_rejected(self):
        other = fake_pipe(5.0)
        mismatched = {"different": FakeTensor([1])}
        other.unet = SimpleNamespace(state_dict=lambda: mismatched)
        pipes = {"a": fake_pipe(1.0), "b": other}
        with patch.object(core, "get_torch", return_value=SimpleNamespace(no_grad=contextlib.nullcontext)), \
             patch.object(core, "load_checkpoint_pipeline", side_effect=lambda model_id, path: pipes[model_id]), \
             patch.object(core, "get_config_item", return_value={"path": "x"}):
            with self.assertRaisesRegex(ValueError, "cannot be mixed"):
                core.build_mixed_pipeline([("a", 50), ("b", 50)])


if __name__ == "__main__":
    unittest.main()
