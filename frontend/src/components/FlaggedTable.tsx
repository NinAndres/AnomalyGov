import { useState } from "react";
import type { RecordsQuery } from "../api/client";
import { ALGORITHMS, type Algorithm, type FlaggedPage, type SourceDefinition } from "../api/types";
import { useApi } from "../api/useApi";
import {
  ALGORITHM_LABELS,
  ALGORITHM_SHORT,
  columnLabel,
  formatNumber,
  formatPercent,
  formatValue,
  MONEY_COLUMNS,
} from "../format";
import { Loading, Notice } from "./Layout";

const PAGE_SIZE = 25;

interface Props {
  /** Loads one page; must be stable between renders (useCallback). */
  load: (query: RecordsQuery) => Promise<FlaggedPage>;
  source: SourceDefinition;
  /** Thresholds the user can choose; when absent the backend uses the job's own p. */
  pOptions?: number[];
}

export function FlaggedTable({ load, source, pOptions }: Props) {
  const [p, setP] = useState<number | undefined>(pOptions?.[0]);
  const [algorithm, setAlgorithm] = useState<Algorithm | null>(null);
  const [page, setPage] = useState(1);
  const { data, error, loading } = useApi(
    () => load({ p, algorithm, page, pageSize: PAGE_SIZE }),
    [load, p, algorithm, page],
  );
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div className="flagged">
      <div className="toolbar">
        {pOptions && (
          <label>
            Limiar p{" "}
            <select
              value={p}
              onChange={(e) => {
                setP(Number(e.target.value));
                setPage(1);
              }}
            >
              {pOptions.map((value) => (
                <option key={value} value={value}>
                  {formatPercent(value, 0)}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          Sinalizados por{" "}
          <select
            value={algorithm ?? ""}
            onChange={(e) => {
              setAlgorithm((e.target.value || null) as Algorithm | null);
              setPage(1);
            }}
          >
            <option value="">qualquer algoritmo</option>
            {ALGORITHMS.map((a) => (
              <option key={a} value={a}>
                {ALGORITHM_LABELS[a]}
              </option>
            ))}
          </select>
        </label>
        {data && (
          <span className="toolbar-info">
            {formatNumber(data.total)} registros sinalizados a p = {formatPercent(data.p, 0)}
          </span>
        )}
      </div>

      {error && <Notice kind="error">{error.message}</Notice>}
      {loading && !data && <Loading />}
      {data && data.items.length === 0 && <Notice>Nenhum registro sinalizado com estes critérios.</Notice>}
      {data && data.items.length > 0 && (
        <div className="table-scroll">
          <table className={loading ? "is-loading" : undefined}>
            <thead>
              <tr>
                <th scope="col">Sinalizado por</th>
                {source.displayColumns.map((c) => (
                  <th key={c} scope="col" className={MONEY_COLUMNS.includes(c) ? "num" : undefined}>
                    {columnLabel(c)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.items.map((item) => (
                <tr key={item.paymentId}>
                  <td>
                    <span className="badges">
                      {ALGORITHMS.filter((a) => item.flags[a]).map((a) => (
                        <span
                          key={a}
                          className={`badge badge-${a}`}
                          title={`${ALGORITHM_LABELS[a]}: escore normalizado ${formatNumber(item.scores[a], 4)}`}
                        >
                          {ALGORITHM_SHORT[a]}
                        </span>
                      ))}
                    </span>
                  </td>
                  {source.displayColumns.map((c) => (
                    <td key={c} className={MONEY_COLUMNS.includes(c) ? "num" : undefined}>
                      {formatValue(c, item.values[c] ?? null, item.values, source.filters)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.total > PAGE_SIZE && (
        <nav className="pagination" aria-label="Páginas">
          <button type="button" onClick={() => setPage(page - 1)} disabled={page <= 1}>
            Anterior
          </button>
          <span>
            Página {page} de {pages}
          </span>
          <button type="button" onClick={() => setPage(page + 1)} disabled={page >= pages}>
            Próxima
          </button>
        </nav>
      )}
    </div>
  );
}
