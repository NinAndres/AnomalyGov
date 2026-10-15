import { mockApi } from "../test/fixtures";
import { api, ApiError } from "./client";

describe("api client", () => {
  it("sends the job in the documented format", async () => {
    const fetch = mockApi({ "POST /api/jobs": (_, init) => ({ id: "x", echo: JSON.parse(String(init?.body)) }) });
    const job = (await api.createJob("payments", { uf: ["SP"] }, 0.02)) as unknown as { echo: unknown };
    expect(job.echo).toEqual({ source: "payments", filters: { uf: ["SP"] }, params: { p: 0.02 } });
    expect(fetch.mock.calls[0][1]?.headers).toMatchObject({ "Content-Type": "application/json" });
  });

  it("omits empty query parameters", async () => {
    const fetch = mockApi({ "GET /api/experiments/principal-2025/records": () => ({}) });
    await api.experimentRecords("principal-2025", { p: 0.01, algorithm: null, page: 2 });
    expect(String(fetch.mock.calls[0][0])).toBe("/api/experiments/principal-2025/records?p=0.01&page=2");
  });

  it("exposes validation errors per field", async () => {
    mockApi({
      "POST /api/jobs": () =>
        new Response(JSON.stringify({ title: "Requisição inválida.", errors: { "filters.uf": ["Valor não disponível: XX."] } }), {
          status: 400,
        }),
    });
    const error = await api.createJob("payments", { uf: ["XX"] }, 0.01).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(400);
    expect(error.message).toBe("Requisição inválida.");
    expect(error.fieldErrors).toEqual({ "filters.uf": ["Valor não disponível: XX."] });
  });

  it("reports network failures and non-JSON errors in Portuguese", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await expect(api.sources()).rejects.toMatchObject({ status: 0, message: "Não foi possível conectar à API." });
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response("gateway", { status: 502 }));
    await expect(api.sources()).rejects.toMatchObject({ status: 502, message: "Erro interno no servidor." });
  });
});
