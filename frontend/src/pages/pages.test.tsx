import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { EXPERIMENT, job, mockApi, PAGE, PORTAL_SOURCE, SOURCE } from "../test/fixtures";
import { ExperimentPage } from "./ExperimentPage";
import { ExplorePage } from "./ExplorePage";
import { JobPage, POLL_INTERVAL_MS } from "./JobPage";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/exploracao" element={<ExplorePage />} />
        <Route path="/exploracao/jobs/:id" element={<JobPage />} />
        <Route path="/experimentos/:name" element={<ExperimentPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ExplorePage", () => {
  it("creates a job and opens its page", async () => {
    const user = userEvent.setup();
    mockApi({
      "GET /api/sources": () => [SOURCE],
      "POST /api/jobs": () => job(),
      [`GET /api/jobs/${job().id}`]: () => job(),
    });
    renderAt("/exploracao");

    await user.click(await screen.findByRole("checkbox", { name: "Pessoa jurídica" }));
    await user.click(screen.getByRole("button", { name: "Executar os três algoritmos" }));
    expect(await screen.findByRole("heading", { name: "Recorte da exploração" })).toBeInTheDocument();
  });

  it("keeps the user on the form and shows field errors when the API rejects the job", async () => {
    const user = userEvent.setup();
    mockApi({
      "GET /api/sources": () => [SOURCE],
      "POST /api/jobs": () =>
        new Response(JSON.stringify({ title: "Requisição inválida.", errors: { "filters.amount": ["\"min\" deve ser menor ou igual a \"max\"."] } }), {
          status: 400,
        }),
    });
    renderAt("/exploracao");

    await user.click(await screen.findByRole("button", { name: "Executar os três algoritmos" }));
    expect(await screen.findByText("\"min\" deve ser menor ou igual a \"max\".")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Requisição inválida.");
  });
});

describe("JobPage", () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  it("polls until the job finishes, then shows the flagged records", async () => {
    const states = [
      job({ status: "pending" }),
      job({ status: "running", startedAt: "2026-10-15T10:00:01Z" }),
      job({
        status: "succeeded",
        startedAt: "2026-10-15T10:00:01Z",
        finishedAt: "2026-10-15T10:00:20Z",
        result: { n_filtered: 4406, n_used: 4406, sampled: false, sample_seed: null, runs: { isolation_forest: 1, lof: 2, one_class_svm: 3 } },
      }),
    ];
    const fetch = mockApi({
      "GET /api/sources": () => [SOURCE],
      [`GET /api/jobs/${job().id}`]: () => states.shift() ?? job({ status: "succeeded" }),
      [`GET /api/jobs/${job().id}/records`]: () => PAGE,
    });
    renderAt(`/exploracao/jobs/${job().id}`);

    expect(await screen.findByText("Na fila")).toBeInTheDocument();
    expect(screen.getByText("Tipo de favorecido: Pessoa jurídica")).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS));
    expect(await screen.findByText("Em execução")).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS));
    expect(await screen.findByText("Concluído")).toBeInTheDocument();
    expect(await screen.findByText("EMPRESA X")).toBeInTheDocument();
    expect(screen.getByText(/relativas a este recorte/)).toBeInTheDocument();

    // No more polling once the job has finished.
    const calls = fetch.mock.calls.filter(([url]) => String(url).endsWith(job().id)).length;
    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3));
    expect(fetch.mock.calls.filter(([url]) => String(url).endsWith(job().id)).length).toBe(calls);
  });

  it("shows the error of a failed job and the sampling notice", async () => {
    mockApi({
      "GET /api/sources": () => [SOURCE],
      [`GET /api/jobs/${job().id}`]: () =>
        job({ status: "failed", startedAt: "2026-10-15T10:00:01Z", finishedAt: "2026-10-15T10:00:02Z", error: "O recorte tem 3 registros; o mínimo é 100. Amplie os filtros." }),
    });
    renderAt(`/exploracao/jobs/${job().id}`);
    expect(await screen.findByText("O recorte tem 3 registros; o mínimo é 100. Amplie os filtros.")).toBeInTheDocument();
  });

  it("shows the download progress and the notices of a Portal API job", async () => {
    const portalJob = (overrides: Parameters<typeof job>[0]) =>
      job({ source: "portal_contracts", filters: { agency_code: ["26000"], period: { from: "2025-01", to: "2025-03" } }, ...overrides });
    const states = [
      portalJob({ status: "running", startedAt: "2026-10-15T10:00:01Z",
        progress: { phase: "fetching", month: "2025-02", received: 450, requests: 31 } }),
      portalJob({
        status: "succeeded",
        startedAt: "2026-10-15T10:00:01Z",
        finishedAt: "2026-10-15T10:09:00Z",
        result: {
          n_filtered: 9990, n_used: 9990, sampled: false, sample_seed: null,
          runs: { isolation_forest: 1, lof: 2, one_class_svm: 3 },
          portal: { requests: 667, received: 10000, excluded: { duplicate: 0, missing_date: 4, non_positive_value: 6 },
            truncated: true, max_rows: 10000 },
        },
      }),
    ];
    mockApi({
      "GET /api/sources": () => [SOURCE, PORTAL_SOURCE],
      [`GET /api/jobs/${job().id}`]: () => states.shift() ?? states[0],
      [`GET /api/jobs/${job().id}/records`]: () => ({ ...PAGE, items: [{ ...PAGE.items[0],
        values: { date: "2025-02-10", favored_type: "company", favored_name: "EMPRESA X", purchase_modality: "Pregão",
          value: 50000, portal_id: "123" } }] }),
    });
    renderAt(`/exploracao/jobs/${job().id}`);

    expect(await screen.findByText(/Consultando a API do Portal \(fev\/2025\): 450 registros recebidos em 31 requisições/))
      .toBeInTheDocument();
    expect(screen.getByText(/Órgão: Ministério da Educação \(26000\)/)).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS));
    expect(await screen.findByText("Concluído")).toBeInTheDocument();
    expect(screen.getByText(/10\.000 recebidos da API do Portal em 667 requisições; descartados: 4 sem data, 6 sem valor positivo/))
      .toBeInTheDocument();
    expect(screen.getByText(/os primeiros registros devolvidos pelo Portal/)).toBeInTheDocument();
    expect(await screen.findByText("Pregão")).toBeInTheDocument();
    expect(screen.getByText("10/02/2025")).toBeInTheDocument();
  });

  it("explains that results expire when the job no longer exists", async () => {
    mockApi({ "GET /api/sources": () => [SOURCE] });
    renderAt(`/exploracao/jobs/${job().id}`);
    expect(await screen.findByText(/ficam disponíveis por 24 horas/)).toBeInTheDocument();
  });
});

describe("ExperimentPage", () => {
  it("shows the article results of the experiment", async () => {
    mockApi({
      "GET /api/experiments/principal-2025": () => EXPERIMENT,
      "GET /api/sources": () => [SOURCE],
      "GET /api/experiments/principal-2025/records": () => PAGE,
    });
    renderAt("/experimentos/principal-2025");

    expect(await screen.findByRole("heading", { name: "Experimento principal-2025" })).toBeInTheDocument();
    expect(screen.getByText("568 (0,67% pond.)")).toBeInTheDocument();
    expect(screen.getByText("Isolation Forest × LOF")).toBeInTheDocument();
    expect(screen.getByText("0,900 (0,890–0,910)")).toBeInTheDocument();
    expect(screen.getByText("1 de 1 testes significativos (α = 0,05).")).toBeInTheDocument();
    expect(await screen.findByText("EMPRESA X")).toBeInTheDocument();
  });

  it("shows charts with table twins for the characteristics, interpretability and overlaps", async () => {
    const user = userEvent.setup();
    mockApi({
      "GET /api/experiments/principal-2025": () => EXPERIMENT,
      "GET /api/sources": () => [SOURCE],
      "GET /api/experiments/principal-2025/records": () => PAGE,
    });
    renderAt("/experimentos/principal-2025");

    expect(await screen.findByText("Tempo total na amostra principal (treino + pontuação, segundos)")).toBeInTheDocument();
    expect(screen.getByText("Registros sinalizados por quantos algoritmos")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "910" })).toBeInTheDocument();
    expect(screen.getByText("H2: estabilidade entre meses (Jaccard mediano dos 132 pares de meses)")).toBeInTheDocument();

    const characteristics = screen.getByRole("heading", { name: "Características dos registros sinalizados" }).closest("section")!;
    // Type labels come from the source definition; rates are weighted.
    const companyRow = within(characteristics).getByRole("row", { name: /Pessoa jurídica/ });
    expect(within(companyRow).getByText("1,48%")).toBeInTheDocument();
    expect(within(characteristics).getByText("Valor recebido (R$)")).toBeInTheDocument();
    expect(within(characteristics).getByText("Ministério da Educação")).toBeInTheDocument();

    await user.selectOptions(within(characteristics).getByRole("combobox", { name: /Limiar p/ }), "0.05");
    expect(within(characteristics).getByText("6,00%")).toBeInTheDocument();

    const interpretability = screen.getByRole("heading", { name: "Interpretabilidade" }).closest("section")!;
    expect(within(interpretability).getByText("0,220")).toBeInTheDocument();
    expect(within(interpretability).getByText("Regras da árvore substituta: LOF")).toBeInTheDocument();
  });
});
