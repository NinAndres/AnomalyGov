using Npgsql;

namespace AnomalyGov.Api.Data;

/// <summary>Converts a libpq URL (postgresql://user:pass@host:port/db?sslmode=...) into an Npgsql connection string.</summary>
public static class PostgresUrl
{
    public static string ToConnectionString(string url)
    {
        var uri = new Uri(url);
        if (uri.Scheme is not ("postgresql" or "postgres"))
        {
            throw new ArgumentException("A URL deve começar com postgresql:// ou postgres://", nameof(url));
        }

        var userInfo = uri.UserInfo.Split(':', 2);
        var builder = new NpgsqlConnectionStringBuilder
        {
            Host = uri.Host,
            Port = uri.IsDefaultPort || uri.Port <= 0 ? 5432 : uri.Port,
            Database = Uri.UnescapeDataString(uri.AbsolutePath.TrimStart('/')),
            Username = Uri.UnescapeDataString(userInfo[0]),
            Password = userInfo.Length > 1 ? Uri.UnescapeDataString(userInfo[1]) : null,
        };

        foreach (var pair in uri.Query.TrimStart('?').Split('&', StringSplitOptions.RemoveEmptyEntries))
        {
            var parts = pair.Split('=', 2);
            if (parts.Length == 2 && parts[0] == "sslmode")
            {
                builder.SslMode = Enum.Parse<SslMode>(parts[1].Replace("-", ""), ignoreCase: true);
            }
        }

        return builder.ConnectionString;
    }

    /// <summary>ConnectionStrings:Default (Npgsql format) or, if absent, the SUPABASE_DATABASE_URL variable.</summary>
    public static string Resolve(IConfiguration configuration)
    {
        var configured = configuration.GetConnectionString("Default");
        if (!string.IsNullOrWhiteSpace(configured))
        {
            return configured;
        }

        var url = configuration["SUPABASE_DATABASE_URL"];
        if (string.IsNullOrWhiteSpace(url))
        {
            throw new InvalidOperationException(
                "Defina ConnectionStrings:Default ou a variável SUPABASE_DATABASE_URL (ver .env.example).");
        }

        return ToConnectionString(url);
    }
}
