"""Use the game's authored mod preview without scanning unrelated artwork."""
from pathlib import Path
import io


def thumbnail_path(mod):
    root = Path(mod.get('path', ''))
    if not root.is_dir():
        return None
    candidates = [root / 'ModProjectPreview.png', root / 'ModProject' / 'ModProjectPreview.png']
    candidates.extend(sorted(root.glob('debug/*/ModProjectPreview.png')))
    candidates.extend(root / name for name in ('preview.png', 'preview.jpg', 'thumbnail.png', 'icon.png'))
    return next((path for path in candidates if path.is_file() and path.stat().st_size <= 20 * 1024 * 1024), None)


def load_thumbnail(mod, size=(56, 56)):
    from PIL import Image, ImageOps
    path = thumbnail_path(mod)
    if path is None:
        return None
    try:
        from extractor import decode_mod_bytes
        with Image.open(io.BytesIO(decode_mod_bytes(path.read_bytes()))) as image:
            if image.width * image.height > 25_000_000:
                return None
            image = ImageOps.exif_transpose(image).convert('RGB')
            return ImageOps.pad(image, size, color='#e8edf5', method=Image.Resampling.LANCZOS)
    except (OSError, ValueError, Image.DecompressionBombError):
        return None
