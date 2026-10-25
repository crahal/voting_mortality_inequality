"""Supplementary regional models and spatial diagnostics for mortality outcomes."""

import hashlib
import json
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
from esda import Moran
from libpysal.weights import KNN, Queen, attach_islands
from scipy.sparse import SparseEfficiencyWarning
from scipy.stats import false_discovery_control, norm, t
from spreg import ML_Error, MoranRes, OLS
from threadpoolctl import threadpool_limits

import helpers


WEIGHT_LABELS = {
    "queen": "Queen + isolated-area nearest neighbour",
    "knn4": "Symmetric 4-nearest neighbours",
}
REGION_COLUMN = "Region name"
MODEL_KEYS = ["Election year", "Mortality year", "Outcome", "Political measure"]


def prepare_spatial_data(frame, year):
    """Join the exact original polygons, never the simplified display geometry."""
    eligible = frame.loc[
        frame["Country name"].eq("England")
        & frame["First party"].notna()
        & frame["First party"].ne("Spk")
    ].copy()
    if eligible["ONS ID"].isna().any() or eligible["ONS ID"].duplicated().any():
        raise ValueError("Spatial analysis requires unique, non-missing constituency codes.")
    if eligible[REGION_COLUMN].isna().any():
        raise ValueError("Missing region assignment in the spatial analysis population.")
    df, predictors, outcomes = helpers._summary_correlation_inputs(eligible, year)
    outcomes = [name for name in outcomes if name.startswith(("ASMR_", "PrematureASMR2021_"))]
    path = {
        "2019": "data/shapefile/2019/WPC_Dec_2019_GCB_UK.shp",
        "2024": "data/shapefile/2024/PCON_JULY_2024_UK_BFC.shp",
    }[year]
    stem = path[:-4]
    for spec in helpers._raw_data_file_specs():
        if spec["path"].startswith(stem + "."):
            helpers._verify_file(helpers.PROJECT_ROOT / spec["path"], spec["sha256"], spec["size"])
    polygons = gpd.read_file(helpers.PROJECT_ROOT / path)
    code = "pcon19cd" if year == "2019" else "PCON24CD"
    polygons = polygons[[code, "geometry"]].rename(columns={code: "ONS ID"})
    joined = df.drop(columns="geometry", errors="ignore").merge(
        polygons, on="ONS ID", how="left", validate="one_to_one"
    )
    joined = gpd.GeoDataFrame(joined, geometry="geometry", crs=polygons.crs).to_crs(27700)
    if joined.geometry.isna().any() or joined.geometry.is_empty.any() or not joined.geometry.is_valid.all():
        raise ValueError("Missing, empty or invalid original constituency geometry.")
    return joined.sort_values("ONS ID").reset_index(drop=True), predictors, outcomes


def build_spatial_weights(frame, kind):
    """Return row-standardised weights plus a reproducible neighbourhood audit."""
    if frame.crs is None or frame.crs.to_epsg() != 27700:
        raise ValueError("Spatial weights require British National Grid (EPSG:27700).")
    ids = frame["ONS ID"].tolist()
    if len(ids) != len(set(ids)) or any(pd.isna(code) for code in ids):
        raise ValueError("Spatial weights require unique, non-missing constituency codes.")
    if len(ids) < 5:
        raise ValueError("At least five constituencies are required for the weights comparison.")
    centroids = frame.geometry.centroid
    coordinates = np.column_stack([centroids.x, centroids.y])
    if len(np.unique(coordinates, axis=0)) != len(ids):
        raise ValueError("Coincident centroids require an explicit neighbour tie policy.")
    island_links = {}
    if kind == "queen":
        weights = Queen.from_dataframe(frame, ids=ids, silence_warnings=True)
        initial_components = weights.n_components
        if weights.islands:
            nearest = KNN.from_array(coordinates, k=1, ids=ids, silence_warnings=True)
            island_links = {code: nearest.neighbors[code][0] for code in weights.islands}
            weights = attach_islands(weights, nearest, silence_warnings=True)
    elif kind == "knn4":
        weights = KNN.from_array(coordinates, k=4, ids=ids, silence_warnings=True)
        initial_components = weights.n_components
        weights = weights.symmetrize()
    else:
        raise ValueError(f"Unknown spatial weights: {kind}")
    weights.transform = "r"
    if weights.id_order != ids or weights.islands:
        raise ValueError("Weights are misaligned or retain an observation with no neighbours.")
    edges = pd.DataFrame([
        {"From": code, "To": neighbour, "Weight": weight}
        for code in ids
        for neighbour, weight in sorted(zip(weights.neighbors[code], weights.weights[code]))
    ])
    audit = {
        "Weights": WEIGHT_LABELS[kind], "N": len(ids),
        "Initial components": initial_components,
        "Final components": weights.n_components,
        "Isolated-area links added": json.dumps(island_links, sort_keys=True),
        "Minimum neighbours": weights.min_neighbors,
        "Maximum neighbours": weights.max_neighbors,
        "Mean neighbours": weights.mean_neighbors,
        "Weights SHA-256": hashlib.sha256(edges.to_csv(index=False).encode()).hexdigest(),
    }
    return weights, audit, edges


def fit_regional_ols(frame, outcome, predictor, adjusted):
    """One political predictor, in 10-percentage-point units, and optional region effects."""
    design = pd.DataFrame({"Political share per 10pp": frame[predictor] / 0.1}, index=frame.index)
    if adjusted:
        dummies = pd.get_dummies(frame[REGION_COLUMN], prefix="Region", drop_first=True, dtype=float)
        design = pd.concat([design, dummies], axis=1)
    x = design.to_numpy(dtype=float)
    y = frame[[outcome]].to_numpy(dtype=float)
    full_design = np.column_stack([np.ones(len(frame)), x])
    if not np.isfinite(full_design).all() or not np.isfinite(y).all():
        raise ValueError("Non-finite observations in regional regression.")
    if len(frame) <= full_design.shape[1] or np.linalg.matrix_rank(full_design) < full_design.shape[1]:
        raise ValueError("Regional regression is underidentified or has no residual degrees of freedom.")
    model = OLS(y, x, name_y=outcome, name_x=list(design.columns), nonspat_diag=False)
    return model, x, list(design.columns)


def _slope_summary(model, spatial=False):
    beta = float(model.betas[1, 0])
    se = float(model.std_err[1])
    critical = norm.ppf(.975) if spatial else t.ppf(.975, model.n - model.k)
    return {
        "N": model.n, "Beta per 10pp": beta, "SE": se,
        "95% CI lower": beta - critical * se,
        "95% CI upper": beta + critical * se,
        "Slope p-value": float((model.z_stat if spatial else model.t_stat)[1][1]),
    }


def _political_label(predictor):
    return {"Brx PC": "Brexit Party", "RUK PC": "Reform UK"}.get(
        predictor, helpers.PUBLICATION_CORRELATION_TABLE_COLUMN_LABELS.get(predictor)
    )


def _fit_spatial_error(y, x, weights, outcome, names):
    # Suppress only known solver-format notices, not numerical/convergence warnings.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="Method 'bounded' does not support relative tolerance in x;.*",
            category=RuntimeWarning, module=r"spreg\.ml_error",
        )
        for message in [
            "splu converted its input to CSC format",
            "spsolve is more efficient when sparse b is in the CSC matrix format",
        ]:
            warnings.filterwarnings("ignore", message=message, category=SparseEfficiencyWarning)
        return ML_Error(y, x, weights, name_y=outcome, name_x=names, method="LU", epsilon=1e-8)


def run_spatial_robustness(df_2019, df_2024):
    """Run all mortality comparisons on the baseline population, retaining zero votes."""
    rows = {key: [] for key in [
        "regional_models", "moran_diagnostics", "spatial_error_models",
        "leave_one_region_out", "coverage", "weights", "weights_edges",
    ]}
    weight_cache = {}
    with threadpool_limits(limits=1):
        for year, source in [("2019", df_2019), ("2024", df_2024)]:
            frame, predictors, outcomes = prepare_spatial_data(source, year)
            print(f"Spatial robustness: {year} voting, {len(frame)} constituencies, "
                  f"{frame[REGION_COLUMN].nunique()} regions.", flush=True)
            for outcome in outcomes:
                mortality_year = "2021" if outcome.startswith("PrematureASMR2021_") else year
                for predictor in predictors:
                    pair = frame.dropna(subset=[outcome, predictor, REGION_COLUMN]).copy()
                    if not pair[predictor].between(0, 1).all():
                        raise ValueError(f"{predictor} must be a proportion in [0, 1].")
                    keys = {
                        "Election year": year, "Mortality year": mortality_year,
                        "Outcome": helpers.PUBLICATION_VARIABLE_LABELS[outcome],
                        "Political measure": _political_label(predictor),
                    }
                    rows["coverage"].append({
                        **keys, "Eligible N": len(frame), "Complete-pair N": len(pair),
                        "Regions": pair[REGION_COLUMN].nunique(),
                        "Excluded codes": ", ".join(frame.loc[~frame.index.isin(pair.index), "ONS ID"]),
                    })
                    models = {}
                    for adjusted, name in [(False, "Unadjusted OLS"), (True, "Region-adjusted OLS")]:
                        model, x, names = fit_regional_ols(pair, outcome, predictor, adjusted)
                        models[name] = model
                        rows["regional_models"].append({
                            **keys, "Model": name, **_slope_summary(model), "R-squared": model.r2,
                        })
                    adjusted_model = models["Region-adjusted OLS"]
                    adjusted_x = adjusted_model.x[:, 1:]
                    adjusted_names = adjusted_model.name_x[1:]
                    for omitted in sorted(pair[REGION_COLUMN].unique()):
                        reduced = pair.loc[pair[REGION_COLUMN].ne(omitted)]
                        refit, _, _ = fit_regional_ols(reduced, outcome, predictor, adjusted=True)
                        rows["leave_one_region_out"].append({
                            **keys, "Omitted region": omitted, **_slope_summary(refit),
                            "Full adjusted beta": float(adjusted_model.betas[1, 0]),
                            "Sign changed": bool(np.sign(refit.betas[1, 0]) != np.sign(adjusted_model.betas[1, 0])),
                        })
                    for kind in WEIGHT_LABELS:
                        cache_key = (year, kind, tuple(pair["ONS ID"]))
                        if cache_key not in weight_cache:
                            weights, audit, edges = build_spatial_weights(pair, kind)
                            weight_cache[cache_key] = (weights, audit["Weights SHA-256"])
                            rows["weights"].append({"Election year": year, **audit})
                            rows["weights_edges"].extend(
                                {"Election year": year, "Weights": WEIGHT_LABELS[kind],
                                 "Weights SHA-256": audit["Weights SHA-256"], **edge}
                                for edge in edges.to_dict("records")
                            )
                        weights, weights_hash = weight_cache[cache_key]
                        spatial_keys = {**keys, "Weights": WEIGHT_LABELS[kind], "Weights SHA-256": weights_hash}
                        for name, model in models.items():
                            diagnostic = MoranRes(model, weights, z=True)
                            rows["moran_diagnostics"].append({
                                **spatial_keys, "Model": name, "N": model.n,
                                "Moran I": float(diagnostic.I),
                                "Expected I": float(diagnostic.eI),
                                "Moran z": float(diagnostic.zI),
                                "Moran p-value": float(diagnostic.p_norm),
                            })
                        spatial_model = _fit_spatial_error(
                            pair[[outcome]].to_numpy(dtype=float), adjusted_x, weights,
                            outcome, adjusted_names,
                        )
                        if not np.isfinite(spatial_model.betas).all() or abs(spatial_model.lam) >= .999:
                            raise ValueError("Spatial error model has non-finite or boundary estimates.")
                        rows["spatial_error_models"].append({
                            **spatial_keys, **_slope_summary(spatial_model, spatial=True),
                            "Lambda": float(spatial_model.lam),
                            "Lambda p-value": float(spatial_model.z_stat[-1][1]),
                            "Filtered residual Moran I (descriptive)": float(
                                Moran(spatial_model.e_filtered.ravel(), weights, permutations=0).I
                            ),
                        })
                print(f"  Completed {helpers.PUBLICATION_VARIABLE_LABELS[outcome]}.", flush=True)
    results = {name: pd.DataFrame(records) for name, records in rows.items()}
    # One exploratory family includes all OLS residual tests, both specifications and weights.
    results["moran_diagnostics"]["Moran q-value (BH)"] = false_discovery_control(
        results["moran_diagnostics"]["Moran p-value"].to_numpy(), method="bh"
    )
    return results


def make_leave_one_region_out_summary(results):
    rows = []
    for keys, group in results["leave_one_region_out"].groupby(MODEL_KEYS, sort=False):
        low, high = group.loc[group["Beta per 10pp"].idxmin()], group.loc[group["Beta per 10pp"].idxmax()]
        rows.append({
            **dict(zip(MODEL_KEYS, keys)), "Full adjusted beta": float(group["Full adjusted beta"].iloc[0]),
            "Minimum beta": low["Beta per 10pp"], "Region omitted at minimum": low["Omitted region"],
            "Maximum beta": high["Beta per 10pp"], "Region omitted at maximum": high["Omitted region"],
            "Sign changes": int(group["Sign changed"].sum()), "Refits": len(group),
        })
    return pd.DataFrame(rows)


def export_spatial_robustness(results):
    helpers.TABLES_DIR.mkdir(parents=True, exist_ok=True)
    paths = {}
    tables = {**results, "leave_one_region_out_summary": make_leave_one_region_out_summary(results)}
    for name, table in tables.items():
        stem = name if name.startswith("spatial_") else f"spatial_{name}"
        path = helpers.TABLES_DIR / f"{stem}.csv"
        table.to_csv(path, index=False)
        paths[name] = path
    return paths
