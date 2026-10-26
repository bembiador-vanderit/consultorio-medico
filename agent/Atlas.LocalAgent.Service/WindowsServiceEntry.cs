using System.ServiceProcess;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Atlas.LocalAgent.Core;

namespace Atlas.LocalAgent.Service;

public static class WindowsServiceEntry
{
    public static async Task<int> RunAsync(string mode, string path)
    {
        try
        {
            var configuration = ServiceConfiguration.Load(path);
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(90));
            if (mode == "--service-copy-state") { ServiceStateMigration.Copy(configuration); Console.WriteLine("ProtectedStateCopyVerified"); }
            else if (mode == "--service-handoff") { await ServiceCredentialHandoff.SendAsync(configuration, timeout.Token); Console.WriteLine("MemoryOnlyHandoffVerified"); }
            else if (mode == "--service-inspect-state")
            {
                ServiceCredentialHandoff.RequireSid(configuration.SourceUserSid);
                configuration.VerifyIdentity(configuration.SourceRoot); configuration.VerifyIdentity(configuration.DataPath);
                var databases = Directory.EnumerateFiles(configuration.DataPath, "*.sqlite", SearchOption.AllDirectories).Select(p => new {
                    RelativePath = Path.GetRelativePath(configuration.DataPath, p), DestinationLogicalSha256 = ServiceStateMigration.LogicalFingerprint(p),
                    SourceLogicalSha256 = ServiceStateMigration.LogicalFingerprint(Path.Combine(configuration.SourceRoot, Path.GetRelativePath(configuration.DataPath, p)))
                }).ToArray();
                Console.WriteLine(JsonSerializer.Serialize(new { configuration.AgentUuid, Databases = databases, PhysicalPrintsSent = 0 }));
            }
            else if (mode == "--service-inspect-credential-binding")
            {
                ServiceCredentialHandoff.RequireSid(configuration.SourceUserSid);
                using var secret = await new WindowsSecretStore(configuration.SourceRoot).ReadAsync("atlas-registry-v1", timeout.Token) ?? throw new InvalidDataException();
                using var json = JsonDocument.Parse(secret.Bytes); var c = json.RootElement;
                Console.WriteLine(JsonSerializer.Serialize(new { AgentUuid = c.GetProperty("agent_uuid").GetGuid(), Endpoint = c.GetProperty("endpoint").GetString(),
                    DevelopmentHttpOptIn = c.GetProperty("allow_loopback_http").GetBoolean(), ExpiresAt = c.GetProperty("expires_at").GetDateTimeOffset(),
                    OrganizationId = c.GetProperty("organization_id").GetInt32(), CenterId = c.GetProperty("center_id").GetInt32(), WorkgroupId = c.GetProperty("workgroup_id").GetInt32() }));
            }
            else ServiceBase.Run(new AtlasWindowsService(configuration) { ServiceName = ServiceConfiguration.Name, AutoLog = false, CanShutdown = true });
            return 0;
        }
        catch (Exception ex) { Console.Error.WriteLine("ServiceOperationDenied:" + ex.GetType().Name); return 1; }
    }
}

internal sealed class AtlasWindowsService(ServiceConfiguration configuration) : ServiceBase
{
    private readonly CancellationTokenSource _stop = new();
    private Task? _work;
    protected override void OnStart(string[] args) => _work = Task.Run(RunAsync);
    protected override void OnShutdown() => OnStop();
    protected override void OnStop()
    {
        _stop.Cancel();
        if (_work is { IsCompleted: false }) _work.GetAwaiter().GetResult();
    }
    private async Task RunAsync()
    {
        var stage = "ServiceIdentity";
        try
        {
            ServiceCredentialHandoff.RequireSid(configuration.ServiceSid);
            using var principal = System.Security.Principal.WindowsIdentity.GetCurrent();
            if (new System.Security.Principal.WindowsPrincipal(principal).IsInRole(System.Security.Principal.WindowsBuiltInRole.Administrator))
                throw new UnauthorizedAccessException("ServiceMustNotBeAdministrator");
            using var lease = StationInstanceLease.Acquire(configuration.AgentUuid, configuration.ServiceSid, configuration.DataPath, configuration.SourceRoot);
            if (configuration.Phase == "Synthetic")
            {
                stage = "SyntheticProfile";
                var bytes = Encoding.UTF8.GetBytes("ATLAS-SERVICE-PROFILE-SYNTHETIC:" + configuration.AgentUuid);
                var store = new WindowsSecretStore(configuration.BasePath);
                try
                {
                    await store.StoreAsync("service-profile-check", bytes, _stop.Token);
                    using var check = await store.ReadAsync("service-profile-check", _stop.Token) ?? throw new InvalidDataException();
                    if (!CryptographicOperations.FixedTimeEquals(bytes, check.Bytes.Span)) throw new InvalidDataException("SyntheticDpapiMismatch");
                }
                finally { CryptographicOperations.ZeroMemory(bytes); }
                var printers = await new WindowsPrinterDiscovery().EnumerateAsync(_stop.Token);
                ValidatePrinters(printers);
                using var http = AtlasRegistryClient.CreateHttpClient();
                using var health = await http.GetAsync(new Uri(new Uri(configuration.Endpoint), "api/v1/health"), _stop.Token);
                if (!health.IsSuccessStatusCode) throw new HttpRequestException();
                WriteStatus(new { Phase = "Synthetic", Completed = true, DpapiProfileValidated = true, Identity = configuration.ServiceSid,
                    PrinterCount = printers.Count, HttpsStatus = (int)health.StatusCode, PhysicalPrintsSent = 0 });
            }
            else if (configuration.Phase == "Handoff")
            {
                stage = "MemoryOnlyHandoff";
                using var timeout = CancellationTokenSource.CreateLinkedTokenSource(_stop.Token); timeout.CancelAfter(TimeSpan.FromSeconds(90));
                await ServiceCredentialHandoff.ReceiveAsync(configuration, timeout.Token);
                await ServiceCredentialHandoff.VerifyAsync(configuration, timeout.Token);
                WriteStatus(new { Phase = "Handoff", Completed = true, RealDpapiReadback = true, configuration.AgentUuid, PhysicalPrintsSent = 0 });
            }
            else
            {
                stage = "RuntimeValidation";
                configuration.VerifyIdentity(configuration.DataPath);
                await ServiceCredentialHandoff.VerifyAsync(configuration, _stop.Token);
                ValidatePrinters(await new WindowsPrinterDiscovery().EnumerateAsync(_stop.Token));
                using var writer = new StreamWriter(Path.Combine(configuration.LogsPath, $"service-{DateTime.UtcNow:yyyyMMdd}.jsonl"), true) { AutoFlush = true };
                var log = new JsonAgentLog(writer);
                using var http = AtlasRegistryClient.CreateHttpClient();
                var registry = new AtlasRegistryClient(http, new WindowsSecretStore(configuration.BasePath));
                var runtime = new AgentRuntime(new(configuration.DataPath), new WindowsPrinterDiscovery(), new MockCloudTransport(), new InMemoryLanDiscovery(), log, registry: registry);
                try
                {
                    stage = "RuntimeStart";
                    await runtime.StartAsync(_stop.Token);
                    if (runtime.Snapshot.State != AgentState.Connected) throw new InvalidOperationException("InitialRegistryConnectionRequired");
                    // No native print coordinator, no physical grant, no mutable IPC control channel in service V1.
                    var consumer = new OfficialPrintConsumer(configuration.DataPath, runtime, registry);
                    if (configuration.ReplayJobId is { } replay) await consumer.ReplayAsync(replay, _stop.Token);
                    WriteStatus(new { Phase = "Run", Completed = true, Running = true, configuration.AgentUuid, State = runtime.Snapshot.State.ToString(),
                        PrinterCount = runtime.Snapshot.Printers.Count, SafeValidation = true, PhysicalGlobal = false, AllowedJobId = (Guid?)null, PhysicalPrintsSent = 0,
                        WindowsSid = principal.User!.Value, SessionId = System.Diagnostics.Process.GetCurrentProcess().SessionId,
                        Profile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), DpapiCredentialValidated = true,
                        SecretsAcl = System.IO.FileSystemAclExtensions.GetAccessControl(new DirectoryInfo(Path.Combine(configuration.BasePath, "secrets"))).GetSecurityDescriptorSddlForm(System.Security.AccessControl.AccessControlSections.All),
                        ProtectedBlobSha256 = Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(Path.Combine(configuration.BasePath, "secrets", "secret.atlas-registry-v1.bin")))) });
                    stage = "HeartbeatAndSafeConsumer";
                    var heartbeat = runtime.RunHeartbeatLoopAsync(TimeSpan.FromSeconds(30), _stop.Token);
                    var consume = consumer.RunAsync(_stop.Token);
                    await Task.WhenAny(heartbeat, consume); _stop.Cancel(); await Task.WhenAll(heartbeat, consume);
                }
                finally { await runtime.StopAsync(); }
            }
            if (configuration.Phase != "Run")
            {
                // One-shot bootstrap remains SCM-running until explicitly stopped by the orchestrator.
                await Task.Delay(Timeout.InfiniteTimeSpan, _stop.Token);
            }
        }
        catch (OperationCanceledException) when (_stop.IsCancellationRequested) { }
        catch (Exception ex)
        {
            WriteStatus(new { Phase = configuration.Phase, Completed = false, Stage = stage, ErrorCode = ex.GetType().Name, PhysicalPrintsSent = 0 });
            // Fatal host failure must reach SCM recovery; do not leave a dead worker labelled Running.
            Environment.Exit(1);
        }
    }
    private void ValidatePrinters(IReadOnlyList<PrinterDevice> printers)
    {
        var actual = printers.Select(p => p.RegistryId ?? p.DeviceId).Order(StringComparer.Ordinal).ToArray();
        if (!actual.SequenceEqual(configuration.PrinterIds.Order(StringComparer.Ordinal))) throw new InvalidDataException("PrinterCatalogMismatch");
    }
    private void WriteStatus(object status)
    {
        var path = Path.Combine(configuration.LogsPath, "service-status.json");
        var temporary = path + ".tmp"; File.WriteAllText(temporary, JsonSerializer.Serialize(status)); File.Move(temporary, path, true);
    }
    protected override void Dispose(bool disposing) { if (disposing) _stop.Dispose(); base.Dispose(disposing); }
}
