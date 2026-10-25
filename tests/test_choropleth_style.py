import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import matplotlib
matplotlib.use("Agg")
import geopandas as gpd
import matplotlib.colors as colors
import numpy as np
import pandas as pd
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import helpers


class ChoroplethStyleTests(unittest.TestCase):
    def test_legend_preserves_palette_bin_orientation_and_tick_precision(self):
        plotter = helpers.BivariateChoroplethPlotter(
            [0, 0.12, 0.24, 0.36, 0.48, 0.6], [200, 400, 600, 800, 1000, 1200],
        )
        self.assertEqual([plotter.color_list_hex[i] for i in [0, 4, 20, 24]],
                         ["#e8e8e8", "#73ae80", "#6c83b5", "#2a5a5b"])
        self.assertEqual(plotter.get_bivariate_color(None, 500), "#cccccc")
        self.assertEqual(plotter.get_bivariate_color(0.12, 400), "#e8e8e8")
        figure, axis = helpers.plt.subplots()
        try:
            plotter.plot_inset_legend(axis, "ASMR\n(Female, 2019)", "Liberal Democrat Vote Share\n(2019)")
            inset = axis.child_axes[0]
            self.assertEqual([tick.get_text() for tick in inset.get_xticklabels()],
                             ["0", "0.1", "0.2", "0.4", "0.5", "0.6"])
            self.assertEqual([tick.get_text() for tick in inset.get_yticklabels()],
                             ["200", "400", "600", "800", "1000", "1200"])
            self.assertEqual(inset.get_xlabel(), "Liberal Democrat\nVote Share\n(2019)")
            self.assertEqual(len(inset.patches), 25)
            for index, rectangle in enumerate(inset.patches):
                self.assertEqual(rectangle.get_xy(), (index // 5, index % 5))
                self.assertEqual(rectangle.get_facecolor(),
                                 colors.to_rgba(plotter.color_list_hex[index], alpha=0.85))
        finally:
            helpers.plt.close(figure)

    def test_all_map_panels_keep_shared_bins_data_and_year_order(self):
        frames = []
        for shift in [0, 0.05]:
            frames.append(gpd.GeoDataFrame({
                "Country name": ["England"] * 6,
                "Lab PC": np.linspace(0.1, 0.8, 6) + shift,
                "ASMR_f": np.linspace(500, 1000, 6) + shift * 100,
                "ASMR_m": np.linspace(700, 1300, 6) + shift * 200,
                "ProportionBadHealth": np.linspace(0.1, 0.4, 6) + shift,
                "ProportionDisabled": np.linspace(0.2, 0.5, 6) + shift,
                "geometry": [box(300000 + i * 10000, 300000, 305000 + i * 10000, 305000)
                             for i in range(6)],
            }, crs="EPSG:27700"))
        originals = [frame.copy(deep=True) for frame in frames]
        vote_edges = pd.concat([frame["Lab PC"] for frame in frames]).quantile(np.linspace(0, 1, 6))
        for kind, outcomes, labels in [
            ("asmr", ["ASMR_f", "ASMR_m"], ["Female ASMR", "Male ASMR"]),
            ("census", ["ProportionBadHealth", "ProportionDisabled"], ["Not good health", "Disability"]),
        ]:
            with self.subTest(kind=kind), patch.object(helpers, "_ensure_output_dirs"), \
                    patch.object(helpers, "_save_figure") as save, patch.object(helpers, "_write_derived"), \
                    patch.object(helpers, "_annotate_map_leaders"), contextlib.redirect_stdout(io.StringIO()):
                figure = getattr(helpers, "plot_bivariate_choropleth_map_" + kind)(*frames, ["Lab", "Labour"])
                try:
                    self.assertEqual(len(figure.axes), 4)
                    for panel, axis in enumerate(figure.axes):
                        frame = frames[panel // 2]
                        outcome = outcomes[panel % 2]
                        year = [2019, 2024][panel // 2]
                        prefix = f"{year} election" if kind == "census" else str(year)
                        self.assertEqual(axis.get_title(loc="right"), f"{prefix} | {labels[panel % 2]}")
                        self.assertEqual(axis.get_title(loc="left"), "abcd"[panel] + ".")
                        self.assertEqual(axis._left_title.get_fontweight(), "bold")
                        self.assertEqual(axis._right_title.get_fontweight(), "bold")
                        self.assertEqual(axis.get_xlim(), (125000, 660000))
                        self.assertEqual(axis.get_ylim(), (10000, 675000))
                        health_edges = pd.concat([f[outcome] for f in frames]).quantile(np.linspace(0, 1, 6))
                        plotter = helpers.BivariateChoroplethPlotter(vote_edges, health_edges)
                        expected = [plotter.get_bivariate_color(x, y) for x, y in zip(frame["Lab PC"], frame[outcome])]
                        np.testing.assert_array_equal(axis.collections[0].get_facecolors(),
                                                      colors.to_rgba_array(expected, alpha=0.85))
                        north = next(text for text in axis.texts if text.get_text() == "N")
                        self.assertEqual(north.xy[0], north.xyann[0])
                        self.assertGreater(north.xy[1], north.xyann[1])
                    save.assert_called_once()
                finally:
                    helpers.plt.close(figure)
        for frame, original in zip(frames, originals):
            pd.testing.assert_frame_equal(frame, original, check_exact=True)


if __name__ == "__main__":
    unittest.main()
