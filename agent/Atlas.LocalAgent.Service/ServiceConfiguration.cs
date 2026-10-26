using System.Security.Principal;
using System.Text.Json;
using System.Text.Json.Serialization;
using Atlas.LocalAgent.Core;

namespace Atlas.LocalAgent.Service;

/// <summary>Admin-owned binding. No credential or physical authorization belongs in this file.</summary>
public sealed record ServiceConfiguration(string BasePath, string SourceRoot, Guid AgentUuid, string SourceUserSid,
    string ServiceSid, string Endpoint, string Phase, string IdentitySha256, string StationSha256,
    string[] PrinterIds, Guid? ReplayJobId = null, bool SafeValidation = true, bool PhysicalGlobal = false,
    Guid? AllowedJobId = null)
{
    public const string Name = "AtlasLocalAgent";
    public static string MachineBase => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "AtlasPergamo", "LocalAgent");
    public static string MachineConfigPath => Path.Combine(MachineBase, "config", "service.json");
    public static JsonSerializerOptions Json { get; } = new() { UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow, MaxDepth = 12, WriteIndented = true };
    public string DataPath => Path.Combine(BasePath, "data");
    public string LogsPath => Path.Combine(BasePath, "logs");
    public string PipeName => "Atlas.LocalAgent.Handoff." + AgentUuid.ToString("N");
    public override string ToString() => "[SERVICE BINDING; NO CREDENTIALS]";

    public ServiceConfiguration Validate()
    {
        foreach (var path in new[] { BasePath, SourceRoot })
        {
            if (!Path.IsPathFullyQualified(path) || path.StartsWith(@"\\", StringComparison.Ordinal) ||
                path.Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar).Any(p => p is "." or ".."))
                throw new InvalidDataException("InvalidServicePath");
            for (var p = Path.GetFullPath(path); !string.IsNullOrEmpty(p); p = Path.GetDirectoryName(p))
                if (Directory.Exists(p) && (File.GetAttributes(p) & FileAttributes.ReparsePoint) != 0)
                    throw new InvalidDataException("ServicePathReparsePoint");
        }
        var sourcePath = Path.GetFullPath(SourceRoot).TrimEnd(Path.DirectorySeparatorChar);
        var basePath = Path.GetFullPath(BasePath).TrimEnd(Path.DirectorySeparatorChar);
        if (sourcePath.Equals(basePath, StringComparison.OrdinalIgnoreCase)
            || sourcePath.StartsWith(basePath + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)
            || basePath.StartsWith(sourcePath + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)
            || AgentUuid == Guid.Empty || !SourceUserSid.StartsWith("S-1-5-21-", StringComparison.Ordinal)
            || !ServiceSid.StartsWith("S-1-5-80-", StringComparison.Ordinal) || SourceUserSid == ServiceSid
            || Phase is not ("Synthetic" or "Handoff" or "Run") || !SafeValidation || PhysicalGlobal || AllowedJobId is not null
            || (ReplayJobId is not null && Phase != "Run") || PrinterIds.Length == 0 || PrinterIds.Distinct().Count() != PrinterIds.Length)
            throw new InvalidDataException("InvalidServiceBinding");
        foreach (var hash in new[] { IdentitySha256, StationSha256 })
            if (hash.Length != 64 || !hash.All(Uri.IsHexDigit)) throw new InvalidDataException("InvalidServiceHash");
        _ = new SecurityIdentifier(SourceUserSid); _ = new SecurityIdentifier(ServiceSid);
        if (new PairingInput(Endpoint, "").ValidateEndpoint().Scheme != "https") throw new InvalidDataException("HttpsOnly");
        return this;
    }
    public static ServiceConfiguration Load(string path)
    {
        if (!Path.GetFullPath(path).Equals(MachineConfigPath, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("MachineConfigRequired");
        if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0) throw new InvalidDataException("ConfigLinkDenied");
        var value = JsonSerializer.Deserialize<ServiceConfiguration>(File.ReadAllBytes(path), Json) ?? throw new InvalidDataException();
        value.Validate();
        if (!value.BasePath.Equals(MachineBase, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("MachineRootRequired");
        return value;
    }
    public void VerifyIdentity(string root)
    {
        foreach (var pair in new[] { ("identity.json", IdentitySha256), ("station.json", StationSha256) })
        {
            var path = Path.Combine(root, pair.Item1);
            if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0 ||
                !Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(path))).Equals(pair.Item2, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("IdentityBindingMismatch");
        }
        if (Wire.Deserialize<AgentIdentity>(File.ReadAllBytes(Path.Combine(root, "identity.json"))).AgentId != AgentUuid)
            throw new InvalidDataException("UuidBindingMismatch");
    }
}
