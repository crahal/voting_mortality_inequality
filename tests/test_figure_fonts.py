import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import matplotlib
matplotlib.use("Agg")
from matplotlib.mathtext import MathTextParser

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import helpers


class FigureFontTests(unittest.TestCase):
    def test_missing_helvetica_prevents_export_without_substitution(self):
        figure = Mock(spec=["savefig"])
        with patch.object(helpers.font_manager, "findfont", side_effect=ValueError("missing")) as find:
            with self.assertRaisesRegex(RuntimeError, "Helvetica is required"):
                helpers._save_figure(figure, "example")
        find.assert_called_once()
        self.assertFalse(find.call_args.kwargs["fallback_to_default"])
        figure.savefig.assert_not_called()

    def test_font_check_requests_all_four_faces(self):
        with patch.object(helpers.font_manager, "findfont", return_value="Helvetica.ttf") as find:
            helpers._require_helvetica()
        faces = []
        for call in find.call_args_list:
            properties = call.args[0]
            self.assertEqual(properties.get_family(), ["Helvetica"])
            self.assertFalse(call.kwargs["fallback_to_default"])
            faces.append((properties.get_style(), properties.get_weight()))
        self.assertEqual(faces, [("normal", "normal"), ("normal", "bold"),
                                 ("oblique", "normal"), ("oblique", "bold")])

    def test_math_symbols_and_svg_glyphs_use_real_helvetica(self):
        try:
            helpers._require_helvetica()
        except RuntimeError:
            self.skipTest("Licensed Helvetica fonts are not installed")
        with matplotlib.rc_context(helpers.FIGURE_FONT_SETTINGS):
            expression = r"Spearman $\rho = 0.514$; Pearson $r = 0.504$"
            parsed = MathTextParser("path").parse(expression)
            self.assertTrue(parsed.glyphs)
            self.assertEqual({font.family_name for font, *_ in parsed.glyphs}, {"Helvetica"})
            self.assertEqual(matplotlib.rcParams["pdf.fonttype"], 42)
            self.assertIsNone(matplotlib.rcParams["mathtext.fallback"])
            figure = helpers.plt.figure(figsize=(2, 1))
            self.addCleanup(helpers.plt.close, figure)
            figure.text(0.1, 0.5, expression, fontsize=9)
            figure.text(0.1, 0.8, "a.", fontweight="bold")
            with tempfile.TemporaryDirectory() as directory, \
                    patch.object(helpers, "FIGURES_DIR", Path(directory)), \
                    contextlib.redirect_stdout(io.StringIO()):
                helpers._save_figure(figure, "font_check")
                svg = (Path(directory) / "font_check.svg").read_text()
            self.assertIn("Helvetica-Oblique", svg)
            self.assertIn("Helvetica-Bold", svg)
            self.assertNotIn("DejaVu", svg)


if __name__ == "__main__":
    unittest.main()
