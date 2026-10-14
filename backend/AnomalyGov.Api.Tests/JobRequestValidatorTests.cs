using System.Text.Json;
using AnomalyGov.Api.Jobs;
using AnomalyGov.Api.Sources;

namespace AnomalyGov.Api.Tests;

public class JobRequestValidatorTests
{
    private static readonly SourceDefinition Source = new("payments", "Pagamentos",
    [
        new FilterDefinition("reference_month", SourceDefinition.MonthRange, "Mês", null,
            JsonSerializer.SerializeToElement("2025-01"), JsonSerializer.SerializeToElement("2025-12")),
        new FilterDefinition("uf", SourceDefinition.Select, "UF", [new FilterOption("SP", "SP"), new FilterOption("RJ", "RJ")],
            null, null),
        new FilterDefinition("amount", SourceDefinition.NumberRange, "Valor", null, null, null),
    ], ["reference_month", "amount"]);

    private static Dictionary<string, string[]> Filters(string json) =>
        JobRequestValidator.ValidateFilters(Source, JsonDocument.Parse(json).RootElement);

    [Fact]
    public void AcceptsMissingOrEmptyFilters()
    {
        Assert.Empty(JobRequestValidator.ValidateFilters(Source, null));
        Assert.Empty(Filters("{}"));
    }

    [Fact]
    public void AcceptsValidFilters()
    {
        Assert.Empty(Filters("""
            {"reference_month": {"from": "2025-03", "to": "2025-06"}, "uf": ["SP"], "amount": {"min": 100}}
            """));
    }

    [Theory]
    [InlineData("""{"unknown": 1}""", "filters.unknown")]
    [InlineData("""{"reference_month": {"from": "2025-13"}}""", "filters.reference_month")]
    [InlineData("""{"reference_month": {"from": "2025-06", "to": "2025-03"}}""", "filters.reference_month")]
    [InlineData("""{"reference_month": {"to": "2024-12"}}""", "filters.reference_month")]
    [InlineData("""{"reference_month": {"from": "2026-01"}}""", "filters.reference_month")]
    [InlineData("""{"reference_month": {}}""", "filters.reference_month")]
    [InlineData("""{"uf": []}""", "filters.uf")]
    [InlineData("""{"uf": ["XX"]}""", "filters.uf")]
    [InlineData("""{"uf": [1]}""", "filters.uf")]
    [InlineData("""{"amount": {"min": 10, "max": 5}}""", "filters.amount")]
    [InlineData("""{"amount": {"min": "10"}}""", "filters.amount")]
    [InlineData("""[]""", "filters")]
    public void RejectsInvalidFilters(string json, string expectedKey)
    {
        Assert.Contains(expectedKey, Filters(json).Keys);
    }

    [Fact]
    public void ParamsDefaultToOnePercent()
    {
        var (parameters, errors) = JobRequestValidator.ValidateParams(null);
        Assert.Empty(errors);
        Assert.Equal(0.01, parameters["p"]);
    }

    [Theory]
    [InlineData("""{"p": 0.05}""", null)]
    [InlineData("""{"p": 0}""", "params.p")]
    [InlineData("""{"p": 0.5}""", "params.p")]
    [InlineData("""{"p": "0.01"}""", "params.p")]
    [InlineData("""{"seed": 1}""", "params.seed")]
    public void ValidatesParams(string json, string? expectedKey)
    {
        var (parameters, errors) = JobRequestValidator.ValidateParams(JsonDocument.Parse(json).RootElement);
        if (expectedKey is null)
        {
            Assert.Empty(errors);
            Assert.Equal(0.05, parameters["p"]);
        }
        else
        {
            Assert.Contains(expectedKey, errors.Keys);
        }
    }
}
