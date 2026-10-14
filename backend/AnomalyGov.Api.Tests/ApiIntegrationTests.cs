using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using AnomalyGov.Api.Data;
using Dapper;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Npgsql;

namespace AnomalyGov.Api.Tests;

/// <summary>Runs only when ANOMALYGOV_TEST_DATABASE_URL points to a database with the migrations and a published experiment.</summary>
public sealed class DatabaseFactAttribute : FactAttribute
{
    public DatabaseFactAttribute()
    {
        if (string.IsNullOrWhiteSpace(ApiFactory.TestDatabaseUrl))
        {
            Skip = "ANOMALYGOV_TEST_DATABASE_URL não definida";
        }
    }
}

public sealed class ApiFactory : WebApplicationFactory<Program>
{
    public static string? TestDatabaseUrl => Environment.GetEnvironmentVariable("ANOMALYGOV_TEST_DATABASE_URL");

    public static string ConnectionString => PostgresUrl.ToConnectionString(TestDatabaseUrl!);

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseSetting("ConnectionStrings:Default", ConnectionString);
        builder.UseSetting("RateLimiting:JobsPerMinute", "1000");
    }
}

public class ApiIntegrationTests : IClassFixture<ApiFactory>
{
    private readonly HttpClient _client;

    public ApiIntegrationTests(ApiFactory factory)
    {
        _client = factory.CreateClient();
    }

    private static async Task<NpgsqlConnection> OpenAsync()
    {
        var conn = new NpgsqlConnection(ApiFactory.ConnectionString);
        await conn.OpenAsync();
        return conn;
    }

    private async Task<string> ExperimentNameAsync()
    {
        var experiments = await _client.GetFromJsonAsync<JsonElement>("/api/experiments");
        Assert.True(experiments.GetArrayLength() > 0, "nenhum experimento publicado no banco de teste");
        return experiments[0].GetProperty("name").GetString()!;
    }

    [DatabaseFact]
    public async Task HealthChecksTheDatabase()
    {
        var response = await _client.GetAsync("/api/health");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [DatabaseFact]
    public async Task ListsSourcesWithTheirFilters()
    {
        var source = await _client.GetFromJsonAsync<JsonElement>("/api/sources/payments");
        var filters = source.GetProperty("filters").EnumerateArray().ToList();
        Assert.Equal(6, filters.Count);
        var types = filters.Single(f => f.GetProperty("name").GetString() == "favored_type");
        Assert.Equal(5, types.GetProperty("options").GetArrayLength());
        Assert.Equal(HttpStatusCode.NotFound, (await _client.GetAsync("/api/sources/unknown")).StatusCode);
    }

    [DatabaseFact]
    public async Task RejectsInvalidJobs()
    {
        var response = await _client.PostAsJsonAsync("/api/jobs",
            new { source = "payments", filters = new { unknown = 1 }, @params = new { p = 0.5 } });
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        var problem = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("Requisição inválida.", problem.GetProperty("title").GetString());
        var errors = problem.GetProperty("errors");
        Assert.True(errors.TryGetProperty("filters.unknown", out _));
        Assert.True(errors.TryGetProperty("params.p", out _));

        response = await _client.PostAsJsonAsync("/api/jobs", new { source = "nope" });
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    [DatabaseFact]
    public async Task CreatesAPendingJob()
    {
        var response = await _client.PostAsJsonAsync("/api/jobs",
            new { source = "payments", filters = new { uf = new[] { "SP" } } });
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var job = await response.Content.ReadFromJsonAsync<JsonElement>();
        var id = job.GetProperty("id").GetGuid();
        try
        {
            Assert.Equal($"/api/jobs/{id}", response.Headers.Location!.OriginalString);
            Assert.Equal("pending", job.GetProperty("status").GetString());
            Assert.Equal(0.01, job.GetProperty("params").GetProperty("p").GetDouble());

            var fetched = await _client.GetFromJsonAsync<JsonElement>($"/api/jobs/{id}");
            Assert.Equal("SP", fetched.GetProperty("filters").GetProperty("uf")[0].GetString());
            Assert.Equal(HttpStatusCode.Conflict, (await _client.GetAsync($"/api/jobs/{id}/records")).StatusCode);
            Assert.Equal(HttpStatusCode.NotFound, (await _client.GetAsync($"/api/jobs/{Guid.NewGuid()}")).StatusCode);
        }
        finally
        {
            await using var conn = await OpenAsync();
            await conn.ExecuteAsync("DELETE FROM jobs WHERE id = @id", new { id });
        }
    }

    [DatabaseFact]
    public async Task ReturnsTheExperimentSummary()
    {
        var name = await ExperimentNameAsync();
        var detail = await _client.GetFromJsonAsync<JsonElement>($"/api/experiments/{name}");

        var mainRuns = detail.GetProperty("mainRuns").EnumerateArray().ToList();
        Assert.Equal(3, mainRuns.Count);
        Assert.All(mainRuns, r => Assert.Equal(3, r.GetProperty("metrics").GetArrayLength()));
        Assert.Equal(9, detail.GetProperty("agreement").GetArrayLength());
        Assert.Equal(HttpStatusCode.NotFound, (await _client.GetAsync("/api/experiments/unknown")).StatusCode);
    }

    [DatabaseFact]
    public async Task FlaggedRecordsMatchTheMetricsComputedInPython()
    {
        var name = await ExperimentNameAsync();
        await using var conn = await OpenAsync();
        var expected = (await conn.QueryAsync<(string Algorithm, int Count)>("""
            SELECT r.algorithm, m.flagged_count FROM run_metrics m JOIN runs r ON r.id = m.run_id
            WHERE r.experiment = @name AND r.purpose = 'main' AND m.p = 0.01
            """, new { name })).ToList();
        Assert.Equal(3, expected.Count);

        foreach (var (algorithm, count) in expected)
        {
            var page = await _client.GetFromJsonAsync<JsonElement>(
                $"/api/experiments/{name}/records?p=0.01&algorithm={algorithm}&pageSize=200");
            Assert.Equal(count, page.GetProperty("total").GetInt64());
            foreach (var item in page.GetProperty("items").EnumerateArray())
            {
                Assert.True(item.GetProperty("flags").GetProperty(algorithm).GetBoolean());
                var values = item.GetProperty("values");
                if (values.GetProperty("favored_type").GetString() == "individual")
                {
                    Assert.Equal(JsonValueKind.Null, values.GetProperty("favored_name").ValueKind);
                }
            }
        }

        var beyond = await _client.GetFromJsonAsync<JsonElement>($"/api/experiments/{name}/records?page=100000");
        Assert.Equal(0, beyond.GetProperty("items").GetArrayLength());
        Assert.True(beyond.GetProperty("total").GetInt64() > 0);
    }

    [DatabaseFact]
    public async Task ServesTheRecordsOfASucceededJob()
    {
        var name = await ExperimentNameAsync();
        await using var conn = await OpenAsync();
        // Stand-in for the worker: a succeeded job whose runs are copies of the experiment's main runs.
        var jobId = await conn.ExecuteScalarAsync<Guid>("""
            INSERT INTO jobs (source, status, params, result, started_at, finished_at)
            VALUES ('payments', 'succeeded', '{"p": 0.01}', '{}', now(), now()) RETURNING id
            """);
        try
        {
            await conn.ExecuteAsync("""
                WITH copied AS (
                    INSERT INTO runs (experiment, config_sha256, mode, purpose, algorithm, params, random_state,
                                      feature_columns, train_sample_id, scored_sample_id, n_train, n_scored,
                                      fit_seconds, score_seconds, environment, job_id)
                    SELECT 'job-test', config_sha256, 'exploration', 'main', algorithm, params, random_state,
                           feature_columns, train_sample_id, scored_sample_id, n_train, n_scored, fit_seconds,
                           score_seconds, environment, @jobId
                    FROM runs WHERE experiment = @name AND purpose = 'main'
                    RETURNING id, algorithm)
                INSERT INTO run_scores (run_id, payment_id, raw_score, normalized_score)
                SELECT c.id, s.payment_id, s.raw_score, s.normalized_score
                FROM copied c JOIN runs r ON r.experiment = @name AND r.purpose = 'main' AND r.algorithm = c.algorithm
                JOIN run_scores s ON s.run_id = r.id
                """, new { jobId, name });

            var fromJob = await _client.GetFromJsonAsync<JsonElement>($"/api/jobs/{jobId}/records?pageSize=10");
            var fromExperiment = await _client.GetFromJsonAsync<JsonElement>($"/api/experiments/{name}/records?pageSize=10");
            Assert.Equal(fromExperiment.GetProperty("total").GetInt64(), fromJob.GetProperty("total").GetInt64());
            Assert.Equal(10, fromJob.GetProperty("items").GetArrayLength());
        }
        finally
        {
            await conn.ExecuteAsync("DELETE FROM jobs WHERE id = @jobId", new { jobId });
        }
    }
}
