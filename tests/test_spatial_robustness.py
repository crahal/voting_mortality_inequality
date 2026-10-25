import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import false_discovery_control, norm
from shapely.geometry import box
from spreg import MoranRes
from threadpoolctl import threadpool_limits

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import helpers
import spatial_robustness as spatial


def example_frame():
    rng = np.random.default_rng(321)
    x = rng.uniform(.05, .8, 64)
    regions = [f"Region {i // 4 + 2 * (j // 4)}" for j in range(8) for i in range(8)]
    y = 100 + 12 * x / .1 + np.array([int(region[-1]) * 20 for region in regions]) + rng.normal(0, 8, 64)
    return gpd.GeoDataFrame({
        "ONS ID": [f"E{i:04d}" for i in range(64)],
        "Region name": regions, "Lab PC": x, "ASMR_f": y,
        "PrematureASMR2021_m": y * .7 + rng.normal(0, 2, 64),
        "Country name": "England", "First party": "Lab",
    }, geometry=[box(i * 1000, j * 1000, (i + 1) * 1000, (j + 1) * 1000)
                 for j in range(8) for i in range(8)], crs=27700)


class SpatialWeightsTests(unittest.TestCase):
    def test_row_standardisation_ids_and_reciprocal_neighbour_support(self):
        frame = example_frame()
        for kind in spatial.WEIGHT_LABELS:
            weights, audit, edges = spatial.build_spatial_weights(frame, kind)
            self.assertEqual(weights.id_order, frame["ONS ID"].tolist())
            np.testing.assert_allclose(np.asarray(weights.sparse.sum(axis=1)).ravel(), 1)
            self.assertFalse(weights.islands)
            self.assertEqual(audit["Final components"], 1)
            for code, neighbours in weights.neighbors.items():
                self.assertNotIn(code, neighbours)
                for neighbour in neighbours:
                    self.assertIn(code, weights.neighbors[neighbour])
            _, repeated_audit, repeated_edges = spatial.build_spatial_weights(frame, kind)
            self.assertEqual(audit["Weights SHA-256"], repeated_audit["Weights SHA-256"])
            pd.testing.assert_frame_equal(edges, repeated_edges, check_exact=True)

    def test_queen_island_is_attached_and_recorded_without_dropping_it(self):
        frame = example_frame()
        frame.loc[63, "geometry"] = box(100000, 100000, 101000, 101000)
        weights, audit, _ = spatial.build_spatial_weights(frame, "queen")
        self.assertEqual(weights.n, 64)
        self.assertFalse(weights.islands)
        self.assertIn('"E0063"', audit["Isolated-area links added"])
        self.assertEqual(audit["Initial components"], 2)
        self.assertEqual(audit["Final components"], 1)

    def test_invalid_crs_codes_size_and_kind_are_rejected(self):
        frame = example_frame()
        with self.assertRaisesRegex(ValueError, "British National Grid"):
            spatial.build_spatial_weights(frame.to_crs(4326), "queen")
        with self.assertRaisesRegex(ValueError, "five"):
            spatial.build_spatial_weights(frame.iloc[:4], "knn4")
        with self.assertRaisesRegex(ValueError, "Unknown spatial"):
            spatial.build_spatial_weights(frame, "wrong")
        duplicated = frame.copy()
        duplicated.loc[1, "ONS ID"] = duplicated.loc[0, "ONS ID"]
        with self.assertRaisesRegex(ValueError, "unique"):
            spatial.build_spatial_weights(duplicated, "queen")


class RegionalModelTests(unittest.TestCase):
    def test_adjusted_coefficient_matches_independent_least_squares_in_10pp_units(self):
        frame = example_frame()
        model, design, _ = spatial.fit_regional_ols(frame, "ASMR_f", "Lab PC", adjusted=True)
        full = np.column_stack([np.ones(len(frame)), design])
        expected = np.linalg.lstsq(full, frame["ASMR_f"].to_numpy(), rcond=None)[0]
        np.testing.assert_allclose(model.betas.ravel(), expected, rtol=1e-10, atol=1e-10)
        np.testing.assert_allclose(design[:, 0], frame["Lab PC"] * 10)
        self.assertEqual(model.k, 5)  # Intercept, vote share, three region indicators.

    def test_moran_uses_regression_residuals_and_regression_specific_null(self):
        frame = example_frame()
        weights, _, _ = spatial.build_spatial_weights(frame, "queen")
        model, _, _ = spatial.fit_regional_ols(frame, "ASMR_f", "Lab PC", adjusted=True)
        diagnostic = MoranRes(model, weights, z=True)
        residuals = model.u.ravel()
        expected = len(frame) / weights.s0 * (residuals @ weights.sparse @ residuals) / (residuals @ residuals)
        self.assertAlmostEqual(diagnostic.I, expected, places=13)
        self.assertAlmostEqual(diagnostic.p_norm, 2 * norm.sf(abs(diagnostic.zI)), places=13)
        self.assertNotAlmostEqual(diagnostic.eI, -1 / (len(frame) - 1), places=5)

    def test_underidentified_design_is_not_silently_fitted(self):
        frame = example_frame()
        frame["Lab PC"] = .5
        with self.assertRaisesRegex(ValueError, "underidentified"):
            spatial.fit_regional_ols(frame, "ASMR_f", "Lab PC", adjusted=True)


class SpatialDataTests(unittest.TestCase):
    def test_original_verified_geometry_replaces_display_geometry_and_preserves_population(self):
        original = example_frame()
        source = original.copy()
        source["geometry"] = source.geometry.buffer(-10)
        source.loc[0, "First party"] = "Spk"
        source.loc[1, "Country name"] = "Wales"
        polygons = original[["ONS ID", "geometry"]].rename(columns={"ONS ID": "PCON24CD"})
        spec = {"path": "data/shapefile/2024/PCON_JULY_2024_UK_BFC.shp", "sha256": "test", "size": 123}
        with patch.object(helpers, "_raw_data_file_specs", return_value=[spec]), \
                patch.object(helpers, "_verify_file") as verify, \
                patch.object(spatial.gpd, "read_file", return_value=polygons):
            frame, _, outcomes = spatial.prepare_spatial_data(source, "2024")
        verify.assert_called_once_with(helpers.PROJECT_ROOT / spec["path"], "test", 123)
        self.assertEqual(len(frame), 62)
        self.assertEqual(outcomes, ["ASMR_f", "ASMR_m"])
        self.assertEqual(frame.geometry.iloc[0].wkb, original.geometry.iloc[2].wkb)
        self.assertNotEqual(frame.geometry.iloc[0].wkb, source.geometry.iloc[2].wkb)
        self.assertFalse(any(name.startswith("Premature") for name in outcomes))


class SpatialPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame = example_frame()
        cls.frame.loc[0, "Lab PC"] = 0.
        cls.frame.loc[1, "PrematureASMR2021_m"] = np.nan
        cls.original = cls.frame.copy(deep=True)

        def prepare(source, year):
            outcomes = ["ASMR_f", "PrematureASMR2021_m"] if year == "2019" else ["ASMR_f"]
            return source.copy(), ["Lab PC"], outcomes

        with patch.object(spatial, "prepare_spatial_data", side_effect=prepare), \
                contextlib.redirect_stdout(io.StringIO()), threadpool_limits(limits=1):
            cls.results = spatial.run_spatial_robustness(cls.frame, cls.frame)

    def test_all_models_loro_and_diagnostics_are_present_and_2021_uses_2019_only(self):
        self.assertEqual(len(self.results["regional_models"]), 6)
        self.assertEqual(len(self.results["moran_diagnostics"]), 12)
        self.assertEqual(len(self.results["spatial_error_models"]), 6)
        self.assertEqual(len(self.results["leave_one_region_out"]), 12)
        for table in [self.results[name] for name in ["regional_models", "moran_diagnostics", "spatial_error_models"]]:
            self.assertTrue(table.loc[table["Mortality year"].eq("2021"), "Election year"].eq("2019").all())
        pd.testing.assert_frame_equal(self.frame, self.original, check_exact=True)

    def test_zeros_are_retained_and_missingness_changes_only_the_relevant_sample(self):
        coverage = self.results["coverage"].set_index("Mortality year")
        self.assertEqual(coverage.loc["2019", "Complete-pair N"], 64)
        self.assertEqual(coverage.loc["2021", "Complete-pair N"], 63)
        self.assertEqual(coverage.loc["2021", "Excluded codes"], "E0001")
        diagnostics = self.results["moran_diagnostics"]
        for _, row in diagnostics.iterrows():
            edges = self.results["weights_edges"].loc[
                self.results["weights_edges"]["Weights SHA-256"].eq(row["Weights SHA-256"])
            ]
            self.assertEqual(edges["From"].nunique(), row["N"])
            self.assertIn("E0000", edges["From"].values)
            if row["Mortality year"] == "2021":
                self.assertNotIn("E0001", edges["From"].values)

    def test_q_values_and_loro_summary_match_the_full_results(self):
        diagnostics = self.results["moran_diagnostics"]
        np.testing.assert_allclose(diagnostics["Moran q-value (BH)"],
                                   false_discovery_control(diagnostics["Moran p-value"], method="bh"))
        summary = spatial.make_leave_one_region_out_summary(self.results)
        self.assertTrue(summary["Refits"].eq(4).all())
        self.assertTrue(summary["Sign changes"].eq(0).all())
        for _, row in summary.iterrows():
            selected = self.results["leave_one_region_out"].loc[
                self.results["leave_one_region_out"]["Mortality year"].eq(row["Mortality year"])
            ]
            self.assertEqual(row["Minimum beta"], selected["Beta per 10pp"].min())
            self.assertEqual(row["Maximum beta"], selected["Beta per 10pp"].max())

    def test_spatial_error_intervals_and_filtered_residuals_are_finite(self):
        table = self.results["spatial_error_models"]
        columns = ["Beta per 10pp", "SE", "95% CI lower", "95% CI upper", "Lambda",
                   "Filtered residual Moran I (descriptive)"]
        self.assertTrue(np.isfinite(table[columns].to_numpy()).all())
        self.assertTrue(table["95% CI lower"].lt(table["Beta per 10pp"]).all())
        self.assertTrue(table["95% CI upper"].gt(table["Beta per 10pp"]).all())
        self.assertTrue(table["Lambda"].abs().lt(.999).all())

    def test_exports_are_additive_and_include_unrounded_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(helpers, "TABLES_DIR", Path(directory)):
                paths = spatial.export_spatial_robustness(self.results)
            self.assertEqual(len(paths), 8)
            saved = pd.read_csv(paths["moran_diagnostics"], float_precision="round_trip")
        np.testing.assert_equal(saved["Moran I"].to_numpy(), self.results["moran_diagnostics"]["Moran I"].to_numpy())
        self.assertTrue(all(path.name.startswith("spatial_") for path in paths.values()))


if __name__ == "__main__":
    unittest.main()
