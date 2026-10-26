using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace Atlas.LocalAgent.IdentityLab;

// Synthetic-only tool. It is not a production service host or credential migrator.
public sealed record LabOptions(string RunId, string CreatorSid, string CandidateSid, string ObserverSid,
    Guid SyntheticAgentUuid, string HealthEndpoint, int Phase, bool SyntheticOnly = true)
{
    public static readonly JsonSerializerOptions Json = new() { WriteIndented = true,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow, MaxDepth = 8 };
    public static string ValidateRoot(string root)
    {
        if (!Path.IsPathFullyQualified(root)) throw new ArgumentException("LabRootInvalid");
        var full = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar);
        // The QA base can be configured machine-wide for both the creator and SCM identities.
        // A leaf name match alone must never authorize an operational data root.
        var basePath = Path.GetFullPath(Environment.GetEnvironmentVariable("ATLAS_IDENTITY_LAB_BASE") ?? @"C:\AtlasQaLabs")
            .TrimEnd(Path.DirectorySeparatorChar);
        if (!Regex.IsMatch(Path.GetFileName(full), @"^service-account-lab-[a-f0-9]{12}$", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant)
            || !string.Equals(Path.GetDirectoryName(full), basePath, StringComparison.OrdinalIgnoreCase)
            || basePath.Contains(@"\Atlas\LocalAgent", StringComparison.OrdinalIgnoreCase)
            || basePath.Contains(@"\AtlasPergamo\", StringComparison.OrdinalIgnoreCase)
            || basePath.EndsWith(@"\AtlasPergamo", StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("LabRootInvalid");
        return full;
    }
    public static LabOptions Load(string root)
    {
        root = ValidateRoot(root);
        RejectLinks(root);
        var value = JsonSerializer.Deserialize<LabOptions>(File.ReadAllBytes(Path.Combine(root, "config", "lab.json")), Json)
            ?? throw new InvalidDataException("LabConfigInvalid");
        value.Validate(root);
        return value;
    }
    public void Validate(string root)
    {
        if (!SyntheticOnly || !Regex.IsMatch(RunId, "^[a-f0-9]{12}$", RegexOptions.CultureInvariant)
            || !ValidateRoot(root).EndsWith(RunId, StringComparison.OrdinalIgnoreCase)
            || SyntheticAgentUuid == Guid.Empty || Phase is not (1 or 2)
            || !CreatorSid.StartsWith("S-1-5-21-", StringComparison.Ordinal)
            || !CandidateSid.StartsWith("S-1-5-80-", StringComparison.Ordinal)
            || !ObserverSid.StartsWith("S-1-5-80-", StringComparison.Ordinal)
            || new[] { CreatorSid, CandidateSid, ObserverSid }.Distinct().Count() != 3)
            throw new ArgumentException("SyntheticScopeInvalid");
        _ = new SecurityIdentifier(CreatorSid); _ = new SecurityIdentifier(CandidateSid); _ = new SecurityIdentifier(ObserverSid);
        _ = ValidateHealth(HealthEndpoint);
    }
    public static Uri ValidateHealth(string endpoint)
    {
        if (!Uri.TryCreate(endpoint, UriKind.Absolute, out var uri) || uri.Scheme != "https"
            || uri.Port != 443 || !string.IsNullOrEmpty(uri.UserInfo) || uri.Query.Length != 0 || uri.Fragment.Length != 0
            || uri.AbsolutePath != "/api/v1/health") throw new ArgumentException("HttpsHealthOnly");
        return uri;
    }
    public static void RejectLinks(string root)
    {
        if ((File.GetAttributes(root) & FileAttributes.ReparsePoint) != 0) throw new IOException("LabReparsePointRejected");
        foreach (var path in Directory.EnumerateFileSystemEntries(root))
            if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0) throw new IOException("LabReparsePointRejected");
    }
    public string CandidateName => "AtlasDpapiCandidateQA_" + RunId;
    public string ObserverName => "AtlasDpapiObserverQA_" + RunId;
    public string PipeName => "Atlas.SyntheticDpapiLab." + RunId;
    public byte[] SyntheticBytes() => Encoding.UTF8.GetBytes("ATLAS-QA-DPAPI-SECRET-DO-NOT-USE\n" + SyntheticAgentUuid.ToString("D"));
    public void RequireSynthetic(ReadOnlySpan<byte> bytes)
    {
        var expected = SyntheticBytes();
        try { if (!CryptographicOperations.FixedTimeEquals(bytes, expected)) throw new InvalidDataException("NonSyntheticInputRejected"); }
        finally { CryptographicOperations.ZeroMemory(expected); }
    }
    public override string ToString() => "[SYNTHETIC LAB CONFIG]";
}
