import type {
  Algorithm,
  ExperimentDetail,
  ExperimentSummary,
  Filters,
  FlaggedPage,
  Job,
  ProblemDetails,
  SourceDefinition,
} from "./types";

const BASE_URL = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

/** HTTP error with the Problem Details body returned by the backend, when there is one. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly problem: ProblemDetails | null,
  ) {
    super(problem?.detail ?? problem?.title ?? describeStatus(status));
    this.name = "ApiError";
  }

  /** Validation messages per field (e.g. "filters.uf"), when the request was rejected. */
  get fieldErrors(): Record<string, string[]> {
    return this.problem?.errors ?? {};
  }
}

function describeStatus(status: number): string {
  if (status === 0) return "Não foi possível conectar à API.";
  if (status === 404) return "Recurso não encontrado.";
  if (status === 429) return "Muitas requisições. Tente novamente em instantes.";
  if (status >= 500) return "Erro interno no servidor.";
  return `Erro ${status}.`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}) },
    });
  } catch {
    throw new ApiError(0, null);
  }
  if (!response.ok) {
    let problem: ProblemDetails | null = null;
    try {
      problem = (await response.json()) as ProblemDetails;
    } catch {
      // Body is not JSON: keep the status message.
    }
    throw new ApiError(response.status, problem);
  }
  return (await response.json()) as T;
}

function query(params: Record<string, string | number | null | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== null && v !== undefined && v !== "");
  return entries.length ? `?${new URLSearchParams(entries.map(([k, v]) => [k, String(v)]))}` : "";
}

export interface RecordsQuery {
  p?: number;
  algorithm?: Algorithm | null;
  page?: number;
  pageSize?: number;
}

export const api = {
  sources: () => request<SourceDefinition[]>("/api/sources"),
  createJob: (source: string, filters: Filters, p: number) =>
    request<Job>("/api/jobs", { method: "POST", body: JSON.stringify({ source, filters, params: { p } }) }),
  job: (id: string) => request<Job>(`/api/jobs/${encodeURIComponent(id)}`),
  jobRecords: (id: string, q: RecordsQuery) =>
    request<FlaggedPage>(`/api/jobs/${encodeURIComponent(id)}/records${query({ ...q })}`),
  experiments: () => request<ExperimentSummary[]>("/api/experiments"),
  experiment: (name: string) => request<ExperimentDetail>(`/api/experiments/${encodeURIComponent(name)}`),
  experimentRecords: (name: string, q: RecordsQuery) =>
    request<FlaggedPage>(`/api/experiments/${encodeURIComponent(name)}/records${query({ ...q })}`),
};
