using AnomalyGov.Api.Data;
using Npgsql;

namespace AnomalyGov.Api.Tests;

public class PostgresUrlTests
{
    [Fact]
    public void DecodesPercentEncodedPasswordAndReadsSslMode()
    {
        var cs = new NpgsqlConnectionStringBuilder(PostgresUrl.ToConnectionString(
            "postgresql://postgres:a%25b%2Fc@db.example.co:6543/postgres?sslmode=require"));

        Assert.Equal("db.example.co", cs.Host);
        Assert.Equal(6543, cs.Port);
        Assert.Equal("postgres", cs.Database);
        Assert.Equal("postgres", cs.Username);
        Assert.Equal("a%b/c", cs.Password);
        Assert.Equal(SslMode.Require, cs.SslMode);
    }

    [Fact]
    public void DefaultsToPort5432()
    {
        var cs = new NpgsqlConnectionStringBuilder(PostgresUrl.ToConnectionString("postgres://u:p@localhost/db"));
        Assert.Equal(5432, cs.Port);
    }

    [Fact]
    public void RejectsOtherSchemes()
    {
        Assert.Throws<ArgumentException>(() => PostgresUrl.ToConnectionString("mysql://u:p@localhost/db"));
    }
}
