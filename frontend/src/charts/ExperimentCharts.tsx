// Charts of the experiment page. Each chart has a table twin on the page (the WCAG equivalent); colors follow the
// entity: one fixed color per algorithm, and an ordinal blue ramp for ordered categories (p, number of algorithms).
import type { ReactElement, ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ErrorBar,
  LabelList,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ALGORITHMS,
  type Agreement,
  type Algorithm,
  type HypothesisTest,
  type MainRun,
  type Overlap,
  type RunProfile,
  type ScalabilityPoint,
  type StabilityComparison,
  type Surrogate,
} from "../api/types";
import { ALGORITHM_LABELS, ALGORITHM_SHORT, compareFeatures, featureLabel, formatMonth, formatNumber, formatPercent } from "../format";

/** Categorical slots 1–3 of the validated palette, in fixed order. Also defined in styles.css (--if, --lof, --ocsvm). */
export const ALGORITHM_COLORS: Record<Algorithm, string> = {
  isolation_forest: "#2a78d6",
  lof: "#eb6834",
  one_class_svm: "#1baf7a",
};
/** Ordinal ramp (light → dark) for ordered series. */
const ORDINAL = ["#86b6ef", "#2a78d6", "#104281"];
const NEUTRAL = "#898781";
const GRID = "#e1e0d9";
const AXIS = "#c3c2b7";
const TICK = { fill: "#5b6676", fontSize: 12 };
const TOOLTIP = {
  contentStyle: { borderRadius: 6, borderColor: "#d9dee5", fontSize: 13 },
  labelStyle: { color: "#1c2430", fontWeight: 600 },
  itemStyle: { color: "#1c2430" },
};
const BAR = 24;

export const samePValue = (a: number, b: number) => Math.abs(a - b) < 1e-9;
/** Percent ticks: no decimals on whole percentages, one otherwise. */
const percentTick = (value: number) => formatPercent(value, Math.abs(value * 100 - Math.round(value * 100)) < 1e-9 ? 0 : 1);
/** Ticks of the [0, 1] axes (Jaccard, retention, R²). */
const UNIT_TICKS = [0, 0.2, 0.4, 0.6, 0.8, 1];
const unitTick = (v: number) => formatNumber(v, 1);

/** Legend whose text keeps the ink color (the swatch carries the series color) and follows the render order. */
function legendProps(label: (name: string) => string) {
  return {
    itemSorter: null,
    formatter: (name: string) => <span className="legend-text">{label(name)}</span>,
  };
}

function ChartFrame({
  title,
  height,
  children,
  note,
  legend,
}: {
  title: string;
  height: number;
  children: ReactNode;
  note?: string;
  /** Algorithms listed in an HTML legend, for charts whose bars are colored per item. */
  legend?: Algorithm[];
}) {
  return (
    <figure className="chart">
      <figcaption>{title}</figcaption>
      {legend && (
        <ul className="chart-legend">
          {legend.map((a) => (
            <li key={a}>
              <span className="swatch" style={{ background: ALGORITHM_COLORS[a] }} aria-hidden="true" />
              {ALGORITHM_LABELS[a]}
            </li>
          ))}
        </ul>
      )}
      <div style={{ width: "100%", height }}>
        <ResponsiveContainer width="100%" height="100%">
          {children as ReactElement}
        </ResponsiveContainer>
      </div>
      {note && <p className="hint">{note}</p>}
    </figure>
  );
}

const algorithmLegend = legendProps((name) => ALGORITHM_LABELS[name as Algorithm] ?? name);

// ---------------------------------------------------------------- execution

export function TimeChart({ runs }: { runs: MainRun[] }) {
  const data = runs.map((r) => ({ algorithm: r.algorithm, name: ALGORITHM_LABELS[r.algorithm], total: r.fitSeconds + r.scoreSeconds }));
  return (
    <ChartFrame title="Tempo total na amostra principal (treino + pontuação, segundos)" height={60 + 44 * data.length}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 56 }}>
        <CartesianGrid horizontal={false} stroke={GRID} />
        <XAxis type="number" stroke={AXIS} tick={TICK} tickFormatter={(v: number) => formatNumber(v)} />
        <YAxis type="category" dataKey="name" width={120} stroke={AXIS} tick={TICK} />
        <Tooltip {...TOOLTIP} formatter={(v) => [`${formatNumber(Number(v), 1)} s`, "Tempo total"]} cursor={{ fill: "#f0efec" }} />
        <Bar dataKey="total" barSize={BAR} radius={[0, 4, 4, 0]} isAnimationActive={false}>
          {data.map((d) => (
            <Cell key={d.algorithm} fill={ALGORITHM_COLORS[d.algorithm]} />
          ))}
          <LabelList dataKey="total" position="right" fill="#1c2430" fontSize={12} formatter={(v) => `${formatNumber(Number(v), 1)} s`} />
        </Bar>
      </BarChart>
    </ChartFrame>
  );
}

export function WeightedShareChart({ runs, pOptions }: { runs: MainRun[]; pOptions: number[] }) {
  const data = pOptions.map((p) => {
    const row: Record<string, number | string> = { p: `p = ${formatPercent(p, 0)}` };
    for (const run of runs) {
      const metric = run.metrics.find((m) => samePValue(m.p, p));
      if (metric) row[run.algorithm] = metric.weightedFlaggedShare;
    }
    return row;
  });
  return (
    <ChartFrame
      title="Proporção ponderada de sinalizados (estimativa para a população)"
      height={300}
      note="Na amostra, cada algoritmo sinaliza p% por construção; a proporção ponderada corrige a sobrerrepresentação dos tipos raros."
    >
      <BarChart data={data} margin={{ top: 8, right: 8 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="p" stroke={AXIS} tick={TICK} />
        <YAxis stroke={AXIS} tick={TICK} tickFormatter={percentTick} width={48} />
        <Tooltip {...TOOLTIP} formatter={(v, name) => [formatPercent(Number(v), 2), ALGORITHM_LABELS[name as Algorithm]]} cursor={{ fill: "#f0efec" }} />
        <Legend {...algorithmLegend} />
        {ALGORITHMS.map((a) => (
          <Bar key={a} dataKey={a} fill={ALGORITHM_COLORS[a]} maxBarSize={BAR} radius={[4, 4, 0, 0]} isAnimationActive={false} />
        ))}
      </BarChart>
    </ChartFrame>
  );
}

// ---------------------------------------------------------------- agreement

export function AgreementChart({ agreement, pOptions }: { agreement: Agreement[]; pOptions: number[] }) {
  const pairs = [...new Set(agreement.map((a) => `${a.algorithmA}|${a.algorithmB}`))];
  const data = pairs.map((pair) => {
    const [a, b] = pair.split("|") as Algorithm[];
    const row: Record<string, number | string> = { pair: `${ALGORITHM_SHORT[a]} × ${ALGORITHM_SHORT[b]}` };
    pOptions.forEach((p, i) => {
      const item = agreement.find((x) => x.algorithmA === a && x.algorithmB === b && samePValue(x.p, p));
      if (item?.jaccard != null) row[`p${i}`] = item.jaccard;
    });
    return row;
  });
  return (
    <ChartFrame title="Jaccard dos sinalizados por par de algoritmos (1 = mesmos registros)" height={300}>
      <BarChart data={data} margin={{ top: 8, right: 8 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="pair" stroke={AXIS} tick={TICK} />
        <YAxis domain={[0, 1]} ticks={UNIT_TICKS} stroke={AXIS} tick={TICK} tickFormatter={unitTick} width={40} />
        <Tooltip {...TOOLTIP} formatter={(v, name) => [formatNumber(Number(v), 3), `Jaccard a ${formatPercent(pOptions[Number(String(name).slice(1))], 0)}`]} cursor={{ fill: "#f0efec" }} />
        <Legend {...legendProps((name) => `p = ${formatPercent(pOptions[Number(name.slice(1))], 0)}`)} />
        {pOptions.map((_, i) => (
          <Bar key={i} dataKey={`p${i}`} fill={ORDINAL[i % ORDINAL.length]} maxBarSize={BAR} radius={[4, 4, 0, 0]} isAnimationActive={false} />
        ))}
      </BarChart>
    </ChartFrame>
  );
}

export function OverlapChart({ overlaps }: { overlaps: Overlap[] }) {
  const ps = [...new Set(overlaps.map((o) => o.p))].sort((a, b) => a - b);
  const counts = [...new Set(overlaps.map((o) => o.algorithmCount))].sort((a, b) => a - b);
  const data = ps.map((p) => {
    const row: Record<string, number | string> = { p: `p = ${formatPercent(p, 0)}` };
    for (const o of overlaps.filter((x) => samePValue(x.p, p))) row[`k${o.algorithmCount}`] = o.recordCount;
    return row;
  });
  const label = (k: number) => (k === 1 ? "Por 1 algoritmo" : k === counts[counts.length - 1] ? `Pelos ${k}` : `Por ${k}`);
  return (
    <ChartFrame title="Registros sinalizados por quantos algoritmos" height={60 + 48 * data.length + 40}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
        <CartesianGrid horizontal={false} stroke={GRID} />
        <XAxis type="number" stroke={AXIS} tick={TICK} tickFormatter={(v: number) => formatNumber(v)} />
        <YAxis type="category" dataKey="p" width={80} stroke={AXIS} tick={TICK} />
        <Tooltip {...TOOLTIP} formatter={(v, name) => [formatNumber(Number(v)), label(Number(String(name).slice(1)))]} cursor={{ fill: "#f0efec" }} />
        <Legend {...legendProps((name) => label(Number(name.slice(1))))} />
        {counts.map((k, i) => (
          <Bar
            key={k}
            dataKey={`k${k}`}
            stackId="overlap"
            fill={ORDINAL[i % ORDINAL.length]}
            stroke="#ffffff"
            strokeWidth={2}
            barSize={BAR}
            radius={i === counts.length - 1 ? [0, 4, 4, 0] : 0}
            isAnimationActive={false}
          />
        ))}
      </BarChart>
    </ChartFrame>
  );
}

// ---------------------------------------------------------------- stability

function median(values: number[]): number {
  const sorted = [...values].sort((x, y) => x - y);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

export function DataStabilityChart({ stability, p }: { stability: StabilityComparison[]; p: number }) {
  const data = ALGORITHMS.flatMap((algorithm) => {
    const values = stability
      .filter((s) => s.purpose === "data_stability" && s.algorithm === algorithm && samePValue(s.p, p))
      .map((s) => s.jaccard)
      .filter((v): v is number => v !== null);
    if (!values.length) return [];
    const m = median(values);
    return [{ algorithm, name: ALGORITHM_LABELS[algorithm], median: m, min: Math.min(...values), max: Math.max(...values), range: [m - Math.min(...values), Math.max(...values) - m] }];
  });
  return (
    <ChartFrame
      title={`Estabilidade frente aos dados: Jaccard a ${formatPercent(p, 0)} com a execução principal`}
      height={60 + 44 * data.length}
      note="Barra: mediana entre as amostras adicionais; traço: mínimo a máximo."
    >
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 56 }}>
        <CartesianGrid horizontal={false} stroke={GRID} />
        <XAxis type="number" domain={[0, 1]} ticks={UNIT_TICKS} stroke={AXIS} tick={TICK} tickFormatter={unitTick} />
        <YAxis type="category" dataKey="name" width={120} stroke={AXIS} tick={TICK} />
        <Tooltip
          {...TOOLTIP}
          cursor={{ fill: "#f0efec" }}
          content={({ active, payload }) => {
            const d = payload?.[0]?.payload as (typeof data)[number] | undefined;
            if (!active || !d) return null;
            return (
              <div className="chart-tooltip">
                <strong>{formatNumber(d.median, 3)}</strong> mediana
                <br />
                {formatNumber(d.min, 3)} a {formatNumber(d.max, 3)}
                <div className="hint">{d.name}</div>
              </div>
            );
          }}
        />
        <Bar dataKey="median" barSize={BAR} radius={[0, 4, 4, 0]} isAnimationActive={false}>
          {data.map((d) => (
            <Cell key={d.algorithm} fill={ALGORITHM_COLORS[d.algorithm]} />
          ))}
          <ErrorBar dataKey="range" width={8} strokeWidth={2} stroke="#1c2430" direction="x" />
        </Bar>
      </BarChart>
    </ChartFrame>
  );
}

export function ParameterStabilityChart({
  stability,
  describe,
}: {
  stability: StabilityComparison[];
  describe: (s: StabilityComparison) => string;
}) {
  const data = stability
    .filter((s) => s.purpose === "parameter" && samePValue(s.p, 0.01) && s.jaccard !== null)
    .map((s) => ({ algorithm: s.algorithm, name: `${ALGORITHM_SHORT[s.algorithm]}: ${describe(s).replaceAll(" = ", "=")}`, jaccard: s.jaccard! }));
  if (!data.length) return null;
  return (
    <ChartFrame
      title="Estabilidade frente aos parâmetros: Jaccard a 1% com a configuração principal"
      height={50 + 30 * data.length}
      legend={ALGORITHMS.filter((a) => data.some((d) => d.algorithm === a))}
    >
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 48 }}>
        <CartesianGrid horizontal={false} stroke={GRID} />
        <XAxis type="number" domain={[0, 1]} ticks={UNIT_TICKS} stroke={AXIS} tick={TICK} tickFormatter={unitTick} />
        <YAxis type="category" dataKey="name" width={290} stroke={AXIS} tick={{ ...TICK, fontSize: 11 }} interval={0} />
        <Tooltip {...TOOLTIP} formatter={(v) => [formatNumber(Number(v), 3), "Jaccard"]} cursor={{ fill: "#f0efec" }} />
        <Bar dataKey="jaccard" barSize={18} radius={[0, 4, 4, 0]} isAnimationActive={false}>
          {data.map((d) => (
            <Cell key={d.name} fill={ALGORITHM_COLORS[d.algorithm]} />
          ))}
          <LabelList dataKey="jaccard" position="right" fill="#1c2430" fontSize={11} formatter={(v) => formatNumber(Number(v), 2)} />
        </Bar>
      </BarChart>
    </ChartFrame>
  );
}

// ---------------------------------------------------------------- scalability

const LOG_TICKS = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000];

export function ScalabilityChart({ points }: { points: ScalabilityPoint[] }) {
  const sizes = [...new Set(points.map((s) => s.nTrain))].sort((a, b) => a - b);
  const data = sizes.map((n) => {
    const row: Record<string, number> = { n };
    for (const point of points.filter((s) => s.nTrain === n)) row[point.algorithm] = point.meanSeconds;
    return row;
  });
  const byKey = new Map(points.map((s) => [`${s.algorithm}|${s.nTrain}`, s]));
  const minTime = Math.min(...points.map((s) => s.meanSeconds));
  const maxTime = Math.max(...points.map((s) => s.meanSeconds));
  return (
    <ChartFrame
      title="Tempo total (s) por tamanho da amostra (escalas logarítmicas)"
      height={320}
      note="Média das repetições. A linha do LOF termina onde a memória da máquina deixou de comportar a regra de vizinhos."
    >
      <LineChart data={data} margin={{ top: 8, right: 16 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="n" type="number" scale="log" domain={["dataMin", "dataMax"]} ticks={sizes} stroke={AXIS} tick={TICK} tickFormatter={(v: number) => `${formatNumber(v / 1000)} mil`} />
        <YAxis
          scale="log"
          domain={[(min: number) => min * 0.7, (max: number) => max * 1.4]}
          ticks={LOG_TICKS.filter((t) => t >= minTime * 0.7 && t <= maxTime * 1.4)}
          interval={0}
          stroke={AXIS}
          tick={TICK}
          tickFormatter={(v: number) => formatNumber(v, v < 1 ? 1 : 0)}
          width={48}
        />
        <Tooltip
          {...TOOLTIP}
          labelFormatter={(n) => `${formatNumber(Number(n))} registros`}
          formatter={(v, name, item) => {
            const point = byKey.get(`${name}|${(item.payload as { n: number }).n}`);
            const range = point ? ` (${formatNumber(point.minSeconds, 1)}–${formatNumber(point.maxSeconds, 1)})` : "";
            return [`${formatNumber(Number(v), 1)} s${range}`, ALGORITHM_LABELS[name as Algorithm]];
          }}
        />
        <Legend {...algorithmLegend} />
        {ALGORITHMS.map((a) => (
          <Line key={a} dataKey={a} stroke={ALGORITHM_COLORS[a]} strokeWidth={2} dot={{ r: 4, fill: ALGORITHM_COLORS[a], stroke: "#fff", strokeWidth: 2 }} activeDot={{ r: 6 }} connectNulls={false} isAnimationActive={false} />
        ))}
      </LineChart>
    </ChartFrame>
  );
}

// ---------------------------------------------------------------- characteristics

function byCategory(profiles: RunProfile[], dimension: RunProfile["dimension"], p: number) {
  const rows = profiles.filter((x) => x.dimension === dimension && samePValue(x.p, p));
  const categories = [...new Set(rows.map((x) => x.category))];
  return categories.map((category) => {
    const row: Record<string, number | string | null> = { category };
    for (const x of rows.filter((r) => r.category === category)) {
      row[x.algorithm] = x.value;
      row.baseline = x.baseline;
    }
    return row;
  });
}

export function TypeRateChart({ profiles, p, typeLabel }: { profiles: RunProfile[]; p: number; typeLabel: (t: string) => string }) {
  const data = byCategory(profiles, "favored_type", p).map((r) => ({ ...r, name: typeLabel(String(r.category)) }));
  const short = (name: string) => (name.length > 24 ? `${name.slice(0, 22).trimEnd()}…` : name);
  return (
    <ChartFrame title={`Taxa ponderada de sinalização por tipo de favorecido (p = ${formatPercent(p, 0)})`} height={320}>
      <BarChart data={data} margin={{ top: 8, right: 8 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="name" stroke={AXIS} tick={TICK} interval={0} tickFormatter={short} />
        <YAxis stroke={AXIS} tick={TICK} tickFormatter={percentTick} width={48} />
        <Tooltip {...TOOLTIP} formatter={(v, name) => [formatPercent(Number(v), 2), ALGORITHM_LABELS[name as Algorithm]]} cursor={{ fill: "#f0efec" }} />
        <Legend {...algorithmLegend} />
        {ALGORITHMS.map((a) => (
          <Bar key={a} dataKey={a} fill={ALGORITHM_COLORS[a]} maxBarSize={BAR} radius={[4, 4, 0, 0]} isAnimationActive={false} />
        ))}
      </BarChart>
    </ChartFrame>
  );
}

export function MonthRateChart({ profiles, p }: { profiles: RunProfile[]; p: number }) {
  const data = byCategory(profiles, "reference_month", p)
    .sort((a, b) => String(a.category).localeCompare(String(b.category)))
    .map((r) => ({ ...r, name: formatMonth(String(r.category)) }));
  return (
    <ChartFrame
      title={`Taxa ponderada de sinalização por mês (p = ${formatPercent(p, 0)})`}
      height={300}
      note="Variações entre meses indicam que a distribuição dos dados muda ao longo do ano (não estacionariedade)."
    >
      <LineChart data={data} margin={{ top: 8, right: 16 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="name" stroke={AXIS} tick={TICK} />
        <YAxis stroke={AXIS} tick={TICK} tickFormatter={(v: number) => formatPercent(v, 1)} width={52} domain={[0, "auto"]} />
        <Tooltip {...TOOLTIP} formatter={(v, name) => [formatPercent(Number(v), 2), ALGORITHM_LABELS[name as Algorithm]]} />
        <Legend {...algorithmLegend} />
        {ALGORITHMS.map((a) => (
          <Line key={a} dataKey={a} stroke={ALGORITHM_COLORS[a]} strokeWidth={2} dot={{ r: 4, fill: ALGORITHM_COLORS[a], stroke: "#fff", strokeWidth: 2 }} activeDot={{ r: 6 }} isAnimationActive={false} />
        ))}
      </LineChart>
    </ChartFrame>
  );
}

export function DominantFeatureChart({ profiles, p }: { profiles: RunProfile[]; p: number }) {
  const data = byCategory(profiles, "dominant_feature", p)
    .sort((a, b) => compareFeatures(String(a.category), String(b.category)))
    .map((r) => ({ ...r, name: featureLabel(String(r.category)) }));
  return (
    <ChartFrame
      title={`Feature dominante dos sinalizados (p = ${formatPercent(p, 0)})`}
      height={320}
      note="Proporção dos sinalizados cuja feature mais afastada do centro (após o escalonamento robusto) é cada uma."
    >
      <BarChart data={data} margin={{ top: 8, right: 8 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="name" stroke={AXIS} tick={{ ...TICK, fontSize: 11 }} interval={0} />
        <YAxis stroke={AXIS} tick={TICK} tickFormatter={percentTick} width={48} domain={[0, 1]} />
        <Tooltip {...TOOLTIP} formatter={(v, name) => [formatPercent(Number(v), 1), ALGORITHM_LABELS[name as Algorithm]]} cursor={{ fill: "#f0efec" }} />
        <Legend {...algorithmLegend} />
        {ALGORITHMS.map((a) => (
          <Bar key={a} dataKey={a} fill={ALGORITHM_COLORS[a]} maxBarSize={BAR} radius={[4, 4, 0, 0]} isAnimationActive={false} />
        ))}
      </BarChart>
    </ChartFrame>
  );
}

export function SurrogateChart({ surrogates }: { surrogates: Surrogate[] }) {
  const data = ALGORITHMS.flatMap((a) => {
    const s = surrogates.find((x) => x.algorithm === a);
    return s?.fidelity != null ? [{ algorithm: a, name: ALGORITHM_LABELS[a], fidelity: s.fidelity }] : [];
  });
  return (
    <ChartFrame
      title="Fidelidade da árvore substituta (R²): quanto do escore é explicado por poucas regras"
      height={60 + 44 * data.length}
    >
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 56 }}>
        <CartesianGrid horizontal={false} stroke={GRID} />
        <XAxis type="number" domain={[0, 1]} ticks={UNIT_TICKS} stroke={AXIS} tick={TICK} tickFormatter={unitTick} />
        <YAxis type="category" dataKey="name" width={120} stroke={AXIS} tick={TICK} />
        <Tooltip {...TOOLTIP} formatter={(v) => [formatNumber(Number(v), 3), "R²"]} cursor={{ fill: "#f0efec" }} />
        <Bar dataKey="fidelity" barSize={BAR} radius={[0, 4, 4, 0]} isAnimationActive={false}>
          {data.map((d) => (
            <Cell key={d.algorithm} fill={ALGORITHM_COLORS[d.algorithm]} />
          ))}
          <LabelList dataKey="fidelity" position="right" fill="#1c2430" fontSize={12} formatter={(v) => formatNumber(Number(v), 2)} />
        </Bar>
      </BarChart>
    </ChartFrame>
  );
}

// ---------------------------------------------------------------- hypotheses

/** H2: median Jaccard between months for IF, the other algorithm and the IF seed noise (reference). */
export function H2Chart({ tests }: { tests: HypothesisTest[] }) {
  const pick = (family: string, suffix: string) =>
    tests.find((t) => t.family === family && t.variable.startsWith("jaccard_if_minus_") && t.variable.endsWith(suffix));
  const data = (["p01", "p05"] as const).flatMap((suffix) => {
    const lof = pick("H2", suffix)?.details as Record<string, number> | undefined;
    const ocsvm = pick("H2_context", suffix)?.details as Record<string, number> | undefined;
    if (!lof?.median_jaccard_if) return [];
    return [{
      p: suffix === "p01" ? "p = 1%" : "p = 5%",
      isolation_forest: lof.median_jaccard_if,
      lof: lof.median_jaccard_other,
      one_class_svm: ocsvm?.median_jaccard_other,
      noise: lof.median_if_seed_noise,
    }];
  });
  if (!data.length) return null;
  const names: Record<string, string> = { ...ALGORITHM_LABELS, noise: "Referência: IF com outra semente" };
  return (
    <ChartFrame
      title="H2: estabilidade entre meses (Jaccard mediano dos 132 pares de meses)"
      height={300}
      note="Quanto mais alto, mais o modelo treinado num mês concorda com o modelo do próprio mês. A referência cinza mede só o ruído da semente do Isolation Forest."
    >
      <BarChart data={data} margin={{ top: 8, right: 8 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="p" stroke={AXIS} tick={TICK} />
        <YAxis domain={[0, 1]} ticks={UNIT_TICKS} stroke={AXIS} tick={TICK} tickFormatter={unitTick} width={40} />
        <Tooltip {...TOOLTIP} formatter={(v, name) => [formatNumber(Number(v), 3), names[String(name)]]} cursor={{ fill: "#f0efec" }} />
        <Legend {...legendProps((name) => names[name])} />
        {ALGORITHMS.map((a) => (
          <Bar key={a} dataKey={a} fill={ALGORITHM_COLORS[a]} maxBarSize={BAR} radius={[4, 4, 0, 0]} isAnimationActive={false} />
        ))}
        <Bar dataKey="noise" fill={NEUTRAL} maxBarSize={BAR} radius={[4, 4, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ChartFrame>
  );
}

/** H1c: share of the originally flagged records still flagged as identical copies are inserted. */
export function H1cChart({ tests }: { tests: HypothesisTest[] }) {
  const retention: Partial<Record<Algorithm, Record<string, number>>> = {};
  for (const t of tests.filter((x) => x.family === "H1c_manipulation" && x.variable.startsWith("retention_"))) {
    const algorithm = ({ retention_if: "isolation_forest", retention_lof: "lof", retention_ocsvm: "one_class_svm" } as const)[
      t.variable as "retention_if" | "retention_lof" | "retention_ocsvm"
    ];
    const medians = t.details.medians as Record<string, number> | undefined;
    if (algorithm && medians) retention[algorithm] = medians;
  }
  const fractions = [...new Set(Object.values(retention).flatMap((m) => Object.keys(m!)))].sort((a, b) => Number(a) - Number(b));
  if (!fractions.length) return null;
  const data = fractions.map((f) => {
    const row: Record<string, number | string> = { fraction: formatPercent(Number(f), 0) };
    for (const a of ALGORITHMS) if (retention[a]?.[f] !== undefined) row[a] = retention[a]![f];
    return row;
  });
  return (
    <ChartFrame
      title="H1c: retenção dos sinalizados ao inserir cópias idênticas (células de empresas)"
      height={300}
      note="Eixo horizontal: fração da célula substituída por cópias de um mesmo registro típico. 1 = os mesmos registros continuam sinalizados."
    >
      <LineChart data={data} margin={{ top: 8, right: 16 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="fraction" stroke={AXIS} tick={TICK} />
        <YAxis domain={[0, 1]} ticks={UNIT_TICKS} stroke={AXIS} tick={TICK} tickFormatter={unitTick} width={40} />
        <Tooltip {...TOOLTIP} labelFormatter={(f) => `${f} de cópias`} formatter={(v, name) => [formatNumber(Number(v), 3), ALGORITHM_LABELS[name as Algorithm]]} />
        <Legend {...algorithmLegend} />
        {ALGORITHMS.map((a) => (
          <Line key={a} dataKey={a} stroke={ALGORITHM_COLORS[a]} strokeWidth={2} dot={{ r: 4, fill: ALGORITHM_COLORS[a], stroke: "#fff", strokeWidth: 2 }} activeDot={{ r: 6 }} isAnimationActive={false} />
        ))}
      </LineChart>
    </ChartFrame>
  );
}
