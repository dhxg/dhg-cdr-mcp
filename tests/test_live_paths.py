import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from tools.live import _validated_destination


class LivePathTests(unittest.TestCase):
    def test_existing_destination_requires_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preview.png"
            path.write_bytes(b"existing")
            with self.assertRaises(FileExistsError):
                _validated_destination(str(path), suffixes={".png"}, overwrite=False)
            self.assertEqual(
                _validated_destination(str(path), suffixes={".png"}, overwrite=True),
                path.resolve(),
            )

    def test_output_root_rejects_outside_path(self):
        previous = os.environ.get("COREL_OUTPUT_ROOT")
        try:
            with tempfile.TemporaryDirectory() as allowed, tempfile.TemporaryDirectory() as outside:
                os.environ["COREL_OUTPUT_ROOT"] = allowed
                with self.assertRaises(PermissionError):
                    _validated_destination(
                        str(Path(outside) / "file.pdf"),
                        suffixes={".pdf"},
                        overwrite=False,
                    )
        finally:
            if previous is None:
                os.environ.pop("COREL_OUTPUT_ROOT", None)
            else:
                os.environ["COREL_OUTPUT_ROOT"] = previous


if __name__ == "__main__":
    unittest.main()
