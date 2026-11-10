using System.Text.Json;
using AnomalyGov.Api.Data;
using Dapper;
using Npgsql;

namespace AnomalyGov.Api.Sources;

public sealed record FilterOption(string Value, string Label);

/// <summary>One filter declared by a data source adapter (see ml/src/anomalygov_ml/sources/ and portal/).</summary>
/// <param name="Required">The job must use this filter (the Portal API bases need an agency and a period).</param>
/// <param name="MaxSelected">Select filters: most values that can be chosen.</param>
/// <param name="MaxMonths">Month ranges: both bounds are required and the range spans at most this many months.</param>
public sealed record FilterDefinition(
    string Name, string Type, string Label, IReadOnlyList<FilterOption>? Options, JsonElement? Min, JsonElement? Max,
    bool Required = false, int? MaxSelected = null, int? MaxMonths = null);

/// <param name="Kind">"sample": jobs filter the published sample; "portal": the worker downloads the cut from the
/// Portal API and its records and scores are in portal_records and portal_scores (db/migrations/009).</param>
public sealed record SourceDefinition(
    string Name, string Label, IReadOnlyList<FilterDefinition> Filters, IReadOnlyList<string> DisplayColumns,
    string Kind = SourceDefinition.Sample)
{
    public const string MonthRange = "month_range";
    public const string Select = "select";
    public const string NumberRange = "number_range";
    public const string Sample = "sample";
    public const string Portal = "portal";

    /// <summary>View with the display columns of the source's records (db/migrations/006).</summary>
    public string DisplayView => System.Text.RegularExpressions.Regex.IsMatch(Name, "^[a-z][a-z0-9_]*$")
        ? $"{Name}_display"
        : throw new InvalidOperationException($"Nome de base inválido: {Name}");
}

public sealed class SourceRepository(NpgsqlDataSource dataSource)
{
    private sealed record Row(string Name, string Label, string Filters, string DisplayColumns, string Kind);

    public async Task<IReadOnlyList<SourceDefinition>> ListAsync(CancellationToken ct)
    {
        await using var conn = await dataSource.OpenConnectionAsync(ct);
        var rows = await conn.QueryAsync<Row>(new CommandDefinition(
            """
            SELECT name, label, filters::text AS filters, display_columns::text AS displaycolumns, kind
            FROM sources ORDER BY kind DESC, name
            """,
            cancellationToken: ct));
        return rows.Select(ToDefinition).ToList();
    }

    public async Task<SourceDefinition?> GetAsync(string name, CancellationToken ct) =>
        (await ListAsync(ct)).FirstOrDefault(s => s.Name == name);

    private static SourceDefinition ToDefinition(Row row) => new(
        row.Name,
        row.Label,
        JsonSerializer.Deserialize<List<FilterDefinition>>(row.Filters, Json.Options) ?? [],
        JsonSerializer.Deserialize<List<string>>(row.DisplayColumns, Json.Options) ?? [],
        row.Kind);
}

public static class SourceEndpoints
{
    public static void MapSources(this IEndpointRouteBuilder app)
    {
        var group = app.MapGroup("/api/sources").WithTags("Bases");
        group.MapGet("/", async (SourceRepository repository, CancellationToken ct) =>
            Results.Ok(await repository.ListAsync(ct)));
        group.MapGet("/{name}", async (string name, SourceRepository repository, CancellationToken ct) =>
            await repository.GetAsync(name, ct) is { } source ? Results.Ok(source) : Results.NotFound());
    }
}
