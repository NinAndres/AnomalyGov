import type { Algorithm, FilterDefinition } from "./api/types";

const LOCALE = "pt-BR";

export const ALGORITHM_LABELS: Record<Algorithm, string> = {
  isolation_forest: "Isolation Forest",
  lof: "LOF",
  one_class_svm: "One-Class SVM",
};

export const ALGORITHM_SHORT: Record<Algorithm, string> = {
  isolation_forest: "IF",
  lof: "LOF",
  one_class_svm: "OCSVM",
};

/** Labels of the display columns of the bases; unknown columns show their own name. */
const COLUMN_LABELS: Record<string, string> = {
  reference_month: "Mês",
  favored_type: "Tipo de favorecido",
  favored_name: "Favorecido",
  superior_agency_name: "Órgão superior",
  management_unit_name: "Unidade gestora",
  uf: "UF",
  municipality: "Município",
  amount: "Valor recebido",
};

export function columnLabel(column: string): string {
  return COLUMN_LABELS[column] ?? column;
}

export function formatNumber(value: number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value.toLocaleString(LOCALE, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

export function formatPercent(share: number | null | undefined, decimals = 1): string {
  if (share === null || share === undefined || !Number.isFinite(share)) return "—";
  return `${formatNumber(share * 100, decimals)}%`;
}

export function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value.toLocaleString(LOCALE, { style: "currency", currency: "BRL" });
}

/** p-values: scientific notation below 0,001. */
export function formatPValue(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  if (value < 0.001) return value.toExponential(1).replace(".", ",");
  return formatNumber(value, 3);
}

export function formatMonth(month: string): string {
  const [year, m] = month.split("-");
  const date = new Date(Number(year), Number(m) - 1, 1);
  const name = date.toLocaleString(LOCALE, { month: "short" }).replace(".", "");
  return `${name}/${year}`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(LOCALE, { dateStyle: "short", timeStyle: "medium" });
}

/** Text of one display value: currency for amounts, option labels for select filters, LGPD for individuals. */
export function formatValue(
  column: string,
  value: string | number | null,
  row: Record<string, string | number | null>,
  filters: FilterDefinition[],
): string {
  if (column === "favored_name" && value === null && row.favored_type === "individual") {
    return "Pessoa física (oculto — LGPD)";
  }
  if (value === null || value === undefined) return "—";
  if (column === "amount") return formatCurrency(Number(value));
  if (column === "reference_month" && typeof value === "string") return formatMonth(value);
  const options = filters.find((f) => f.name === column)?.options;
  return options?.find((o) => o.value === value)?.label ?? String(value);
}

/** Every month between two "YYYY-MM" values, inclusive. */
export function monthsBetween(first: string, last: string): string[] {
  const months: string[] = [];
  let [year, month] = first.split("-").map(Number);
  const [lastYear, lastMonth] = last.split("-").map(Number);
  while (year < lastYear || (year === lastYear && month <= lastMonth)) {
    months.push(`${year}-${String(month).padStart(2, "0")}`);
    month += 1;
    if (month > 12) {
      month = 1;
      year += 1;
    }
  }
  return months;
}
