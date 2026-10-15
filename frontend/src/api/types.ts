// Types of the backend API (docs/contratos.md, section "API (backend)").

export type Algorithm = "isolation_forest" | "lof" | "one_class_svm";
export const ALGORITHMS: Algorithm[] = ["isolation_forest", "lof", "one_class_svm"];

export interface FilterOption {
  value: string;
  label: string;
}

export interface FilterDefinition {
  name: string;
  type: "month_range" | "select" | "number_range";
  label: string;
  options: FilterOption[] | null;
  min: string | number | null;
  max: string | number | null;
}

export interface SourceDefinition {
  name: string;
  label: string;
  filters: FilterDefinition[];
  displayColumns: string[];
}

export type MonthRange = { from?: string; to?: string };
export type NumberRange = { min?: number; max?: number };
export type FilterValue = MonthRange | NumberRange | string[];
export type Filters = Record<string, FilterValue>;

export type JobStatus = "pending" | "running" | "succeeded" | "failed";

export interface JobResult {
  n_filtered: number;
  n_used: number;
  sampled: boolean;
  sample_seed: number | null;
  runs: Record<Algorithm, number>;
}

export interface Job {
  id: string;
  source: string;
  mode: string;
  status: JobStatus;
  filters: Filters;
  params: { p: number };
  result: JobResult | null;
  error: string | null;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface FlaggedRecord {
  paymentId: number;
  flaggedCount: number;
  flags: Record<Algorithm, boolean>;
  scores: Record<Algorithm, number | null>;
  values: Record<string, string | number | null>;
}

export interface FlaggedPage {
  p: number;
  algorithm: Algorithm | null;
  page: number;
  pageSize: number;
  total: number;
  items: FlaggedRecord[];
}

export interface ExperimentSummary {
  name: string;
  source: string;
  runs: number;
  firstRunAt: string;
  lastRunAt: string;
}

export interface RunMetric {
  p: number;
  flaggedCount: number;
  flaggedShare: number;
  weightedFlaggedShare: number;
}

export interface MainRun {
  id: number;
  algorithm: Algorithm;
  params: Record<string, unknown>;
  randomState: number | null;
  nTrain: number;
  fitSeconds: number;
  scoreSeconds: number;
  metrics: RunMetric[];
}

export interface Agreement {
  algorithmA: Algorithm;
  algorithmB: Algorithm;
  p: number;
  jaccard: number | null;
  spearman: number | null;
}

export interface StabilityComparison {
  runId: number;
  purpose: "parameter" | "data_stability" | "artifact";
  algorithm: Algorithm;
  params: Record<string, unknown>;
  p: number;
  jaccard: number | null;
  spearman: number | null;
}

export interface ScalabilityPoint {
  algorithm: Algorithm;
  nTrain: number;
  repetitions: number;
  meanSeconds: number;
  minSeconds: number;
  maxSeconds: number;
}

export interface HypothesisTest {
  hypothesis: string;
  family: string;
  test: string;
  variable: string;
  n: number;
  statistic: number | null;
  effect: number | null;
  ciLow: number | null;
  ciHigh: number | null;
  pValue: number | null;
  pAdjusted: number | null;
  details: Record<string, unknown> & { alpha?: number };
}

/** Dimensions of the characteristics of the flagged records (docs/contratos.md, migration 008). */
export type ProfileDimension =
  | "favored_type"
  | "reference_month"
  | "superior_agency"
  | "feature_median"
  | "dominant_feature";

/**
 * One characteristic of the records flagged by a main run. favored_type and reference_month: value = weighted
 * flagged rate, baseline = weighted share of the population; superior_agency: value = weighted share among the
 * flagged, baseline = share of the population; feature_median: value = median among the flagged, baseline = median
 * of the sample; dominant_feature: value = share of the flagged, baseline = null.
 */
export interface RunProfile {
  algorithm: Algorithm;
  p: number;
  dimension: ProfileDimension;
  category: string;
  value: number | null;
  baseline: number | null;
}

/** Global surrogate: shallow regression tree imitating the normalized scores of a main run. */
export interface Surrogate {
  algorithm: Algorithm;
  depth: number;
  fidelity: number | null;
  rules: string;
}

/** Records of the main sample flagged by exactly algorithmCount algorithms. */
export interface Overlap {
  p: number;
  algorithmCount: number;
  recordCount: number;
}

export interface ExperimentDetail {
  name: string;
  source: string;
  mainSampleId: number;
  mainRuns: MainRun[];
  agreement: Agreement[];
  stability: StabilityComparison[];
  scalability: ScalabilityPoint[];
  hypothesisTests: HypothesisTest[];
  profiles: RunProfile[];
  surrogates: Surrogate[];
  overlaps: Overlap[];
}

export interface ProblemDetails {
  title?: string;
  detail?: string;
  status?: number;
  errors?: Record<string, string[]>;
}
