import tempfile
import unittest
from pathlib import Path
from PIL import Image
from thumbnails import load_thumbnail, thumbnail_path


class ThumbnailTests(unittest.TestCase):
    def test_workshop_and_project_previews_and_missing_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod = {'path': str(root)}
            self.assertIsNone(load_thumbnail(mod))
            (root / 'ModProject').mkdir()
            path = root / 'ModProject' / 'ModProjectPreview.png'
            Image.new('RGB', (400, 200), 'blue').save(path)
            self.assertEqual(thumbnail_path(mod), path)
            self.assertEqual(load_thumbnail(mod).size, (56, 56))
            from extractor import MAGIC, MOD_KEY
            payload = path.read_bytes()
            path.write_bytes(MAGIC + bytes((v + MOD_KEY[i % len(MOD_KEY)]) & 255 for i, v in enumerate(payload)))
            self.assertEqual(load_thumbnail(mod).size, (56, 56))
            (root / 'ModProjectPreview.png').write_bytes(b'corrupt')
            self.assertIsNone(load_thumbnail(mod))


if __name__ == '__main__':
    unittest.main()
