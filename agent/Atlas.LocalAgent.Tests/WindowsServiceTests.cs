using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.Json;
using Atlas.LocalAgent.Core;
using Atlas.LocalAgent.Service;
using Microsoft.Data.Sqlite;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Atlas.LocalAgent.Tests;

[TestClass]
public sealed class WindowsServiceTests
{
    private static ServiceConfiguration Config(string root) => new(root, root + "-source", Guid.NewGuid(),
        "S-1-5-21-1-2-3-1001", "S-1-5-80-1-2-3-4-5", "https://example.com/", "Run", new('a', 64), new('b', 64), ["printer-qa"]);
    private static string Fresh() => Path.Combine(Path.GetTempPath(), "atlas-service-tests-" + Guid.NewGuid().ToString("N"));
    [TestMethod]
    public void ServiceRejectsPhysicalFlagsWrongIdentityAndUnsafeEndpoint()
    {
        var c = Config(Fresh()); c.Validate();
        foreach (var bad in new[] { c with { SafeValidation = false }, c with { PhysicalGlobal = true }, c with { AllowedJobId = Guid.NewGuid() },
            c with { AgentUuid = Guid.Empty }, c with { SourceUserSid = c.ServiceSid }, c with { Phase = "PhysicalQa" },
            c with { Endpoint = "http://127.0.0.1/" }, c with { PrinterIds = [] }, c with { PrinterIds = ["p", "p"] } })
            Assert.Throws<Exception>(() => bad.Validate());
    }
    [TestMethod]
    public void ServiceRejectsRelativeUncTraversalAndOverlappingRoots()
    {
        var c = Config(Fresh());
        foreach (var bad in new[] { c with { BasePath = "relative" }, c with { SourceRoot = @"\\server\share" },
            c with { SourceRoot = c.BasePath + @"\..\outside" }, c with { SourceRoot = c.DataPath } })
            Assert.ThrowsExactly<InvalidDataException>(() => bad.Validate());
    }
    [TestMethod]
    public void ServiceCannotLoadConfigFromCallerSelectedDataDirectory()
    {
        Assert.ThrowsExactly<InvalidDataException>(() => ServiceConfiguration.Load(Path.Combine(Fresh(), "service.json")));
    }
    [TestMethod]
    public void CrossSessionLeaseRejectsSecondOwnerAndReleasesAfterDispose()
    {
        var root = Fresh(); Directory.CreateDirectory(root);
        var id = Guid.NewGuid(); var sid = WindowsIdentity.GetCurrent().User!.Value;
        using (var first = StationInstanceLease.Acquire(id, sid, root))
        {
            Assert.ThrowsExactly<IOException>(() => StationInstanceLease.Acquire(id, sid, root));
            Assert.ThrowsExactly<IOException>(() => new FileStream(Path.Combine(root, "service.lock"), FileMode.Open, FileAccess.ReadWrite, FileShare.None));
        }
        using (StationInstanceLease.Acquire(id, sid, root)) { }
        Directory.Delete(root, true);
    }
    [TestMethod]
    public void LegacyRootLockIsHeldAlongsideCanonicalRoot()
    {
        var root = Fresh(); var source = Path.Combine(root, "source"); var target = Path.Combine(root, "target");
        Directory.CreateDirectory(source); Directory.CreateDirectory(target);
        using (StationInstanceLease.Acquire(Guid.NewGuid(), WindowsIdentity.GetCurrent().User!.Value, source, target))
            foreach (var path in new[] { source, target })
                Assert.ThrowsExactly<IOException>(() => new FileStream(Path.Combine(path, "service.lock"), FileMode.Open, FileAccess.ReadWrite, FileShare.None));
        Directory.Delete(root, true);
    }
    private static byte[] Credential(ServiceConfiguration c, Guid? uuid = null, string? endpoint = null, bool http = false) =>
        JsonSerializer.SerializeToUtf8Bytes(new { agent_uuid = uuid ?? c.AgentUuid, endpoint = endpoint ?? c.Endpoint,
            allow_loopback_http = http, expires_at = DateTimeOffset.UtcNow.AddHours(1), organization_id = 1, center_id = 1, workgroup_id = 1,
            token = "ala_SYNTHETIC_ONLY_NOT_A_REAL_CREDENTIAL_123456789" });
    [TestMethod]
    public void HandoffCredentialIsBoundToUuidHttpsEndpointAndScope()
    {
        var c = Config(Fresh()); ServiceCredentialHandoff.ValidateCredential(Credential(c), c);
        foreach (var bytes in new[] { Credential(c, Guid.NewGuid()), Credential(c, endpoint: "https://other.example.com/"), Credential(c, http: true) })
            Assert.ThrowsExactly<InvalidDataException>(() => ServiceCredentialHandoff.ValidateCredential(bytes, c));
        Assert.AreEqual("[SERVICE BINDING; NO CREDENTIALS]", c.ToString());
        Assert.IsFalse(JsonSerializer.Serialize(c).Contains("ala_", StringComparison.Ordinal));
    }
    [TestMethod]
    public void ProductionCopyDropsLegacyHttpOptInWithoutChangingIdentityOrToken()
    {
        var c = Config(Fresh()); var original = Credential(c, http: true);
        var production = ServiceCredentialHandoff.PrepareProductionCopy(original, c);
        try
        {
            using var a = JsonDocument.Parse(original); using var b = JsonDocument.Parse(production);
            Assert.IsTrue(a.RootElement.GetProperty("allow_loopback_http").GetBoolean());
            Assert.IsFalse(b.RootElement.GetProperty("allow_loopback_http").GetBoolean());
            foreach (var field in new[] { "token", "agent_uuid", "endpoint", "expires_at", "organization_id", "center_id", "workgroup_id" })
                Assert.IsTrue(JsonElement.DeepEquals(a.RootElement.GetProperty(field), b.RootElement.GetProperty(field)), field);
            Assert.ThrowsExactly<InvalidDataException>(() => ServiceCredentialHandoff.PrepareProductionCopy(Credential(c, endpoint: "http://127.0.0.1/", http: true), c));
        }
        finally { CryptographicOperations.ZeroMemory(original); CryptographicOperations.ZeroMemory(production); }
    }
    [TestMethod]
    public async Task CurrentUserDpapiRoundtripUsesSyntheticOnly()
    {
        var root = Fresh(); var bytes = Encoding.UTF8.GetBytes("ATLAS-SERVICE-TEST-SYNTHETIC-ONLY");
        try
        {
            await new WindowsSecretStore(root).StoreAsync("synthetic", bytes);
            using var check = await new WindowsSecretStore(root).ReadAsync("synthetic");
            Assert.IsNotNull(check); Assert.IsTrue(CryptographicOperations.FixedTimeEquals(bytes, check.Bytes.Span));
            Assert.IsTrue(File.ReadAllBytes(Path.Combine(root, "secrets", "secret.synthetic.bin")).AsSpan().IndexOf(bytes) < 0);
        }
        finally { CryptographicOperations.ZeroMemory(bytes); if (Directory.Exists(root)) Directory.Delete(root, true); }
    }
    [TestMethod]
    public void SqliteLogicalHashSurvivesOnlineBackupAndDetectsMutation()
    {
        var root = Fresh(); Directory.CreateDirectory(root); var a = Path.Combine(root, "a.sqlite"); var b = Path.Combine(root, "b.sqlite");
        using (var source = new SqliteConnection($"Data Source={a};Pooling=False"))
        using (var target = new SqliteConnection($"Data Source={b};Pooling=False"))
        {
            source.Open(); target.Open(); using var q = source.CreateCommand(); q.CommandText = "PRAGMA journal_mode=WAL; CREATE TABLE jobs(id TEXT PRIMARY KEY,state TEXT); INSERT INTO jobs VALUES('synthetic','unknown')"; q.ExecuteNonQuery();
            source.BackupDatabase(target);
            Assert.AreEqual(ServiceStateMigration.LogicalFingerprint(a), ServiceStateMigration.LogicalFingerprint(b));
            q.CommandText = "UPDATE jobs SET state='printed'"; q.ExecuteNonQuery();
            Assert.AreNotEqual(ServiceStateMigration.LogicalFingerprint(a), ServiceStateMigration.LogicalFingerprint(b));
        }
        Directory.Delete(root, true);
    }
    [TestMethod]
    public void MissingIdentityDoesNotCreateAnotherUuid()
    {
        var c = Config(Fresh());
        Assert.Throws<IOException>(() => c.VerifyIdentity(c.DataPath));
        Assert.IsFalse(Directory.Exists(c.DataPath));
    }
}
