import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from core.coordinates import Bounds, bounds_to_corel, corel_bounds_to_top_left


class CoordinateTests(unittest.TestCase):
    def test_round_trip(self):
        original = Bounds(10.5, 20.25, 30.0, 40.0)
        left, bottom, right, top = bounds_to_corel(original, 297.0)
        restored = corel_bounds_to_top_left(left, bottom, original.width, original.height, 297.0)
        self.assertEqual(original, restored)
        self.assertEqual((left, bottom, right, top), (10.5, 236.75, 40.5, 276.75))

    def test_rejects_non_positive_size(self):
        with self.assertRaises(ValueError):
            bounds_to_corel(Bounds(0, 0, 0, 10), 100)


if __name__ == "__main__":
    unittest.main()
