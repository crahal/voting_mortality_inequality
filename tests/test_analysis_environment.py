import contextlib
import io
import os
import sys
import tempfile
import unittest
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import nbformat

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import analysis_environment as environment


class AnalysisEnvironmentTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.requirements = Path(directory) / "requirements.txt"
        self.requirements.write_text(
            "# Runtime pins\n-c constraints.txt\n\nnumpy==1.26.4\nspreg==1.8.3\n"
            "not_needed==1.0; python_version < '3.0'\n"
        )
        self.enterContext(patch.object(environment, "REQUIREMENTS_PATH", self.requirements))
        self.enterContext(patch.object(environment.sys, "version_info", (3, 12, 7)))
        self.enterContext(patch.dict(environment.sys.modules, {
            "numpy": SimpleNamespace(__version__="1.26.4"),
            "spreg": SimpleNamespace(__version__="1.8.3"),
        }))
        self.versions = {"numpy": "1.26.4", "spreg": "1.8.3"}
        self.version = self.enterContext(patch.object(
            environment, "version", side_effect=lambda name: self.versions[name],
        ))

    def test_verified_versions_pass_and_comments_includes_markers_are_handled(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            environment.validate_analysis_environment()
        self.assertIn("matches requirements.txt", output.getvalue())
        self.assertIn(os.path.relpath(sys.executable), output.getvalue())
        self.assertNotIn(sys.executable, output.getvalue())
        self.assertEqual([call.args[0] for call in self.version.call_args_list], ["numpy", "spreg"])

    def test_wrong_numpy_identifies_the_kernel_and_required_version(self):
        self.versions["numpy"] = "2.5.4"
        with self.assertRaises(RuntimeError) as caught:
            environment.validate_analysis_environment()
        message = str(caught.exception)
        self.assertIn("numpy: installed 2.5.4; required ==1.26.4", message)
        self.assertIn("Voting mortality (pinned)", message)
        self.assertIn(os.path.relpath(sys.executable), message)
        self.assertNotIn(sys.executable, message)
        self.assertIn("Do not replace the pinned result hashes", message)

    def test_missing_spatial_dependency_is_reported_before_analysis(self):
        self.version.side_effect = lambda name: (
            self.versions[name] if name == "numpy" else self._missing(name)
        )
        with self.assertRaisesRegex(RuntimeError, "spreg: missing; required ==1.8.3"):
            environment.validate_analysis_environment()

    @staticmethod
    def _missing(name):
        raise PackageNotFoundError(name)

    def test_stale_import_after_installing_pins_requires_a_kernel_restart(self):
        with patch.dict(environment.sys.modules, {"numpy": SimpleNamespace(__version__="2.5.4")}):
            with self.assertRaisesRegex(RuntimeError, "this kernel has 2.5.4 loaded; restart it"):
                environment.validate_analysis_environment()

    def test_python_minor_version_is_checked(self):
        with patch.object(environment.sys, "version_info", (3, 13, 0)):
            with self.assertRaisesRegex(RuntimeError, "required 3.12"):
                environment.validate_analysis_environment()

    def test_notebook_checks_environment_before_importing_analysis_helpers(self):
        root = Path(__file__).resolve().parents[1]
        notebook = nbformat.read(root / "src/analysis.ipynb", as_version=4)
        first_code = next(cell.source for cell in notebook.cells if cell.cell_type == "code")
        self.assertLess(first_code.index("validate_analysis_environment()"), first_code.index("from helpers import"))
        self.assertEqual(notebook.metadata.kernelspec.name, "voting-mortality-inequality")


if __name__ == "__main__":
    unittest.main()
