using System.Text.Json;
using AnomalyGov.Api.Data;
using AnomalyGov.Api.Records;
using AnomalyGov.Api.Sources;
using Dapper;
using Npgsql;

namespace AnomalyGov.Api.Jobs;

public sealed record CreateJobRequest(string? Source, JsonElement? Filters, JsonElement? Params);

public sealed record Job(
    Guid Id, string Source, string Mode, string Status, JsonElement Filters, JsonElement Params,
    JsonElement? Result, string? Error, DateTime CreatedAt, DateTime? StartedAt, DateTime? FinishedAt);

public sealed class JobRepository(NpgsqlDataSource dataSource)
{
    private sealed record Row(
        Guid Id, string Source, string Mode, string Status, string Filters, string Params, string? Result,
        string? Error, DateTime CreatedAt, DateTime? StartedAt, DateTime? FinishedAt);

    private const string Columns = """
        id, source, mode, status, filters::text AS filters, params::text AS params, result::text AS result, error,
        created_at AS createdat, started_at AS startedat, finished_at AS finishedat
        """;

    public async Task<Job> CreateAsync(string source, JsonElement filters, object parameters, CancellationToken ct)
    {
        await using var conn = await dataSource.OpenConnectionAsync(ct);
        var row = await conn.QuerySingleAsync<Row>(new CommandDefinition(
            $"INSERT INTO jobs (source, filters, params) VALUES (@source, @filters::jsonb, @params::jsonb) RETURNING {Columns}",
            new { source, filters = filters.GetRawText(), @params = JsonSerializer.Serialize(parameters) },
            cancellationToken: ct));
        return ToJob(row);
    }

    public async Task<Job?> GetAsync(Guid id, CancellationToken ct)
    {
        await using var conn = await dataSource.OpenConnectionAsync(ct);
        var row = await conn.QuerySingleOrDefaultAsync<Row>(new CommandDefinition(
            $"SELECT {Columns} FROM jobs WHERE id = @id", new { id }, cancellationToken: ct));
        return row is null ? null : ToJob(row);
    }

    private static Job ToJob(Row r) => new(
        r.Id, r.Source, r.Mode, r.Status, Json.Parse(r.Filters)!.Value, Json.Parse(r.Params)!.Value,
        Json.Parse(r.Result), r.Error, r.CreatedAt, r.StartedAt, r.FinishedAt);
}

public static class JobEndpoints
{
    public const string RateLimitPolicy = "jobs";

    public static void MapJobs(this IEndpointRouteBuilder app)
    {
        var group = app.MapGroup("/api/jobs").WithTags("Jobs");

        group.MapPost("/", async (CreateJobRequest request, SourceRepository sources, JobRepository jobs,
            CancellationToken ct) =>
        {
            if (string.IsNullOrWhiteSpace(request.Source))
            {
                return Results.ValidationProblem(new Dictionary<string, string[]> { ["source"] = ["Informe a base."] });
            }

            var source = await sources.GetAsync(request.Source, ct);
            if (source is null)
            {
                return Results.ValidationProblem(new Dictionary<string, string[]> { ["source"] = ["Base desconhecida."] });
            }

            var errors = JobRequestValidator.ValidateFilters(source, request.Filters);
            var (parameters, paramErrors) = JobRequestValidator.ValidateParams(request.Params);
            foreach (var (key, messages) in paramErrors)
            {
                errors[key] = messages;
            }

            if (errors.Count > 0)
            {
                return Results.ValidationProblem(errors);
            }

            var filters = request.Filters is { ValueKind: JsonValueKind.Object } f ? f : JsonDocument.Parse("{}").RootElement;
            var job = await jobs.CreateAsync(source.Name, filters, parameters, ct);
            return Results.Created($"/api/jobs/{job.Id}", job);
        }).RequireRateLimiting(RateLimitPolicy);

        group.MapGet("/{id:guid}", async (Guid id, JobRepository jobs, CancellationToken ct) =>
            await jobs.GetAsync(id, ct) is { } job ? Results.Ok(job) : Results.NotFound());

        group.MapGet("/{id:guid}/records", async (Guid id, string? algorithm, int? page, int? pageSize,
            JobRepository jobs, SourceRepository sources, FlaggedRecords records, CancellationToken ct) =>
        {
            var job = await jobs.GetAsync(id, ct);
            if (job is null)
            {
                return Results.NotFound();
            }

            if (job.Status != "succeeded")
            {
                return Results.Problem($"O job ainda não terminou com sucesso (status: {job.Status}).",
                    statusCode: StatusCodes.Status409Conflict);
            }

            if (algorithm is not null && !FlaggedRecords.Algorithms.Contains(algorithm))
            {
                return Results.ValidationProblem(new Dictionary<string, string[]> { ["algorithm"] = ["Algoritmo desconhecido."] });
            }

            var source = (await sources.GetAsync(job.Source, ct))!;
            var p = job.Params.TryGetProperty("p", out var value) ? value.GetDouble() : JobRequestValidator.DefaultP;
            var parameters = new DynamicParameters(new { jobId = id });
            return Results.Ok(await records.QueryAsync(source, "job_id = @jobId", parameters, p, algorithm,
                page ?? 1, pageSize ?? 50, ct));
        });
    }
}
