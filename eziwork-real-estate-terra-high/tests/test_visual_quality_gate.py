from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from visual_quality_gate import reference_comparison  # noqa: E402


class ReferenceComparisonTests(unittest.TestCase):
    def test_identical_rasters_are_pixel_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate.png"
            reference = root / "reference.png"
            pixels = np.full((40, 30, 3), (8, 47, 88), dtype=np.uint8)
            Image.fromarray(pixels).save(candidate)
            Image.fromarray(pixels).save(reference)
            result = reference_comparison([candidate], [reference])
            self.assertEqual(result["pixel_exact_pages"], 1)
            self.assertEqual(result["pixel_exact_percent"], 100.0)
            self.assertEqual(result["perceptual_similarity_percent"], 100.0)

    def test_changed_pixel_is_not_reported_as_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate.png"
            reference = root / "reference.png"
            a = np.full((20, 20, 3), 255, dtype=np.uint8)
            b = a.copy()
            b[0, 0] = (0, 0, 0)
            Image.fromarray(a).save(candidate)
            Image.fromarray(b).save(reference)
            result = reference_comparison([candidate], [reference])
            self.assertEqual(result["pixel_exact_pages"], 0)
            self.assertLess(result["pixel_exact_percent"], 100.0)
            self.assertLess(result["perceptual_similarity_percent"], 100.0)


if __name__ == "__main__":
    unittest.main()
