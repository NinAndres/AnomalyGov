import pandas as pd
import pytest

pytest.importorskip("matplotlib")
from anomalygov_ml import figures  # noqa: E402

ALGS = figures.ALGORITHMS
PS = (0.01, 0.02, 0.05)


def synthetic() -> figures.FigureData:
    comparisons = pd.DataFrame(
        [("main", "main", "isolation_forest", "lof", {}, {}, p, 0.1, 0.2) for p in PS]
        + [("main", "main", "isolation_forest", "one_class_svm", {}, {}, p, 0.3, 0.0) for p in PS]
        + [("main", "main", "lof", "one_class_svm", {}, {}, p, 0.2, 0.1) for p in PS]
        + [("main", "parameter", "isolation_forest", "isolation_forest", {}, {"n_estimators": 200, "max_samples": 256},
            0.01, 0.42, 0.98)]
        + [("data_stability", "main", a, a, {"novelty": True}, {}, p, j, 0.99)
           for a in ALGS for p in (0.01, 0.05) for j in (0.8, 0.9)],
        columns=["purpose_a", "purpose_b", "algorithm_a", "algorithm_b", "params_a", "params_b", "p", "jaccard",
                 "spearman"],
    )
    agreement, stability = figures.split_comparisons(comparisons)
    profiles = []
    for a in ALGS:
        for t in ("individual", "company"):
            profiles.append((a, 0.01, "favored_type", t, 0.01, 0.5))
        for m in ("2025-01", "2025-02"):
            profiles.append((a, 0.01, "reference_month", m, 0.01, 0.5))
        for f in ("log_amount", "amount_vs_ug"):
            profiles.append((a, 0.01, "dominant_feature", f, 0.5, None))
    tests = pd.DataFrame([
        ("H2", "jaccard_if_minus_lof_p01",
         {"median_jaccard_if": 0.68, "median_jaccard_other": 0.48, "median_if_seed_noise": 0.89}),
        ("H2_context", "jaccard_if_minus_ocsvm_p01",
         {"median_jaccard_if": 0.68, "median_jaccard_other": 0.37, "median_if_seed_noise": 0.89}),
        ("H1c_manipulation", "retention_if", {"medians": {"0.0": 1.0, "0.5": 0.79}}),
        ("H1c_manipulation", "retention_lof", {"medians": {"0.0": 1.0, "0.5": 0.27}}),
    ], columns=["family", "variable", "details"])
    return figures.FigureData(
        name="teste",
        main=pd.DataFrame({"algorithm": ALGS, "total_seconds": [5.6, 30.0, 4.0]}),
        metrics=pd.DataFrame([(a, p, p * 0.8) for a in ALGS for p in PS],
                             columns=["algorithm", "p", "weighted_flagged_share"]),
        agreement=agreement,
        stability=stability,
        scalability=pd.DataFrame([(a, n, 1.0, 0.9, 1.1) for a in ALGS for n in (5000, 10000)]
                                 + [("isolation_forest", 20000, 2.0, 1.9, 2.1)],
                                 columns=["algorithm", "n_train", "mean", "min", "max"]),
        profiles=pd.DataFrame(profiles, columns=["algorithm", "p", "dimension", "category", "value", "baseline"]),
        surrogates=pd.DataFrame({"algorithm": ALGS, "fidelity": [0.59, 0.22, 0.52]}),
        overlaps=pd.DataFrame([(p, k, 100 * k) for p in PS for k in (1, 2, 3)],
                              columns=["p", "algorithm_count", "record_count"]),
        tests=tests,
    )


def test_split_comparisons_keeps_the_other_run_of_each_stability_pair():
    data = synthetic()
    assert len(data.agreement) == 3 * len(PS)
    assert set(data.stability.purpose) == {"parameter", "data_stability"}
    parameter = data.stability[data.stability.purpose == "parameter"].iloc[0]
    assert parameter.params == {"n_estimators": 200, "max_samples": 256}
    # The data stability run is run_a in the synthetic pairs: its own params must be kept, not the main run's.
    assert all(p == {"novelty": True} for p in data.stability[data.stability.purpose == "data_stability"].params)


def test_hypothesis_helpers_read_the_stored_details():
    data = synthetic()
    h2 = figures.h2_medians(data.tests)
    assert h2.iloc[0].to_dict() == {"p": 0.01, "isolation_forest": 0.68, "lof": 0.48, "one_class_svm": 0.37,
                                    "noise": 0.89}
    h1c = figures.h1c_retention(data.tests)
    assert list(h1c.index) == [0.0, 0.5]
    assert h1c.loc[0.5, "lof"] == 0.27


def test_number_formats_are_brazilian():
    assert figures.br(1234.5, 1) == "1.234,5"
    assert figures.pct(0.0067, 2) == "0,67%"
    assert figures.short_params("one_class_svm", {"nu": 0.01, "gamma": "scale"}) == "nu=0,01, gamma=scale"
    assert figures.short_params("one_class_svm", {"nu": 0.05, "gamma": 1.0}) == "nu=0,05, gamma=1"


def test_render_writes_every_figure_and_the_captions(tmp_path):
    written = figures.render(synthetic(), tmp_path, ("png", "svg"))
    pngs = sorted(p.name for p in written if p.suffix == ".png")
    assert len(pngs) == len(figures.FIGURES)
    assert pngs[0] == "01-tempo-execucao.png"
    assert all((tmp_path / p).stat().st_size > 0 for p in pngs)
    captions = (tmp_path / "legendas.md").read_text(encoding="utf-8")
    assert captions.count("| `") == len(figures.FIGURES)
    assert "não indicam fraude" in captions


def test_render_is_reproducible(tmp_path):
    first = figures.render(synthetic(), tmp_path / "a", ("png", "svg"))
    second = figures.render(synthetic(), tmp_path / "b", ("png", "svg"))
    assert [p.read_bytes() for p in first] == [p.read_bytes() for p in second]


def test_hypothesis_figures_are_skipped_without_hypothesis_results(tmp_path):
    data = synthetic()
    data.tests = data.tests.iloc[0:0]
    written = figures.render(data, tmp_path, ("png",))
    assert not any("h2" in p.name or "h1c" in p.name for p in written)
