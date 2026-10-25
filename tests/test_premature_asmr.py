import contextlib
import hashlib
import io
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
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

    def test_full_docx_is_main_table_1_and_preserves_every_cell(self):
        with patch.object(helpers, "make_premature_asmr_2021", return_value=self.rates):
            r19, p19 = helpers.make_summary_tables(self.frame, self.frame, "2019")
        r24, p24 = helpers.make_summary_tables(self.frame, self.frame, "2024")
        tables = [r19, p19, r24, p24]
        originals = [table.copy(deep=True) for table in tables]
        expected = helpers.make_combined_correlation_p_value_table(*tables)
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(helpers, "TABLES_DIR", Path(directory)), patch.object(helpers, "_ensure_output_dirs"):
                path = helpers.export_full_correlation_tables_docx(*tables)
            with zipfile.ZipFile(path) as archive:
                root = ET.fromstring(archive.read("word/document.xml"))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs = ["".join(p.itertext()) for p in root.findall("w:body/w:p", ns)]
        self.assertEqual(paragraphs[0],
                         "Table 1. Constituency-level correlations of political party vote share and turnout "
                         "with mortality, Census health and caring measures, and health deprivation in England.")
        self.assertEqual(paragraphs[1:], [
            "Entries are Spearman's \u03c1 or Pearson's r, with two-sided unadjusted p-values in parentheses; "
            "these p-values do not account for spatial dependence. N denotes constituencies. "
            "The 2021 rows are premature ASMRs paired only with 2019 voting; "
            "the election-year column therefore remains 2019. Census measures refer to 2021, "
            "separately tabulated to each election geography. Deprivation ranks use the 2019 and 2025 "
            "releases for the 2019 and 2024 election comparisons respectively; rank 1 denotes greatest deprivation. "
            "Brexit/Reform UK denotes the party relevant to the election year. "
            "The Speaker is excluded; zero party vote shares are retained.",
        ])
        rows = root.findall(".//w:tbl/w:tr", ns)
        cells = [["".join(cell.itertext()) for cell in row.findall("w:tc", ns)] for row in rows]
        self.assertEqual(cells, [list(expected.columns)] + expected.astype(str).values.tolist())
        self.assertEqual(len(cells), 29)
        self.assertEqual(root.find(".//w:pgSz", ns).get(f"{{{ns['w']}}}orient"), "landscape")
        for table, original in zip(tables, originals):
            pd.testing.assert_frame_equal(table, original, check_exact=True)

    def test_mortality_year_displays_preserve_every_coefficient_and_p_value(self):
        with patch.object(helpers, "make_premature_asmr_2021", return_value=self.rates):
            r19, p19 = helpers.make_summary_tables(self.frame, self.frame, "2019")
        r24, p24 = helpers.make_summary_tables(self.frame, self.frame, "2024")
        for tables in [(r19, r24), (p19, p24)]:
            originals = [table.copy(deep=True) for table in tables]
            groups = []
            for mortality_year in [2019, 2021, 2024, None]:
                with self.subTest(year=mortality_year, tables="p" if tables[0] is p19 else "r"):
                    display = helpers.make_mortality_year_display_table(*tables, mortality_year)
                    groups.append(display)
                    self.assertEqual(len(display), 16 if mortality_year is None else 4)
                    self.assertEqual(set(display["Correlation"]), {"Spearman", "Pearson"})
                    self.assertEqual(set(display["Mortality year"]),
                                     {"" if mortality_year is None else str(mortality_year)})
                    if mortality_year is None:
                        self.assertEqual(set(display["Election year"]), {"2019", "2024"})
                        self.assertFalse(display["Health/deprivation measure"].str.contains("ASMR").any())
                    else:
                        self.assertEqual(set(display["Election year"]),
                                         {"2019" if mortality_year == 2021 else str(mortality_year)})
                        self.assertEqual(set(display["N"]), {3 if mortality_year == 2021 else 4})
            lookup = pd.concat(groups).set_index(["Correlation", "Election year", "Health/deprivation measure"])
            self.assertTrue(lookup.index.is_unique)
            self.assertEqual(len(lookup), 28)
            for table, original in zip(tables, originals):
                pd.testing.assert_frame_equal(table, original, check_exact=True)
                for _, row in table.iterrows():
                    key = (row["Statistic"], row["Year"], helpers.PUBLICATION_VARIABLE_LABELS[row["Variable"]])
                    self.assertEqual(lookup.loc[key, "N"], row["N"])
                    for column in helpers._correlation_value_columns(table):
                        name = "Brx/RUK PC" if column in {"Brx PC", "RUK PC"} else column
                        label = helpers.PUBLICATION_CORRELATION_TABLE_COLUMN_LABELS[name]
                        self.assertEqual(lookup.loc[key, label], row[column])

    def test_mortality_year_display_rejects_unknown_year(self):
        with self.assertRaisesRegex(ValueError, "Unsupported mortality year"):
            helpers.make_mortality_year_display_table(pd.DataFrame(), pd.DataFrame(), 2020)

    def test_manuscript_statistics_prints_2021_for_both_sexes(self):
        with patch.object(helpers, "make_premature_asmr_2021", return_value=self.rates):
            r19, _ = helpers.make_summary_tables(self.frame, self.frame, "2019")
        r24, _ = helpers.make_summary_tables(self.frame, self.frame, "2024")
        output = io.StringIO()
        with patch.object(helpers, "make_leader_asmr_table", return_value=pd.DataFrame(columns=["Year", "Leader"])), \
                contextlib.redirect_stdout(output):
            helpers.print_manuscript_statistics(r19, r24)
        printed = output.getvalue()
        self.assertIn("2019 election only; no 2024 boundary proxy", printed)
        for sex, variable in [("Male", "PrematureASMR2021_m"), ("Female", "PrematureASMR2021_f")]:
            spearman = helpers._summary_table_coefficient(r19, "Spearman", variable, "Lab PC")
            pearson = helpers._summary_table_coefficient(r19, "Pearson", variable, "Lab PC")
            self.assertIn(f"{sex} premature ASMR (2021): Spearman rho = {spearman:.3f}; "
                          f"Pearson r = {pearson:.3f}; N = 3.", printed)

    def test_manuscript_table_includes_2021_for_2019_only(self):
        with patch.object(helpers, "make_premature_asmr_2021", return_value=self.rates):
            r19, p19 = helpers.make_summary_tables(self.frame, self.frame, "2019")
        r24, p24 = helpers.make_summary_tables(self.frame, self.frame, "2024")
        table = helpers.make_manuscript_correlation_p_value_table(r19, p19, r24, p24)
        self.assertEqual(table.shape, (13, 12))
        for sex in ["female", "male"]:
            label = f"Premature ASMR (2021), {sex}"
            self.assertIn((label, "2019"), table.columns)
            self.assertNotIn((label, "2024"), table.columns)
            self.assertEqual(table.iloc[-1][(label, "2019")], "3")
            for statistic, row in [("Spearman", 1), ("Pearson", 7)]:
                variable = "PrematureASMR2021_f" if sex == "female" else "PrematureASMR2021_m"
                coefficient = helpers._summary_table_row(r19, statistic, variable)["Lab PC"]
                p_value = helpers._summary_table_row(p19, statistic, variable)["Lab PC"]
                expected = helpers._format_manuscript_coefficient_with_p_value(coefficient, p_value)
                self.assertEqual(table.iloc[row][(label, "2019")], expected)
            self.assertEqual(table.iloc[4][(label, "2019")], "")
            self.assertEqual(table.iloc[10][(label, "2019")], "")
        self.assertEqual(table.iloc[-1][("ASMR (female)", "2019")], "4")

    def test_manuscript_docx_headers_and_grid_match_the_new_columns(self):
        with patch.object(helpers, "make_premature_asmr_2021", return_value=self.rates):
            r19, p19 = helpers.make_summary_tables(self.frame, self.frame, "2019")
        r24, p24 = helpers.make_summary_tables(self.frame, self.frame, "2024")
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(helpers, "TABLES_DIR", Path(directory)), patch.object(helpers, "_ensure_output_dirs"):
                path = helpers.export_correlation_tables_docx(r19, p19, r24, p24)
            with zipfile.ZipFile(path) as archive:
                root = ET.fromstring(archive.read("word/document.xml"))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        title = "".join(root.find("w:body/w:p", ns).itertext())
        self.assertTrue(title.startswith("Online compact summary."))
        self.assertFalse(title.startswith("Table 1."))
        table = root.find(".//w:tbl", ns)
        grid = table.findall("w:tblGrid/w:gridCol", ns)
        self.assertEqual(len(grid), 12)
        self.assertEqual(sum(int(col.attrib[f"{{{ns['w']}}}w"]) for col in grid), 16450)
        rows = table.findall("w:tr", ns)
        self.assertEqual(len(rows), 15)
        labels = [node.text for node in rows[0].findall(".//w:t", ns)]
        self.assertIn("Premature ASMR (2021), female", labels)
        self.assertIn("Premature ASMR (2021), male", labels)
        year_labels = [node.text or "" for node in rows[1].findall(".//w:t", ns)]
        self.assertEqual(year_labels, ["", "", "2019", "2024", "2019", "2024",
                                       "2019", "2019", "2019", "2024", "2019", "2024"])
        for row in rows[1:]:
            self.assertEqual(len(row.findall("w:tc", ns)), 12)

    def test_portrait_rows_leave_unavailable_2024_comparisons_blank(self):
        with patch.object(helpers, "make_premature_asmr_2021", return_value=self.rates):
            r19, p19 = helpers.make_summary_tables(self.frame, self.frame, "2019")
        r24, p24 = helpers.make_summary_tables(self.frame, self.frame, "2024")
        rows = helpers.make_portrait_correlation_p_value_rows(r19, p19, r24, p24)
        self.assertEqual(len(rows), 78)
        self.assertTrue(all(row[4] == "" for row in rows[26:52]))


if __name__ == "__main__":
    unittest.main()
