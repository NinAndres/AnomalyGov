using System.Threading.RateLimiting;
using AnomalyGov.Api.Data;
using AnomalyGov.Api.Experiments;
using AnomalyGov.Api.Jobs;
using AnomalyGov.Api.Records;
using AnomalyGov.Api.Sources;
using Dapper;
using Npgsql;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddSingleton(_ =>
{
    // Opening a connection is the step that fails on an unstable network: keep one open and alive.
    var connection = new NpgsqlConnectionStringBuilder(PostgresUrl.Resolve(builder.Configuration));
    if (connection.KeepAlive == 0) connection.KeepAlive = 30;
    if (connection.MinPoolSize == 0) connection.MinPoolSize = 1;
    return NpgsqlDataSource.Create(connection.ConnectionString);
});
builder.Services.AddSingleton<SourceRepository>();
builder.Services.AddSingleton<JobRepository>();
builder.Services.AddSingleton<ExperimentRepository>();
builder.Services.AddSingleton<FlaggedRecords>();
builder.Services.AddExceptionHandler<DatabaseUnavailableHandler>();
// Interface texts are in Portuguese (AGENTS.md, section 11), including error titles.
builder.Services.AddProblemDetails(options => options.CustomizeProblemDetails = context =>
    context.ProblemDetails.Title = context.ProblemDetails.Status switch
    {
        StatusCodes.Status400BadRequest => "Requisição inválida.",
        StatusCodes.Status404NotFound => "Recurso não encontrado.",
        StatusCodes.Status409Conflict => "Conflito com o estado atual do recurso.",
        StatusCodes.Status429TooManyRequests => "Muitas requisições. Tente novamente em instantes.",
        StatusCodes.Status500InternalServerError => "Erro interno.",
        StatusCodes.Status503ServiceUnavailable => "Banco de dados indisponível no momento. Tente novamente em instantes.",
        _ => context.ProblemDetails.Title,
    });

var origins = builder.Configuration.GetSection("Cors:AllowedOrigins").Get<string[]>() ?? [];
builder.Services.AddCors(options => options.AddDefaultPolicy(policy =>
    policy.WithOrigins(origins).AllowAnyHeader().WithMethods("GET", "POST")));

// Without authentication, job creation is throttled per client IP: each job costs worker time.
var jobsPerMinute = builder.Configuration.GetValue("RateLimiting:JobsPerMinute", 10);
builder.Services.AddRateLimiter(options =>
{
    options.RejectionStatusCode = StatusCodes.Status429TooManyRequests;
    options.AddPolicy(JobEndpoints.RateLimitPolicy, context => RateLimitPartition.GetFixedWindowLimiter(
        context.Connection.RemoteIpAddress?.ToString() ?? "unknown",
        _ => new FixedWindowRateLimiterOptions { PermitLimit = jobsPerMinute, Window = TimeSpan.FromMinutes(1) }));
});

var app = builder.Build();

app.UseExceptionHandler();
app.UseStatusCodePages();
app.UseCors();
app.UseRateLimiter();

app.MapGet("/api/health", async (NpgsqlDataSource dataSource, CancellationToken ct) =>
{
    await using var conn = await dataSource.OpenConnectionAsync(ct);
    await conn.ExecuteScalarAsync<int>(new CommandDefinition("SELECT 1", cancellationToken: ct));
    return Results.Ok(new { status = "ok" });
}).WithTags("Saúde");
app.MapSources();
app.MapJobs();
app.MapExperiments();

app.Run();

public partial class Program;
