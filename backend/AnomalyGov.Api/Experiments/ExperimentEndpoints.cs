using System.Text.Json;
using AnomalyGov.Api.Data;
using AnomalyGov.Api.Records;
using AnomalyGov.Api.Sources;
using Dapper;
using Npgsql;

namespace AnomalyGov.Api.Experiments;

public sealed record ExperimentSummary(string Name, string Source, int Runs, DateTime FirstRunAt, DateTime LastRunAt);

public sealed record RunMetric(double P, int FlaggedCount, double FlaggedShare, double WeightedFlaggedShare);

public sealed record MainRun(
    int Id, string Algorithm, JsonElement Params, int? RandomState, int NTrain, double FitSeconds,
    double ScoreSeconds, IReadOnlyList<RunMetric> Metrics);

public sealed record Agreement(string AlgorithmA, string AlgorithmB, double P, double? Jaccard, double? Spearman);

public sealed record StabilityComparison(
    int RunId, string Purpose, string Algorithm, JsonElement Params, double P, double? Jaccard, double? Spearman);

public sealed record ScalabilityPoint(
    string Algorithm, int NTrain, int Repetitions, double MeanSeconds, double MinSeconds, double MaxSeconds);

public sealed record HypothesisTest(
    string Hypothesis, string Family, string Test, string Variable, int N, double? Statistic, double? Effect,
    double? CiLow, double? CiHigh, double? PValue, double? PAdjusted, JsonElement Details);

public sealed record ExperimentDetail(
    string Name, string Source, int MainSampleId, IReadOnlyList<MainRun> MainRuns, IReadOnlyList<Agreement> Agreement,
    IReadOnlyList<StabilityComparison> Stability, IReadOnlyList<ScalabilityPoint> Scalability,
    IReadOnlyList<HypothesisTest> HypothesisTests);

public sealed class ExperimentRepository(NpgsqlDataSource dataSource)
{
    public async Task<IReadOnlyList<ExperimentSummary>> ListAsync(CancellationToken ct)
    {
        await using var conn = await dataSource.OpenConnectionAsync(ct);
        return (await conn.QueryAsync<ExperimentSummary>(new CommandDefinition("""
            SELECT r.experiment AS name, min(s.source) AS source, count(*)::int AS runs,
                   min(r.created_at) AS firstrunat, max(r.created_at) AS lastrunat
            FROM runs r JOIN samples s ON s.id = r.train_sample_id
            WHERE r.mode = 'experiment' GROUP BY r.experiment ORDER BY r.experiment
            """, cancellationToken: ct))).ToList();
    }

    public async Task<ExperimentDetail?> GetAsync(string name, CancellationToken ct)
    {
        await using var conn = await dataSource.OpenConnectionAsync(ct);
        var args = new { name };

        var main = (await conn.QueryAsync<(int Id, string Algorithm, string Params, int? RandomState, int NTrain,
            double FitSeconds, double ScoreSeconds, int SampleId, string Source)>(new CommandDefinition("""
            SELECT r.id, r.algorithm, r.params::text, r.random_state, r.n_train, r.fit_seconds, r.score_seconds,
                   r.scored_sample_id, s.source
            FROM runs r JOIN samples s ON s.id = r.scored_sample_id
            WHERE r.experiment = @name AND r.mode = 'experiment' AND r.purpose = 'main' ORDER BY r.algorithm
            """, args, cancellationToken: ct))).ToList();
        if (main.Count == 0)
        {
            return null;
        }

        var metrics = (await conn.QueryAsync<(int RunId, double P, int FlaggedCount, double FlaggedShare,
            double WeightedFlaggedShare)>(new CommandDefinition("""
            SELECT m.run_id, m.p::float8, m.flagged_count, m.flagged_share, m.weighted_flagged_share
            FROM run_metrics m WHERE m.run_id = ANY(@ids) ORDER BY m.p
            """, new { ids = main.Select(r => r.Id).ToArray() }, cancellationToken: ct))).ToLookup(m => m.RunId);

        var comparisons = (await conn.QueryAsync<(int RunA, int RunB, double P, double Jaccard, double Spearman,
            string PurposeA, string PurposeB, string AlgorithmA, string AlgorithmB, string ParamsA, string ParamsB)>(
            new CommandDefinition("""
            SELECT c.run_a, c.run_b, c.p::float8, c.jaccard, c.spearman, a.purpose, b.purpose, a.algorithm,
                   b.algorithm, a.params::text, b.params::text
            FROM run_comparisons c JOIN runs a ON a.id = c.run_a JOIN runs b ON b.id = c.run_b
            WHERE a.experiment = @name ORDER BY c.run_a, c.run_b, c.p
            """, args, cancellationToken: ct))).ToList();

        var scalability = (await conn.QueryAsync<ScalabilityPoint>(new CommandDefinition("""
            SELECT algorithm, n_train AS ntrain, count(*)::int AS repetitions,
                   avg(fit_seconds + score_seconds) AS meanseconds, min(fit_seconds + score_seconds) AS minseconds,
                   max(fit_seconds + score_seconds) AS maxseconds
            FROM runs WHERE experiment = @name AND mode = 'experiment' AND purpose = 'scalability'
            GROUP BY algorithm, n_train ORDER BY n_train, algorithm
            """, args, cancellationToken: ct))).ToList();

        var tests = (await conn.QueryAsync<(string Hypothesis, string Family, string Test, string Variable, int N,
            double? Statistic, double? Effect, double? CiLow, double? CiHigh, double? PValue, double? PAdjusted,
            string Details)>(new CommandDefinition("""
            SELECT hypothesis, family, test, variable, n, statistic, effect, ci_low, ci_high, p_value, p_adjusted,
                   details::text
            FROM hypothesis_tests WHERE experiment = @name ORDER BY id
            """, args, cancellationToken: ct)))
            .Select(t => new HypothesisTest(t.Hypothesis, t.Family, t.Test, t.Variable, t.N, Json.Finite(t.Statistic),
                Json.Finite(t.Effect), Json.Finite(t.CiLow), Json.Finite(t.CiHigh), Json.Finite(t.PValue),
                Json.Finite(t.PAdjusted), Json.Parse(t.Details)!.Value))
            .ToList();

        var mainRuns = main.Select(r => new MainRun(r.Id, r.Algorithm, Json.Parse(r.Params)!.Value, r.RandomState,
            r.NTrain, r.FitSeconds, r.ScoreSeconds,
            metrics[r.Id].Select(m => new RunMetric(m.P, m.FlaggedCount, m.FlaggedShare, m.WeightedFlaggedShare)).ToList()))
            .ToList();
        var agreement = comparisons.Where(c => c.PurposeA == "main" && c.PurposeB == "main")
            .Select(c => new Agreement(c.AlgorithmA, c.AlgorithmB, c.P, Json.Finite(c.Jaccard), Json.Finite(c.Spearman))).ToList();
        var stability = comparisons.Where(c => c.PurposeA == "main" ^ c.PurposeB == "main")
            .Select(c => c.PurposeA == "main"
                ? new StabilityComparison(c.RunB, c.PurposeB, c.AlgorithmB, Json.Parse(c.ParamsB)!.Value, c.P,
                    Json.Finite(c.Jaccard), Json.Finite(c.Spearman))
                : new StabilityComparison(c.RunA, c.PurposeA, c.AlgorithmA, Json.Parse(c.ParamsA)!.Value, c.P,
                    Json.Finite(c.Jaccard), Json.Finite(c.Spearman)))
            .ToList();

        return new ExperimentDetail(name, main[0].Source, main[0].SampleId, mainRuns, agreement, stability, scalability, tests);
    }
}

public static class ExperimentEndpoints
{
    public static void MapExperiments(this IEndpointRouteBuilder app)
    {
        var group = app.MapGroup("/api/experiments").WithTags("Experimentos");

        group.MapGet("/", async (ExperimentRepository repository, CancellationToken ct) =>
            Results.Ok(await repository.ListAsync(ct)));

        group.MapGet("/{name}", async (string name, ExperimentRepository repository, CancellationToken ct) =>
            await repository.GetAsync(name, ct) is { } detail ? Results.Ok(detail) : Results.NotFound());

        group.MapGet("/{name}/records", async (string name, double? p, string? algorithm, int? page, int? pageSize,
            ExperimentRepository experiments, SourceRepository sources, FlaggedRecords records, CancellationToken ct) =>
        {
            if (p is { } value && value is <= 0 or > 0.10)
            {
                return Results.ValidationProblem(new Dictionary<string, string[]> { ["p"] = ["p deve estar entre 0 e 0,10."] });
            }

            if (algorithm is not null && !FlaggedRecords.Algorithms.Contains(algorithm))
            {
                return Results.ValidationProblem(new Dictionary<string, string[]> { ["algorithm"] = ["Algoritmo desconhecido."] });
            }

            var detail = await experiments.GetAsync(name, ct);
            if (detail is null)
            {
                return Results.NotFound();
            }

            var source = (await sources.GetAsync(detail.Source, ct))!;
            var parameters = new DynamicParameters(new { name });
            return Results.Ok(await records.QueryAsync(source,
                "experiment = @name AND mode = 'experiment' AND purpose = 'main'", parameters,
                p ?? 0.01, algorithm, page ?? 1, pageSize ?? 50, ct));
        });
    }
}
