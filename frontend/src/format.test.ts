import type { FilterDefinition } from "./api/types";
import { formatCurrency, formatPercent, formatPValue, formatValue, monthsBetween } from "./format";

const FILTERS: FilterDefinition[] = [
  {
    name: "favored_type",
    type: "select",
    label: "Tipo",
    options: [{ value: "company", label: "Pessoa jurídica" }],
    min: null,
    max: null,
  },
];

describe("formatting", () => {
  it("uses Brazilian separators", () => {
    expect(formatPercent(0.0067, 2)).toBe("0,67%");
    expect(formatCurrency(13668.91).replace(/\s/g, " ")).toBe("R$ 13.668,91");
  });

  it("shows missing and non-finite values as a dash", () => {
    expect(formatPercent(null)).toBe("—");
    expect(formatPValue(Number.NaN)).toBe("—");
  });

  it("uses scientific notation for very small p-values", () => {
    expect(formatPValue(5.7e-20)).toBe("5,7e-20");
    expect(formatPValue(0.0137)).toBe("0,014");
  });

  it("lists every month of a range", () => {
    expect(monthsBetween("2025-11", "2026-02")).toEqual(["2025-11", "2025-12", "2026-01", "2026-02"]);
  });
});

describe("formatValue", () => {
  it("never shows the name of an individual (LGPD)", () => {
    const row = { favored_type: "individual", favored_name: null };
    expect(formatValue("favored_name", null, row, FILTERS)).toBe("Pessoa física (oculto — LGPD)");
  });

  it("uses the option label of select filters and formats amounts", () => {
    expect(formatValue("favored_type", "company", {}, FILTERS)).toBe("Pessoa jurídica");
    expect(formatValue("amount", 10, {}, FILTERS)).toContain("10,00");
    expect(formatValue("uf", null, {}, FILTERS)).toBe("—");
  });

  it("formats the columns of the Portal API bases", () => {
    expect(formatValue("value", 1234.5, {}, [])).toContain("1.234,50");
    expect(formatValue("date", "2025-03-14", {}, [])).toBe("14/03/2025");
    expect(formatValue("favored_type", "management_unit", {}, [])).toBe("Unidade gestora federal");
    expect(formatValue("favored_name", null, { favored_type: "other" }, [])).toBe("Não identificado (oculto)");
  });
});
