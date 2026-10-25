import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import helpers


class ZeroVoteRobustnessTests(unittest.TestCase):
    def setUp(self):
        self.outcomes = [
            "ASMR_f", "ASMR_m", "ProportionBadHealth", "ProportionDisabled",
            "ProportionProvidesAnyUnpaidCare", "HealthDeprivationAndDisabilityRank",
        ]
        self.frame = pd.DataFrame({
            "ONS ID": list("ABCDEF"),
            "Con PC": [.1, .2, 0., .4, .5, .6],
            "Lab PC": [0., .2, .3, .4, np.nan, .6],
            "Lib PC": [.1, 0., .3, .4, .5, .6],
            "Brx PC": [0., 0., .3, .4, .5, .6],
            "RUK PC": [0., 0., .3, .4, .5, .6],
            "Vote PC": [.7, .6, .8, .9, .5, .4],
            **{outcome: [0., 40., 30., np.nan, 60., 20.] for outcome in self.outcomes},
        }, index=[7, 5, 2, 8, 1, 9])
        self.frame["ASMR_m"] = [10., 40., 30., 50., 60., 20.]
        self.premature = pd.DataFrame({
            "ONS ID": list("FABCDE"),
            "PrematureASMR2021_f": [100., 160., 130., 150., 120., np.nan],
            "PrematureASMR2021_m": [200., 260., 230., 250., 220., 240.],
        })

    def test_every_pair_matches_independent_calculation_without_mutating_inputs(self):
        original = self.frame.copy(deep=True)
        with patch.object(helpers, "make_premature_asmr_2021", return_value=self.premature):
            result = helpers.make_zero_vote_robustness_table(self.frame, "2019")
        self.assertEqual(len(result), 80)
        joined = self.frame.merge(self.premature, on="ONS ID", how="left")
        lookup = result.set_index(["Health/deprivation measure", "Political measure", "Correlation"])
        political_labels = {
            "Con PC": "Conservative", "Lab PC": "Labour", "Lib PC": "Liberal Democrat",
            "Brx PC": "Brexit Party", "Vote PC": "Turnout",
        }
        for outcome in self.outcomes + ["PrematureASMR2021_f", "PrematureASMR2021_m"]:
            for measure, label in political_labels.items():
                pairs = joined[[measure, outcome]].dropna()
                retained = pairs.loc[pairs[measure].ne(0)]
                for statistic, function in [("Spearman", spearmanr), ("Pearson", pearsonr)]:
                    with self.subTest(outcome=outcome, measure=measure, statistic=statistic):
                        row = lookup.loc[(helpers.PUBLICATION_VARIABLE_LABELS[outcome], label, statistic)]
                        self.assertEqual(row["N (all)"], len(pairs))
                        self.assertEqual(row["N (non-zero)"], len(retained))
                        self.assertEqual(row["Zeros excluded"], len(pairs) - len(retained))
                        for sample, values in [("all", pairs), ("non-zero", retained)]:
                            if len(values) < 3:
                                self.assertTrue(pd.isna(row[f"Coefficient ({sample})"]))
                                self.assertTrue(pd.isna(row[f"p-value ({sample})"]))
                            else:
                                coefficient, p_value = function(values[measure], values[outcome])
                                self.assertEqual(row[f"Coefficient ({sample})"], coefficient)
                                self.assertEqual(row[f"p-value ({sample})"], p_value)
                        np.testing.assert_equal(row["Coefficient change"],
                                                row["Coefficient (non-zero)"] - row["Coefficient (all)"])
        pd.testing.assert_frame_equal(self.frame, original, check_exact=True)

    def test_party_zeros_do_not_exclude_other_parties_or_turnout(self):
        table = helpers.make_zero_vote_robustness_table(self.frame, "2024")
        rows = table.loc[
            table["Health/deprivation measure"].eq("ASMR, male") & table["Correlation"].eq("Pearson")
        ].set_index("Political measure")
        self.assertEqual(rows.loc["Conservative", "N (non-zero)"], 5)
        self.assertEqual(rows.loc["Labour", "N (non-zero)"], 4)
        self.assertEqual(rows.loc["Liberal Democrat", "N (non-zero)"], 5)
        self.assertEqual(rows.loc["Reform UK", "N (non-zero)"], 4)
        self.assertEqual(rows.loc["Turnout", "N (non-zero)"], 6)
        self.assertEqual(rows.loc["Turnout", "Coefficient change"], 0)

    def test_zero_outcomes_are_retained_and_missing_pairs_are_not_counted_as_zero_exclusions(self):
        frame = self.frame.copy()
        frame.loc[8, "Con PC"] = 0.  # This constituency lacks female ASMR already.
        table = helpers.make_zero_vote_robustness_table(frame, "2024")
        row = table.loc[
            table["Health/deprivation measure"].eq("ASMR, female")
            & table["Political measure"].eq("Conservative") & table["Correlation"].eq("Spearman")
        ].iloc[0]
        self.assertEqual(row["N (all)"], 5)
        self.assertEqual(row["N (non-zero)"], 4)  # Includes the zero health outcome in A.
        self.assertEqual(row["Zeros excluded"], 1)

    def test_zero_turnout_is_only_removed_from_turnout_correlations(self):
        frame = self.frame.copy()
        frame.loc[7, "Vote PC"] = 0.
        table = helpers.make_zero_vote_robustness_table(frame, "2024")
        rows = table.loc[table["Health/deprivation measure"].eq("ASMR, male")]
        self.assertTrue(rows.loc[rows["Political measure"].eq("Turnout"), "Zeros excluded"].eq(1).all())
        self.assertTrue(rows.loc[rows["Political measure"].eq("Conservative"), "N (non-zero)"].eq(5).all())

    def test_2021_is_2019_only_and_all_primary_coefficients_are_unchanged(self):
        for year in ["2019", "2024"]:
            with patch.object(helpers, "make_premature_asmr_2021", return_value=self.premature) as read:
                before = helpers.make_summary_tables(self.frame, self.frame, year)
                table = helpers.make_zero_vote_robustness_table(self.frame, year)
                after = helpers.make_summary_tables(self.frame, self.frame, year)
            if year == "2024":
                read.assert_not_called()
                self.assertFalse(table["Mortality year"].eq("2021").any())
                self.assertEqual(len(table), 60)
            else:
                rows = table.loc[table["Mortality year"].eq("2021")]
                self.assertEqual(len(rows), 20)
                self.assertTrue(rows["Election year"].eq("2019").all())
            for original, repeated, column in zip(before, after, ["Coefficient (all)", "p-value (all)"]):
                pd.testing.assert_frame_equal(original, repeated, check_exact=True)
                for _, row in table.iterrows():
                    source = original.loc[
                        original["Variable"].map(helpers.PUBLICATION_VARIABLE_LABELS).eq(row["Health/deprivation measure"])
                        & original["Statistic"].eq(row["Correlation"])
                    ].iloc[0]
                    label = row["Political measure"]
                    measure = {"Brexit Party": "Brx PC", "Reform UK": "RUK PC"}.get(label)
                    if measure is None:
                        measure = next(key for key, value in helpers.PUBLICATION_CORRELATION_TABLE_COLUMN_LABELS.items()
                                       if value == label)
                    self.assertEqual(row[column], source[measure])

    def test_unestimable_samples_are_explicit_without_scipy_warnings(self):
        frame = self.frame.copy()
        frame["Con PC"] = 0.
        frame["Lab PC"] = [.1, 0., 0., 0., 0., 0.]
        frame["Lib PC"] = [.1, .2, 0., 0., 0., 0.]
        frame["RUK PC"] = .1
        with patch.object(helpers, "pearsonr", wraps=pearsonr) as pearson:
            table = helpers.make_zero_vote_robustness_table(frame, "2024")
        self.assertTrue(table.loc[table["Political measure"].ne("Turnout"), "Coefficient (non-zero)"].isna().all())
        self.assertTrue(table.loc[table["Political measure"].ne("Turnout"), "p-value (non-zero)"].isna().all())
        for args, _ in pearson.call_args_list:
            self.assertGreaterEqual(len(args[0]), 3)
            self.assertGreater(args[0].nunique(), 1)
        display = helpers.make_zero_vote_robustness_display_table(table)
        self.assertTrue(display.loc[display["Political measure"].ne("Turnout"),
                                    "Non-zero votes: coefficient (p)"].eq("Not estimable").all())

    def test_display_and_csv_preserve_unrounded_comparison_data(self):
        table = helpers.make_zero_vote_robustness_table(self.frame, "2024")
        original = table.copy(deep=True)
        display = helpers.make_zero_vote_robustness_display_table(table)
        self.assertIn("All votes: coefficient (p)", display)
        self.assertIn("Non-zero votes: coefficient (p)", display)
        self.assertEqual(len(display), len(table))
        pd.testing.assert_frame_equal(table, original, check_exact=True)
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(helpers, "TABLES_DIR", Path(directory) / "tables"):
                path = helpers.export_zero_vote_robustness_table(table)
            saved = pd.read_csv(path, keep_default_na=False, na_values=[""],
                                dtype={"Election year": str}, float_precision="round_trip")
        self.assertEqual(len(saved), len(table))
        for column in ["Coefficient (all)", "Coefficient (non-zero)", "p-value (all)", "p-value (non-zero)"]:
            np.testing.assert_equal(saved[column].to_numpy(), table[column].to_numpy())

    def test_invalid_year_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "year must be"):
            helpers.make_zero_vote_robustness_table(self.frame, "2021")


if __name__ == "__main__":
    unittest.main()
