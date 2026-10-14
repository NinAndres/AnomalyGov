using System.Text.Json;

namespace AnomalyGov.Api.Data;

public static class Json
{
    /// <summary>Parses a jsonb column read as text; null stays null.</summary>
    public static JsonElement? Parse(string? text) =>
        text is null ? null : JsonDocument.Parse(text).RootElement.Clone();

    public static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web);

    /// <summary>JSON has no NaN or infinity: such values are returned as null.</summary>
    public static double? Finite(double? value) => value is { } v && double.IsFinite(v) ? v : null;
}
