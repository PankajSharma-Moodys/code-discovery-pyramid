using static Acme.Api.App.Keys;

namespace Acme.Api.App;

public class Startup
{
    private readonly IConfiguration _configuration;

    public Startup(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    public string Url() => _configuration[WidgetUrl];

    public int Retries() => _configuration.GetSection("Global").GetValue<int>("Retries");

    public string Env() => Environment.GetEnvironmentVariable("WIDGET_REGION");

    public string Db() => _configuration.GetConnectionString("Main");
}
