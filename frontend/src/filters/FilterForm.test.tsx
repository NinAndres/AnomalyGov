import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PORTAL_SOURCE, SOURCE } from "../test/fixtures";
import { buildFilters, FilterForm } from "./FilterForm";

describe("buildFilters", () => {
  it("keeps only filters with a value", () => {
    expect(
      buildFilters({
        reference_month: { from: "2025-02", to: undefined },
        favored_type: [],
        amount: { min: undefined, max: undefined },
        uf: ["SP"],
      }),
    ).toEqual({ reference_month: { from: "2025-02" }, uf: ["SP"] });
  });
});

describe("FilterForm", () => {
  it("builds one field per filter of the source definition", () => {
    render(<FilterForm source={SOURCE} errors={{}} submitting={false} onSubmit={() => {}} />);
    for (const filter of SOURCE.filters) {
      expect(screen.getByRole("group", { name: filter.label })).toBeInTheDocument();
    }
    expect(screen.getByRole("checkbox", { name: "Pessoa jurídica" })).toBeInTheDocument();
  });

  it("submits the selected filters and p", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<FilterForm source={SOURCE} errors={{}} submitting={false} onSubmit={onSubmit} />);

    await user.selectOptions(screen.getByRole("combobox", { name: "De" }), "2025-03");
    await user.click(screen.getByRole("checkbox", { name: "Pessoa jurídica" }));
    await user.type(screen.getByRole("spinbutton", { name: "Mínimo" }), "1000");
    await user.selectOptions(screen.getByRole("combobox", { name: "p" }), "0.05");
    await user.click(screen.getByRole("button", { name: "Executar os três algoritmos" }));

    expect(onSubmit).toHaveBeenCalledWith(
      { reference_month: { from: "2025-03" }, favored_type: ["company"], amount: { min: 1000 } },
      0.05,
    );
  });

  it("shows the validation errors returned by the API next to each field", () => {
    render(
      <FilterForm
        source={SOURCE}
        errors={{ "filters.favored_type": ["Valor não disponível: XX."] }}
        submitting={false}
        onSubmit={() => {}}
      />,
    );
    expect(screen.getByText("Valor não disponível: XX.")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Tipo de favorecido" })).toHaveAttribute("aria-invalid", "true");
  });

  it("disables submission while a job is being created", () => {
    render(<FilterForm source={SOURCE} errors={{}} submitting onSubmit={() => {}} />);
    expect(screen.getByRole("button", { name: "Enviando…" })).toBeDisabled();
  });
});

describe("FilterForm with a Portal API base", () => {
  it("marks the required filters, picks a single agency and tells the period limit", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<FilterForm source={PORTAL_SOURCE} errors={{}} submitting={false} onSubmit={onSubmit} />);

    expect(screen.getAllByText("(obrigatório)")).toHaveLength(2);
    expect(screen.getByText("Até 12 meses por consulta.")).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "Ministério da Educação (26000)" }));
    await user.click(screen.getByRole("radio", { name: "Ministério da Saúde (36000)" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "De" }), "2025-01");
    await user.selectOptions(screen.getByRole("combobox", { name: "Até" }), "2025-06");
    await user.click(screen.getByRole("button", { name: "Executar os três algoritmos" }));

    expect(onSubmit).toHaveBeenCalledWith(
      { agency_code: ["36000"], period: { from: "2025-01", to: "2025-06" } },
      0.01,
    );
  });
});
