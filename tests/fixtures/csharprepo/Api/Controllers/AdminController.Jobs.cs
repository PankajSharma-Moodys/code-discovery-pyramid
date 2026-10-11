using Microsoft.AspNetCore.Mvc;

namespace Acme.Api.Controllers;

public partial class AdminController
{
    [HttpGet("jobs/{jobId}")]
    public IActionResult GetJob(string jobId)
    {
        return Ok(Pair<string>(jobId));
    }

    [HttpPost("/internal/rebuild")]
    public async Task<IActionResult> Rebuild() => Ok();

    private (int Count, string Name) Pair<T>(T value)
    {
        return (1, value.ToString());
    }

    internal static int Weight() => 1;

    protected virtual void OnRebuilt()
    {
    }
}
