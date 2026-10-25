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
                np.testing.assert_array_equal(figure.get_size_inches(), [12, 10])
                self.assertEqual(len(figure.axes), 4)
                self.assertEqual([axis.get_title(loc="right") for axis in figure.axes],
                                 ["", "", "", ""])
                self.assertEqual([axis.get_title(loc="left") for axis in figure.axes],
                                 ["a.", "b.", "c.", "d."])
                self.assertEqual([axis.get_ylabel() for axis in figure.axes],
                                 ["ASMR (Female)", "ASMR (Male)"] * 2)
                for axis, year in zip(figure.axes, [2019, 2019, 2024, 2024]):
                    self.assertTrue(axis.get_xlabel().endswith(f"({year})"))
                for axis, outcome in zip(figure.axes, ["ASMR_f", "ASMR_m"] * 2):
                    self.assertEqual(axis.yaxis.get_major_formatter()(1000), "1,000")
                    self.assertEqual(axis._left_title.get_fontweight(), "bold")
                    self.assertEqual(axis._left_title.get_fontsize(), 19)
                    np.testing.assert_allclose(axis.collections[0].get_facecolors(), expected)
                    np.testing.assert_array_equal(
                        axis.collections[0].get_offsets(), frame[[party, outcome]].to_numpy(),
                    )
                    reference, reference_axis = helpers.plt.subplots()
                    reference_points = reference_axis.scatter(frame[party], frame[outcome])
                    y_min, y_max = reference_axis.get_ylim()
                    np.testing.assert_allclose(axis.get_xlim(), reference_axis.get_xlim())
                    np.testing.assert_allclose(axis.get_ylim(),
                                               [y_min - 0.05 * (y_max - y_min),
                                                y_max + 0.20 * (y_max - y_min)])
                    np.testing.assert_array_equal(axis.collections[0].get_sizes(), reference_points.get_sizes())
                    helpers.plt.close(reference)
                    self.assertTrue(axis.get_axisbelow())
                    self.assertEqual(axis.collections[0].get_linewidths()[0], 0.65)
                    correlation_boxes = [artist for artist in axis.artists
                                         if isinstance(artist, helpers.AnchoredText)]
                    self.assertEqual(len(correlation_boxes), 1)
                    self.assertEqual(correlation_boxes[0].patch.get_edgecolor(), colors.to_rgba("black"))
                figure.canvas.draw()
                renderer = figure.canvas.get_renderer()
                for axis in figure.axes:
                    for gridlines in (axis.get_xgridlines(), axis.get_ygridlines()):
                        self.assertTrue(gridlines)
                        for line in gridlines:
                            self.assertTrue(line.get_visible())
                            self.assertEqual(line.get_color(), "#e6e6e6")
                            self.assertEqual(line.get_linestyle(), "--")
                            self.assertEqual(line.get_alpha(), 0.75)
                            self.assertEqual(line.get_linewidth(), 0.6)
                    box = next(artist for artist in axis.artists if isinstance(artist, helpers.AnchoredText))
                    self.assertEqual(box.loc, helpers.AnchoredText.codes["upper left"])
                    bounds = box.get_window_extent(renderer)
                    np.testing.assert_allclose(axis.transAxes.inverted().transform((bounds.x0, bounds.y1)),
                                               [0.02, 0.98])
                    plot_bounds = axis.get_window_extent(renderer)
                    self.assertTrue(plot_bounds.contains(*bounds.p0))
                    self.assertTrue(plot_bounds.contains(*bounds.p1))
                    self.assertFalse(bounds.overlaps(axis._left_title.get_window_extent(renderer)))
                    legend = axis.get_legend()
                    self.assertIsNotNone(legend)
                    legend_bounds = legend.get_window_extent(renderer)
                    self.assertGreater(legend_bounds.x0, bounds.x1)
                    self.assertAlmostEqual(legend_bounds.y1, bounds.y1)
                    self.assertEqual(legend._ncols, 3)
                    self.assertTrue(plot_bounds.contains(*legend_bounds.p0))
                    self.assertTrue(plot_bounds.contains(*legend_bounds.p1))
                    np.testing.assert_allclose(
                        axis.transAxes.inverted().transform((legend_bounds.x1, legend_bounds.y1)),
                        [0.98, 0.98],
                    )
                    legend_colors = [colors.to_rgba(item.get_markerfacecolor()) for item in legend.get_lines()]
                    np.testing.assert_allclose(legend_colors, expected[[1, 0, 2]])
                    self.assertEqual(legend.get_frame().get_edgecolor(), colors.to_rgba("black"))
                    for marker in legend.get_lines():
                        self.assertEqual(marker.get_marker(), "o")
                        self.assertEqual(marker.get_markersize(), matplotlib.rcParams["lines.markersize"])
                    labels = legend.get_texts()
                    self.assertEqual([label.get_text() for label in labels], ["Conservative", "Labour", "Other"])
                    for label in labels:
                        self.assertEqual(label.get_fontsize(), 9)
                        self.assertAlmostEqual(label.get_window_extent(renderer).y0,
                                               labels[0].get_window_extent(renderer).y0)
                save.assert_called_once()
                pd.testing.assert_frame_equal(frame, original)

    def test_labour_correlation_boxes_leave_low_mortality_markers_visible(self):
        frame = pd.DataFrame({
            "First party": ["Lab"] * 5,
            "first_party_3": ["Lab"] * 5,
            "Lab PC": [0.1, 0.3, 0.65, 0.8, 0.75],
            "ASMR_f": [500., 700., 1000., 600., 510.],
            "ASMR_m": [700., 1100., 1500., 900., 720.],
        })
        with patch.object(helpers, "_ensure_output_dirs"), \
                patch.object(helpers, "_save_figure"), contextlib.redirect_stdout(io.StringIO()):
            figure = helpers.plot_scatters(frame, frame, ["Lab PC", "Labour", False])
        self.addCleanup(helpers.plt.close, figure)
        figure.canvas.draw()
        renderer = figure.canvas.get_renderer()
        for axis in figure.axes:
            box = next(artist for artist in axis.artists if isinstance(artist, helpers.AnchoredText))
            points = axis.collections[0]
            marker_radius = (np.sqrt(points.get_sizes().max()) + points.get_linewidths().max()) / 2
            clearance = renderer.points_to_pixels(marker_radius + 2)
            bounds = box.get_window_extent(renderer).padded(clearance)
            positions = points.get_offset_transform().transform(points.get_offsets())
            self.assertFalse(any(bounds.contains(x, y) for x, y in positions))
            legend = axis.get_legend()
            if legend is not None:
                self.assertFalse(box.get_window_extent(renderer).overlaps(legend.get_window_extent(renderer)))
                self.assertGreater(legend.get_window_extent(renderer).x0, box.get_window_extent(renderer).x1)
                legend_bounds = legend.get_window_extent(renderer).padded(clearance)
                self.assertFalse(any(legend_bounds.contains(x, y) for x, y in positions))


if __name__ == "__main__":
    unittest.main()
