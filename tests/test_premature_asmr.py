import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from scipy.stats import pearsonr, spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import helpers


class PrematureSnapshotTests(unittest.TestCase):
    def test_both_sources_download_and_verify_independently(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources, downloads = [], {}
            for dataset in ["2019_2024", "2021_premature"]:
                data = dataset.encode()
                url = f"https://example.test/{dataset}.xlsx"
                sources.append({
                    "dataset": dataset,
                    "path": f"data/raw/mortality/{dataset}.xlsx",
                    "snapshot_path": f"data/raw/mortality/snapshots/{dataset}_timestamp.xlsx",
                    "download": url, "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                })
                downloads[url] = data
            with patch.multiple(helpers, PROJECT_ROOT=root, RAW_DATA_SOURCES=sources,
                                RAW_DATA_SOURCE_EXTRA_FILES={}):
                with patch.object(helpers, "validate_raw_data_schema"):
                    with patch.object(helpers, "_fetch_mortality_download", side_effect=downloads.get) as fetch:
                        helpers.ensure_raw_data()
                    self.assertEqual(fetch.call_count, 2)
                for source in sources:
                    self.assertEqual(helpers.mortality_data_path(source["dataset"]).read_bytes(),
                                     downloads[source["download"]])
                with patch.object(helpers, "_fetch_mortality_download", return_value=b"new version"):
                    with self.assertWarnsRegex(RuntimeWarning, "2021 premature ASMR download has changed"):
                        helpers.ensure_mortality_snapshot(dataset="2021_premature")
                self.assertEqual(helpers.mortality_data_path("2021_premature").read_bytes(),
                                 b"2021_premature")

    def test_unknown_source_fails_before_download(self):
        with patch.object(helpers, "_fetch_mortality_download") as fetch:
            with self.assertRaisesRegex(ValueError, "Unknown mortality dataset"):
                helpers.ensure_mortality_snapshot(dataset="not_a_dataset")
        fetch.assert_not_called()

    def test_reader_uses_correct_sex_sheets_and_matches_codes(self):
        male = pd.DataFrame({"Parliamentary Constituency ": ["B", "A"], "ASMR": [200, 100]})
        female = pd.DataFrame({"Parliamentary Constituency ": ["A", "B"], "ASMR": [80, 160]})
        with patch.object(helpers, "mortality_data_path", return_value=Path("verified.xlsx")) as path:
            with patch.object(helpers.pd, "read_excel", side_effect=[male, female]) as read:
                rates = helpers.make_premature_asmr_2021().set_index("ONS ID")
        path.assert_called_once_with("2021_premature")
        self.assertEqual([call.kwargs for call in read.call_args_list],
                         [{"sheet_name": "1", "skiprows": 4}, {"sheet_name": "2", "skiprows": 4}])
        self.assertEqual(rates.loc["A", "PrematureASMR2021_m"], 100)
        self.assertEqual(rates.loc["A", "PrematureASMR2021_f"], 80)

    def test_duplicate_source_codes_fail(self):
        duplicated = pd.DataFrame({"Parliamentary Constituency ": ["A", "A"], "ASMR": [100, 200]})
        with patch.object(helpers, "mortality_data_path", return_value=Path("verified.xlsx")):
            with patch.object(helpers.pd, "read_excel", return_value=duplicated):
                with self.assertRaises(pd.errors.MergeError):
                    helpers.make_premature_asmr_2021()


class PrematureCorrelationTests(unittest.TestCase):
    def setUp(self):
        values = [3., 8., 1., 4.]
        self.frame = pd.DataFrame({
            "ONS ID": ["D", "A", "C", "B"],
            **{column: values for column in [
                "Con PC", "Lab PC", "Lib PC", "Brx PC", "RUK PC", "Vote PC",
                "ASMR_f", "ASMR_m", "ProportionBadHealth", "ProportionDisabled",
                "ProportionProvidesAnyUnpaidCare", "HealthDeprivationAndDisabilityRank",
            ]},
        }, index=[8, 2, 7, 3])
        self.rates = pd.DataFrame({
            "ONS ID": ["A", "B", "C"],
            "PrematureASMR2021_f": [100., 200., 150.],
            "PrematureASMR2021_m": [210., 270., 250.],
        })

    def test_new_rows_pairwise_complete_without_filtering_existing_outcomes(self):
        original = self.frame.copy(deep=True)
        with patch.object(helpers, "make_premature_asmr_2021", return_value=self.rates):
            coefficients, p_values = helpers.make_summary_tables(self.frame, self.frame, "2019")
        pd.testing.assert_frame_equal(self.frame, original, check_exact=True)
        self.assertEqual(len(coefficients), 16)
        coefficients = coefficients.set_index(["Statistic", "Variable"])
        p_values = p_values.set_index(["Statistic", "Variable"])
        for name, function in [("Spearman", spearmanr), ("Pearson", pearsonr)]:
            for variable in ["PrematureASMR2021_f", "PrematureASMR2021_m"]:
                pairs = original.merge(self.rates, on="ONS ID")
                expected_r, expected_p = function(pairs["Lab PC"], pairs[variable])
                self.assertEqual(coefficients.loc[(name, variable), "Lab PC"], expected_r)
                self.assertEqual(p_values.loc[(name, variable), "Lab PC"], expected_p)
                self.assertEqual(coefficients.loc[(name, variable), "N"], 3)
            self.assertEqual(coefficients.loc[(name, "ASMR_f"), "N"], 4)

    def test_2024_does_not_join_old_boundary_rates(self):
        with patch.object(helpers, "make_premature_asmr_2021") as read:
            coefficients, _ = helpers.make_summary_tables(self.frame, self.frame, "2024")
        read.assert_not_called()
        self.assertEqual(len(coefficients), 12)
        self.assertFalse(coefficients["Variable"].str.startswith("Premature").any())

    def test_full_export_has_both_new_outcomes_and_p_values(self):
        with patch.object(helpers, "make_premature_asmr_2021", return_value=self.rates):
            r19, p19 = helpers.make_summary_tables(self.frame, self.frame, "2019")
        r24, p24 = helpers.make_summary_tables(self.frame, self.frame, "2024")
        full = helpers.make_combined_correlation_p_value_table(r19, p19, r24, p24)
        new_rows = full[full["Health/deprivation measure"].str.startswith("Premature ASMR")]
        self.assertEqual(len(new_rows), 4)
        self.assertEqual(set(new_rows["Election year"]), {"2019"})
        self.assertTrue(new_rows["Labour"].str.contains(r"\(.+\)").all())


if __name__ == "__main__":
    unittest.main()
