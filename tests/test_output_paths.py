import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from IPython.core.formatters import DisplayFormatter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import helpers


class NotebookFileLinkTests(unittest.TestCase):
    def test_html_and_plain_text_both_use_relative_paths(self):
        with tempfile.TemporaryDirectory(prefix="notebook links ") as directory:
            root = Path(directory).resolve()
            (root / "src").mkdir()
            path = root / "output/tables/a & b.docx"
            path.parent.mkdir(parents=True)
            path.touch()
            for cwd, expected in [(root, "output/tables/a & b.docx"),
                                  (root / "src", "../output/tables/a & b.docx")]:
                with self.subTest(cwd=cwd), contextlib.chdir(cwd):
                    for input_path in [path, expected]:
                        link = helpers.RelativeFileLink(input_path)
                        data, _ = DisplayFormatter().format(link)
                        self.assertEqual(data["text/plain"], expected)
                        self.assertIn(expected.replace("&", "&amp;"), data["text/html"])
                        self.assertNotIn(str(root), str(data))
                        self.assertEqual(Path(link.path).resolve(), path)

    def test_missing_file_message_is_also_relative(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.chdir(directory):
            link = helpers.RelativeFileLink(Path(directory) / "missing.csv")
            data, _ = DisplayFormatter().format(link)
            self.assertEqual(data["text/plain"], "missing.csv")
            self.assertIn("doesn't exist", data["text/html"])
            self.assertNotIn(directory, str(data))


class TableOutputPathTests(unittest.TestCase):
    def setUp(self):
        for name in ["_ensure_output_dirs", "make_manuscript_correlation_p_value_rows",
                     "_docx_manuscript_table", "make_combined_correlation_p_value_table"]:
            self.enterContext(patch.object(helpers, name))
        self.writer = self.enterContext(patch.object(helpers, "_write_docx_table"))

    def test_both_docx_exports_report_paths_relative_to_each_working_directory(self):
        with tempfile.TemporaryDirectory(prefix="table exports ") as directory:
            root = Path(directory).resolve()
            (root / "src").mkdir()
            tables = root / "output/tables"
            for cwd, prefix in [(root, Path("output/tables")),
                                (root / "src", Path("../output/tables"))]:
                for export in [helpers.export_correlation_tables_docx,
                               helpers.export_full_correlation_tables_docx]:
                    with self.subTest(cwd=cwd, export=export.__name__), contextlib.chdir(cwd), \
                            patch.object(helpers, "TABLES_DIR", tables), \
                            contextlib.redirect_stdout(io.StringIO()) as output:
                        path = export(None, None, None, None, filename="my table.docx")
                        reported = Path(output.getvalue().strip().removeprefix("Wrote "))
                        self.assertEqual(reported.resolve(), path)
                    self.assertEqual(output.getvalue(), f"Wrote {prefix / 'my table.docx'}\n")
                    self.assertNotIn(str(root), output.getvalue())
                    self.assertEqual(self.writer.call_args.args[0], tables / "my table.docx")

    def test_failed_docx_exports_are_not_reported_as_saved(self):
        self.writer.side_effect = OSError("export failed")
        for export in [helpers.export_correlation_tables_docx,
                       helpers.export_full_correlation_tables_docx]:
            with self.subTest(export=export.__name__), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaisesRegex(OSError, "export failed"):
                    export(None, None, None, None)
            self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
