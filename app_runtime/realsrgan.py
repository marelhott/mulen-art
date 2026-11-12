"""Tiled SwinIR Real-SR GAN inference used by the optional output upscaler."""
from __future__ import annotations

import hashlib
import math
import urllib.request
from pathlib import Path

MODEL_URL = (
    "https://github.com/JingyunLiang/SwinIR/releases/download/v0.0/"
    "003_realSR_BSRGAN_DFO_s64w8_SwinIR-M_x4_GAN.pth"
)
MODEL_SHA256 = "b9afb61e65e04eb7f8aba5095d070bbe9af28df76acd0c9405aeb33b814bcfc6"
MODEL_PATH = Path("/tmp/swinir-realsr-gan-x4.pth")
TILE = 256
HALO = 32
_MODEL = None
_REAL_MODEL = None


def _load_model():
    global _MODEL
    if _MODEL is not None:
        return _MODEL

    import torch
    from spandrel import ModelLoader

    if not MODEL_PATH.exists() or hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest() != MODEL_SHA256:
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = MODEL_PATH.with_suffix(".download")
        urllib.request.urlretrieve(MODEL_URL, temporary)
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        if digest != MODEL_SHA256:
            temporary.unlink(missing_ok=True)
            raise RuntimeError("SwinIR Real-SR GAN checkpoint checksum mismatch")
        temporary.replace(MODEL_PATH)

    checkpoint = torch.load(MODEL_PATH, map_location="cpu", weights_only=True)
    model = ModelLoader().load_from_state_dict(checkpoint)
    if getattr(model, "scale", None) != 4:
        raise RuntimeError("Unexpected SwinIR Real-SR GAN scale")
    _MODEL = model.eval().cuda()
    del checkpoint
    return _MODEL


def _load_real_model():
    global _REAL_MODEL
    if _REAL_MODEL is not None:
        return _REAL_MODEL
    import torch
    from spandrel import ModelLoader
    url = 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth'
    sha256 = '4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1'
    path = Path('/tmp/RealESRGAN_x4plus.pth')
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
        temp = path.with_suffix('.download')
        urllib.request.urlretrieve(url, temp)
        if hashlib.sha256(temp.read_bytes()).hexdigest() != sha256:
            temp.unlink(missing_ok=True)
            raise RuntimeError('Real-ESRGAN checkpoint checksum mismatch')
        temp.replace(path)
    checkpoint = torch.load(path, map_location='cpu', weights_only=True)
    model = ModelLoader().load_from_state_dict(checkpoint)
    if getattr(model, 'scale', None) != 4:
        raise RuntimeError('Unexpected Real-ESRGAN scale')
    _REAL_MODEL = model.eval().cuda()
    return _REAL_MODEL


def upscale(image, model_name='swinir'):
    """Apply x4 GAN restoration in overlapping-context tiles to bound VRAM use."""
    import numpy as np
    import torch
    from PIL import Image

    model = _load_model() if model_name == 'swinir' else _load_real_model()
    source = np.asarray(image.convert("RGB"), dtype=np.uint8)
    height, width = source.shape[:2]
    padded_h = math.ceil(height / TILE) * TILE
    padded_w = math.ceil(width / TILE) * TILE
    # Pad beyond the image so edge tiles receive the same context as interior tiles.
    padded = np.pad(source, ((HALO, padded_h - height + HALO),
                             (HALO, padded_w - width + HALO), (0, 0)), mode="reflect")
    output = np.empty((padded_h * 4, padded_w * 4, 3), dtype=np.uint8)
    with torch.inference_mode():
        for top in range(0, padded_h, TILE):
            for left in range(0, padded_w, TILE):
                patch = padded[top:top + TILE + 2 * HALO, left:left + TILE + 2 * HALO]
                tensor = torch.from_numpy(patch.copy()).permute(2, 0, 1).unsqueeze(0).float().cuda() / 255
                restored = model(tensor)[0].clamp(0, 1)
                restored = restored[:, HALO * 4:(HALO + TILE) * 4,
                                    HALO * 4:(HALO + TILE) * 4]
                tile = restored.permute(1, 2, 0).mul(255).round().byte().cpu().numpy()
                output[top * 4:(top + TILE) * 4, left * 4:(left + TILE) * 4] = tile
                del tensor, restored

    # Core tiles are written at source coordinates; discard only padded bottom/right tiles.
    output = output[:height * 4, :width * 4]
    return Image.fromarray(output)
