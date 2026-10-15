import { useMemo, useState, type FormEvent } from "react";
import type { FilterDefinition, Filters, FilterValue, MonthRange, NumberRange, SourceDefinition } from "../api/types";
import { formatMonth, formatPercent, monthsBetween } from "../format";

export const P_OPTIONS = [0.01, 0.02, 0.05];
const VISIBLE_OPTIONS = 100;

/** Keeps only filters with a value, in the format of docs/contratos.md. */
export function buildFilters(values: Record<string, FilterValue | undefined>): Filters {
  const filters: Filters = {};
  for (const [name, value] of Object.entries(values)) {
    if (value === undefined) continue;
    if (Array.isArray(value)) {
      if (value.length > 0) filters[name] = value;
      continue;
    }
    const bounds = Object.fromEntries(Object.entries(value).filter(([, v]) => v !== undefined && v !== ""));
    if (Object.keys(bounds).length > 0) filters[name] = bounds as FilterValue;
  }
  return filters;
}

interface Props {
  source: SourceDefinition;
  errors: Record<string, string[]>;
  submitting: boolean;
  onSubmit: (filters: Filters, p: number) => void;
}

export function FilterForm({ source, errors, submitting, onSubmit }: Props) {
  const [values, setValues] = useState<Record<string, FilterValue | undefined>>({});
  const [p, setP] = useState(P_OPTIONS[0]);
  const set = (name: string) => (value: FilterValue | undefined) => setValues((v) => ({ ...v, [name]: value }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit(buildFilters(values), p);
  };

  return (
    <form className="filter-form" onSubmit={submit} noValidate>
      {source.filters.map((filter) => {
        const fieldErrors = errors[`filters.${filter.name}`];
        return (
          <fieldset key={filter.name} className="filter" aria-invalid={fieldErrors ? true : undefined}>
            <legend>{filter.label}</legend>
            {filter.type === "month_range" && (
              <MonthRangeInput filter={filter} value={values[filter.name] as MonthRange} onChange={set(filter.name)} />
            )}
            {filter.type === "select" && (
              <MultiSelectInput filter={filter} value={values[filter.name] as string[]} onChange={set(filter.name)} />
            )}
            {filter.type === "number_range" && (
              <NumberRangeInput filter={filter} value={values[filter.name] as NumberRange} onChange={set(filter.name)} />
            )}
            {fieldErrors?.map((message) => (
              <p key={message} className="field-error">
                {message}
              </p>
            ))}
          </fieldset>
        );
      })}

      <fieldset className="filter">
        <legend>Limiar de sinalização</legend>
        <label>
          p{" "}
          <select value={p} onChange={(e) => setP(Number(e.target.value))}>
            {P_OPTIONS.map((value) => (
              <option key={value} value={value}>
                {formatPercent(value, 0)} mais anômalos de cada algoritmo
              </option>
            ))}
          </select>
        </label>
        {errors["params.p"]?.map((message) => (
          <p key={message} className="field-error">
            {message}
          </p>
        ))}
      </fieldset>

      <div className="form-actions">
        <button type="submit" className="primary" disabled={submitting}>
          {submitting ? "Enviando…" : "Executar os três algoritmos"}
        </button>
        <button type="button" onClick={() => setValues({})} disabled={submitting}>
          Limpar filtros
        </button>
      </div>
    </form>
  );
}

function MonthRangeInput({ filter, value, onChange }: InputProps<MonthRange>) {
  const months = useMemo(
    () => (filter.min && filter.max ? monthsBetween(String(filter.min), String(filter.max)) : []),
    [filter.min, filter.max],
  );
  const update = (key: keyof MonthRange, month: string) => onChange({ ...value, [key]: month || undefined });
  return (
    <div className="range">
      <label>
        De{" "}
        <select value={value?.from ?? ""} onChange={(e) => update("from", e.target.value)}>
          <option value="">início</option>
          {months.map((m) => (
            <option key={m} value={m}>
              {formatMonth(m)}
            </option>
          ))}
        </select>
      </label>
      <label>
        Até{" "}
        <select value={value?.to ?? ""} onChange={(e) => update("to", e.target.value)}>
          <option value="">fim</option>
          {months.map((m) => (
            <option key={m} value={m}>
              {formatMonth(m)}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}

function NumberRangeInput({ filter, value, onChange }: InputProps<NumberRange>) {
  const update = (key: keyof NumberRange, text: string) =>
    onChange({ ...value, [key]: text === "" ? undefined : Number(text) });
  return (
    <div className="range">
      <label>
        Mínimo{" "}
        <input type="number" inputMode="decimal" min={0} step="any" value={value?.min ?? ""}
          placeholder={filter.min !== null ? String(filter.min) : undefined}
          onChange={(e) => update("min", e.target.value)} />
      </label>
      <label>
        Máximo{" "}
        <input type="number" inputMode="decimal" min={0} step="any" value={value?.max ?? ""}
          placeholder={filter.max !== null ? String(filter.max) : undefined}
          onChange={(e) => update("max", e.target.value)} />
      </label>
    </div>
  );
}

function MultiSelectInput({ filter, value, onChange }: InputProps<string[]>) {
  const [search, setSearch] = useState("");
  const selected = value ?? [];
  const options = filter.options ?? [];
  const matches = useMemo(() => {
    const term = search.trim().toLocaleLowerCase("pt-BR");
    return term ? options.filter((o) => `${o.label} ${o.value}`.toLocaleLowerCase("pt-BR").includes(term)) : options;
  }, [options, search]);
  const toggle = (option: string) =>
    onChange(selected.includes(option) ? selected.filter((v) => v !== option) : [...selected, option]);
  const labelOf = (option: string) => options.find((o) => o.value === option)?.label ?? option;

  return (
    <div className="multi-select">
      {selected.length > 0 && (
        <ul className="chips" aria-label={`${filter.label}: selecionados`}>
          {selected.map((option) => (
            <li key={option}>
              <button type="button" className="chip" onClick={() => toggle(option)} title="Remover">
                {labelOf(option)} ×
              </button>
            </li>
          ))}
        </ul>
      )}
      {options.length > 10 && (
        <input type="search" placeholder={`Buscar em ${options.length} opções`} value={search}
          aria-label={`Buscar ${filter.label}`} onChange={(e) => setSearch(e.target.value)} />
      )}
      <div className="options" role="group" aria-label={`Opções de ${filter.label}`}>
        {matches.slice(0, VISIBLE_OPTIONS).map((option) => (
          <label key={option.value} className="option">
            <input type="checkbox" checked={selected.includes(option.value)} onChange={() => toggle(option.value)} />
            {option.label}
          </label>
        ))}
        {matches.length > VISIBLE_OPTIONS && (
          <p className="hint">Mostrando {VISIBLE_OPTIONS} de {matches.length}. Refine a busca.</p>
        )}
        {matches.length === 0 && <p className="hint">Nenhuma opção encontrada.</p>}
      </div>
    </div>
  );
}

interface InputProps<T> {
  filter: FilterDefinition;
  value: T | undefined;
  onChange: (value: T | undefined) => void;
}
