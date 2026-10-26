using System.Security.Cryptography;
using System.Text;
using Atlas.LocalAgent.IdentityLab;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Atlas.LocalAgent.Tests;

[TestClass]
public sealed class IdentityLabTests
{
    private const string Root = @"C:\AtlasQaLabs\service-account-lab-0123456789ab";
    private static LabOptions Options() => new("0123456789ab", "S-1-5-21-1-2-3-1001", "S-1-5-80-1-2-3-4-5",
        "S-1-5-80-6-7-8-9-10", Guid.Parse("a12aa12a-1111-2222-3333-444455556666"), "https://example.com/api/v1/health", 1);

    [TestMethod]
    public void LabRootCannotReferenceRealOrArbitraryAgentData()
    {
        foreach (var root in new[] { @"C:\AtlasQaLabs\operational-agent\data", @"C:\ProgramData\AtlasPergamo\LocalAgent", @"C:\Users\other\AppData\Local\Atlas\LocalAgent", "relative", Root + @"\..\other" })
            Assert.ThrowsExactly<ArgumentException>(() => LabOptions.ValidateRoot(root));
        Assert.AreEqual(Root, LabOptions.ValidateRoot(Root));
    }
    [TestMethod]
    public void OnlyDistinctSyntheticServiceIdentitiesAndPhasesAreAccepted()
    {
        Options().Validate(Root);
        foreach (var change in new[] { Options() with { SyntheticOnly = false }, Options() with { CandidateSid = "S-1-5-18" },
            Options() with { ObserverSid = Options().CandidateSid }, Options() with { Phase = 3 },
            Options() with { SyntheticAgentUuid = Guid.Empty }, Options() with { RunId = "aaaaaaaaaaaa" } })
            Assert.ThrowsExactly<ArgumentException>(() => change.Validate(Root));
    }
    [TestMethod]
    public void HealthProbeCannotUseHttpCredentialsOrMutationEndpoints()
    {
        foreach (var endpoint in new[] { "http://localhost/api/v1/health", "https://user:password@example.com/api/v1/health", "https://example.com/api/v1/local-agents/pair", "https://example.com/api/v1/health?token=no", "https://example.com:8001/api/v1/health" })
            Assert.ThrowsExactly<ArgumentException>(() => LabOptions.ValidateHealth(endpoint));
        Assert.AreEqual("https", LabOptions.ValidateHealth("https://example.com/api/v1/health").Scheme);
    }
    [TestMethod]
    public void HandoffRejectsEveryValueOtherThanThisExactSyntheticIdentity()
    {
        var options = Options(); var bytes = options.SyntheticBytes();
        try
        {
            options.RequireSynthetic(bytes);
            Assert.ThrowsExactly<InvalidDataException>(() => options.RequireSynthetic(Encoding.UTF8.GetBytes("not-a-real-token")));
            bytes[^1] ^= 1;
            Assert.ThrowsExactly<InvalidDataException>(() => options.RequireSynthetic(bytes));
            Assert.ThrowsExactly<InvalidDataException>(() => options.RequireSynthetic([]));
        }
        finally { CryptographicOperations.ZeroMemory(bytes); }
    }
    [TestMethod]
    public void SyntheticUuidSurvivesAccountSelectionAndRestart()
    {
        var before = Options(); var after = before with { Phase = 2 };
        Assert.AreEqual(before.SyntheticAgentUuid, after.SyntheticAgentUuid);
        Assert.AreNotEqual(before.CreatorSid, after.CandidateSid);
        after.Validate(Root);
        var a = before.SyntheticBytes(); var b = after.SyntheticBytes();
        try { CollectionAssert.AreEqual(a, b); }
        finally { CryptographicOperations.ZeroMemory(a); CryptographicOperations.ZeroMemory(b); }
    }
    [TestMethod]
    public void LabDiagnosticsNeverStringifySyntheticSecret()
    {
        Assert.AreEqual("[SYNTHETIC LAB CONFIG]", Options().ToString());
        Assert.IsFalse(Options().ToString().Contains("ATLAS-QA-DPAPI-SECRET", StringComparison.Ordinal));
    }
}
