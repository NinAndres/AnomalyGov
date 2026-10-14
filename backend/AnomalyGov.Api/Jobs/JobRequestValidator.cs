using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;
using AnomalyGov.Api.Sources;

namespace AnomalyGov.Api.Jobs;

/// <summary>Validates the `filters` and `params` of a job against the source definition (docs/contratos.md).</summary>
public static partial class JobRequestValidator
{
    public const double DefaultP = 0.01;
    public const double MaxP = 0.10;
    public const int MaxSelectedOptions = 500;

    [GeneratedRegex(@"^\d{4}-(0[1-9]|1[0-2])$")]
    private static partial Regex MonthPattern();

    public static Dictionary<string, string[]> ValidateFilters(SourceDefinition source, JsonElement? filters)
    {
        var errors = new Dictionary<string, string[]>();
        if (filters is not { } value || value.ValueKind == JsonValueKind.Null)
        {
            return errors;
        }

        if (value.ValueKind != JsonValueKind.Object)
        {
            errors["filters"] = ["Os filtros devem ser um objeto."];
            return errors;
        }

        foreach (var property in value.EnumerateObject())
        {
            var key = $"filters.{property.Name}";
            var definition = source.Filters.FirstOrDefault(f => f.Name == property.Name);
            var problem = definition is null
                ? "Filtro desconhecido para esta base."
                : definition.Type switch
                {
                    SourceDefinition.MonthRange => ValidateMonthRange(definition, property.Value),
                    SourceDefinition.Select => ValidateSelect(definition, property.Value),
                    SourceDefinition.NumberRange => ValidateNumberRange(property.Value),
                    _ => $"Tipo de filtro não suportado: {definition.Type}.",
                };
            if (problem is not null)
            {
                errors[key] = [problem];
            }
        }

        return errors;
    }

    /// <summary>Returns the normalized params ({"p": ...}) or the validation errors.</summary>
    public static (Dictionary<string, object> Params, Dictionary<string, string[]> Errors) ValidateParams(JsonElement? parameters)
    {
        var errors = new Dictionary<string, string[]>();
        var normalized = new Dictionary<string, object> { ["p"] = DefaultP };
        if (parameters is not { } value || value.ValueKind == JsonValueKind.Null)
        {
            return (normalized, errors);
        }

        if (value.ValueKind != JsonValueKind.Object)
        {
            errors["params"] = ["Os parâmetros devem ser um objeto."];
            return (normalized, errors);
        }

        foreach (var property in value.EnumerateObject())
        {
            if (property.Name != "p")
            {
                errors[$"params.{property.Name}"] = ["Parâmetro desconhecido."];
            }
            else if (property.Value.ValueKind != JsonValueKind.Number || property.Value.GetDouble() is <= 0 or > MaxP)
            {
                errors["params.p"] = [string.Create(CultureInfo.InvariantCulture,
                    $"p deve ser um número maior que 0 e no máximo {MaxP}.")];
            }
            else
            {
                normalized["p"] = property.Value.GetDouble();
            }
        }

        return (normalized, errors);
    }

    private static string? ValidateMonthRange(FilterDefinition definition, JsonElement value)
    {
        if (value.ValueKind != JsonValueKind.Object)
        {
            return "Use um objeto com \"from\" e/ou \"to\" no formato AAAA-MM.";
        }

        string? from = null, to = null;
        foreach (var bound in value.EnumerateObject())
        {
            if (bound.Name is not ("from" or "to"))
            {
                return $"Campo desconhecido: {bound.Name}.";
            }

            if (bound.Value.ValueKind != JsonValueKind.String || !MonthPattern().IsMatch(bound.Value.GetString()!))
            {
                return $"\"{bound.Name}\" deve estar no formato AAAA-MM.";
            }

            if (bound.Name == "from") from = bound.Value.GetString(); else to = bound.Value.GetString();
        }

        if (from is null && to is null)
        {
            return "Informe \"from\" e/ou \"to\".";
        }

        if (from is not null && to is not null && string.CompareOrdinal(from, to) > 0)
        {
            return "\"from\" deve ser anterior ou igual a \"to\".";
        }

        // An open bound extends to the edge of the available data.
        var min = definition.Min?.GetString();
        var max = definition.Max?.GetString();
        var start = from ?? min;
        var end = to ?? max;
        var endsBeforeData = min is not null && end is not null && string.CompareOrdinal(end, min) < 0;
        var startsAfterData = max is not null && start is not null && string.CompareOrdinal(start, max) > 0;
        if (endsBeforeData || startsAfterData)
        {
            return $"O intervalo não tem dados: os meses disponíveis vão de {min} a {max}.";
        }

        return null;
    }

    private static string? ValidateSelect(FilterDefinition definition, JsonElement value)
    {
        if (value.ValueKind != JsonValueKind.Array || value.GetArrayLength() == 0)
        {
            return "Use uma lista não vazia de valores.";
        }

        if (value.GetArrayLength() > MaxSelectedOptions)
        {
            return $"Selecione no máximo {MaxSelectedOptions} valores.";
        }

        var allowed = definition.Options?.Select(o => o.Value).ToHashSet();
        foreach (var item in value.EnumerateArray())
        {
            if (item.ValueKind != JsonValueKind.String)
            {
                return "Os valores devem ser textos.";
            }

            if (allowed is not null && !allowed.Contains(item.GetString()!))
            {
                return $"Valor não disponível: {item.GetString()}.";
            }
        }

        return null;
    }

    private static string? ValidateNumberRange(JsonElement value)
    {
        if (value.ValueKind != JsonValueKind.Object)
        {
            return "Use um objeto com \"min\" e/ou \"max\".";
        }

        double? min = null, max = null;
        foreach (var bound in value.EnumerateObject())
        {
            if (bound.Name is not ("min" or "max"))
            {
                return $"Campo desconhecido: {bound.Name}.";
            }

            if (bound.Value.ValueKind != JsonValueKind.Number)
            {
                return $"\"{bound.Name}\" deve ser um número.";
            }

            if (bound.Name == "min") min = bound.Value.GetDouble(); else max = bound.Value.GetDouble();
        }

        if (min is null && max is null)
        {
            return "Informe \"min\" e/ou \"max\".";
        }

        return min > max ? "\"min\" deve ser menor ou igual a \"max\"." : null;
    }
}
