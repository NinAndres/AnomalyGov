import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PAGE, SOURCE } from "../test/fixtures";
import { FlaggedTable } from "./FlaggedTable";

describe("FlaggedTable", () => {
  it("shows which algorithms flagged each record and hides individuals' names", async () => {
    const load = vi.fn().mockResolvedValue(PAGE);
    render(<FlaggedTable load={load} source={SOURCE} />);

    const rows = await screen.findAllByRole("row");
    expect(within(rows[1]).getAllByText(/^(IF|LOF|OCSVM)$/)).toHaveLength(3);
    expect(within(rows[1]).getByText("EMPRESA X")).toBeInTheDocument();
    expect(within(rows[2]).getAllByText(/^(IF|LOF|OCSVM)$/).map((b) => b.textContent)).toEqual(["LOF"]);
    expect(within(rows[2]).getByText("Pessoa física (oculto — LGPD)")).toBeInTheDocument();
    expect(screen.getByText("2 registros sinalizados a p = 1%")).toBeInTheDocument();
  });

  it("reloads from the first page when the algorithm or p changes", async () => {
    const user = userEvent.setup();
    const load = vi.fn().mockResolvedValue({ ...PAGE, total: 60 });
    render(<FlaggedTable load={load} source={SOURCE} pOptions={[0.01, 0.05]} />);

    await user.click(await screen.findByRole("button", { name: "Próxima" }));
    expect(load).toHaveBeenLastCalledWith({ p: 0.01, algorithm: null, page: 2, pageSize: 25 });

    await user.selectOptions(screen.getByRole("combobox", { name: "Sinalizados por" }), "lof");
    expect(load).toHaveBeenLastCalledWith({ p: 0.01, algorithm: "lof", page: 1, pageSize: 25 });

    await user.selectOptions(screen.getByRole("combobox", { name: "Limiar p" }), "0.05");
    expect(load).toHaveBeenLastCalledWith({ p: 0.05, algorithm: "lof", page: 1, pageSize: 25 });
  });

  it("explains when nothing was flagged", async () => {
    render(<FlaggedTable load={vi.fn().mockResolvedValue({ ...PAGE, total: 0, items: [] })} source={SOURCE} />);
    expect(await screen.findByText("Nenhum registro sinalizado com estes critérios.")).toBeInTheDocument();
  });
});
