import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

import matplotlib
matplotlib.use("Agg")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import helpers


class FigureExportTests(unittest.TestCase):
    def setUp(self):
        font_check = patch.object(helpers, "_require_helvetica")
        font_check.start()
        self.addCleanup(font_check.stop)

    def test_all_formats_are_reported_relative_to_the_working_directory(self):
        with tempfile.TemporaryDirectory(prefix="figure exports ") as directory:
            root = Path(directory).resolve()
            (root / "src").mkdir()
            figures = root / "output" / "figures"
            for cwd, prefix in [(root, Path("output/figures")),
                                (root / "src", Path("../output/figures"))]:
                figure = Mock(spec=["savefig"])
                with self.subTest(cwd=cwd), contextlib.chdir(cwd), \
                        patch.object(helpers, "FIGURES_DIR", figures), \
                        contextlib.redirect_stdout(io.StringIO()) as output:
                    helpers._save_figure(figure, "labour_asmr_scatter")
                self.assertEqual(figure.savefig.call_args_list, [
                    call(figures / "labour_asmr_scatter.pdf", bbox_inches="tight"),
                    call(figures / "labour_asmr_scatter.svg", bbox_inches="tight"),
                    call(figures / "labour_asmr_scatter.png", bbox_inches="tight", dpi=800),
                ])
                self.assertEqual(output.getvalue().splitlines(), [
                    f"Wrote {prefix / ('labour_asmr_scatter.' + extension)}"
                    for extension in ["pdf", "svg", "png"]
                ])
                self.assertNotIn(str(root), output.getvalue())

    def test_failed_export_is_not_reported_as_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            figure = Mock(spec=["savefig"])
            figure.savefig.side_effect = [None, OSError("export failed")]
            with contextlib.chdir(root), \
                    patch.object(helpers, "FIGURES_DIR", root / "output" / "figures"), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaisesRegex(OSError, "export failed"):
                    helpers._save_figure(figure, "example")
            self.assertEqual(output.getvalue(), f"Wrote {Path('output/figures/example.pdf')}\n")
            self.assertEqual(figure.savefig.call_count, 2)

    def test_reported_paths_locate_real_exports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "src").mkdir()
            figures = root / "output" / "figures"
            figures.mkdir(parents=True)
            figure = helpers.plt.figure(figsize=(0.5, 0.5))
            self.addCleanup(helpers.plt.close, figure)
            axis = figure.add_axes([0, 0, 1, 1])
            axis.plot([0, 1], [0, 1])
            axis.set_axis_off()
            with contextlib.chdir(root / "src"), \
                    patch.object(helpers, "FIGURES_DIR", figures), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                helpers._save_figure(figure, "example")
                for line in output.getvalue().splitlines():
                    path = Path(line.removeprefix("Wrote "))
                    self.assertFalse(path.is_absolute())
                    self.assertTrue(path.is_file())
                    self.assertGreater(path.stat().st_size, 0)
            self.assertEqual(len(output.getvalue().splitlines()), 3)


if __name__ == "__main__":
    unittest.main()
