using Microsoft.AspNetCore.Diagnostics;
using Npgsql;

namespace AnomalyGov.Api.Data;

/// <summary>Answers 503 when the database cannot be reached (network, timeout), instead of a generic 500.</summary>
/// <remarks>SQL errors (<see cref="PostgresException"/>) are bugs and keep the default 500 handling.</remarks>
public sealed class DatabaseUnavailableHandler(IProblemDetailsService problemDetails, ILogger<DatabaseUnavailableHandler> logger)
    : IExceptionHandler
{
    public async ValueTask<bool> TryHandleAsync(HttpContext context, Exception exception, CancellationToken ct)
    {
        if (exception is PostgresException || exception is not (NpgsqlException or TimeoutException))
        {
            return false;
        }

        logger.LogWarning(exception, "Banco de dados indisponível");
        context.Response.StatusCode = StatusCodes.Status503ServiceUnavailable;
        context.Response.Headers.RetryAfter = "5";
        return await problemDetails.TryWriteAsync(new ProblemDetailsContext
        {
            HttpContext = context,
            Exception = exception,
            ProblemDetails = { Status = StatusCodes.Status503ServiceUnavailable },
        });
    }
}
