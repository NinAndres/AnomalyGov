"""Static figures of one experiment for the article (decision 0013).

Usage: python -m anomalygov_ml.figures EXPERIMENT [--out DIR] [--formats png,svg]

Reads only what anomalygov_ml.report already stored in the local database (DATABASE_URL): run_metrics,
run_comparisons, run_profiles, run_surrogates, experiment_overlaps and hypothesis_tests. Nothing is recomputed,
so the figures show the same numbers as docs/resultados/<experimento>.md and the application. Run the report
first. Writes one file per figure and format plus legendas.md, with a suggested caption for each figure.
"""

import argparse
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import psycopg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.ticker import FuncFormatter, LogLocator, MultipleLocator, NullFormatter  # noqa: E402

from anomalygov_ml.sources.payments import FAVORED_TYPE_LABELS  # noqa: E402

ALGORITHMS = ("isolation_forest", "lof", "one_class_svm")
LABELS = {"isolation_forest": "Isolation Forest", "lof": "LOF", "one_class_svm": "One-Class SVM"}
SHORT = {"isolation_forest": "IF", "lof": "LOF", "one_class_svm": "OCSVM"}
# Same validated palette as the application (decision 0012): one fixed color per algorithm, plus a marker so
# the series stay apart in grayscale print.
COLORS = {"isolation_forest": "#2a78d6", "lof": "#eb6834", "one_class_svm": "#1baf7a"}
MARKERS = {"isolation_forest": "o", "lof": "s", "one_class_svm": "^"}
ORDINAL = ("#86b6ef", "#2a78d6", "#104281")  # one hue, light to dark, for ordered series (p, number of algorithms)
NEUTRAL = "#898781"
INK = "#1c2430"
MUTED = "#5b6676"
GRID = "#e1e0d9"
FEATURES = {
    "log_amount": "Valor (log)",
    "amount_vs_ug": "Valor vs. unidade\ngestora",
    "amount_vs_favored": "Valor vs. próprio\nfavorecido",
    "favored_months": "Meses com\nrecebimento",
    "favored_ug_count": "Unidades pagadoras\n(log)",
}
SHORT_TYPES = {
    "individual": "Pessoa\nfísica",
    "company": "Pessoa\njurídica",
    "management_unit": "Unidade\ngestora",
    "foreign": "Exterior",
    "special": "Código\nespecial",
}
MAIN_P = 0.01
WIDTH = 6.3  # inches: text width of an A4 page with 3 cm and 2 cm margins (ABNT)

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Arial"],
    "font.size": 9,
    "axes.edgecolor": "#c3c2b7",
    "axes.labelcolor": INK,
    "axes.titlesize": 9,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "legend.frameon": False,
    "legend.fontsize": 8,
    "svg.fonttype": "none",
    "svg.hashsalt": "anomalygov",  # stable element ids, so re-generated files are identical
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
})


def br(value: float, decimals: int = 1) -> str:
    """Brazilian number format: comma for decimals, dot for thousands."""
    return f"{value:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def pct(value: float, decimals: int = 0) -> str:
    return br(100 * value, decimals) + "%"


def percent_axis(decimals: int = 0) -> FuncFormatter:
    return FuncFormatter(lambda v, _: pct(v, decimals))


def number_axis(decimals: int = 1) -> FuncFormatter:
    return FuncFormatter(lambda v, _: br(v, decimals))


def legend_above(ax, ncols: int = 3, **kwargs) -> None:
    ax.legend(ncols=ncols, loc="lower center", bbox_to_anchor=(0.5, 1.0), **kwargs)


def grid(ax, axis: str = "y") -> None:
    ax.grid(axis=axis, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def same_p(series: pd.Series, p: float) -> pd.Series:
    return (series.astype(float) - p).abs() < 1e-9


# ---------------------------------------------------------------- data


@dataclass
class FigureData:
    """Tables stored by the report for one experiment, already restricted to what the figures need."""

    name: str
    main: pd.DataFrame  # algorithm, total_seconds
    metrics: pd.DataFrame  # algorithm, p, weighted_flagged_share
    agreement: pd.DataFrame  # algorithm_a, algorithm_b, p, jaccard, spearman (main x main)
    stability: pd.DataFrame  # purpose, algorithm, params, p, jaccard, spearman (other run x its main run)
    scalability: pd.DataFrame  # algorithm, n_train, mean, min, max
    profiles: pd.DataFrame  # algorithm, p, dimension, category, value, baseline
    surrogates: pd.DataFrame  # algorithm, fidelity
    overlaps: pd.DataFrame  # p, algorithm_count, record_count
    tests: pd.DataFrame  # family, variable, details


def frame(conn: psycopg.Connection, query: str, params: tuple, columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(conn.execute(query, params).fetchall(), columns=columns)


def load(conn: psycopg.Connection, name: str) -> FigureData:
    args = (name,)
    main = frame(conn, """SELECT algorithm, fit_seconds + score_seconds FROM runs
                          WHERE experiment = %s AND mode = 'experiment' AND purpose = 'main'""",
                 args, ["algorithm", "total_seconds"])
    if main.empty:
        raise ValueError(f"nenhuma execução principal para o experimento {name!r}")
    metrics = frame(conn, """SELECT r.algorithm, m.p::float8, m.weighted_flagged_share FROM run_metrics m
                             JOIN runs r ON r.id = m.run_id
                             WHERE r.experiment = %s AND r.mode = 'experiment' AND r.purpose = 'main'""",
                    args, ["algorithm", "p", "weighted_flagged_share"])
    comparisons = frame(conn, """SELECT a.purpose, b.purpose, a.algorithm, b.algorithm, a.params, b.params,
                                        c.p::float8, c.jaccard, c.spearman
                                 FROM run_comparisons c JOIN runs a ON a.id = c.run_a JOIN runs b ON b.id = c.run_b
                                 WHERE a.experiment = %s AND a.mode = 'experiment'""",
                        args, ["purpose_a", "purpose_b", "algorithm_a", "algorithm_b", "params_a", "params_b", "p",
                               "jaccard", "spearman"])
    agreement, stability = split_comparisons(comparisons)
    scalability = frame(conn, """SELECT algorithm, n_train, avg(fit_seconds + score_seconds),
                                        min(fit_seconds + score_seconds), max(fit_seconds + score_seconds)
                                 FROM runs WHERE experiment = %s AND mode = 'experiment' AND purpose = 'scalability'
                                 GROUP BY algorithm, n_train ORDER BY n_train""",
                        args, ["algorithm", "n_train", "mean", "min", "max"])
    profiles = frame(conn, """SELECT r.algorithm, pr.p::float8, pr.dimension, pr.category, pr.value, pr.baseline
                              FROM run_profiles pr JOIN runs r ON r.id = pr.run_id WHERE r.experiment = %s""",
                     args, ["algorithm", "p", "dimension", "category", "value", "baseline"])
    surrogates = frame(conn, """SELECT r.algorithm, s.fidelity FROM run_surrogates s JOIN runs r ON r.id = s.run_id
                                WHERE r.experiment = %s""", args, ["algorithm", "fidelity"])
    overlaps = frame(conn, """SELECT p::float8, algorithm_count, record_count FROM experiment_overlaps
                              WHERE experiment = %s ORDER BY p, algorithm_count""",
                     args, ["p", "algorithm_count", "record_count"])
    tests = frame(conn, "SELECT family, variable, details FROM hypothesis_tests WHERE experiment = %s",
                  args, ["family", "variable", "details"])
    if profiles.empty:
        raise ValueError("características dos sinalizados ausentes: rode antes python -m anomalygov_ml.report")
    return FigureData(name, main, metrics, agreement, stability, scalability, profiles, surrogates, overlaps, tests)


def split_comparisons(comparisons: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pairs of main runs (agreement) and each other run against its main run (stability)."""
    both_main = (comparisons.purpose_a == "main") & (comparisons.purpose_b == "main")
    agreement = comparisons[both_main][["algorithm_a", "algorithm_b", "p", "jaccard", "spearman"]]
    one_main = comparisons[(comparisons.purpose_a == "main") ^ (comparisons.purpose_b == "main")]
    other_is_b = one_main.purpose_a == "main"
    stability = pd.DataFrame({
        "purpose": np.where(other_is_b, one_main.purpose_b, one_main.purpose_a),
        "algorithm": np.where(other_is_b, one_main.algorithm_b, one_main.algorithm_a),
        "params": [b if o else a for a, b, o in zip(one_main.params_a, one_main.params_b, other_is_b)],
        "p": one_main.p.to_numpy(),
        "jaccard": one_main.jaccard.to_numpy(),
        "spearman": one_main.spearman.to_numpy(),
    })
    return agreement.reset_index(drop=True), stability


def short_params(algorithm: str, params: dict | str) -> str:
    params = json.loads(params) if isinstance(params, str) else params
    keys = {"isolation_forest": ("n_estimators", "max_samples"), "lof": ("n_neighbors", "neighbors_margin"),
            "one_class_svm": ("nu", "gamma")}[algorithm]
    return ", ".join(f"{k}={br(v, 3).rstrip('0').rstrip(',') if isinstance(v, float) else v}"
                     for k in keys if (v := params.get(k)) is not None)


# ---------------------------------------------------------------- figures


def bars_by_algorithm(ax, groups: list[str], values: Callable[[str, str], float], width: float = 0.24) -> None:
    """Grouped vertical bars: one group per label, one bar per algorithm (fixed order and color)."""
    x = np.arange(len(groups))
    for i, algorithm in enumerate(ALGORITHMS):
        heights = [values(algorithm, g) for g in groups]
        ax.bar(x + (i - 1) * width, heights, width * 0.92, color=COLORS[algorithm], label=LABELS[algorithm])
    ax.set_xticks(x, groups)
    ax.tick_params(axis="x", length=0)


def fig_time(d: FigureData) -> Figure:
    fig, ax = plt.subplots(figsize=(WIDTH, 1.8))
    data = d.main.set_index("algorithm").reindex(ALGORITHMS)
    y = np.arange(len(ALGORITHMS))[::-1]
    ax.barh(y, data.total_seconds, 0.55, color=[COLORS[a] for a in ALGORITHMS])
    for yi, v in zip(y, data.total_seconds):
        ax.text(v, yi, f"  {br(v)} s", va="center", color=INK, fontsize=8)
    ax.set_yticks(y, [LABELS[a] for a in ALGORITHMS])
    ax.set_xlabel("Tempo total na amostra principal (s): treino + pontuação")
    ax.xaxis.set_major_formatter(number_axis(0))
    ax.tick_params(axis="y", length=0)
    grid(ax, "x")
    ax.set_xlim(0, data.total_seconds.max() * 1.15)
    return fig


def fig_scalability(d: FigureData) -> Figure:
    fig, ax = plt.subplots(figsize=(WIDTH, 3.2))
    for a in ALGORITHMS:
        s = d.scalability[d.scalability.algorithm == a].sort_values("n_train")
        if s.empty:
            continue
        err = [s["mean"] - s["min"], s["max"] - s["mean"]]
        ax.errorbar(s.n_train, s["mean"], yerr=err, color=COLORS[a], marker=MARKERS[a], markersize=5, linewidth=1.6,
                    capsize=2, label=LABELS[a], markeredgecolor="white", markeredgewidth=0.8)
    ax.set_xscale("log")
    ax.set_yscale("log")
    sizes = sorted(d.scalability.n_train.unique())
    ax.set_xticks(sizes, [br(n, 0) for n in sizes])
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.yaxis.set_major_locator(LogLocator(base=10, subs=(1, 2, 5)))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: br(v, 2 if v < 0.1 else 1 if v < 1 else 0)))
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_xlabel("Registros na amostra (escala logarítmica)")
    ax.set_ylabel("Tempo total (s, escala log.)")
    grid(ax, "both")
    handles = [plt.Line2D([], [], color=COLORS[a], marker=MARKERS[a], linewidth=1.6) for a in ALGORITHMS]
    ax.legend(handles, [LABELS[a] for a in ALGORITHMS], loc="upper left")
    return fig


def fig_weighted_share(d: FigureData) -> Figure:
    fig, ax = plt.subplots(figsize=(WIDTH, 2.6))
    by_label = {f"p = {pct(p)}": p for p in sorted(d.metrics.p.unique())}
    m = d.metrics.set_index(["algorithm", "p"]).weighted_flagged_share
    bars_by_algorithm(ax, list(by_label), lambda a, g: m.get((a, by_label[g]), np.nan))
    ax.yaxis.set_major_formatter(percent_axis(0))
    ax.set_ylabel("Proporção ponderada de sinalizados")
    grid(ax)
    legend_above(ax)
    return fig


def fig_agreement(d: FigureData) -> Figure:
    fig, ax = plt.subplots(figsize=(WIDTH, 2.6))
    pairs = [(a, b) for i, a in enumerate(ALGORITHMS) for b in ALGORITHMS[i + 1:]]
    ps = sorted(d.agreement.p.unique())
    x = np.arange(len(pairs))
    width = 0.8 / len(ps)
    for i, p in enumerate(ps):
        rows = d.agreement[same_p(d.agreement.p, p)]
        values = []
        for a, b in pairs:
            hit = rows[((rows.algorithm_a == a) & (rows.algorithm_b == b)) | ((rows.algorithm_a == b) & (rows.algorithm_b == a))]
            values.append(hit.jaccard.iloc[0] if len(hit) else np.nan)
        ax.bar(x + (i - (len(ps) - 1) / 2) * width, values, width * 0.92, color=ORDINAL[i % 3], label=f"p = {pct(p)}")
    ax.set_xticks(x, [f"{SHORT[a]} × {SHORT[b]}" for a, b in pairs])
    ax.tick_params(axis="x", length=0)
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(number_axis(1))
    ax.set_ylabel("Jaccard dos sinalizados")
    grid(ax)
    legend_above(ax)
    return fig


def fig_overlap(d: FigureData) -> Figure:
    fig, ax = plt.subplots(figsize=(WIDTH, 2.0))
    ps = sorted(d.overlaps.p.unique())
    counts = sorted(d.overlaps.algorithm_count.unique())
    y = np.arange(len(ps))[::-1]
    left = np.zeros(len(ps))
    for i, k in enumerate(counts):
        values = np.array([d.overlaps[same_p(d.overlaps.p, p) & (d.overlaps.algorithm_count == k)].record_count.sum()
                           for p in ps], dtype=float)
        label = "Por 1 algoritmo" if k == 1 else (f"Pelos {k}" if k == counts[-1] else f"Por {k}")
        ax.barh(y, values, 0.55, left=left, color=ORDINAL[i % 3], edgecolor="white", linewidth=1, label=label)
        left += values
    ax.set_yticks(y, [f"p = {pct(p)}" for p in ps])
    ax.tick_params(axis="y", length=0)
    ax.xaxis.set_major_formatter(number_axis(0))
    ax.set_xlabel("Registros sinalizados na amostra principal")
    grid(ax, "x")
    legend_above(ax)
    return fig


def fig_parameter_stability(d: FigureData) -> Figure:
    rows = d.stability[(d.stability.purpose == "parameter") & same_p(d.stability.p, MAIN_P)].copy()
    rows["order"] = rows.algorithm.map(ALGORITHMS.index)
    rows = rows.sort_values("order", kind="stable")
    fig, ax = plt.subplots(figsize=(WIDTH, 0.6 + 0.22 * len(rows)))
    y = np.arange(len(rows))[::-1]
    ax.barh(y, rows.jaccard, 0.65, color=[COLORS[a] for a in rows.algorithm])
    for yi, v in zip(y, rows.jaccard):
        ax.text(v, yi, f" {br(v, 2)}", va="center", color=INK, fontsize=7)
    ax.set_yticks(y, [f"{SHORT[a]}: {short_params(a, p)}" for a, p in zip(rows.algorithm, rows.params)], fontsize=7)
    ax.tick_params(axis="y", length=0)
    ax.set_xlim(0, 1.05)
    ax.xaxis.set_major_formatter(number_axis(1))
    ax.set_xlabel(f"Jaccard dos sinalizados (p = {pct(MAIN_P)}) com a configuração principal")
    grid(ax, "x")
    handles = [plt.Rectangle((0, 0), 1, 1, color=COLORS[a]) for a in ALGORITHMS]
    legend_above(ax, handles=handles, labels=[LABELS[a] for a in ALGORITHMS])
    return fig


def fig_data_stability(d: FigureData) -> Figure:
    rows = d.stability[d.stability.purpose == "data_stability"]
    ps = sorted(rows.p.unique())
    ps = [p for p in ps if p in (0.01, 0.05)] or ps
    fig, ax = plt.subplots(figsize=(WIDTH, 2.4))
    offsets = np.linspace(-0.12, 0.12, len(ps))
    p_markers = ("o", "D", "s")
    for i, a in enumerate(ALGORITHMS):
        for j, p in enumerate(ps):
            values = rows[(rows.algorithm == a) & same_p(rows.p, p)].jaccard
            if values.empty:
                continue
            med = values.median()
            ax.errorbar(i + offsets[j], med, yerr=[[med - values.min()], [values.max() - med]], color=COLORS[a],
                        marker=p_markers[j], markersize=6, capsize=3, linewidth=1.4,
                        markeredgecolor="white", markeredgewidth=0.8)
    ax.set_xticks(range(len(ALGORITHMS)), [LABELS[a] for a in ALGORITHMS])
    ax.tick_params(axis="x", length=0)
    ax.set_xlim(-0.5, len(ALGORITHMS) - 0.5)
    ax.yaxis.set_major_formatter(number_axis(2))
    ax.set_ylabel("Jaccard com a execução principal")
    grid(ax)
    handles = [plt.Line2D([], [], color=MUTED, marker=p_markers[j], linestyle="none") for j in range(len(ps))]
    ax.legend(handles, [f"p = {pct(p)}" for p in ps], ncols=len(ps), loc="lower left")
    return fig


def profile_values(d: FigureData, dimension: str, p: float = MAIN_P) -> pd.Series:
    rows = d.profiles[(d.profiles.dimension == dimension) & same_p(d.profiles.p, p)]
    return rows.set_index(["algorithm", "category"]).value


def fig_type_rate(d: FigureData) -> Figure:
    values = profile_values(d, "favored_type")
    rows = d.profiles[(d.profiles.dimension == "favored_type") & same_p(d.profiles.p, MAIN_P)]
    order = (rows.groupby("category").baseline.first().sort_values(ascending=False).index.tolist())
    fig, ax = plt.subplots(figsize=(WIDTH, 2.8))
    labels = [SHORT_TYPES.get(t, t) for t in order]
    bars_by_algorithm(ax, labels, lambda a, g: values.get((a, order[labels.index(g)]), np.nan))
    ax.yaxis.set_major_formatter(percent_axis(0))
    ax.set_ylabel(f"Taxa ponderada de sinalização (p = {pct(MAIN_P)})")
    ax.tick_params(axis="x", labelsize=8)
    grid(ax)
    legend_above(ax)
    return fig


def fig_month_rate(d: FigureData) -> Figure:
    values = profile_values(d, "reference_month")
    months = sorted(values.index.get_level_values("category").unique())
    names = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
    fig, ax = plt.subplots(figsize=(WIDTH, 2.6))
    x = np.arange(len(months))
    for a in ALGORITHMS:
        ax.plot(x, [values.get((a, m), np.nan) for m in months], color=COLORS[a], marker=MARKERS[a], markersize=4.5,
                linewidth=1.6, label=LABELS[a], markeredgecolor="white", markeredgewidth=0.6)
    ax.set_xticks(x, [names[int(m[5:7]) - 1] for m in months])
    ax.set_xlabel(f"Mês de referência ({months[0][:4]})" if months[0][:4] == months[-1][:4] else "Mês de referência")
    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_locator(MultipleLocator(0.002))
    ax.yaxis.set_major_formatter(percent_axis(1))
    ax.set_ylabel(f"Taxa ponderada (p = {pct(MAIN_P)})")
    grid(ax)
    legend_above(ax)
    return fig


def fig_dominant_feature(d: FigureData) -> Figure:
    values = profile_values(d, "dominant_feature")
    features = [f for f in FEATURES if f in values.index.get_level_values("category")]
    labels = [FEATURES[f] for f in features]
    fig, ax = plt.subplots(figsize=(WIDTH, 2.8))
    bars_by_algorithm(ax, labels, lambda a, g: values.get((a, features[labels.index(g)]), np.nan))
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(percent_axis(0))
    ax.set_ylabel("Proporção dos sinalizados")
    ax.tick_params(axis="x", labelsize=8)
    grid(ax)
    legend_above(ax)
    return fig


def fig_surrogate(d: FigureData) -> Figure:
    fig, ax = plt.subplots(figsize=(WIDTH, 1.8))
    data = d.surrogates.set_index("algorithm").reindex(ALGORITHMS)
    y = np.arange(len(ALGORITHMS))[::-1]
    ax.barh(y, data.fidelity, 0.55, color=[COLORS[a] for a in ALGORITHMS])
    for yi, v in zip(y, data.fidelity):
        ax.text(v, yi, f"  {br(v, 2)}", va="center", color=INK, fontsize=8)
    ax.set_yticks(y, [LABELS[a] for a in ALGORITHMS])
    ax.tick_params(axis="y", length=0)
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(number_axis(1))
    ax.set_xlabel("Fidelidade (R²) da árvore substituta de profundidade 3")
    grid(ax, "x")
    return fig


def h2_medians(tests: pd.DataFrame) -> pd.DataFrame:
    """Median Jaccard between months per p: IF, LOF, One-Class SVM and the IF seed noise (decision 0008)."""
    rows = []
    for suffix, p in (("p01", 0.01), ("p05", 0.05)):
        lof = tests[(tests.family == "H2") & (tests.variable == f"jaccard_if_minus_lof_{suffix}")]
        ocsvm = tests[(tests.family == "H2_context") & (tests.variable == f"jaccard_if_minus_ocsvm_{suffix}")]
        if lof.empty:
            continue
        dl = lof.details.iloc[0]
        do = ocsvm.details.iloc[0] if len(ocsvm) else {}
        rows.append({"p": p, "isolation_forest": dl["median_jaccard_if"], "lof": dl["median_jaccard_other"],
                     "one_class_svm": do.get("median_jaccard_other", np.nan), "noise": dl["median_if_seed_noise"]})
    return pd.DataFrame(rows)


def fig_h2(d: FigureData) -> Figure | None:
    data = h2_medians(d.tests)
    if data.empty:
        return None
    fig, ax = plt.subplots(figsize=(WIDTH, 2.6))
    series = [*ALGORITHMS, "noise"]
    names = {**LABELS, "noise": "Referência: IF com outra semente"}
    colors = {**COLORS, "noise": NEUTRAL}
    x = np.arange(len(data))
    width = 0.2
    for i, s in enumerate(series):
        ax.bar(x + (i - 1.5) * width, data[s], width * 0.92, color=colors[s], label=names[s])
    ax.set_xticks(x, [f"p = {pct(p)}" for p in data.p])
    ax.tick_params(axis="x", length=0)
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(number_axis(1))
    ax.set_ylabel("Jaccard mediano entre meses")
    grid(ax)
    legend_above(ax, ncols=2)
    return fig


def h1c_retention(tests: pd.DataFrame) -> pd.DataFrame:
    """Median retention of the flagged records per fraction of identical copies (H1c), one column per algorithm."""
    columns = {"retention_if": "isolation_forest", "retention_lof": "lof", "retention_ocsvm": "one_class_svm"}
    rows = tests[(tests.family == "H1c_manipulation") & tests.variable.isin(list(columns))]
    data = {columns[v]: {float(f): m for f, m in det["medians"].items()} for v, det in zip(rows.variable, rows.details)}
    return pd.DataFrame(data).sort_index()


def fig_h1c(d: FigureData) -> Figure | None:
    data = h1c_retention(d.tests)
    if data.empty:
        return None
    fig, ax = plt.subplots(figsize=(WIDTH, 2.6))
    for a in ALGORITHMS:
        if a in data:
            ax.plot(data.index, data[a], color=COLORS[a], marker=MARKERS[a], markersize=5, linewidth=1.6,
                    label=LABELS[a], markeredgecolor="white", markeredgewidth=0.6)
    ax.set_xticks(data.index, [pct(f) for f in data.index])
    ax.set_ylim(0, 1.05)
    ax.yaxis.set_major_formatter(number_axis(1))
    ax.set_xlabel("Fração da célula substituída por cópias de um registro típico")
    ax.set_ylabel("Retenção dos sinalizados")
    grid(ax)
    legend_above(ax)
    return fig


# Order, file name, builder and suggested caption of each figure.
FIGURES: list[tuple[str, Callable[[FigureData], Figure | None], str]] = [
    ("tempo-execucao", fig_time,
     "Tempo total de execução (treino e pontuação) de cada algoritmo na amostra principal, com a configuração principal."),
    ("escalabilidade", fig_scalability,
     "Tempo total por tamanho da amostra (média de 3 repetições; barras: mínimo e máximo). O LOF não foi executado "
     "acima de cerca de 57 mil registros, por limite de memória com a regra de vizinhos."),
    ("proporcao-ponderada", fig_weighted_share,
     "Proporção ponderada de registros sinalizados por limiar p, que estima a proporção na população."),
    ("concordancia-jaccard", fig_agreement,
     "Concordância entre os algoritmos: índice de Jaccard dos conjuntos sinalizados, por par e por limiar p."),
    ("sobreposicao", fig_overlap,
     "Registros da amostra principal sinalizados por exatamente 1, 2 ou 3 algoritmos, por limiar p."),
    ("estabilidade-parametros", fig_parameter_stability,
     "Estabilidade frente aos parâmetros: Jaccard dos sinalizados (p = 1%) entre cada variação de hiperparâmetros "
     "e a configuração principal do mesmo algoritmo."),
    ("estabilidade-dados", fig_data_stability,
     "Estabilidade frente aos dados: Jaccard entre a execução principal e as execuções treinadas em 10 amostras "
     "adicionais, que pontuam a amostra principal (ponto: mediana; barras: mínimo e máximo)."),
    ("taxa-por-tipo", fig_type_rate,
     "Taxa ponderada de sinalização por tipo de favorecido (p = 1%), em ordem decrescente de participação na população."),
    ("taxa-por-mes", fig_month_rate,
     "Taxa ponderada de sinalização por mês de referência (p = 1%)."),
    ("feature-dominante", fig_dominant_feature,
     "Feature dominante dos registros sinalizados (p = 1%): proporção dos sinalizados cuja feature mais afastada do "
     "centro, após o escalonamento robusto, é cada uma."),
    ("fidelidade-substituto", fig_surrogate,
     "Fidelidade (R²) de uma árvore de regressão de profundidade 3 treinada para imitar o escore normalizado de cada "
     "algoritmo."),
    ("h2-estabilidade-meses", fig_h2,
     "H2: Jaccard mediano, nos 132 pares de meses, entre o modelo treinado em um mês e o modelo do próprio mês. A "
     "referência mede apenas o efeito de trocar a semente do Isolation Forest."),
    ("h1c-retencao", fig_h1c,
     "H1c: retenção mediana dos registros sinalizados nas 12 células de pessoa jurídica, conforme uma fração da "
     "célula é substituída por cópias idênticas de um registro típico."),
]


def render(data: FigureData, out: Path, formats: tuple[str, ...] = ("png", "svg")) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written, captions = [], []
    number = 0
    for slug, build, caption in FIGURES:
        fig = build(data)
        if fig is None:
            continue
        number += 1
        stem = f"{number:02d}-{slug}"
        for fmt in formats:
            path = out / f"{stem}.{fmt}"
            # Fixed metadata keeps re-generated files byte-identical when the data does not change.
            metadata = {"Software": None} if fmt == "png" else {"Date": None}
            fig.savefig(path, format=fmt, metadata=metadata)
            written.append(path)
        plt.close(fig)
        captions.append(f"| `{stem}` | {caption} |")
    legend = out / "legendas.md"
    legend.write_text(
        f"# Figuras do experimento `{data.name}`\n\n"
        "Geradas por `python -m anomalygov_ml.figures` a partir das tabelas gravadas por `anomalygov_ml.report` "
        "(os mesmos números de `docs/resultados/`). Legendas sugeridas; no artigo, indicar a fonte como "
        "\"elaborado pelo autor com dados do Portal da Transparência (2025)\". Registros sinalizados são "
        "estatisticamente atípicos e não indicam fraude ou irregularidade.\n\n"
        "| Arquivo | Legenda sugerida |\n|---|---|\n" + "\n".join(captions) + "\n",
        encoding="utf-8", newline="\n")
    written.append(legend)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera as figuras de um experimento para o artigo.")
    parser.add_argument("experiment")
    parser.add_argument("--out", type=Path, help="pasta de saída (padrão: ../docs/resultados/figuras/<experimento>)")
    parser.add_argument("--formats", default="png,svg", help="formatos separados por vírgula (png, svg, pdf)")
    args = parser.parse_args()
    out = args.out or Path(__file__).resolve().parents[3] / "docs" / "resultados" / "figuras" / args.experiment
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        data = load(conn, args.experiment)
    written = render(data, out, tuple(args.formats.split(",")))
    print(f"{len(written)} arquivos gravados em {out}")


if __name__ == "__main__":
    main()
