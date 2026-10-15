using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;

namespace AnomalyGov.Api.Tests;

/// <summary>API pointed at a port where nothing listens: every database call fails to connect.</summary>
public sealed class UnreachableDatabaseFactory : WebApplicationFactory<Program>
{
    protected override void ConfigureWebHost(IWebHostBuilder builder) =>
        builder.UseSetting("ConnectionStrings:Default", "Host=127.0.0.1;Port=1;Username=x;Password=x;Database=x;Timeout=2");
}

public class DatabaseUnavailableTests(UnreachableDatabaseFactory factory) : IClassFixture<UnreachableDatabaseFactory>
{
    [Theory]
    [InlineData("/api/health")]
    [InlineData("/api/experiments")]
    [InlineData("/api/sources")]
    public async Task AnswersServiceUnavailableInPortuguese(string path)
    {
        var response = await factory.CreateClient().GetAsync(path);

        Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);
        Assert.True(response.Headers.Contains("Retry-After"));
        var problem = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("Banco de dados indisponível no momento. Tente novamente em instantes.",
            problem.GetProperty("title").GetString());
    }
}
