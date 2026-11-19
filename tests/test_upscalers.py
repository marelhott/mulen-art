import hashlib
import tempfile
import unittest
from pathlib import Path

from app_runtime import core, realsrgan, restormer


class UpscalerDownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.bin"
        self.source.write_bytes(b"checkpoint-bytes")
        self.sha = hashlib.sha256(b"checkpoint-bytes").hexdigest()

    def tearDown(self):
        self.tmp.cleanup()

    def test_verified_download_is_cached_and_a_bad_checksum_leaves_nothing_behind(self):
        target = self.root / "cache" / "model.pth"
        url = self.source.as_uri()
        self.assertEqual(realsrgan.download_checked(url, target, self.sha, "test"), target)
        self.source.unlink()  # a second call must not touch the network (here: the vanished source)
        self.assertEqual(realsrgan.download_checked(url, target, self.sha, "test"), target)
        self.source.write_bytes(b"checkpoint-bytes")
        bad = self.root / "cache" / "bad.pth"
        with self.assertRaisesRegex(RuntimeError, "checksum"):
            realsrgan.download_checked(url, bad, "0" * 64, "test")
        self.assertFalse(bad.exists())
        self.assertEqual(list((self.root / "cache").glob("*.download")), [])

    def test_release_drops_the_loaded_models(self):
        realsrgan._MODEL = realsrgan._REAL_MODEL = object()
        restormer._MODELS["motion"] = object()
        core.release_upscalers()
        self.assertIsNone(realsrgan._MODEL)
        self.assertIsNone(realsrgan._REAL_MODEL)
        self.assertEqual(restormer._MODELS, {})


if __name__ == "__main__":
    unittest.main()
