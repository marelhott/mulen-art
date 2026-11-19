"""Optional Restormer deblurring, processed in overlapping-context tiles."""
import math

MODELS = {
    'motion': ('motion_deblurring.pt', 'e17e1875586051988d70ba4dbcf5dc6ae55f7e541c3db10e5c1c021385d220b1'),
    'defocus': ('single_image_defocus_deblurring.pt', '8f3513f48bf77cce3f40fd73663ea16d80d88f6487f1f1bae6976e64238a0497'),
}
_MODELS = {}


def _model(mode):
    import torch
    if mode in _MODELS:
        return _MODELS[mode]
    filename, expected = MODELS[mode]
    from .realsrgan import cache_dir, download_checked
    path = download_checked('https://huggingface.co/spaces/swzamir/Restormer/resolve/main/' + filename, cache_dir() / filename, expected, 'Restormer')
    _MODELS[mode] = torch.jit.load(str(path), map_location='cpu').eval().cuda()
    return _MODELS[mode]


def release():
    """Drop the GPU copies (called when an SDXL pipeline is evicted)."""
    _MODELS.clear()


def deblur(image, mode):
    import numpy as np
    import torch
    from PIL import Image
    model = _model(mode)
    source = np.asarray(image.convert('RGB'), dtype=np.uint8)
    height, width = source.shape[:2]
    tile, halo = 512, 32
    padded_h = math.ceil(height / tile) * tile
    padded_w = math.ceil(width / tile) * tile
    padded = np.pad(source, ((halo, padded_h-height+halo), (halo, padded_w-width+halo), (0, 0)), mode='reflect')
    output = np.empty((padded_h, padded_w, 3), dtype=np.uint8)
    with torch.inference_mode():
        for top in range(0, padded_h, tile):
            for left in range(0, padded_w, tile):
                patch = padded[top:top+tile+2*halo, left:left+tile+2*halo]
                tensor = torch.from_numpy(patch.copy()).permute(2, 0, 1).unsqueeze(0).float().cuda() / 255
                restored = model(tensor)[0].clamp(0, 1)[:, halo:halo+tile, halo:halo+tile]
                output[top:top+tile, left:left+tile] = restored.permute(1, 2, 0).mul(255).round().byte().cpu().numpy()
                del tensor, restored
    return Image.fromarray(output[:height, :width])
