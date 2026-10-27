import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError, type RecordsQuery } from "../api/client";
import type { Filters, Job, JobResult, SourceDefinition } from "../api/types";
import { useApi } from "../api/useApi";
import { FlaggedTable } from "../components/FlaggedTable";
import { Loading, Notice } from "../components/Layout";
import { formatDateTime, formatMonth, formatNumber, formatPercent } from "../format";

export const POLL_INTERVAL_MS = 1500;

const STATUS_LABELS: Record<Job["status"], string> = {
  pending: "Na fila",
  running: "Em execução",
  succeeded: "Concluído",
  failed: "Falhou",
};

/** Polls the job until it finishes (the backend never pushes updates). */
function useJob(id: string) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const current = await api.job(id);
        if (!active) return;
        setJob(current);
        setError(null);
        if (current.status === "pending" || current.status === "running") {
          timer = setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch (e) {
        if (!active) return;
        setError(e instanceof ApiError ? e : new ApiError(0, null));
        timer = setTimeout(poll, POLL_INTERVAL_MS * 2);
      }
    };
    poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [id]);

  return { job, error };
}

export function JobPage() {
  const { id = "" } = useParams();
  const { job, error } = useJob(id);
  const sources = useApi(() => api.sources(), []);
  const source = sources.data?.find((s) => s.name === job?.source) ?? null;
  const loadRecords = useCallback((q: RecordsQuery) => api.jobRecords(id, q), [id]);

  if (error?.status === 404) {
    return (
      <Notice kind="error">
        Job não encontrado. Os resultados da exploração ficam disponíveis por 24 horas.{" "}
        <Link to="/exploracao">Criar outro recorte</Link>
      </Notice>
    );
  }
  if (!job) return error ? <Notice kind="error">{error.message}</Notice> : <Loading />;

  const finished = job.status === "succeeded" || job.status === "failed";
  return (
    <section>
      <p>
        <Link to="/exploracao">← Novo recorte</Link>
      </p>
      <h1>Recorte da exploração</h1>
      <dl className="job-summary">
        <dt>Situação</dt>
        <dd>
          <span className={`status status-${job.status}`} aria-live="polite">
            {STATUS_LABELS[job.status]}
          </span>
          {!finished && <span className="hint"> atualizando automaticamente…</span>}
        </dd>
        {!finished && job.progress && (
          <>
            <dt>Andamento</dt>
            <dd aria-live="polite">{describeProgress(job.progress)}</dd>
          </>
        )}
        <dt>Filtros</dt>
        <dd>{source ? describeFilters(job.filters, source) : "…"}</dd>
        <dt>Limiar</dt>
        <dd>{formatPercent(job.params.p, 0)} mais anômalos de cada algoritmo</dd>
        <dt>Criado em</dt>
        <dd>{formatDateTime(job.createdAt)}</dd>
        {job.result && (
          <>
            <dt>Registros</dt>
            <dd>
              {formatNumber(job.result.n_filtered)} no recorte
              {job.result.sampled && `, ${formatNumber(job.result.n_used)} sorteados para a execução`}
              {job.result.portal && describeDownload(job.result.portal)}
            </dd>
          </>
        )}
      </dl>
      {error && <Notice kind="warning">Falha ao atualizar a situação: {error.message} Tentando novamente…</Notice>}
      {job.status === "failed" && <Notice kind="error">{job.error}</Notice>}
      {job.result?.portal?.truncated && (
        <Notice kind="warning">
          A consulta foi interrompida no limite de {formatNumber(job.result.portal.max_rows)} registros da exploração.
          O recorte analisado contém <strong>os primeiros registros devolvidos pelo Portal</strong>, não uma amostra
          aleatória do período. Para analisar o período inteiro, reduza o intervalo de meses.
        </Notice>
      )}
      {job.result?.sampled && (
        <Notice kind="warning">
          O recorte tem mais registros que o limite da exploração. Os algoritmos foram executados sobre uma amostra
          aleatória de {formatNumber(job.result.n_used)} registros (semente {job.result.sample_seed}).
        </Notice>
      )}
      {job.status === "succeeded" && source && (
        <>
          <Notice>
            As anomalias abaixo são <strong>relativas a este recorte</strong> e ficam disponíveis por 24 horas.
          </Notice>
          <h2>Registros sinalizados</h2>
          <FlaggedTable load={loadRecords} source={source} />
        </>
      )}
    </section>
  );
}

const EXCLUSION_LABELS: Record<string, string> = {
  duplicate: "repetidos",
  missing_date: "sem data",
  non_positive_value: "sem valor positivo",
};

function describeProgress(progress: NonNullable<Job["progress"]>): string {
  const counts = `${formatNumber(progress.received)} registros recebidos em ${formatNumber(progress.requests)} requisições`;
  if (progress.phase === "scoring") return `Download concluído (${counts}). Executando os algoritmos…`;
  return `Consultando a API do Portal${progress.month ? ` (${formatMonth(progress.month)})` : ""}: ${counts}…`;
}

function describeDownload(portal: NonNullable<JobResult["portal"]>): string {
  const excluded = Object.entries(portal.excluded)
    .filter(([, n]) => n > 0)
    .map(([reason, n]) => `${formatNumber(n)} ${EXCLUSION_LABELS[reason] ?? reason}`);
  return (
    ` (${formatNumber(portal.received)} recebidos da API do Portal em ${formatNumber(portal.requests)} requisições` +
    (excluded.length ? `; descartados: ${excluded.join(", ")}` : "") +
    ")"
  );
}

export function describeFilters(filters: Filters, source: SourceDefinition): string {
  const parts = Object.entries(filters).map(([name, value]) => {
    const definition = source.filters.find((f) => f.name === name);
    const label = definition?.label ?? name;
    if (Array.isArray(value)) {
      const labels = value.map((v) => definition?.options?.find((o) => o.value === v)?.label ?? v);
      return `${label}: ${labels.length > 3 ? `${labels.slice(0, 3).join(", ")} e mais ${labels.length - 3}` : labels.join(", ")}`;
    }
    if ("from" in value || "to" in value) {
      const { from, to } = value as { from?: string; to?: string };
      return `${label}: ${from ? formatMonth(from) : "início"} a ${to ? formatMonth(to) : "fim"}`;
    }
    const { min, max } = value as { min?: number; max?: number };
    return `${label}: ${min ?? "sem mínimo"} a ${max ?? "sem máximo"}`;
  });
  return parts.length ? parts.join("; ") : "nenhum (amostra publicada inteira)";
}
