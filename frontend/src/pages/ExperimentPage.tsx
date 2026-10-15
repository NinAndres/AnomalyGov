import { useCallback } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { api, type RecordsQuery } from "../api/client";
import {
  ALGORITHMS,
  type Algorithm,
  type ExperimentDetail,
  type HypothesisTest,
  type MainRun,
  type StabilityComparison,
} from "../api/types";
import { useApi } from "../api/useApi";
import { FlaggedTable } from "../components/FlaggedTable";
import { Loading, Notice } from "../components/Layout";
import { P_OPTIONS } from "../filters/FilterForm";
import { ALGORITHM_LABELS, formatNumber, formatPercent, formatPValue } from "../format";

/** Lists the experiments; with a single one, opens it directly. */
export function ExperimentsPage() {
  const { data, error, loading } = useApi(() => api.experiments(), []);
  if (loading) return <Loading />;
  if (error) return <Notice kind="error">{error.message}</Notice>;
  if (!data?.length) return <Notice>Nenhum experimento publicado.</Notice>;
  if (data.length === 1) return <Navigate to={`/experimentos/${encodeURIComponent(data[0].name)}`} replace />;
  return (
    <section>
      <h1>Experimentos</h1>
      <ul>
        {data.map((e) => (
          <li key={e.name}>
            <Link to={`/experimentos/${encodeURIComponent(e.name)}`}>{e.name}</Link> ({formatNumber(e.runs)} execuções)
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ExperimentPage() {
  const { name = "" } = useParams();
  const experiment = useApi(() => api.experiment(name), [name]);
  const sources = useApi(() => api.sources(), []);
  const loadRecords = useCallback((q: RecordsQuery) => api.experimentRecords(name, q), [name]);

  if (experiment.loading) return <Loading />;
  if (experiment.error) return <Notice kind="error">{experiment.error.message}</Notice>;
  const detail = experiment.data!;
  const source = sources.data?.find((s) => s.name === detail.source) ?? null;

  return (
    <article className="experiment">
      <h1>Experimento {detail.name}</h1>
      <p className="lead">
        Comparação de Isolation Forest, LOF e One-Class SVM sobre a amostra estratificada de 2025 (amostra{" "}
        {detail.mainSampleId}). Estes são os resultados usados no artigo; não há rótulos de referência, por isso as
        métricas descrevem concordância, estabilidade e custo, e não acerto.
      </p>
      <nav className="toc" aria-label="Seções do experimento">
        <a href="#execucao">Execução</a>
        <a href="#concordancia">Concordância</a>
        <a href="#estabilidade">Estabilidade</a>
        <a href="#escalabilidade">Escalabilidade</a>
        {detail.hypothesisTests.length > 0 && <a href="#hipoteses">Hipóteses</a>}
        <a href="#registros">Registros sinalizados</a>
      </nav>
      <MainRunsSection runs={detail.mainRuns} />
      <AgreementSection detail={detail} />
      <StabilitySection detail={detail} />
      <ScalabilitySection detail={detail} />
      {detail.hypothesisTests.length > 0 && <HypothesesSection tests={detail.hypothesisTests} />}
      <section id="registros">
        <h2>Registros sinalizados</h2>
        {source ? (
          <FlaggedTable load={loadRecords} source={source} pOptions={P_OPTIONS} />
        ) : sources.error ? (
          <Notice kind="error">{sources.error.message}</Notice>
        ) : (
          <Loading />
        )}
      </section>
    </article>
  );
}

function describeParams(run: { algorithm: Algorithm; params: Record<string, unknown> }): string {
  const keys: Record<Algorithm, string[]> = {
    isolation_forest: ["n_estimators", "max_samples"],
    lof: ["n_neighbors", "neighbors_margin"],
    one_class_svm: ["nu", "gamma"],
  };
  return keys[run.algorithm]
    .filter((k) => run.params[k] !== undefined && run.params[k] !== null)
    .map((k) => `${k} = ${String(run.params[k]).replace(".", ",")}`)
    .join(", ");
}

function MainRunsSection({ runs }: { runs: MainRun[] }) {
  return (
    <section id="execucao">
      <h2>Configuração principal: tempo e proporção de sinalizados</h2>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Algoritmo</th>
              <th scope="col">Parâmetros</th>
              <th scope="col" className="num">Registros</th>
              <th scope="col" className="num">Tempo (s)</th>
              {P_OPTIONS.map((p) => (
                <th key={p} scope="col" className="num">
                  Sinalizados a {formatPercent(p, 0)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id}>
                <th scope="row">{ALGORITHM_LABELS[run.algorithm]}</th>
                <td>{describeParams(run)}</td>
                <td className="num">{formatNumber(run.nTrain)}</td>
                <td className="num">{formatNumber(run.fitSeconds + run.scoreSeconds, 1)}</td>
                {P_OPTIONS.map((p) => {
                  const metric = run.metrics.find((m) => Math.abs(m.p - p) < 1e-9);
                  return (
                    <td key={p} className="num" title="Proporção ponderada: estimativa para a população">
                      {metric ? `${formatNumber(metric.flaggedCount)} (${formatPercent(metric.weightedFlaggedShare, 2)} pond.)` : "—"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint">
        “pond.” é a proporção ponderada pelos pesos amostrais, que estima a proporção de sinalizados na população.
      </p>
    </section>
  );
}

function AgreementSection({ detail }: { detail: ExperimentDetail }) {
  const pairs = [...new Set(detail.agreement.map((a) => `${a.algorithmA}|${a.algorithmB}`))];
  return (
    <section id="concordancia">
      <h2>Concordância entre os algoritmos</h2>
      <p>Jaccard dos conjuntos sinalizados (1 = mesmos registros, 0 = nenhum em comum) e Spearman dos escores.</p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Par</th>
              {P_OPTIONS.map((p) => (
                <th key={p} scope="col" className="num">
                  Jaccard a {formatPercent(p, 0)}
                </th>
              ))}
              <th scope="col" className="num">Spearman</th>
            </tr>
          </thead>
          <tbody>
            {pairs.map((pair) => {
              const [a, b] = pair.split("|") as Algorithm[];
              const rows = detail.agreement.filter((x) => x.algorithmA === a && x.algorithmB === b);
              return (
                <tr key={pair}>
                  <th scope="row">
                    {ALGORITHM_LABELS[a]} × {ALGORITHM_LABELS[b]}
                  </th>
                  {P_OPTIONS.map((p) => (
                    <td key={p} className="num">
                      {formatNumber(rows.find((r) => Math.abs(r.p - p) < 1e-9)?.jaccard, 3)}
                    </td>
                  ))}
                  <td className="num">{formatNumber(rows[0]?.spearman, 3)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function median(values: number[]): number {
  const sorted = [...values].sort((x, y) => x - y);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function StabilitySection({ detail }: { detail: ExperimentDetail }) {
  const at = (items: StabilityComparison[], p: number) => items.filter((s) => Math.abs(s.p - p) < 1e-9);
  const parameter = at(detail.stability, 0.01).filter((s) => s.purpose === "parameter");
  return (
    <section id="estabilidade">
      <h2>Estabilidade</h2>
      <h3>Frente aos dados</h3>
      <p>
        Cada algoritmo treinado em amostras diferentes pontua a amostra principal. Jaccard com a configuração
        principal: mediana (mínimo–máximo).
      </p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Algoritmo</th>
              <th scope="col" className="num">Amostras</th>
              {P_OPTIONS.map((p) => (
                <th key={p} scope="col" className="num">
                  Jaccard a {formatPercent(p, 0)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ALGORITHMS.map((algorithm) => {
              const items = detail.stability.filter((s) => s.purpose === "data_stability" && s.algorithm === algorithm);
              if (!items.length) return null;
              return (
                <tr key={algorithm}>
                  <th scope="row">{ALGORITHM_LABELS[algorithm]}</th>
                  <td className="num">{at(items, 0.01).length}</td>
                  {P_OPTIONS.map((p) => {
                    const values = at(items, p).map((s) => s.jaccard).filter((v): v is number => v !== null);
                    return (
                      <td key={p} className="num">
                        {values.length
                          ? `${formatNumber(median(values), 3)} (${formatNumber(Math.min(...values), 3)}–${formatNumber(Math.max(...values), 3)})`
                          : "—"}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <h3>Frente aos parâmetros</h3>
      <p>Cada variação comparada com a configuração principal do mesmo algoritmo (p = 1%).</p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Algoritmo</th>
              <th scope="col">Variação</th>
              <th scope="col" className="num">Jaccard</th>
              <th scope="col" className="num">Spearman</th>
            </tr>
          </thead>
          <tbody>
            {parameter.map((s) => (
              <tr key={s.runId}>
                <th scope="row">{ALGORITHM_LABELS[s.algorithm]}</th>
                <td>{describeParams(s)}</td>
                <td className="num">{formatNumber(s.jaccard, 3)}</td>
                <td className="num">{formatNumber(s.spearman, 3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ScalabilitySection({ detail }: { detail: ExperimentDetail }) {
  const sizes = [...new Set(detail.scalability.map((s) => s.nTrain))].sort((a, b) => a - b);
  if (!sizes.length) return null;
  return (
    <section id="escalabilidade">
      <h2>Escalabilidade</h2>
      <p>Tempo total (treino + pontuação), média e faixa entre repetições. “—” indica tamanho não executado.</p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col" className="num">Registros</th>
              {ALGORITHMS.map((a) => (
                <th key={a} scope="col" className="num">
                  {ALGORITHM_LABELS[a]} (s)
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sizes.map((n) => (
              <tr key={n}>
                <th scope="row" className="num">{formatNumber(n)}</th>
                {ALGORITHMS.map((a) => {
                  const point = detail.scalability.find((s) => s.nTrain === n && s.algorithm === a);
                  return (
                    <td key={a} className="num">
                      {point
                        ? `${formatNumber(point.meanSeconds, 1)} (${formatNumber(point.minSeconds, 1)}–${formatNumber(point.maxSeconds, 1)})`
                        : "—"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const FAMILY_TITLES: Record<string, string> = {
  H2: "H2: Isolation Forest × LOF entre meses (unilateral: IF mais estável)",
  H2_context: "Contexto da H2: Isolation Forest × One-Class SVM",
  H1a_type: "H1a: indicadores por tipo de favorecido",
  H1b_association: "H1b: atipicidade da célula × indicadores",
  H1c_manipulation: "H1c: manipulação controlada de duplicados",
};

function HypothesesSection({ tests }: { tests: HypothesisTest[] }) {
  const families = [...new Set(tests.map((t) => t.family))];
  return (
    <section id="hipoteses">
      <h2>Hipóteses</h2>
      <p>
        Correção de Holm dentro de cada família; em destaque, os testes com p ajustado abaixo de α. Os testes indicam
        associação ou diferença nos dados observados, não causa (exceto a manipulação controlada).
      </p>
      {families.map((family) => {
        const rows = tests.filter((t) => t.family === family);
        const alpha = rows[0]?.details.alpha ?? 0.05;
        const significant = rows.filter((t) => t.pAdjusted !== null && t.pAdjusted < alpha).length;
        return (
          <div key={family} className="family">
            <h3>{FAMILY_TITLES[family] ?? family}</h3>
            <p className="hint">
              {significant} de {rows.length} testes significativos (α = {formatNumber(alpha, 2)}).
            </p>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Variável</th>
                    <th scope="col">Teste</th>
                    <th scope="col" className="num">n</th>
                    <th scope="col" className="num">Efeito</th>
                    <th scope="col" className="num">IC 95%</th>
                    <th scope="col" className="num">p ajustado</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((t) => (
                    <tr key={`${t.family}-${t.variable}`} className={t.pAdjusted !== null && t.pAdjusted < alpha ? "significant" : undefined}>
                      <td><code>{t.variable}</code></td>
                      <td>{t.test}</td>
                      <td className="num">{t.n}</td>
                      <td className="num">{formatNumber(t.effect, 3)}</td>
                      <td className="num">
                        {t.ciLow !== null && t.ciHigh !== null ? `${formatNumber(t.ciLow, 3)} a ${formatNumber(t.ciHigh, 3)}` : "—"}
                      </td>
                      <td className="num">{formatPValue(t.pAdjusted)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </section>
  );
}
