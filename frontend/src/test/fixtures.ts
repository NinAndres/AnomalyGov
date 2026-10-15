import { vi } from "vitest";
import type { ExperimentDetail, FlaggedPage, Job, SourceDefinition } from "../api/types";

export const SOURCE: SourceDefinition = {
  name: "payments",
  label: "Recebimentos de recursos por favorecido",
  filters: [
    { name: "reference_month", type: "month_range", label: "Mês de referência", options: null, min: "2025-01", max: "2025-12" },
    {
      name: "favored_type",
      type: "select",
      label: "Tipo de favorecido",
      options: [
        { value: "company", label: "Pessoa jurídica" },
        { value: "individual", label: "Pessoa física" },
      ],
      min: null,
      max: null,
    },
    { name: "amount", type: "number_range", label: "Valor recebido (R$)", options: null, min: 0.01, max: 1e9 },
  ],
  displayColumns: ["reference_month", "favored_type", "favored_name", "amount"],
};

export const PAGE: FlaggedPage = {
  p: 0.01,
  algorithm: null,
  page: 1,
  pageSize: 25,
  total: 2,
  items: [
    {
      paymentId: 1,
      flaggedCount: 3,
      flags: { isolation_forest: true, lof: true, one_class_svm: true },
      scores: { isolation_forest: 0.999, lof: 0.998, one_class_svm: 1 },
      values: { reference_month: "2025-07", favored_type: "company", favored_name: "EMPRESA X", amount: 13668.91 },
    },
    {
      paymentId: 2,
      flaggedCount: 1,
      flags: { isolation_forest: false, lof: true, one_class_svm: false },
      scores: { isolation_forest: 0.5, lof: 0.997, one_class_svm: 0.4 },
      values: { reference_month: "2025-03", favored_type: "individual", favored_name: null, amount: 700 },
    },
  ],
};

export function job(overrides: Partial<Job> = {}): Job {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    source: "payments",
    mode: "exploration",
    status: "pending",
    filters: { favored_type: ["company"] },
    params: { p: 0.02 },
    result: null,
    error: null,
    createdAt: "2026-10-15T10:00:00Z",
    startedAt: null,
    finishedAt: null,
    ...overrides,
  };
}

export const EXPERIMENT: ExperimentDetail = {
  name: "principal-2025",
  source: "payments",
  mainSampleId: 5,
  mainRuns: [
    {
      id: 14,
      algorithm: "isolation_forest",
      params: { n_estimators: 1000, max_samples: 4096 },
      randomState: 0,
      nTrain: 56768,
      fitSeconds: 2.7,
      scoreSeconds: 2.9,
      metrics: [{ p: 0.01, flaggedCount: 568, flaggedShare: 0.01, weightedFlaggedShare: 0.0067 }],
    },
  ],
  agreement: [{ algorithmA: "isolation_forest", algorithmB: "lof", p: 0.01, jaccard: 0.103, spearman: 0.225 }],
  stability: [
    { runId: 37, purpose: "data_stability", algorithm: "isolation_forest", params: {}, p: 0.01, jaccard: 0.89, spearman: 0.998 },
    { runId: 38, purpose: "data_stability", algorithm: "isolation_forest", params: {}, p: 0.01, jaccard: 0.91, spearman: 0.998 },
    { runId: 17, purpose: "parameter", algorithm: "isolation_forest", params: { n_estimators: 200, max_samples: 256 }, p: 0.01, jaccard: 0.422, spearman: 0.987 },
  ],
  scalability: [{ algorithm: "isolation_forest", nTrain: 5679, repetitions: 3, meanSeconds: 2.1, minSeconds: 2.1, maxSeconds: 2.2 }],
  hypothesisTests: [
    {
      hypothesis: "H2",
      family: "H2",
      test: "wilcoxon_greater",
      variable: "jaccard_if_minus_lof_p01",
      n: 132,
      statistic: 8085,
      effect: 0.203,
      ciLow: 0.163,
      ciHigh: 0.242,
      pValue: 2.8e-20,
      pAdjusted: 5.7e-20,
      details: { alpha: 0.05, median_jaccard_if: 0.677, median_jaccard_other: 0.481, median_if_seed_noise: 0.886 },
    },
  ],
  profiles: [
    { algorithm: "isolation_forest", p: 0.01, dimension: "favored_type", category: "company", value: 0.0148, baseline: 0.304 },
    { algorithm: "lof", p: 0.01, dimension: "favored_type", category: "company", value: 0.0032, baseline: 0.304 },
    { algorithm: "isolation_forest", p: 0.01, dimension: "reference_month", category: "2025-01", value: 0.0075, baseline: 0.07 },
    { algorithm: "isolation_forest", p: 0.01, dimension: "superior_agency", category: "Ministério da Educação", value: 0.397, baseline: 0.2 },
    { algorithm: "isolation_forest", p: 0.01, dimension: "feature_median", category: "amount", value: 39429.62, baseline: 1032 },
    { algorithm: "isolation_forest", p: 0.01, dimension: "dominant_feature", category: "amount_vs_ug", value: 0.326, baseline: null },
    { algorithm: "isolation_forest", p: 0.05, dimension: "favored_type", category: "company", value: 0.06, baseline: 0.304 },
  ],
  surrogates: [{ algorithm: "lof", depth: 3, fidelity: 0.22, rules: "|--- favored_ug_count <= 2.60\n" }],
  overlaps: [
    { p: 0.01, algorithmCount: 1, recordCount: 910 },
    { p: 0.01, algorithmCount: 2, recordCount: 240 },
    { p: 0.01, algorithmCount: 3, recordCount: 105 },
  ],
};

type Handler = (url: URL, init?: RequestInit) => unknown;

/** Replaces fetch with handlers keyed by "METHOD /path"; a handler may return a Response. */
export function mockApi(handlers: Record<string, Handler>) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = new URL(String(input), "http://localhost");
    const key = `${init?.method ?? "GET"} ${url.pathname}`;
    const handler = handlers[key];
    if (!handler) return new Response(JSON.stringify({ title: "não mapeado" }), { status: 404 });
    const body = handler(url, init);
    return body instanceof Response ? body : new Response(JSON.stringify(body), { status: 200 });
  });
}
