import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import matplotlib
matplotlib.use("Agg")
import matplotlib.colors as colors
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import helpers


class ScatterPaletteTests(unittest.TestCase):
    def test_points_and_legend_use_the_same_palette_for_all_scatters(self):
        frame = pd.DataFrame({
            "First party": ["Lab", "Con", "Lib"],
            "first_party_3": ["Lab", "Con", "Other"],
            "ASMR_f": [300., 200., 250.],
            "ASMR_m": [400., 320., 350.],
            **{party: [0.4, 0.2, 0.3] for party in ["Lab PC", "Con PC", "Lib PC", "Vote PC"]},
        })
        original = frame.copy(deep=True)
        expected = colors.to_rgba_array(["#E66859", "#416FA0", "lightgrey"])
        for party in ["Lab PC", "Con PC", "Lib PC", "Vote PC"]:
            with self.subTest(party=party), patch.object(helpers, "_ensure_output_dirs"), \
                    patch.object(helpers, "_save_figure") as save, contextlib.redirect_stdout(io.StringIO()):
                figure = helpers.plot_scatters(frame, frame, [party, party, False])
                self.assertEqual(len(figure.axes), 4)
                for axis in figure.axes:
                    np.testing.assert_allclose(axis.collections[0].get_facecolors(), expected)
                legend_colors = [item.get_facecolor() for item in figure.axes[0].get_legend().get_patches()]
                np.testing.assert_allclose(legend_colors, expected[[1, 0, 2]])
                for label in figure.axes[0].get_legend().get_texts():
                    self.assertEqual(label.get_fontsize(), 9)
                save.assert_called_once()
                pd.testing.assert_frame_equal(frame, original)


if __name__ == "__main__":
    unittest.main()
