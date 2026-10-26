using System.Net;
using System.Text;
using System.Text.Json;
using Atlas.LocalAgent.Core;
using Atlas.LocalAgent.Service;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Atlas.LocalAgent.Tests;

[TestClass]
public sealed class RegistryTests
{
    private string _root = null!;
    private AgentSnapshot _snapshot = null!;
    [TestInitialize] public async Task Setup()
    {
        _root = Directory.CreateTempSubdirectory("atlas-pairing-test-").FullName;
        var identity = await new LocalIdentityStore(_root).LoadOrCreateAsync();
        var config = await new LocalIdentityStore(_root).LoadConfigurationAsync(identity);
        var printer = new PrinterDevice(PrinterDevice.IdFor("QA Printer"), "QA Printer", "Ready", false,
            PrinterConnection.Local, "QA Driver", new(false, false, 1, []));
        _snapshot = new(true, identity, config, AgentState.Unpaired,
            new(identity.AgentId, config.StationName, AgentVersion.Current, AgentVersion.Protocol, "QA", AgentState.Unpaired,
                DateTimeOffset.UtcNow, new(1, 0)), [printer], AgentErrorCode.None);
    }
    [TestCleanup] public void Cleanup() => Directory.Delete(_root, true);
    private static PairingInput Input() => new("https://atlas.example.test/", "AAAA-AAAA-AAAA-AAAA-AAAA-AAAA-AA");
    private sealed class Handler(Guid id) : HttpMessageHandler
    {
        public readonly List<string> Paths = [];
        public readonly List<Uri> Urls = [];
        public readonly List<string> Bodies = [];
        public bool Offline, Reject;
        public string CurrentToken = "ala_" + new string('s', 43);
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Urls.Add(request.RequestUri!);
            if (Offline) throw new HttpRequestException("SYNTHETIC-RAW-ERROR-MUST-NOT-ESCAPE");
            var path = request.RequestUri!.AbsolutePath; Paths.Add(path);
            Bodies.Add(request.Content is null ? "" : await request.Content.ReadAsStringAsync(cancellationToken));
            if (Reject) return new(HttpStatusCode.Unauthorized);
            var json = path.EndsWith("/pair", StringComparison.Ordinal) || path.EndsWith("/rotate", StringComparison.Ordinal)
                ? JsonSerializer.Serialize(new { credential = CurrentToken, expires_at = DateTimeOffset.UtcNow.AddDays(90),
                    agent_uuid = id, organization_id = 1, center_id = 2, workgroup_id = 3 })
                : path.EndsWith("/heartbeat", StringComparison.Ordinal) ? "{\"organization_id\":1,\"center_id\":2,\"workgroup_id\":3}" : "{}";
            return new(HttpStatusCode.OK) { Content = new StringContent(json, Encoding.UTF8, "application/json") };
        }
    }
    [TestMethod] public async Task UnpairedStartupDoesNotContactAtlas()
    {
        using var handler = new Handler(_snapshot.Identity.AgentId); using var http = new HttpClient(handler);
        var client = new AtlasRegistryClient(http, new WindowsSecretStore(_root));
        Assert.AreEqual(AgentState.Unpaired, (await client.SynchronizeAsync(_snapshot, default)).State);
        Assert.AreEqual(0, handler.Paths.Count);
    }
    [TestMethod] public void TlsLoopbackExceptionIsExplicitAndNotForLan()
    {
        Assert.ThrowsExactly<ArgumentException>(() => new PairingInput("http://atlas.example.test", "", true).ValidateEndpoint());
        Assert.ThrowsExactly<ArgumentException>(() => new PairingInput("http://localhost:8001", "").ValidateEndpoint());
        Assert.ThrowsExactly<ArgumentException>(() => new PairingInput("https://user:password@example.test", "").ValidateEndpoint());
        Assert.ThrowsExactly<ArgumentException>(() => new PairingInput("https://example.test/?token=secret", "").ValidateEndpoint());
        Assert.ThrowsExactly<ArgumentException>(() => new PairingInput("http://127.0.0.1:18067", "", true).ValidateEndpoint());
        Assert.AreEqual("http", new PairingInput("http://127.0.0.1:18067", "", true).ValidateEndpoint(CommunicationEnvironment.Development).Scheme);
        Assert.AreEqual("127.0.0.1", new PairingInput("http://localhost:18067", "", true).ValidateEndpoint(CommunicationEnvironment.Development).Host);
    }
    [TestMethod] public async Task PairPersistsDpapiNotPlaintextAndHeartbeatSyncs()
    {
        using var handler = new Handler(_snapshot.Identity.AgentId); using var http = new HttpClient(handler);
        var client = new AtlasRegistryClient(http, new WindowsSecretStore(_root));
        var paired = await client.PairAsync(Input(), _snapshot, default);
        Assert.AreEqual(AgentState.Connected, paired.State); Assert.AreEqual("2", paired.Association.CenterId);
        var bytes = await File.ReadAllBytesAsync(Path.Combine(_root, "secrets", "secret.atlas-registry-v1.bin"));
        Assert.IsFalse(Encoding.UTF8.GetString(bytes).Contains(handler.CurrentToken, StringComparison.Ordinal));
        Assert.IsFalse(paired.ToString().Contains(handler.CurrentToken, StringComparison.Ordinal));
        var fresh = new AtlasRegistryClient(http, new WindowsSecretStore(_root));
        Assert.AreEqual(AgentState.Connected, (await fresh.SynchronizeAsync(_snapshot, default)).State);
        CollectionAssert.AreEqual(new[] { "/api/v1/local-agents/pair", "/api/v1/local-agents/device/heartbeat", "/api/v1/local-agents/device/printers" }, handler.Paths);
        var pair = JsonDocument.Parse(handler.Bodies[0]);
        Assert.IsFalse(pair.RootElement.TryGetProperty("organization_id", out _));
        Assert.IsFalse(pair.RootElement.TryGetProperty("username", out _));
        StringAssert.Contains(handler.Bodies[2], "local_id");
        StringAssert.Contains(handler.Bodies[1], "device_summary");
    }
    [TestMethod] public async Task UnavailableThenReconnectDoesNotLoseCredential()
    {
        using var handler = new Handler(_snapshot.Identity.AgentId); using var http = new HttpClient(handler);
        var client = new AtlasRegistryClient(http, new WindowsSecretStore(_root));
        await client.PairAsync(Input(), _snapshot, default); handler.Offline = true;
        var status = await client.SynchronizeAsync(_snapshot, default);
        Assert.AreEqual(AgentState.Disconnected, status.State);
        Assert.IsFalse(status.ToString().Contains("SYNTHETIC-RAW-ERROR", StringComparison.Ordinal));
        handler.Offline = false;
        Assert.AreEqual(AgentState.Connected, (await client.SynchronizeAsync(_snapshot, default)).State);
    }
    [TestMethod] public async Task ProductionRejectsLegacyHttpAssociationWithoutLosingPairing()
    {
        using var handler = new Handler(_snapshot.Identity.AgentId); using var http = new HttpClient(handler);
        var store = new WindowsSecretStore(_root);
        var development = new AtlasRegistryClient(http, store, CommunicationEnvironment.Development);
        Assert.AreEqual(AgentState.Connected, (await development.PairAsync(
            new("http://127.0.0.1:18067/", Input().Code, true), _snapshot, default)).State);
        var path = Path.Combine(_root,"secrets","secret.atlas-registry-v1.bin");
        var before = await File.ReadAllBytesAsync(path); var requests = handler.Paths.Count;
        var production = new AtlasRegistryClient(http,store);
        Assert.AreEqual("TransportPolicyDenied", (await production.SynchronizeAsync(_snapshot,default)).Code);
        Assert.AreEqual("TransportPolicyDenied", (await production.RotateAsync(default)).Code);
        Assert.AreEqual(requests,handler.Paths.Count);
        CollectionAssert.AreEqual(before,await File.ReadAllBytesAsync(path));
    }
    [TestMethod] public async Task HttpsUnavailableNeverFallsBackToHttpOrChangesDpapi()
    {
        using var handler = new Handler(_snapshot.Identity.AgentId);
        using var http = new HttpClient(handler);
        var store = new WindowsSecretStore(_root);
        var client = new AtlasRegistryClient(http, store, CommunicationEnvironment.Production);
        Assert.AreEqual(AgentState.Connected, (await client.PairAsync(Input(), _snapshot, default)).State);
        var path = Path.Combine(_root, "secrets", "secret.atlas-registry-v1.bin");
        var protectedBefore = await File.ReadAllBytesAsync(path);
        var identityBefore = await File.ReadAllBytesAsync(Path.Combine(_root, "identity.json"));
        handler.Urls.Clear(); handler.Offline = true;
        Assert.AreEqual(AgentState.Disconnected, (await client.SynchronizeAsync(_snapshot, default)).State);
        Assert.AreEqual(1, handler.Urls.Count);
        Assert.IsTrue(handler.Urls.All(uri => uri.Scheme == "https" && uri.Host == "atlas.example.test"));
        CollectionAssert.AreEqual(protectedBefore, await File.ReadAllBytesAsync(path));
        CollectionAssert.AreEqual(identityBefore, await File.ReadAllBytesAsync(Path.Combine(_root, "identity.json")));
        handler.Offline = false;
        var restarted = new AtlasRegistryClient(http, store, CommunicationEnvironment.Production);
        Assert.AreEqual(AgentState.Connected, (await restarted.SynchronizeAsync(_snapshot, default)).State);
        Assert.AreEqual(3, handler.Urls.Count); // One failed heartbeat, then heartbeat + inventory.
        Assert.IsTrue(handler.Urls.All(uri => uri.Scheme == "https" && uri.Host == "atlas.example.test"));
        Assert.AreEqual(1, handler.Paths.Count(path => path.EndsWith("/pair", StringComparison.Ordinal)));
        CollectionAssert.AreEqual(protectedBefore, await File.ReadAllBytesAsync(path));
    }
    [TestMethod] public async Task RevokedCredentialStopsHeartbeatAndNoAutomaticPair()
    {
        using var handler = new Handler(_snapshot.Identity.AgentId); using var http = new HttpClient(handler);
        var client = new AtlasRegistryClient(http, new WindowsSecretStore(_root));
        await client.PairAsync(Input(), _snapshot, default); handler.Reject = true;
        Assert.AreEqual(AgentState.Revoked, (await client.SynchronizeAsync(_snapshot, default)).State);
        var count = handler.Paths.Count;
        Assert.AreEqual(AgentState.Revoked, (await client.SynchronizeAsync(_snapshot, default)).State);
        Assert.AreEqual(count, handler.Paths.Count);
        Assert.AreEqual("AlreadyPaired", (await client.PairAsync(Input(), _snapshot, default)).Code);
    }
    [TestMethod] public async Task RotationUsesExistingIdentityAndSecureStorage()
    {
        using var handler = new Handler(_snapshot.Identity.AgentId); using var http = new HttpClient(handler);
        var client = new AtlasRegistryClient(http, new WindowsSecretStore(_root));
        await client.PairAsync(Input(), _snapshot, default); handler.CurrentToken = "ala_" + new string('r',43);
        Assert.AreEqual("CredentialRotated", (await client.RotateAsync(default)).Code);
        Assert.AreEqual(AgentState.Connected, (await new AtlasRegistryClient(http, new WindowsSecretStore(_root)).SynchronizeAsync(_snapshot, default)).State);
    }
    [TestMethod] public async Task CorruptProtectedCredentialFailsClosedWithoutNetworking()
    {
        Directory.CreateDirectory(Path.Combine(_root, "secrets"));
        await File.WriteAllBytesAsync(Path.Combine(_root, "secrets", "secret.atlas-registry-v1.bin"), [1, 2, 3, 4]);
        using var handler = new Handler(_snapshot.Identity.AgentId); using var http = new HttpClient(handler);
        var status = await new AtlasRegistryClient(http, new WindowsSecretStore(_root)).SynchronizeAsync(_snapshot, default);
        Assert.AreEqual("RegistryUnavailable", status.Code);
        Assert.AreEqual(0, handler.Paths.Count);
    }
    [TestMethod] public async Task ForeignIdentityReplyIsNotStoredOrTrusted()
    {
        using var handler = new Handler(Guid.NewGuid()); using var http = new HttpClient(handler);
        var store = new WindowsSecretStore(_root);
        var client = new AtlasRegistryClient(http, store);
        Assert.AreEqual("PairingUncertainCheckRegistry", (await client.PairAsync(Input(), _snapshot, default)).Code);
        using var credential = await store.ReadAsync("atlas-registry-v1");
        Assert.IsNull(credential);
    }
    [TestMethod] public void PrinterRegistryIdentitySurvivesRenameButNotPortReplacement()
    {
        var id = PrinterDevice.RegistryIdFor("Old", "USB001", "QA Driver", null, false);
        Assert.AreEqual(id, PrinterDevice.RegistryIdFor("New", "USB001", "QA Driver", null, false));
        Assert.AreNotEqual(id, PrinterDevice.RegistryIdFor("Old", "USB002", "QA Driver", null, false));
    }
    [TestMethod] public void PairingRequestAndSecretsHaveRedactedStringRepresentation()
    {
        Assert.IsFalse(Input().ToString().Contains(Input().Code, StringComparison.Ordinal));
        Assert.IsFalse(new LocalRequest(LocalCommand.PairWithAtlas, Pairing: Input()).ToString().Contains(Input().Code, StringComparison.Ordinal));
        Assert.AreEqual(64, InstallationFingerprint.For(_snapshot.Identity).Length);
        Assert.AreEqual(InstallationFingerprint.For(_snapshot.Identity), InstallationFingerprint.For(_snapshot.Identity));
    }

    [TestMethod] public async Task RealHttpTemporaryRegistryOnlyWhenOptedIn()
    {
        var endpoint = Environment.GetEnvironmentVariable("ATLAS_REGISTRY_QA_ENDPOINT");
        var code = Environment.GetEnvironmentVariable("ATLAS_REGISTRY_QA_CODE");
        if (string.IsNullOrEmpty(endpoint) || string.IsNullOrEmpty(code))
        { Assert.Inconclusive("Real HTTP requires disposable registry fixture."); return; }
        Assert.AreEqual("http://127.0.0.1:18067/", endpoint);  // Never official Atlas port.
        using var http = AtlasRegistryClient.CreateHttpClient(CommunicationEnvironment.Development);
        var client = new AtlasRegistryClient(http, new WindowsSecretStore(_root), CommunicationEnvironment.Development);
        Assert.AreEqual(AgentState.Connected, (await client.PairAsync(new(endpoint,code,true), _snapshot, default)).State);
        Assert.AreEqual(AgentState.Connected, (await client.SynchronizeAsync(_snapshot, default)).State);
        Assert.AreEqual("CredentialRotated", (await client.RotateAsync(default)).Code);
        Assert.AreEqual(AgentState.Connected, (await client.SynchronizeAsync(_snapshot, default)).State);
    }
}
