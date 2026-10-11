using Microsoft.AspNetCore.Mvc;

namespace Acme.Api.Controllers;

[ApiController]
[Route("v1/{tenantId}/[controller]")]
public partial class AdminController(
    IWidgetStore store,
    IWidgetCache cache,
    IClock clock,
    ILogger<AdminController> logger,
    IOptions<WidgetSettings> options,
    IMetrics metrics,
    IFeatureFlags flags,
    IAuditLog audit,
    INotifier notifier,
    IScheduler scheduler,
    IRetryPolicy retry,
    IHttpClientFactory http,
    IEncryptor encryptor,
    IIdGenerator ids,
    ITenantResolver tenants,
    IUserContext users) : ControllerBase
{
    private readonly IWidgetStore _store = store;

    [HttpGet]
    public IActionResult List() => Ok(_store.All());

    private bool IsAllowed(string user) => user.Length > 0;
}
