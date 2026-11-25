"""Rozpad modelu: the UNet is damaged only in the first part of a run, a healthy model finishes it (docs/atelier-lab-ramec.md).

Nothing is stored in the weights. The damage is made by forward hooks on pipe.unet (and, for one operation, by replacing attention
processors) that are active for the first `until` fraction of the UNet calls and are always removed again, so the cached pipeline
is never changed for the next job. At the guidance scales of the Atelier and of unCLIP one step is one UNet call (classifier-free
guidance runs as one batch), so a call counter equals the step number.

Operations (tested on three artist checkpoints, docs/atelier-lab-ramec.md section 9):
  top_suppress  the strongest 5 % of the activations of the mid block and the first up block are zeroed: forms break into shards,
                layout, colour and handwriting stay
  chan_drop     25 % of the channels of the second down block are zeroed (also in its skip connections): a milder break
  sa_identity   self-attention of the mid block returns only its value projection (no attention map): the structure shifts gently
"""
from contextlib import contextmanager
import zlib

GLITCH_OPS = ("top_suppress", "chan_drop", "sa_identity")
GLITCH_UNTIL_DEFAULT = 0.3
GLITCH_UNTIL_RANGE = (0.1, 0.6)
GLITCH_LABELS = {"top_suppress": "Rozpad aktivací", "chan_drop": "Vynechané kanály", "sa_identity": "Chybné čtení pozornosti"}


def calls_before_healing(total_calls: int, until: float) -> int:
    """How many UNet calls are damaged: the first `until` of the run, at least one when there is any damage."""
    return max(1, int(until * max(1, total_calls)))


def seed_for(seed: int, op: str) -> int:
    return seed * 1000003 + zlib.crc32(op.encode()) % 100000


@contextmanager
def damaged(pipe, op: str, total_calls: int, until: float, seed: int):
    """Damage pipe.unet in the first `until` of `total_calls` UNet calls. Yields a dict that describes what was done.

    With op == "" it does nothing. Everything is undone on exit, also when the run fails.
    """
    info = {"glitch": op or "", "glitch_until": until, "glitch_calls": 0}
    if not op:
        yield info
        return
    if op not in GLITCH_OPS:
        raise ValueError(f"Unknown glitch operation: {op}")
    from . import core
    torch = core.get_torch()
    unet = pipe.unet
    limit = calls_before_healing(total_calls, until)
    state = {"calls": 0}
    rng = torch.Generator(device=unet.device).manual_seed(seed_for(seed, op))
    handles, undo = [], []

    def active():
        return state["calls"] <= limit

    def count(_module, _args):
        state["calls"] += 1

    handles.append(unet.register_forward_pre_hook(count))

    def suppress(tensor):
        flat = tensor.abs().float().flatten()
        threshold = flat.kthvalue(max(1, int(flat.numel() * 0.95))).values
        return tensor.masked_fill(tensor.abs().float() >= threshold, 0)

    try:
        if op == "top_suppress":
            def hook(_module, _args, out):
                return suppress(out) if active() else None
            handles.append(unet.mid_block.register_forward_hook(hook))
            handles.append(unet.up_blocks[0].register_forward_hook(hook))
        elif op == "chan_drop":
            block = unet.down_blocks[1]
            channels = block.resnets[-1].out_channels
            chosen = torch.randperm(channels, generator=rng, device=unet.device)[:channels // 4]

            def drop(tensor):
                tensor = tensor.clone()
                tensor[:, chosen] = 0
                return tensor

            def hook(_module, _args, out):
                if not active():
                    return None
                hidden, residuals = out
                return drop(hidden), tuple(drop(item) for item in residuals)
            handles.append(block.register_forward_hook(hook))
        else:  # sa_identity
            original = dict(unet.attn_processors)
            picked = [name for name in original if name.startswith("mid_block") and ".attn1." in name]
            if not picked:
                raise RuntimeError("This UNet has no self-attention in its mid block")

            class Identity:
                def __init__(self, inner):
                    self.inner = inner

                def __call__(self, attn, hidden_states, *args, **kwargs):
                    if not active():
                        return self.inner(attn, hidden_states, *args, **kwargs)
                    return attn.to_out[1](attn.to_out[0](attn.to_v(hidden_states)))

            unet.set_attn_processor({name: (Identity(proc) if name in picked else proc) for name, proc in original.items()})
            undo.append(lambda: unet.set_attn_processor(original))
        yield info
    finally:
        for handle in handles:
            handle.remove()
        for restore in undo:
            restore()
        info["glitch_calls"] = state["calls"]
