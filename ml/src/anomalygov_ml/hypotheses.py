"""Tests of hypotheses H1 and H2 on the main sample of an experiment (decision 0008).

Usage: python -m anomalygov_ml.hypotheses CONFIG [--only h1,h2]

Every algorithm fit is recorded in `runs` (purposes h1_* and h2_*, with the subset in `runs.subset`);
per-unit measures go to `hypothesis_units` and test results to `hypothesis_tests`. Re-running replaces the
previous hypothesis runs and results of the same experiment.
"""

import argparse
import hashlib
import itertools
import os
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import psycopg
from psycopg.types.json import Jsonb
from scipy.stats import friedmanchisquare, kurtosis, ks_2samp, mannwhitneyu, skew, wilcoxon
from sklearn.preprocessing import RobustScaler

from anomalygov_ml import metrics, stats
from anomalygov_ml.db import read_query
from anomalygov_ml.experiment import environment, insert_run, log
from anomalygov_ml.ingest import ADAPTERS
from anomalygov_ml.models import DETECTORS

ALGORITHMS = ("isolation_forest", "lof", "one_class_svm")
PAIRS = list(itertools.combinations(ALGORITHMS, 2))
SHORT = {"isolation_forest": "if", "lof": "lof", "one_class_svm": "ocsvm"}
PURPOSES = ("h1_cell", "h1_subsample", "h1_manipulation", "h2_month", "h2_noise")


def pkey(p: float) -> str:
    return f"p{round(p * 100):02d}"


@dataclass
class Context:
    conn: psycopg.Connection
    config: dict[str, Any]
    config_sha256: str
    experiment: str
    main_params: dict[str, dict[str, Any]]
    sample_id: int
    features: np.ndarray  # unscaled, rows aligned with `records`
    feature_columns: list[str]
    records: pd.DataFrame  # month, favored_type
    environment: dict[str, Any]
    test_rows: list[dict[str, Any]]


def load_context(conn: psycopg.Connection, config_path: Path) -> Context:
    raw = config_path.read_bytes()
    config = tomllib.loads(raw.decode("utf-8"))
    base = tomllib.loads((config_path.parent / config["base_config"]).read_text(encoding="utf-8"))
    experiment = base["name"]
    row = conn.execute(
        "SELECT scored_sample_id FROM runs WHERE experiment = %s AND purpose = 'main' LIMIT 1", (experiment,)
    ).fetchone()
    if row is None:
        raise ValueError(f"o experimento {experiment!r} ainda não tem execuções principais")
    sample_id = row[0]
    records = read_query(
        conn,
        f"""SELECT sr.payment_id, extract(month FROM p.reference_month)::int AS month, f.favored_type
            FROM sample_records sr JOIN payments p ON p.id = sr.payment_id JOIN favored f ON f.id = p.favored_id
            WHERE sr.sample_id = {int(sample_id)} ORDER BY sr.payment_id""",
    )
    adapter = ADAPTERS[base["source"]]
    columns = list(adapter.feature_columns)
    features = adapter.load_features(conn, records["payment_id"].tolist())[columns].to_numpy()
    return Context(conn, config, hashlib.sha256(raw).hexdigest(), experiment, base["main"], sample_id, features,
                   columns, records, environment(), [])


def fit_score(ctx: Context, purpose: str, algorithm: str, X_train: np.ndarray, subset: dict[str, Any],
              score_sets: list[np.ndarray | None], novelty: bool = False,
              random_state: int | None = None) -> list[np.ndarray]:
    """Fit one algorithm on X_train and score each set (None = the training rows); record the run."""
    params = dict(ctx.main_params[algorithm])
    configured_state = params.pop("random_state", None)
    state = configured_state if random_state is None else random_state
    detector = DETECTORS[algorithm](params, state)
    if novelty and algorithm == "lof":
        detector.params["novelty"] = True
    scaler = RobustScaler().fit(X_train)
    Xt = scaler.transform(X_train)
    start = time.perf_counter()
    detector.fit(Xt)
    fit_seconds = time.perf_counter() - start
    start = time.perf_counter()
    scores = [detector.score(Xt) if S is None else detector.score(scaler.transform(S)) for S in score_sets]
    score_seconds = time.perf_counter() - start
    with ctx.conn.transaction(), ctx.conn.cursor() as cur:
        insert_run(cur, ctx.experiment, ctx.config_sha256, purpose, algorithm, detector.resolved_params, state,
                   ctx.feature_columns, ctx.sample_id, None, len(Xt), sum(len(s) for s in scores), fit_seconds,
                   score_seconds, ctx.environment, subset)
    return scores


def add_test(ctx: Context, hypothesis: str, family: str, test: str, variable: str, n: int, statistic=None,
             effect=None, ci=(None, None), p_value=None, **details) -> None:
    ctx.test_rows.append(dict(hypothesis=hypothesis, family=family, test=test, variable=variable, n=n,
                              statistic=statistic, effect=effect, ci_low=ci[0], ci_high=ci[1], p_value=p_value,
                              details=details))


def store_units(ctx: Context, hypothesis: str, units: list[tuple[dict, dict]]) -> None:
    with ctx.conn.transaction(), ctx.conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO hypothesis_units (experiment, hypothesis, unit, measures) VALUES (%s, %s, %s, %s)",
            [(ctx.experiment, hypothesis, Jsonb(unit), Jsonb(measures)) for unit, measures in units],
        )


# ---------------------------------------------------------------- H2


def run_h2(ctx: Context) -> None:
    cfg, p_values = ctx.config, (ctx.config["p"], ctx.config["p_secondary"])
    X, months = ctx.features, sorted(ctx.records["month"].unique())
    rng = np.random.default_rng(cfg["seed"])
    A, B = {}, {}
    for m in months:
        rows = rng.permutation(np.flatnonzero(ctx.records["month"].to_numpy() == m))
        A[m], B[m] = np.sort(rows[: len(rows) // 2]), np.sort(rows[len(rows) // 2:])

    scores = {}
    for alg in ALGORITHMS:
        for t in months:
            subset = {"month": int(t), "half": "A", "scored": "half B of every month"}
            result = fit_score(ctx, "h2_month", alg, X[A[t]], subset, [X[B[e]] for e in months], novelty=True)
            scores[alg, t] = dict(zip(months, result))
        log(f"H2: {alg} treinado nos 12 meses")
    noise = {}
    for e in months:
        subset = {"month": int(e), "half": "A", "scored": "half B of the same month"}
        noise[e] = fit_score(ctx, "h2_noise", "isolation_forest", X[A[e]], subset, [X[B[e]]],
                             random_state=cfg["h2"]["noise_seed"])[0]

    units, rows = [], []
    for t, e in itertools.permutations(months, 2):
        drift = float(np.mean([ks_2samp(X[A[t], j], X[A[e], j]).statistic for j in range(X.shape[1])]))
        measures = {"drift": drift}
        for alg in ALGORITHMS:
            own, other = scores[alg, e][e], scores[alg, t][e]
            for p in p_values:
                measures[f"jaccard_{SHORT[alg]}_{pkey(p)}"] = metrics.jaccard(
                    metrics.flagged(other, p), metrics.flagged(own, p))
            measures[f"spearman_{SHORT[alg]}"] = metrics.spearman(other, own)
        units.append(({"train_month": int(t), "eval_month": int(e)}, measures))
        rows.append({"eval_month": e, **measures})
    for e in months:
        measures = {f"jaccard_if_noise_{pkey(p)}": metrics.jaccard(
            metrics.flagged(noise[e], p), metrics.flagged(scores["isolation_forest", e][e], p)) for p in p_values}
        units.append(({"eval_month": int(e), "kind": "seed_noise"}, measures))
    store_units(ctx, "H2", units)

    df = pd.DataFrame(rows)
    noise_df = pd.DataFrame([m for u, m in units if u.get("kind") == "seed_noise"])
    for family, other in (("H2", "lof"), ("H2_context", "ocsvm")):
        for p in p_values:
            d = (df[f"jaccard_if_{pkey(p)}"] - df[f"jaccard_{other}_{pkey(p)}"]).to_numpy()
            alternative = "greater" if family == "H2" else "two-sided"
            w = wilcoxon(d, alternative=alternative)
            ci = stats.block_bootstrap_mean(d, df["eval_month"].to_numpy(), cfg["bootstrap"], cfg["seed"])
            add_test(ctx, "H2", family, f"wilcoxon_{alternative}", f"jaccard_if_minus_{other}_{pkey(p)}", len(d),
                     statistic=float(w.statistic), effect=float(np.mean(d)), ci=ci, p_value=float(w.pvalue),
                     median_difference=float(np.median(d)),
                     median_jaccard_if=float(df[f"jaccard_if_{pkey(p)}"].median()),
                     median_jaccard_other=float(df[f"jaccard_{other}_{pkey(p)}"].median()),
                     median_if_seed_noise=float(noise_df[f"jaccard_if_noise_{pkey(p)}"].median()))
        d = (df[f"jaccard_if_{pkey(cfg['p'])}"] - df[f"jaccard_{other}_{pkey(cfg['p'])}"]).to_numpy()
        rho, p_perm = stats.spearman_permutation(df["drift"].to_numpy(), d, cfg["permutations"], cfg["seed"])
        add_test(ctx, "H2", family, "spearman_permutation", f"drift_vs_jaccard_if_minus_{other}_{pkey(cfg['p'])}",
                 len(d), statistic=rho, effect=rho, p_value=p_perm)
    log("H2: testes calculados")


# ---------------------------------------------------------------- H1


def cell_indicators(ctx: Context, Xc: np.ndarray, subset: dict, purpose: str, rng: np.random.Generator,
                    with_stability: bool) -> tuple[dict[str, float], dict[str, np.ndarray]]:
    """Agreement (and optionally subsample stability) of the algorithms in one cell; also returns the scores.

    Comparisons on a subset of rows always re-apply the top-p threshold within that subset, so that both
    sides flag the same number of rows and the Jaccard has no mechanical ceiling.
    """
    p, cfg = ctx.config["p"], ctx.config["h1"]
    scores = {alg: fit_score(ctx, purpose, alg, Xc, subset, [None])[0] for alg in ALGORITHMS}
    flags = {alg: metrics.flagged(s, p) for alg, s in scores.items()}
    measures = {f"jaccard_{SHORT[a]}_{SHORT[b]}": metrics.jaccard(flags[a], flags[b]) for a, b in PAIRS}
    if with_stability:
        size = round(cfg["subsample_fraction"] * len(Xc))
        for alg in ALGORITHMS:
            values = []
            for repetition in range(cfg["subsample_repetitions"]):
                rows = np.sort(rng.choice(len(Xc), size=size, replace=False))
                sub_subset = {**subset, "subsample": repetition, "fraction": cfg["subsample_fraction"]}
                sub_scores = fit_score(ctx, "h1_subsample", alg, Xc[rows], sub_subset, [None])[0]
                values.append(metrics.jaccard(metrics.flagged(sub_scores, p), metrics.flagged(scores[alg][rows], p)))
            measures[f"stability_{SHORT[alg]}"] = float(np.mean(values))
    return measures, scores


def atypicality(ctx: Context, Xc: np.ndarray) -> dict[str, float]:
    log_amount = Xc[:, ctx.feature_columns.index("log_amount")]
    duplicated = pd.DataFrame(np.round(Xc, 9)).duplicated(keep=False).mean()
    return {"duplicate_share": float(duplicated), "kurtosis": float(kurtosis(log_amount)),
            "skewness": float(skew(log_amount))}


def run_h1(ctx: Context) -> None:
    cfg, h1 = ctx.config, ctx.config["h1"]
    X, months = ctx.features, sorted(ctx.records["month"].unique())
    rng = np.random.default_rng(cfg["seed"])
    month_of, type_of = ctx.records["month"].to_numpy(), ctx.records["favored_type"].to_numpy()

    units, rows = [], []
    for m, t in itertools.product(months, h1["types"]):
        Xc = X[(month_of == m) & (type_of == t)]
        subset = {"month": int(m), "favored_type": t}
        indicators, _ = cell_indicators(ctx, Xc, subset, "h1_cell", rng, with_stability=True)
        measures = {**indicators, **atypicality(ctx, Xc), "n": len(Xc)}
        units.append((subset, measures))
        rows.append({**subset, **measures})
    log("H1: 24 células analisadas")

    if h1["manipulation_fractions"][0] != 0:
        raise ValueError("a primeira fração da manipulação deve ser 0 (referência)")
    manipulation_units, manipulation_rows = [], []
    for m in months:
        Xc = X[(month_of == m) & (type_of == h1["manipulation_type"])]
        scaled = RobustScaler().fit_transform(Xc)
        typical = Xc[np.argmin(np.abs(scaled - np.median(scaled, axis=0)).sum(axis=1))]
        replaced_order = rng.permutation(len(Xc))
        baseline = None
        for fraction in h1["manipulation_fractions"]:
            replaced = np.sort(replaced_order[: round(fraction * len(Xc))])
            Xm = Xc.copy()
            Xm[replaced] = typical
            subset = {"month": int(m), "favored_type": h1["manipulation_type"], "duplicate_fraction": fraction}
            measures, scores = cell_indicators(ctx, Xm, subset, "h1_manipulation", rng, with_stability=False)
            kept = np.setdiff1d(np.arange(len(Xc)), replaced)
            if baseline is None:
                baseline = scores
            p = cfg["p"]
            for alg in ALGORITHMS:
                # Threshold within the kept rows on both sides: the copies are never flagged, so thresholding over
                # the whole manipulated cell would cap the Jaccard at about 1 - fraction regardless of the algorithm.
                measures[f"retention_{SHORT[alg]}"] = metrics.jaccard(
                    metrics.flagged(scores[alg][kept], p), metrics.flagged(baseline[alg][kept], p))
            measures["duplicate_share"] = atypicality(ctx, Xm)["duplicate_share"]
            manipulation_units.append((subset, measures))
            manipulation_rows.append({**subset, **measures})
    log("H1: manipulação controlada concluída")
    store_units(ctx, "H1", units + manipulation_units)

    df = pd.DataFrame(rows)
    indicators = [f"jaccard_{SHORT[a]}_{SHORT[b]}" for a, b in PAIRS] + [f"stability_{SHORT[a]}" for a in ALGORITHMS]
    first, second = h1["types"]
    for name in indicators:
        g1, g2 = df.loc[df.favored_type == first, name], df.loc[df.favored_type == second, name]
        u = mannwhitneyu(g1, g2, alternative="two-sided")
        add_test(ctx, "H1", "H1a_type", "mann_whitney", name, len(df), statistic=float(u.statistic),
                 effect=stats.rank_biserial(u.statistic, len(g1), len(g2)), p_value=float(u.pvalue),
                 groups=[first, second], median_first=float(g1.median()), median_second=float(g2.median()))
    for measure in ("duplicate_share", "kurtosis", "skewness"):
        for name in indicators:
            rho, p_perm = stats.spearman_permutation(df[measure].to_numpy(), df[name].to_numpy(),
                                                     cfg["permutations"], cfg["seed"])
            add_test(ctx, "H1", "H1b_association", "spearman_permutation", f"{measure}_vs_{name}", len(df),
                     statistic=rho, effect=rho, p_value=p_perm)

    mdf = pd.DataFrame(manipulation_rows)
    fractions = h1["manipulation_fractions"]
    for name in [f"jaccard_{SHORT[a]}_{SHORT[b]}" for a, b in PAIRS] + [f"retention_{SHORT[a]}" for a in ALGORITHMS]:
        table = mdf.pivot(index="month", columns="duplicate_fraction", values=name)[fractions]
        f = friedmanchisquare(*(table[c].to_numpy() for c in fractions))
        kendall_w = f.statistic / (len(table) * (len(fractions) - 1))
        add_test(ctx, "H1", "H1c_manipulation", "friedman", name, len(table), statistic=float(f.statistic),
                 effect=float(kendall_w), p_value=float(f.pvalue),
                 medians={str(c): float(table[c].median()) for c in fractions})
    log("H1: testes calculados")


# ---------------------------------------------------------------- storage


def finish(ctx: Context) -> None:
    rows = pd.DataFrame(ctx.test_rows)
    rows["p_adjusted"] = None
    for family, idx in rows.groupby("family").groups.items():
        rows.loc[idx, "p_adjusted"] = stats.holm(rows.loc[idx, "p_value"].tolist())
    # pandas turns a missing value (e.g. no confidence interval) into NaN; store it as NULL.
    rows = rows.astype(object).where(rows.notna(), None)
    with ctx.conn.transaction(), ctx.conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO hypothesis_tests (experiment, hypothesis, family, test, variable, n, statistic, effect,
                                             ci_low, ci_high, p_value, p_adjusted, details)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [(ctx.experiment, r.hypothesis, r.family, r.test, r.variable, int(r.n), r.statistic, r.effect,
              r.ci_low, r.ci_high, r.p_value, r.p_adjusted, Jsonb({**r.details, "alpha": ctx.config["alpha"]}))
             for r in rows.itertuples()],
        )


def clear_previous(ctx: Context, hypotheses: tuple[str, ...]) -> None:
    purposes = [p for p in PURPOSES if p.split("_")[0].upper() in hypotheses]
    with ctx.conn.transaction():
        ctx.conn.execute("DELETE FROM runs WHERE experiment = %s AND purpose = ANY (%s)", (ctx.experiment, purposes))
        ctx.conn.execute("DELETE FROM hypothesis_units WHERE experiment = %s AND hypothesis = ANY (%s)",
                         (ctx.experiment, list(hypotheses)))
        ctx.conn.execute("DELETE FROM hypothesis_tests WHERE experiment = %s AND hypothesis = ANY (%s)",
                         (ctx.experiment, list(hypotheses)))


def run(conn: psycopg.Connection, config_path: Path, only: tuple[str, ...] = ("H1", "H2")) -> Context:
    ctx = load_context(conn, config_path)
    clear_previous(ctx, only)
    if "H2" in only:
        run_h2(ctx)
    if "H1" in only:
        run_h1(ctx)
    finish(ctx)
    return ctx


def main() -> None:
    parser = argparse.ArgumentParser(description="Executa os testes das hipóteses H1 e H2 (decisão 0008).")
    parser.add_argument("config", type=Path)
    parser.add_argument("--only", default="h1,h2")
    args = parser.parse_args()
    only = tuple(h.strip().upper() for h in args.only.split(","))
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        run(conn, args.config, only)


if __name__ == "__main__":
    main()
