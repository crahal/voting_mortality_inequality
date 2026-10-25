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
                for axis, outcome in zip(figure.axes, ["ASMR_f", "ASMR_m"] * 2):
                    np.testing.assert_allclose(axis.collections[0].get_facecolors(), expected)
                    np.testing.assert_array_equal(
                        axis.collections[0].get_offsets(), frame[[party, outcome]].to_numpy(),
                    )
                    reference, reference_axis = helpers.plt.subplots()
                    reference_points = reference_axis.scatter(frame[party], frame[outcome])
                    y_min, y_max = reference_axis.get_ylim()
                    np.testing.assert_allclose(axis.get_xlim(), reference_axis.get_xlim())
                    np.testing.assert_allclose(axis.get_ylim(), [y_min - 0.05 * (y_max - y_min), y_max])
                    np.testing.assert_array_equal(axis.collections[0].get_sizes(), reference_points.get_sizes())
                    helpers.plt.close(reference)
                    self.assertTrue(axis.get_axisbelow())
                    self.assertEqual(axis.collections[0].get_linewidths()[0], 0.65)
                    correlation_boxes = [artist for artist in axis.artists
                                         if isinstance(artist, helpers.AnchoredText)]
                    self.assertEqual(len(correlation_boxes), 1)
                    self.assertEqual(correlation_boxes[0].patch.get_edgecolor(), colors.to_rgba("black"))
                legend = figure.axes[0].get_legend()
                legend_colors = [colors.to_rgba(item.get_markerfacecolor()) for item in legend.get_lines()]
                np.testing.assert_allclose(legend_colors, expected[[1, 0, 2]])
                self.assertEqual(legend.get_frame().get_edgecolor(), colors.to_rgba("black"))
                for marker in legend.get_lines():
                    self.assertEqual(marker.get_marker(), "o")
                    self.assertEqual(marker.get_markersize(), matplotlib.rcParams["lines.markersize"])
                figure.canvas.draw()
                renderer = figure.canvas.get_renderer()
                for axis in figure.axes:
                    self.assertFalse(any(line.get_visible() for line in axis.get_xgridlines()))
                    self.assertTrue(any(line.get_visible() for line in axis.get_ygridlines()))
                    box = next(artist for artist in axis.artists if isinstance(artist, helpers.AnchoredText))
                    location = "lower right" if party == "Lab PC" else (
                        "lower left" if axis is figure.axes[0] and party != "Lib PC" else "upper right"
                    )
                    self.assertEqual(box.loc, helpers.AnchoredText.codes[location])
                    if axis is figure.axes[0]:
                        self.assertFalse(box.get_window_extent(renderer).overlaps(legend.get_window_extent(renderer)))
                for label in legend.get_texts():
                    self.assertEqual(label.get_fontsize(), 9)
                save.assert_called_once()
                pd.testing.assert_frame_equal(frame, original)


if __name__ == "__main__":
    unittest.main()
