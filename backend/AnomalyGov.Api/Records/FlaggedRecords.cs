using AnomalyGov.Api.Sources;
using Dapper;
using Npgsql;

namespace AnomalyGov.Api.Records;

public sealed record FlaggedRecord(
    long PaymentId,
    int FlaggedCount,
    IReadOnlyDictionary<string, bool> Flags,
    IReadOnlyDictionary<string, double?> Scores,
    IReadOnlyDictionary<string, object?> Values);

public sealed record FlaggedPage(
    double P, string? Algorithm, int Page, int PageSize, long Total, IReadOnlyList<FlaggedRecord> Items);

/// <summary>Records flagged by at least one run of a set of runs that scored the same records.</summary>
/// <remarks>
/// Same rule as ml/src/anomalygov_ml/metrics.py: a record is flagged by a run when its raw score is greater than
/// or equal to the (1 - p) quantile of the run's scores, with linear interpolation (percentile_cont = numpy).
/// </remarks>
public sealed class FlaggedRecords(NpgsqlDataSource dataSource)
{
    public static readonly string[] Algorithms = ["isolation_forest", "lof", "one_class_svm"];
    public const int MaxPageSize = 200;

    /// <param name="runFilter">SQL condition on `runs` selecting the runs; must only use parameters from <paramref name="parameters"/>.</param>
    public async Task<FlaggedPage> QueryAsync(SourceDefinition source, string runFilter, DynamicParameters parameters,
        double p, string? algorithm, int page, int pageSize, CancellationToken ct)
    {
        if (algorithm is not null && !Algorithms.Contains(algorithm))
        {
            throw new ArgumentException($"Algoritmo desconhecido: {algorithm}", nameof(algorithm));
        }

        page = Math.Max(page, 1);
        pageSize = Math.Clamp(pageSize, 1, MaxPageSize);
        parameters.Add("p", p);
        parameters.Add("limit", pageSize);
        parameters.Add("offset", (page - 1) * pageSize);

        var perAlgorithm = string.Join(",\n", Algorithms.Select(a =>
            $"coalesce(bool_or(flagged) FILTER (WHERE algorithm = '{a}'), false) AS flag_{a}, " +
            $"max(normalized_score) FILTER (WHERE algorithm = '{a}') AS score_{a}"));
        var algorithmCondition = algorithm is null ? "true" : $"agg.flag_{algorithm}";
        var sql = $"""
            WITH r AS (SELECT id, algorithm FROM runs WHERE {runFilter}),
            q AS (
                SELECT s.run_id, percentile_cont(1 - @p) WITHIN GROUP (ORDER BY s.raw_score) AS threshold
                FROM run_scores s JOIN r ON r.id = s.run_id GROUP BY s.run_id),
            f AS (
                SELECT s.payment_id, r.algorithm, s.normalized_score::float8 AS normalized_score,
                       s.raw_score >= q.threshold AS flagged
                FROM run_scores s JOIN r ON r.id = s.run_id JOIN q ON q.run_id = s.run_id),
            agg AS (
                SELECT payment_id, {perAlgorithm},
                       count(*) FILTER (WHERE flagged)::int AS flagged_count,
                       max(normalized_score) FILTER (WHERE flagged) AS max_flagged_score
                FROM f GROUP BY payment_id HAVING bool_or(flagged))
            SELECT count(*) OVER () AS total, agg.*, d.*
            FROM agg JOIN {source.DisplayView} d ON d.id = agg.payment_id
            WHERE {algorithmCondition}
            ORDER BY agg.flagged_count DESC, agg.max_flagged_score DESC, agg.payment_id
            LIMIT @limit OFFSET @offset
            """;

        await using var conn = await dataSource.OpenConnectionAsync(ct);
        var rows = (await conn.QueryAsync(new CommandDefinition(sql, parameters, cancellationToken: ct)))
            .Cast<IDictionary<string, object?>>()
            .ToList();

        var items = rows.Select(row => new FlaggedRecord(
            Convert.ToInt64(row["payment_id"]),
            Convert.ToInt32(row["flagged_count"]),
            Algorithms.ToDictionary(a => a, a => (bool)row[$"flag_{a}"]!),
            Algorithms.ToDictionary(a => a, a => row[$"score_{a}"] is double s ? s : (double?)null),
            source.DisplayColumns.ToDictionary(c => c, c => row.TryGetValue(c, out var v) ? v : null))).ToList();
        long total;
        if (rows.Count > 0)
        {
            total = Convert.ToInt64(rows[0]["total"]);
        }
        else
        {
            // Past the last page the window count has no row to ride on: count separately.
            var countSql = sql[..sql.IndexOf("SELECT count(*) OVER ()", StringComparison.Ordinal)] +
                           $"SELECT count(*) FROM agg WHERE {algorithmCondition}";
            total = await conn.ExecuteScalarAsync<long>(new CommandDefinition(countSql, parameters, cancellationToken: ct));
        }

        return new FlaggedPage(p, algorithm, page, pageSize, total, items);
    }
}
