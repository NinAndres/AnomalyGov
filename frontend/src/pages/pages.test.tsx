import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { EXPERIMENT, job, mockApi, PAGE, SOURCE } from "../test/fixtures";
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
});
