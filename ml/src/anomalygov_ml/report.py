"""Metrics of section 2 of AGENTS.md for one experiment (decision 0007).

Usage: python -m anomalygov_ml.report EXPERIMENT [--out FILE.md]

Reads the runs of the experiment from the local database (DATABASE_URL), stores per-run metrics and
pairwise comparisons (run_metrics, run_comparisons) and writes a Markdown report.
"""

import argparse
import itertools
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg
from sklearn.preprocessing import RobustScaler
from sklearn.metrics import r2_score
from sklearn.tree import DecisionTreeRegressor, export_text

from anomalygov_ml import metrics
from anomalygov_ml.db import read_query
from anomalygov_ml.ingest import ADAPTERS

P_VALUES = (0.01, 0.02, 0.05)
MAIN_P = 0.01
ALGORITHMS = ("isolation_forest", "lof", "one_class_svm")
LABELS = {"isolation_forest": "Isolation Forest", "lof": "LOF", "one_class_svm": "One-Class SVM"}
SURROGATE_DEPTH = 3


# ---------------------------------------------------------------- pure metrics


def weighted_share(mask: np.ndarray, weights: np.ndarray) -> float:
    return float(weights[mask].sum() / weights.sum())


def overlap_counts(flags: dict[str, np.ndarray]) -> dict[int, int]:
    """How many records are flagged by exactly k of the algorithms, for k = 1..len(flags)."""
    votes = np.sum(list(flags.values()), axis=0)
    return {k: int((votes == k).sum()) for k in range(1, len(flags) + 1)}


def group_profile(flags: np.ndarray, groups: pd.Series, weights: np.ndarray) -> pd.DataFrame:
    """Per group: weighted share of the population, weighted share among flagged, weighted flagged rate."""
    frame = pd.DataFrame({"group": groups.to_numpy(), "w": weights, "wf": weights * flags})
    by = frame.groupby("group")[["w", "wf"]].sum()
    return pd.DataFrame({
        "population_share": by["w"] / by["w"].sum(),
        "flagged_share": by["wf"] / by["wf"].sum(),
        "flagged_rate": by["wf"] / by["w"],
    })


def dominant_feature(X_scaled: np.ndarray, flags: np.ndarray, columns: list[str]) -> pd.Series:
    """Share of flagged records whose most extreme (robust-scaled) feature is each column."""
    dominant = np.abs(X_scaled[flags]).argmax(axis=1)
    counts = pd.Series(dominant).value_counts(normalize=True)
    return pd.Series({c: float(counts.get(i, 0.0)) for i, c in enumerate(columns)})


def surrogate_tree(X: np.ndarray, normalized_scores: np.ndarray, columns: list[str]) -> tuple[float, str]:
    """Global surrogate: shallow regression tree imitating the normalized scores.

    Returns its fidelity (R² against the scores) and its rules, with thresholds in the original feature units.
    """
    tree = DecisionTreeRegressor(max_depth=SURROGATE_DEPTH, random_state=0).fit(X, normalized_scores)
    fidelity = float(r2_score(normalized_scores, tree.predict(X)))
    return fidelity, export_text(tree, feature_names=columns, decimals=2)


# ---------------------------------------------------------------- data


@dataclass
class ExperimentData:
    name: str
    runs: pd.DataFrame  # one row per run, indexed by id
    scores: pd.DataFrame  # raw scores of runs that scored the main sample: payment_id x run_id
    records: pd.DataFrame  # main sample records with weights and attributes, indexed by payment_id
    features: pd.DataFrame  # unscaled features of the main sample, indexed by payment_id
    dataset_files: pd.DataFrame
    hypothesis_tests: pd.DataFrame

    def main_run(self, algorithm: str) -> int:
        return int(self.runs[(self.runs.purpose == "main") & (self.runs.algorithm == algorithm)].index[0])

    def flags(self, run_id: int, p: float) -> np.ndarray:
        return metrics.flagged(self.scores[run_id].to_numpy(), p)


def load(conn: psycopg.Connection, name: str) -> ExperimentData:
    rows = conn.execute(
        """SELECT id, purpose, algorithm, params, random_state, train_sample_id, scored_sample_id, n_train,
                  n_scored, fit_seconds, score_seconds, environment, config_sha256
           FROM runs WHERE experiment = %s ORDER BY id""",
        (name,),
    ).fetchall()
    if not rows:
        raise ValueError(f"nenhuma execução para o experimento {name!r}")
    columns = ["id", "purpose", "algorithm", "params", "random_state", "train_sample_id", "scored_sample_id",
               "n_train", "n_scored", "fit_seconds", "score_seconds", "environment", "config_sha256"]
    runs = pd.DataFrame(rows, columns=columns).set_index("id")

    main_sample = int(runs.loc[runs.purpose == "main", "scored_sample_id"].iloc[0])
    scored_ids = ",".join(str(i) for i in runs.index[runs.scored_sample_id == main_sample])
    scores = read_query(
        conn, f"SELECT run_id, payment_id, raw_score FROM run_scores WHERE run_id IN ({scored_ids})"
    ).pivot(index="payment_id", columns="run_id", values="raw_score")

    records = read_query(
        conn,
        f"""SELECT sr.payment_id, sr.weight, f.favored_type, p.reference_month, p.amount,
                   m.superior_agency_name
            FROM sample_records sr
            JOIN payments p ON p.id = sr.payment_id
            JOIN favored f ON f.id = p.favored_id
            JOIN management_units m ON m.code = p.management_unit_code
            WHERE sr.sample_id = {main_sample}""",
        parse_dates=["reference_month"],
    ).set_index("payment_id").loc[scores.index]

    source = conn.execute("SELECT source FROM samples WHERE id = %s", (main_sample,)).fetchone()[0]
    adapter = ADAPTERS[source]
    features = adapter.load_features(conn, scores.index.tolist())[list(adapter.feature_columns)]
    dataset_files = read_query(
        conn,
        f"""SELECT d.id, d.file_name, d.loaded_row_count FROM dataset_files d
            JOIN samples s ON d.id = ANY (s.dataset_file_ids) WHERE s.id = {main_sample} ORDER BY d.id""",
    )
    test_rows = conn.execute(
        """SELECT hypothesis, family, test, variable, n, statistic, effect, ci_low, ci_high, p_value, p_adjusted,
                  details FROM hypothesis_tests WHERE experiment = %s ORDER BY id""",
        (name,),
    ).fetchall()
    hypothesis_tests = pd.DataFrame(test_rows, columns=[
        "hypothesis", "family", "test", "variable", "n", "statistic", "effect", "ci_low", "ci_high", "p_value",
        "p_adjusted", "details"])
    return ExperimentData(name, runs, scores, records, features, dataset_files, hypothesis_tests)


# ---------------------------------------------------------------- metrics tables


def compute_tables(data: ExperimentData) -> tuple[pd.DataFrame, pd.DataFrame]:
    weights = data.records["weight"].to_numpy()
    metric_rows = []
    for run_id in data.scores.columns:
        for p in P_VALUES:
            flags = data.flags(run_id, p)
            metric_rows.append((run_id, p, int(flags.sum()), float(flags.mean()), weighted_share(flags, weights)))
    run_metrics = pd.DataFrame(
        metric_rows, columns=["run_id", "p", "flagged_count", "flagged_share", "weighted_flagged_share"]
    )

    main = {alg: data.main_run(alg) for alg in ALGORITHMS}
    pairs = list(itertools.combinations(main.values(), 2))
    for run_id, run in data.runs.loc[data.scores.columns].iterrows():
        if run.purpose != "main":
            pairs.append((main[run.algorithm], run_id))
    comparison_rows = []
    for a, b in pairs:
        a, b = sorted((int(a), int(b)))
        rho = metrics.spearman(data.scores[a].to_numpy(), data.scores[b].to_numpy())
        for p in P_VALUES:
            comparison_rows.append((a, b, p, metrics.jaccard(data.flags(a, p), data.flags(b, p)), rho))
    run_comparisons = pd.DataFrame(comparison_rows, columns=["run_a", "run_b", "p", "jaccard", "spearman"])
    return run_metrics, run_comparisons


def store_tables(conn: psycopg.Connection, run_metrics: pd.DataFrame, run_comparisons: pd.DataFrame) -> None:
    run_ids = [int(i) for i in run_metrics["run_id"].unique()]
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("DELETE FROM run_metrics WHERE run_id = ANY (%s)", (run_ids,))
        cur.execute("DELETE FROM run_comparisons WHERE run_a = ANY (%s) OR run_b = ANY (%s)", (run_ids, run_ids))
        cur.executemany(
            "INSERT INTO run_metrics VALUES (%s, %s, %s, %s, %s)",
            [(int(r), float(p), int(n), float(s), float(w)) for r, p, n, s, w in run_metrics.itertuples(index=False)],
        )
        cur.executemany(
            "INSERT INTO run_comparisons VALUES (%s, %s, %s, %s, %s)",
            [(int(a), int(b), float(p), float(j), float(r)) for a, b, p, j, r in run_comparisons.itertuples(index=False)],
        )


# ---------------------------------------------------------------- report


def num(value: float, decimals: int = 3) -> str:
    return f"{value:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def pct(value: float, decimals: int = 1) -> str:
    return num(100 * value, decimals) + "%"


def table(header: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def short_params(run: pd.Series) -> str:
    keys = {
        "isolation_forest": ("n_estimators", "max_samples"),
        "lof": ("n_neighbors", "neighbors_margin"),
        "one_class_svm": ("nu", "gamma"),
    }[run.algorithm]
    return ", ".join(f"{k}={run.params.get(k)}" for k in keys if run.params.get(k) is not None)


def render(data: ExperimentData, run_metrics: pd.DataFrame, run_comparisons: pd.DataFrame) -> str:
    runs, weights = data.runs, data.records["weight"].to_numpy()
    main = {alg: data.main_run(alg) for alg in ALGORITHMS}
    main_flags = {alg: data.flags(run_id, MAIN_P) for alg, run_id in main.items()}
    jaccard = run_comparisons.set_index(["run_a", "run_b", "p"])["jaccard"]
    spearman = run_comparisons.groupby(["run_a", "run_b"])["spearman"].first()
    env = runs.loc[main["isolation_forest"], "environment"]
    columns = list(data.features.columns)
    out = []

    def pair(a: int, b: int, p: float) -> float:
        return float(jaccard[(min(a, b), max(a, b), p)])

    out.append(f"# Resultados: experimento `{data.name}`\n")
    out.append("Gerado por `python -m anomalygov_ml.report`. Os registros sinalizados são estatisticamente "
               "atípicos e **não** indicam fraude ou irregularidade.\n")

    out.append("## Identificação\n")
    main_run = runs.loc[main["isolation_forest"]]
    out.append(table(["Item", "Valor"], [
        ["Configuração (SHA-256)", f"`{main_run.config_sha256}`"],
        ["Amostra principal", f"id {int(main_run.scored_sample_id)}, {num(len(data.records), 0)} registros"],
        ["Base", f"{len(data.dataset_files)} arquivos, {num(data.dataset_files.loaded_row_count.sum(), 0)} "
                 "registros (hashes em `docs/datasets.md`)"],
        ["Features", ", ".join(f"`{c}`" for c in columns)],
        ["Ambiente", f"Python {env['python']}, scikit-learn {env['scikit_learn']}, numpy {env['numpy']}, "
                     f"pandas {env['pandas']}, {env['cpu_count']} CPUs lógicas, n_jobs={env['n_jobs']}"],
    ]))

    out.append("\n## 1. Tempo de execução\n")
    out.append("Configuração principal, amostra principal:\n")
    out.append(table(["Algoritmo", "Parâmetros", "Treino (s)", "Pontuação (s)", "Total (s)"], [
        [LABELS[a], short_params(runs.loc[r]), num(runs.loc[r].fit_seconds, 1), num(runs.loc[r].score_seconds, 1),
         num(runs.loc[r].fit_seconds + runs.loc[r].score_seconds, 1)] for a, r in main.items()
    ]))
    scal = runs[runs.purpose == "scalability"].assign(total=lambda d: d.fit_seconds + d.score_seconds)
    if len(scal):
        grouped = scal.groupby(["n_train", "algorithm"])["total"].agg(["mean", "min", "max"])
        out.append("\nEscalabilidade (tempo total; média e faixa entre repetições; “—” = não executado):\n")
        rows = []
        for n in sorted(scal.n_train.unique()):
            row = [num(n, 0)]
            for alg in ALGORITHMS:
                if (n, alg) in grouped.index:
                    g = grouped.loc[(n, alg)]
                    row.append(f"{num(g['mean'], 1)} ({num(g['min'], 1)}–{num(g['max'], 1)})")
                else:
                    row.append("—")
            rows.append(row)
        out.append(table(["Registros", *(LABELS[a] for a in ALGORITHMS)], rows))

    out.append("\n## 2. Proporção de registros sinalizados\n")
    out.append("“Ponderada” estima a proporção na população usando os pesos amostrais (decisão 0005).\n")
    rm = run_metrics.set_index(["run_id", "p"])
    out.append(table(["Algoritmo", "p", "Sinalizados", "Proporção na amostra", "Proporção ponderada"], [
        [LABELS[a], pct(p, 0), num(rm.loc[(r, p)].flagged_count, 0), pct(rm.loc[(r, p)].flagged_share, 2),
         pct(rm.loc[(r, p)].weighted_flagged_share, 2)] for a, r in main.items() for p in P_VALUES
    ]))

    out.append("\n## 3. Concordância e divergência\n")
    rows = []
    for a, b in itertools.combinations(ALGORITHMS, 2):
        ra, rb = main[a], main[b]
        rows.append([f"{LABELS[a]} × {LABELS[b]}", *(num(pair(ra, rb, p)) for p in P_VALUES),
                     num(float(spearman[(min(ra, rb), max(ra, rb))]))])
    out.append(table(["Par", *(f"Jaccard p={pct(p, 0)}" for p in P_VALUES), "Spearman dos escores"], rows))
    out.append("")
    rows = []
    for p in P_VALUES:
        counts = overlap_counts({alg: data.flags(r, p) for alg, r in main.items()})
        rows.append([pct(p, 0), *(num(counts[k], 0) for k in (1, 2, 3))])
    out.append(table(["p", "Sinalizado por 1 algoritmo", "Por 2", "Pelos 3"], rows))

    out.append("\n## 4. Estabilidade\n")
    out.append("### Frente aos parâmetros\n")
    out.append("Cada variação comparada com a configuração principal do mesmo algoritmo.\n")
    rows = []
    for run_id, run in runs[runs.purpose == "parameter"].iterrows():
        r0 = main[run.algorithm]
        rows.append([LABELS[run.algorithm], short_params(run), *(num(pair(r0, run_id, p)) for p in (0.01, 0.05)),
                     num(float(spearman[(min(r0, run_id), max(r0, run_id))]))])
    out.append(table(["Algoritmo", "Variação", "Jaccard p=1%", "Jaccard p=5%", "Spearman"], rows))
    out.append("\n### Frente aos dados\n")
    out.append("Treino em cada amostra adicional, pontuação da amostra principal. Mediana (mínimo–máximo) "
               "entre as amostras. O LOF usa `novelty=True` nessas execuções e `novelty=False` na principal.\n")
    rows = []
    for alg in ALGORITHMS:
        r0 = main[alg]
        ids = runs.index[(runs.purpose == "data_stability") & (runs.algorithm == alg)]
        if not len(ids):
            continue
        cells = [LABELS[alg], str(len(ids))]
        for p in (0.01, 0.05):
            values = [pair(r0, i, p) for i in ids]
            cells.append(f"{num(np.median(values))} ({num(min(values))}–{num(max(values))})")
        cells.append(num(float(np.median([spearman[(min(r0, i), max(r0, i))] for i in ids]))))
        rows.append(cells)
    out.append(table(["Algoritmo", "Amostras", "Jaccard p=1%", "Jaccard p=5%", "Spearman (mediana)"], rows))

    out.append(f"\n## 5. Características dos registros sinalizados (p = {pct(MAIN_P, 0)})\n")
    out.append("### Por tipo de favorecido\n")
    out.append("Taxa = proporção ponderada de registros do tipo que foram sinalizados.\n")
    profiles = {alg: group_profile(f, data.records["favored_type"], weights) for alg, f in main_flags.items()}
    types = profiles["isolation_forest"].index
    out.append(table(
        ["Tipo", "Na população", *(f"Taxa {LABELS[a]}" for a in ALGORITHMS)],
        [[f"`{t}`", pct(profiles["isolation_forest"].loc[t, "population_share"]),
          *(pct(profiles[a].loc[t, "flagged_rate"], 2) for a in ALGORITHMS)] for t in types],
    ))
    out.append("\n### Por mês (não estacionariedade)\n")
    months = data.records["reference_month"].dt.strftime("%Y-%m")
    month_profiles = {alg: group_profile(f, months, weights) for alg, f in main_flags.items()}
    out.append(table(
        ["Mês", *(f"Taxa {LABELS[a]}" for a in ALGORITHMS)],
        [[m, *(pct(month_profiles[a].loc[m, "flagged_rate"], 2) for a in ALGORITHMS)]
         for m in sorted(months.unique())],
    ))
    out.append("\n### Features: mediana na amostra × mediana dos sinalizados\n")
    rows = []
    for c in columns:
        values = data.features[c].to_numpy()
        row = [f"`{c}`", num(float(np.median(values)), 2)]
        for alg in ALGORITHMS:
            row.append(num(float(np.median(values[main_flags[alg]])), 2))
        rows.append(row)
    amounts = data.records["amount"].to_numpy(dtype=float)
    rows.append(["valor (R$)", num(float(np.median(amounts)), 2),
                 *(num(float(np.median(amounts[main_flags[a]])), 2) for a in ALGORITHMS)])
    out.append(table(["Feature", "Amostra", *(f"Sinalizados {LABELS[a]}" for a in ALGORITHMS)], rows))
    out.append("\n### Órgãos superiores com mais sinalizados (contagem ponderada)\n")
    for alg in ALGORITHMS:
        f = main_flags[alg]
        top = (pd.Series(weights[f], index=data.records["superior_agency_name"].to_numpy()[f])
               .groupby(level=0).sum().sort_values(ascending=False).head(5))
        share = top / weights[f].sum()
        out.append(f"- **{LABELS[alg]}:** " + "; ".join(f"{name} ({pct(s)})" for name, s in share.items()))

    out.append("\n## 6. Interpretabilidade\n")
    out.append(f"**Substituto global:** árvore de regressão de profundidade {SURROGATE_DEPTH} treinada para "
               "reproduzir o escore normalizado de cada algoritmo a partir das features. Fidelidade = R² entre a "
               "previsão da árvore e o escore; quanto maior, mais a lógica do algoritmo é explicável por poucas "
               "regras simples. Nas regras, `value` é o escore normalizado médio da folha (perto de 1 = anômalo).\n")
    X_raw = data.features.to_numpy()
    X_scaled = RobustScaler().fit_transform(X_raw)
    trees = {alg: surrogate_tree(X_raw, metrics.normalize(data.scores[r].to_numpy()), columns)
             for alg, r in main.items()}
    dominants = {alg: dominant_feature(X_scaled, f, columns) for alg, f in main_flags.items()}
    out.append(table(["Algoritmo", "Fidelidade (R²)"], [[LABELS[a], num(trees[a][0])] for a in ALGORITHMS]))
    out.append("\n**Feature dominante:** feature com maior desvio robusto (|valor escalado|) em cada registro "
               "sinalizado; proporção dos sinalizados por feature.\n")
    out.append(table(["Feature", *(LABELS[a] for a in ALGORITHMS)],
                     [[f"`{c}`", *(pct(dominants[a][c]) for a in ALGORITHMS)] for c in columns]))
    for alg in ALGORITHMS:
        out.append(f"\n<details><summary>Regras da árvore substituta: {LABELS[alg]}</summary>\n\n"
                   f"```\n{trees[alg][1]}```\n\n</details>")

    if len(data.hypothesis_tests):
        out.append(render_hypotheses(data.hypothesis_tests))

    artifacts = runs[runs.purpose == "artifact"]
    if len(artifacts):
        out.append("\n## Apêndice: artefato do LOF com vetores duplicados\n")
        out.append("Execuções demonstrativas, fora das métricas comparativas (decisão 0005).\n")
        rows = []
        for run_id, run in artifacts.iterrows():
            s = data.scores[run_id].to_numpy()
            f = metrics.flagged(s, MAIN_P)
            r0 = main[run.algorithm]
            rows.append([short_params(run), f"{s.max():.2e}", f"{num(int((f & (s > 1e3)).sum()), 0)} de {int(f.sum())}",
                         num(pair(r0, run_id, MAIN_P))])
        out.append(table(["Parâmetros", "Escore máximo", "Sinalizados com escore > 1.000", "Jaccard com o LOF principal"],
                         rows))
    return "\n".join(out) + "\n"


FAMILY_TITLES = {
    "H2": "H2: Isolation Forest × LOF entre meses (teste unilateral: IF mais estável)",
    "H2_context": "Contexto da H2: Isolation Forest × One-Class SVM (bilateral)",
    "H1a_type": "H1a: indicadores por tipo de favorecido (`individual` × `company`)",
    "H1b_association": "H1b: associação entre atipicidade da célula e indicadores",
    "H1c_manipulation": "H1c: manipulação controlada de duplicados (células `company`)",
}


def describe_details(test: pd.Series) -> str:
    d = test.details
    if "median_jaccard_if" in d:
        return (f"IF {num(d['median_jaccard_if'])}; outro {num(d['median_jaccard_other'])}; "
                f"ruído de semente do IF {num(d['median_if_seed_noise'])}")
    if "median_first" in d:
        return f"{d['groups'][0]} {num(d['median_first'])}; {d['groups'][1]} {num(d['median_second'])}"
    if "medians" in d:
        return "; ".join(f"{pct(float(f), 0)}: {num(v)}" for f, v in d["medians"].items())
    return ""


def render_hypotheses(tests: pd.DataFrame) -> str:
    out = ["\n## 7. Hipóteses (decisão 0008)\n"]
    alpha = tests.details.iloc[0]["alpha"]
    out.append(f"p ajustado pela correção de Holm dentro de cada família; significativo quando p ajustado < {num(alpha, 2)}. "
               "Efeito: diferença média dos Jaccard (H2, com IC 95% por bootstrap em blocos de meses), correlação "
               "bisserial de postos (H1a), Spearman (H1b) ou W de Kendall (H1c). As medianas descrevem os indicadores.\n")
    for family, title in FAMILY_TITLES.items():
        rows = tests[tests.family == family]
        if not len(rows):
            continue
        significant = int((rows.p_adjusted < alpha).sum())
        out.append(f"\n### {title}\n")
        out.append(f"{significant} de {len(rows)} testes significativos.\n")
        out.append(table(
            ["Variável", "n", "Teste", "Estatística", "Efeito", "IC 95%", "p", "p ajustado", "Medianas"],
            [[f"`{r.variable}`", r.n, r.test, num(r.statistic), num(r.effect),
              f"{num(r.ci_low)} a {num(r.ci_high)}" if r.ci_low is not None and not pd.isna(r.ci_low) else "",
              f"{r.p_value:.2g}", ("**" if r.p_adjusted < alpha else "") + f"{r.p_adjusted:.2g}" +
              ("**" if r.p_adjusted < alpha else ""), describe_details(r)]
             for r in rows.itertuples()],
        ))
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calcula as métricas de um experimento e gera o relatório.")
    parser.add_argument("experiment")
    parser.add_argument("--out", type=Path, help="arquivo Markdown de saída")
    args = parser.parse_args()
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        data = load(conn, args.experiment)
        run_metrics, run_comparisons = compute_tables(data)
        store_tables(conn, run_metrics, run_comparisons)
    text = render(data, run_metrics, run_comparisons)
    if args.out:
        args.out.write_text(text, encoding="utf-8", newline="\n")
        print(f"relatório gravado em {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
