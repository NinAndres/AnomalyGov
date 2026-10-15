import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { Filters } from "../api/types";
import { useApi } from "../api/useApi";
import { Loading, Notice } from "../components/Layout";
import { FilterForm } from "../filters/FilterForm";

export function ExplorePage() {
  const navigate = useNavigate();
  const sources = useApi(() => api.sources(), []);
  const [sourceName, setSourceName] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const source = sources.data?.find((s) => s.name === sourceName) ?? sources.data?.[0] ?? null;

  const submit = async (filters: Filters, p: number) => {
    if (!source) return;
    setSubmitting(true);
    setErrors({});
    setSubmitError(null);
    try {
      const job = await api.createJob(source.name, filters, p);
      navigate(`/exploracao/jobs/${job.id}`);
    } catch (e) {
      const error = e instanceof ApiError ? e : new ApiError(0, null);
      setErrors(error.fieldErrors);
      setSubmitError(error.message);
      setSubmitting(false);
    }
  };

  return (
    <section>
      <h1>Exploração</h1>
      <p className="lead">
        Escolha um recorte da amostra publicada e execute os três algoritmos sobre ele. As anomalias são{" "}
        <strong>relativas ao recorte</strong>: um registro é atípico em comparação com os demais registros filtrados,
        não com a base inteira. Os resultados da exploração não fazem parte do experimento do artigo.
      </p>

      {sources.loading && <Loading />}
      {sources.error && <Notice kind="error">{sources.error.message}</Notice>}
      {sources.data && sources.data.length > 1 && (
        <label className="source-picker">
          Base{" "}
          <select value={source?.name} onChange={(e) => setSourceName(e.target.value)}>
            {sources.data.map((s) => (
              <option key={s.name} value={s.name}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
      )}
      {source && (
        <>
          <h2>{source.label}</h2>
          {submitError && <Notice kind="error">{submitError}</Notice>}
          <FilterForm key={source.name} source={source} errors={errors} submitting={submitting} onSubmit={submit} />
        </>
      )}
    </section>
  );
}
