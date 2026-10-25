using System.Buffers.Binary;
using System.Collections.Concurrent;
using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;
using System.Text.Json;
using Atlas.LocalAgent.Core;
using Atlas.LocalAgent.Service;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Atlas.LocalAgent.Tests;

[TestClass]
public sealed class FoundationTests
{
    private string _root = null!;
    [TestInitialize] public void Setup() => _root = Directory.CreateTempSubdirectory("atlas-agent-test-").FullName;
    [TestCleanup] public void Cleanup() => Directory.Delete(_root, recursive: true);
    private static PrinterDevice Printer(string name = "QA Printer") => new(PrinterDevice.IdFor(name), name, "Unknown", false, PrinterConnection.Unknown, null, new(null, null, null, []));
    private static AgentAuthorizationContext Context() => new(Guid.NewGuid(), Guid.NewGuid(), "qa-org", "qa-center", "print", new("credential-reference", DateTimeOffset.UtcNow.AddHours(1))) { TargetOnline = true };
    private static PrintJob Job() => new(PrintJobId.New(), Guid.NewGuid(), "qa-printer", "opaque-document-id", PrintDocumentFormat.Pdf, 1);

    [TestMethod] public async Task IdentityPersistsAcrossInstances()
    {
        var first = await new LocalIdentityStore(_root).LoadOrCreateAsync(); var second = await new LocalIdentityStore(_root).LoadOrCreateAsync();
        Assert.AreNotEqual(Guid.Empty, first.AgentId); Assert.AreEqual(first, second);
    }
    [TestMethod] public async Task ConcurrentIdentityCreationHasOneUuid()
    {
        var results = await Task.WhenAll(Enumerable.Range(0, 12).Select(_ => new LocalIdentityStore(_root).LoadOrCreateAsync()));
        Assert.AreEqual(1, results.Select(x => x.AgentId).Distinct().Count());
    }
    [TestMethod] public async Task CorruptIdentityIsNotSilentlyReplaced()
    {
        var path = Path.Combine(_root, "identity.json"); await File.WriteAllTextAsync(path, "corrupt-qa");
        await Assert.ThrowsExactlyAsync<JsonException>(() => new LocalIdentityStore(_root).LoadOrCreateAsync());
        Assert.AreEqual("corrupt-qa", await File.ReadAllTextAsync(path));
    }
    [TestMethod] public async Task StationRenameAndCodeDoNotChangeIdentity()
    {
        var store = new LocalIdentityStore(_root); var identity = await store.LoadOrCreateAsync(); var initial = await store.LoadConfigurationAsync(identity);
        Assert.IsTrue(initial.DisplayCode.StartsWith("ATLAS-", StringComparison.Ordinal));
        await store.SaveConfigurationAsync(initial with { StationName = "QA Station", DisplayCode = "QA-01", Association = new("qa-org", "qa-center", "qa-group") });
        var loaded = await store.LoadConfigurationAsync(identity); Assert.AreEqual("QA-01", loaded.DisplayCode); Assert.AreEqual("qa-group", loaded.Association.WorkgroupId);
        Assert.AreEqual(identity, await store.LoadOrCreateAsync());
    }
    [TestMethod] public void InvalidDisplayCodeAndNameAreRejected()
    {
        Assert.ThrowsExactly<ArgumentException>(() => new StationConfiguration("QA", "../secret", new()).Validate());
        Assert.ThrowsExactly<ArgumentException>(() => new StationConfiguration("\n", "QA-01", new()).Validate());
    }
    [TestMethod] public void PublicConfigurationRejectsSecretProperties()
    {
        var payload = Encoding.UTF8.GetBytes("{\"stationName\":\"QA\",\"displayCode\":\"QA-01\",\"association\":{},\"token\":\"synthetic-do-not-store\"}");
        Assert.ThrowsExactly<JsonException>(() => Wire.Deserialize<StationConfiguration>(payload));
        var serialized = Encoding.UTF8.GetString(Wire.Serialize(new StationConfiguration("QA", "QA-01", new())));
        Assert.IsFalse(serialized.Contains("token", StringComparison.OrdinalIgnoreCase));
    }
    [TestMethod] public void AgentStatesAreDistinctAndSerializable()
    {
        Assert.AreEqual(7, Enum.GetValues<AgentState>().Length);
        foreach (var state in Enum.GetValues<AgentState>()) Assert.AreEqual(state, Wire.Deserialize<AgentState>(Wire.Serialize(state)));
    }
    [TestMethod] public void SecretBufferRedactsAndZerosOnDispose()
    {
        var bytes = Encoding.UTF8.GetBytes("synthetic-secret"); var buffer = new SecretBuffer(bytes);
        Assert.AreEqual("[REDACTED]", buffer.ToString()); buffer.Dispose(); Assert.IsTrue(bytes.All(x => x == 0));
    }
    [TestMethod] public async Task WindowsDpapiRoundTripIsNotPlaintext()
    {
        var store = new WindowsSecretStore(_root); var bytes = Encoding.UTF8.GetBytes("SYNTHETIC-DPAPI-FIXTURE-NOT-A-CREDENTIAL");
        await store.StoreAsync("fixture", bytes); using var read = await store.ReadAsync("fixture"); Assert.IsNotNull(read);
        CollectionAssert.AreEqual(bytes, read.Bytes.ToArray());
        var disk = await File.ReadAllBytesAsync(Path.Combine(_root, "secrets", "secret.fixture.bin"));
        Assert.IsFalse(Encoding.UTF8.GetString(disk).Contains(Encoding.UTF8.GetString(bytes), StringComparison.Ordinal));
        Assert.IsNotNull(new WindowsSecretStore(_root)); await store.RemoveAsync("fixture"); Assert.IsNull(await store.ReadAsync("fixture"));
    }
    [TestMethod] public async Task SecureStoreRejectsTraversalAndOversizeSecrets()
    {
        var store = new WindowsSecretStore(_root);
        await Assert.ThrowsExactlyAsync<ArgumentException>(() => store.StoreAsync("../escape", new byte[2]));
        await Assert.ThrowsExactlyAsync<ArgumentException>(() => store.StoreAsync("large", new byte[16385]));
        Assert.IsFalse(File.Exists(Path.Combine(_root, "escape")));
    }
    [TestMethod] public void DeviceIdentityAndDeduplicationAreStable()
    {
        Assert.AreEqual(PrinterDevice.IdFor("QA Printer"), PrinterDevice.IdFor("qa printer"));
        var devices = DeviceCatalog.Unique([Printer(), Printer("qa printer"), Printer("Other")]); Assert.AreEqual(2, devices.Count);
    }
    [TestMethod] public async Task WindowsPrintersAreEnumeratedWithOnlyReportedCapabilities()
    {
        var devices = await new WindowsPrinterDiscovery().EnumerateAsync(CancellationToken.None);
        Assert.AreEqual(devices.Count, devices.Select(x => x.DeviceId).Distinct().Count());
        foreach (var printer in devices)
        {
            Assert.IsFalse(string.IsNullOrWhiteSpace(printer.Name)); Assert.IsFalse(string.IsNullOrWhiteSpace(printer.Status));
            Assert.IsTrue(printer.Capabilities.MaximumCopies is null or > 0);
            Assert.IsTrue(printer.Capabilities.PaperSizes.All(x => x.WidthTenthsMillimeter is null or > 0));
        }
    }
    [TestMethod] public void MissingDriverCapabilitiesRemainUnknown()
    {
        var device = Printer(); Assert.IsNull(device.Driver); Assert.IsNull(device.Capabilities.Color); Assert.AreEqual(0, device.Capabilities.PaperSizes.Count);
    }
    [TestMethod] public async Task TransportRejectsPlaintextAndEmbeddedCredentials()
    {
        await using var transport = new MockCloudTransport(); var credential = Context().Credential;
        foreach (var uri in new[] { "http://localhost", "ws://localhost", "https://user:password@localhost", "https://localhost?token=synthetic" })
            await Assert.ThrowsExactlyAsync<ArgumentException>(() => transport.ConnectAsync(new(new(uri), true, credential), CancellationToken.None));
        await transport.ConnectAsync(new(new("https://atlas.example.test"), false, credential), CancellationToken.None);
    }
    [TestMethod] public async Task LanDiscoveryNeverAuthorizesRoutesOrJobs()
    {
        var context = Context(); var discovery = new InMemoryLanDiscovery([new(context.TargetAgent, new("https://192.0.2.10"), DateTimeOffset.UtcNow)]);
        Assert.AreEqual(1, (await discovery.DiscoverAsync(CancellationToken.None)).Count);
        var selector = new AuthorizedRouteSelector(new DenyAllAuthorizationPolicy());
        await using var local = new MockLocalTransport(); await using var cloud = new MockCloudTransport();
        Assert.IsNull(await selector.SelectAsync(context, local, cloud, CancellationToken.None));
    }
    [TestMethod] public async Task AuthorizedRoutePrefersLocalAndFallsBackToCloud()
    {
        var selector = new AuthorizedRouteSelector(new FixtureAuthorization()); var context = Context();
        await using var local = new MockLocalTransport(); await using var cloud = new MockCloudTransport();
        await local.ConnectAsync(new(new("https://peer.example.test"), true, context.Credential with { Kind = AuthenticationKind.MutualTls }) { ExpectedPeerAgent = context.TargetAgent }, default);
        await cloud.ConnectAsync(new(new("https://atlas.example.test"), false, context.Credential), default);
        Assert.AreSame(local, await selector.SelectAsync(context, local, cloud, CancellationToken.None));
        await local.DisposeAsync(); Assert.AreSame(cloud, await selector.SelectAsync(context, local, cloud, CancellationToken.None));
        await cloud.DisposeAsync(); Assert.IsNull(await selector.SelectAsync(context, local, cloud, CancellationToken.None));
    }
    [TestMethod] public async Task ExpiredAndForeignScopeCannotSelectTransport()
    {
        var selector = new AuthorizedRouteSelector(new FixtureAuthorization()); var context = Context();
        await using var local = new MockLocalTransport(); await using var cloud = new MockCloudTransport();
        Assert.IsNull(await selector.SelectAsync(context with { OrganizationId = "foreign" }, local, cloud, CancellationToken.None));
        Assert.IsNull(await selector.SelectAsync(context with { Credential = context.Credential with { ExpiresAt = DateTimeOffset.UtcNow.AddMinutes(-1) } }, local, cloud, CancellationToken.None));
    }
    [TestMethod] public void PrintJobIdentityAndWireContractArePreserved()
    {
        var job = Job(); Assert.AreEqual(job, Wire.Deserialize<PrintJob>(Wire.Serialize(job))); Assert.AreEqual(PrintJobStatus.Queued, job.Status);
        Assert.ThrowsExactly<ArgumentException>(() => new PrintJobId(Guid.Empty));
        Assert.ThrowsExactly<ArgumentException>(() => (job with { Copies = 0 }).Validate());
        Assert.AreEqual(11, Enum.GetValues<PrintJobStatus>().Length);
        Assert.AreEqual(8, (int)PrintJobStatus.Submitted); // Preserve every pre-extension enum ordinal.
        Assert.AreEqual(9, (int)PrintJobStatus.Unknown);
        Assert.AreEqual(10, (int)PrintJobStatus.Expired);
    }
    [TestMethod] public void SameJobIdIsOneIntentAndDifferentPayloadConflicts()
    {
        var registry = new InMemoryPrintJobRegistry(); var job = Job();
        Assert.AreEqual(PrintJobRegistration.Registered, registry.Register(job));
        Assert.AreEqual(PrintJobRegistration.Duplicate, registry.Register(job with { Status = PrintJobStatus.Printed }));
        Assert.AreEqual(PrintJobRegistration.Conflict, registry.Register(job with { Copies = 2 }));
        Assert.AreEqual(PrintJobRegistration.Registered, registry.Register(job with { Id = PrintJobId.New() }));
    }
    [TestMethod] public async Task ConcurrentPrintJobRegistrationHasOneLogicalExecution()
    {
        var registry = new InMemoryPrintJobRegistry(); var job = Job();
        var result = await Task.WhenAll(Enumerable.Range(0, 30).Select(_ => Task.Run(() => registry.Register(job))));
        Assert.AreEqual(1, result.Count(x => x == PrintJobRegistration.Registered)); Assert.AreEqual(29, result.Count(x => x == PrintJobRegistration.Duplicate));
    }
    [TestMethod] public async Task StartupHeartbeatAndShutdownPreserveIdentityAndUnpairedState()
    {
        using var writer = new StringWriter(); var cloud = new MockCloudTransport();
        var runtime = Runtime(new FixturePrinters(), cloud, writer); await runtime.StartAsync(CancellationToken.None);
        var id = runtime.Snapshot.Identity.AgentId; Assert.IsTrue(runtime.Snapshot.Running); Assert.AreEqual(AgentState.Unpaired, runtime.Snapshot.State);
        Assert.AreEqual(1, runtime.Snapshot.Printers.Count); Assert.AreEqual(id, cloud.LastHeartbeat?.AgentId);
        Assert.AreEqual(AgentVersion.Protocol, cloud.LastHeartbeat?.ProtocolVersion); Assert.AreEqual(1, cloud.LastHeartbeat?.Devices.Printers);
        await runtime.ConfigureAsync("QA Station", "qa-01", CancellationToken.None); await runtime.RefreshAsync(CancellationToken.None);
        Assert.AreEqual("QA Station", cloud.LastHeartbeat?.Station); Assert.AreEqual(id, runtime.Snapshot.Identity.AgentId);
        await runtime.StopAsync(); await runtime.StopAsync(); Assert.IsFalse(runtime.Snapshot.Running);
        Assert.AreEqual(AgentState.Disconnected, runtime.Snapshot.State); Assert.IsFalse(cloud.IsAvailable);
        Assert.AreEqual(1, writer.ToString().Split('\n').Count(x => x.Contains("Shutdown", StringComparison.Ordinal)));
    }
    [TestMethod] public async Task EnumerationErrorIsDegradedAndDoesNotLeakExceptionOrPrinterName()
    {
        using var writer = new StringWriter(); var runtime = Runtime(new FixturePrinters(fail: true), new MockCloudTransport(), writer);
        await runtime.StartAsync(CancellationToken.None); Assert.AreEqual(AgentState.Degraded, runtime.Snapshot.State);
        Assert.AreEqual(AgentErrorCode.PrinterUnavailable, runtime.Snapshot.LastError); await runtime.StopAsync();
        Assert.IsFalse(writer.ToString().Contains("SYNTHETIC-SENSITIVE", StringComparison.Ordinal));
        Assert.IsFalse(writer.ToString().Contains("QA Printer", StringComparison.Ordinal));
        Assert.IsTrue(writer.ToString().Contains("PrinterUnavailable", StringComparison.Ordinal));
    }
    [TestMethod] public async Task CancellingHeartbeatLoopStopsCleanly()
    {
        using var writer = new StringWriter(); var runtime = Runtime(new FixturePrinters(), new MockCloudTransport(), writer);
        await runtime.StartAsync(CancellationToken.None); using var cancellation = new CancellationTokenSource(50);
        try { await runtime.RunHeartbeatLoopAsync(TimeSpan.FromMilliseconds(10), cancellation.Token); }
        catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { }
        await runtime.StopAsync(); Assert.IsFalse(runtime.Snapshot.Running);
    }
    [TestMethod] public async Task IpcRejectsUnknownCommandsAndIdentityForgery()
    {
        using var writer = new StringWriter(); var runtime = Runtime(new FixturePrinters(), new MockCloudTransport(), writer); await runtime.StartAsync(CancellationToken.None);
        var server = new LocalPipeServer(_root, runtime, new JsonAgentLog(writer));
        var response = await server.DispatchAsync(new((LocalCommand)99), CancellationToken.None); Assert.AreEqual(AgentErrorCode.InvalidRequest, response.Error);
        Assert.ThrowsExactly<JsonException>(() => Wire.Deserialize<LocalRequest>(Encoding.UTF8.GetBytes("{\"command\":\"Configure\",\"agentId\":\"forged\"}")));
        Assert.IsTrue(runtime.Snapshot.Running); Assert.AreEqual(AgentState.Unpaired, runtime.Snapshot.State); await runtime.StopAsync();
    }
    [TestMethod] public async Task LocalPipeSnapshotAndConfigurationWorkWithoutStoppingService()
    {
        using var writer = new StringWriter(); var runtime = Runtime(new FixturePrinters(), new MockCloudTransport(), writer); await runtime.StartAsync(CancellationToken.None);
        var server = new LocalPipeServer(_root, runtime, new JsonAgentLog(writer)); using var cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(8));
        var serving = server.RunAsync(cancellation.Token);
        try
        {
            var client = new LocalAgentClient(_root); var before = await client.SendAsync(new(LocalCommand.Snapshot), cancellation.Token);
            var changed = await client.SendAsync(new(LocalCommand.Configure, "QA IPC", "QA-IPC"), cancellation.Token);
            Assert.AreEqual(before.Snapshot?.Identity.AgentId, changed.Snapshot?.Identity.AgentId); Assert.AreEqual("QA IPC", changed.Snapshot?.Configuration.StationName);
            var invalid = await client.SendAsync(new(LocalCommand.Configure, "", "!"), cancellation.Token); Assert.AreEqual(AgentErrorCode.InvalidConfiguration, invalid.Error);
            Assert.IsTrue(runtime.Snapshot.Running);
        }
        finally { cancellation.Cancel(); try { await serving; } catch (OperationCanceledException) { } await runtime.StopAsync(); }
    }
    [TestMethod] public async Task WireRejectsOversizeFramesBeforeReadingPayload()
    {
        var header = new byte[4]; BinaryPrimitives.WriteInt32LittleEndian(header, Wire.MaxFrameBytes + 1);
        using var stream = new MemoryStream(header);
        await Assert.ThrowsExactlyAsync<InvalidDataException>(() => Wire.ReadAsync<LocalRequest>(stream, CancellationToken.None));
    }

    [TestMethod] public async Task LocalPipeRestrictsAclToUserAndSurvivesMalformedClient()
    {
        using var writer = new StringWriter(); var runtime = Runtime(new FixturePrinters(), new MockCloudTransport(), writer);
        await runtime.StartAsync(CancellationToken.None);
        var server = new LocalPipeServer(_root, runtime, new JsonAgentLog(writer));
        using var cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(8)); var serving = server.RunAsync(cancellation.Token);
        try
        {
            await using (var pipe = new NamedPipeClientStream(".", AgentPaths.PipeName(_root), PipeDirection.InOut, PipeOptions.Asynchronous))
            {
                await pipe.ConnectAsync(cancellation.Token);
                using var identity = WindowsIdentity.GetCurrent(); var security = pipe.GetAccessControl();
                Assert.AreEqual(identity.User, security.GetOwner(typeof(SecurityIdentifier)));
                var rules = security.GetAccessRules(true, true, typeof(SecurityIdentifier)); Assert.HasCount(1, rules);
                var rule = rules[0]; Assert.IsNotNull(rule); Assert.AreEqual(identity.User, rule.IdentityReference);
                var header = new byte[4]; BinaryPrimitives.WriteInt32LittleEndian(header, Wire.MaxFrameBytes + 1);
                await pipe.WriteAsync(header, cancellation.Token); await pipe.FlushAsync(cancellation.Token);
                Assert.AreEqual(0, await pipe.ReadAsync(new byte[1], cancellation.Token));
            }
            for (var i = 0; i < 20; i++)
                Assert.IsTrue((await new LocalAgentClient(_root).SendAsync(new(LocalCommand.Snapshot), cancellation.Token)).Snapshot?.Running);
            Assert.IsTrue(writer.ToString().Contains("InvalidRequest", StringComparison.Ordinal));
        }
        finally { cancellation.Cancel(); try { await serving; } catch (OperationCanceledException) { } await runtime.StopAsync(); }
    }

    private AgentRuntime Runtime(IPrinterDiscovery discovery, MockCloudTransport cloud, StringWriter log) => new(new(_root), discovery, cloud, new InMemoryLanDiscovery(), new JsonAgentLog(log));
    private sealed class FixturePrinters(bool fail = false) : IPrinterDiscovery
    {
        public Task<IReadOnlyList<PrinterDevice>> EnumerateAsync(CancellationToken cancellationToken)
        {
            if (fail) throw new IOException("SYNTHETIC-SENSITIVE: do not log driver messages");
            return Task.FromResult<IReadOnlyList<PrinterDevice>>([Printer(), Printer()]);
        }
    }
    private sealed class FixtureAuthorization : IAgentAuthorizationPolicy
    {
        public Task<AuthorizationDecision> AuthorizeAsync(AgentAuthorizationContext context, CancellationToken cancellationToken) => Task.FromResult(new AuthorizationDecision(context.OrganizationId == "qa-org" && context.CenterId == "qa-center", "fixture-only"));
    }
}
