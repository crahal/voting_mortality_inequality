import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import nbformat
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_repository
import manage_data
import run_analysis
import verify_results


class RepositoryCheckTests(unittest.TestCase):
    def test_runner_temp_is_configured_at_step_scope(self):
        import yaml

        root = Path(__file__).resolve().parents[1]
        workflow = yaml.safe_load((root / ".github/workflows/checks.yml").read_text())
        job = workflow["jobs"]["checks"]
        self.assertNotIn("MPLCONFIGDIR", job["env"])
        step = next(step for step in job["steps"] if step.get("name") == "Test with synthetic data")
        self.assertEqual(step["env"]["MPLCONFIGDIR"], "${{ runner.temp }}/matplotlib")

    def test_dependency_constraints_are_valid_exact_pins(self):
        from packaging.requirements import Requirement
        from packaging.utils import canonicalize_name

        root = Path(__file__).resolve().parents[1]
        lines = (root / "requirements-constraints.txt").read_text().splitlines()
        constraints = {}
        for line in lines:
            if not line.strip() or line.startswith("#"):
                continue
            requirement = Requirement(line)
            self.assertIsNone(requirement.url)
            self.assertEqual(len(requirement.specifier), 1)
            self.assertEqual(next(iter(requirement.specifier)).operator, "==")
            name = canonicalize_name(requirement.name)
            self.assertNotIn(name, constraints)
            constraints[name] = requirement.specifier
        self.assertIn("-c requirements-constraints.txt", (root / "requirements.txt").read_text())
        for filename in ["requirements.txt", "requirements-dev.txt"]:
            declared = set()
            for line in (root / filename).read_text().splitlines():
                if not line.strip() or line.startswith(("#", "-")):
                    continue
                requirement = Requirement(line)
                name = canonicalize_name(requirement.name)
                with self.subTest(filename=filename, dependency=name):
                    self.assertIsNone(requirement.url)
                    self.assertNotIn(name, declared)
                    self.assertIn(name, constraints)
                    self.assertEqual(requirement.specifier, constraints[name])
                declared.add(name)
            if filename == "requirements.txt":
                self.assertTrue({"ipython", "jupyter-client", "nbclient", "nbformat", "ipykernel"} <= declared)

    def test_markdown_and_html_links_are_parsed_without_code_examples(self):
        text = '[Guide](docs/guide.md) ![Figure](assets/plot.png) <img src="assets/header.png" />\n\n'
        text += '```text\n[Not a link](missing.txt)\n```\n'
        self.assertEqual(check_repository.markdown_links(text),
                         ["docs/guide.md", "assets/plot.png", "assets/header.png"])

    def test_link_checks_handle_fragments_and_encoded_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "with space.md"
            target.touch()
            readme = root / "README.md"
            readme.write_text('[Local](with%20space.md#section) [Section](#section) [Web](https://example.test)')
            check_repository.check_document_links(readme, root)
            readme.write_text('[Missing](missing.md)')
            with self.assertRaisesRegex(ValueError, "broken local link"):
                check_repository.check_document_links(readme, root)

    def test_notebook_syntax_and_saved_errors_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "example.ipynb"
            notebook = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell("x = 1")])
            nbformat.write(notebook, path)
            check_repository.check_notebook(path)
            notebook.cells[0].source = "x ="
            nbformat.write(notebook, path)
            with self.assertRaises(SyntaxError):
                check_repository.check_notebook(path)
            notebook.cells[0].source = "raise ValueError()"
            notebook.cells[0].outputs = [nbformat.v4.new_output(
                "error", ename="ValueError", evalue="example", traceback=[],
            )]
            nbformat.write(notebook, path)
            with self.assertRaisesRegex(ValueError, "saved error"):
                check_repository.check_notebook(path)


class DataCommandTests(unittest.TestCase):
    def test_verify_is_explicitly_offline_and_fetch_still_verifies(self):
        for command, download in [("verify", False), ("fetch", True)]:
            with self.subTest(command=command), patch.object(manage_data.helpers, "ensure_raw_data") as ensure:
                manage_data.main([command])
                ensure.assert_called_once_with(download=download, verify=True)

    def test_sources_does_not_fetch(self):
        with patch.object(manage_data.helpers, "ensure_raw_data") as ensure, \
                patch.object(manage_data.helpers, "raw_data_sources_markdown", return_value="manifest"), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            manage_data.main(["sources"])
        ensure.assert_not_called()
        self.assertEqual(output.getvalue(), "manifest\n")


class NotebookRunnerTests(unittest.TestCase):
    def test_current_python_kernel_is_closed_on_success_and_failure(self):
        for failure in [False, True]:
            with self.subTest(failure=failure), \
                    patch.object(run_analysis.nbformat, "read", return_value=nbformat.v4.new_notebook()), \
                    patch.object(run_analysis.nbformat, "write") as write, \
                    patch.object(run_analysis, "KernelManager") as manager_class, \
                    patch.object(run_analysis, "NotebookClient") as client_class, \
                    patch.object(verify_results, "validate_analysis_environment") as environment, \
                    patch.object(verify_results, "main") as verify, \
                    patch.object(verify_results, "verify_exported_robustness") as robustness:
                manager = manager_class.return_value
                manager.has_kernel = True
                if failure:
                    client_class.return_value.execute.side_effect = RuntimeError("cell failed")
                    with self.assertRaisesRegex(RuntimeError, "cell failed"):
                        run_analysis.main()
                    write.assert_not_called()
                    verify.assert_not_called()
                else:
                    run_analysis.main()
                    write.assert_called_once()
                    verify.assert_called_once_with([])
                    robustness.assert_called_once_with()
                self.assertEqual(manager.kernel_spec.argv[0], sys.executable)
                if not failure:
                    self.assertEqual(write.call_args.args[0].metadata.kernelspec.name,
                                     "voting-mortality-inequality")
                manager.shutdown_kernel.assert_called_once_with(now=True)
                environment.assert_called_once_with()

    def test_wrong_environment_stops_runner_and_verifier_before_loading_any_data(self):
        with patch.object(verify_results, "validate_analysis_environment", side_effect=RuntimeError("wrong kernel")), \
                patch.object(run_analysis.nbformat, "read") as read, \
                patch.object(verify_results.helpers, "ensure_raw_data") as fetch:
            with self.assertRaisesRegex(RuntimeError, "wrong kernel"):
                run_analysis.main()
            with self.assertRaisesRegex(RuntimeError, "wrong kernel"):
                verify_results.main([])
            read.assert_not_called()
            fetch.assert_not_called()


class ResultHashTests(unittest.TestCase):
    def setUp(self):
        self.coefficients = pd.DataFrame({
            "Variable": ["ASMR_f", "PrematureASMR2021_f"],
            "N": [4, 3], "Lab PC": [0.25, 0.4],
        })
        self.p_values = self.coefficients.assign(**{"Lab PC": [0.1, 0.2]})
        self.expected = {}
        for name, table in [("coefficients", self.coefficients), ("p_values", self.p_values)]:
            self.expected[name] = verify_results.table_hash(table)
            self.expected[name + "_without_2021"] = verify_results.table_hash(table.iloc[:1].reset_index(drop=True))

    def test_full_and_historical_hashes_are_checked_without_mutation(self):
        original = self.coefficients.copy(deep=True)
        verify_results.check_tables(self.coefficients, self.p_values, self.expected)
        pd.testing.assert_frame_equal(self.coefficients, original, check_exact=True)
        altered = dict(self.expected, coefficients_without_2021="incorrect")
        with self.assertRaisesRegex(ValueError, "coefficients_without_2021 changed"):
            verify_results.check_tables(self.coefficients, self.p_values, altered)

    def test_reference_hashes_match_the_notebook_contract(self):
        baseline = json.loads((verify_results.ROOT / "tests/fixtures/summary_hashes.json").read_text())
        self.assertEqual(set(baseline["years"]), {"2019", "2024"})
        for year, expected in baseline["years"].items():
            self.assertEqual(set(expected), set(self.expected))
            self.assertEqual(expected["coefficients"], verify_results.helpers.EXPECTED_SUMMARY_TABLE_HASHES[year])
            for fingerprint in expected.values():
                self.assertRegex(fingerprint, r"^[0-9a-f]{64}$")

    def test_coefficient_p_value_and_sample_size_changes_fail(self):
        for target, column in [("coefficients", "Lab PC"), ("p_values", "Lab PC"), ("coefficients", "N")]:
            with self.subTest(target=target, column=column):
                coefficients, p_values = self.coefficients.copy(), self.p_values.copy()
                changed = coefficients if target == "coefficients" else p_values
                changed.loc[0, column] += 1
                with self.assertRaisesRegex(ValueError, target + " changed"):
                    verify_results.check_tables(coefficients, p_values, self.expected)

    def test_robustness_export_changes_are_rejected(self):
        import hashlib

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests/fixtures").mkdir(parents=True)
            (root / "output/tables").mkdir(parents=True)
            content = b"coefficient,p\n0.5,0.02\n"
            (root / "tests/fixtures/robustness_hashes.json").write_text(json.dumps({
                "files": {"test.csv": hashlib.sha256(content).hexdigest()},
            }))
            path = root / "output/tables/test.csv"
            path.write_bytes(content)
            with patch.object(verify_results, "ROOT", root):
                verify_results.verify_exported_robustness()
                path.write_bytes(b"coefficient,p\n0.6,0.02\n")
                with self.assertRaisesRegex(ValueError, "test.csv changed"):
                    verify_results.verify_exported_robustness()


if __name__ == "__main__":
    unittest.main()
