using System.Security.Cryptography;
using System.Text;

namespace Atlas.LocalAgent.Core;

public sealed record PairingInput(string Endpoint, string Code, bool AllowLoopbackHttp = false)
{
    public override string ToString() => "[PAIRING REDACTED]";
    public Uri ValidateEndpoint(CommunicationEnvironment environment = CommunicationEnvironment.Production)
    {
        if (!Uri.TryCreate(Endpoint, UriKind.Absolute, out var uri) || !string.IsNullOrEmpty(uri.UserInfo)
            || !string.IsNullOrEmpty(uri.Query) || !string.IsNullOrEmpty(uri.Fragment) || uri.AbsolutePath != "/"
            || (uri.Scheme != "https" && !(environment == CommunicationEnvironment.Development && AllowLoopbackHttp && uri.Scheme == "http"
                && uri.Host is "localhost" or "127.0.0.1" or "[::1]")))
            throw new ArgumentException("Use HTTPS; HTTP solo es válido en loopback de desarrollo explícito.");
        // Development HTTP must reach the loopback socket, not a DNS/proxy interpretation of localhost.
        return uri.Scheme == "http" && uri.Host == "localhost" ? new UriBuilder(uri) { Host = "127.0.0.1" }.Uri : uri;
    }
}

public sealed record RegistryStatus(AgentState State, string Code, AtlasAssociation Association,
    DateTimeOffset? CredentialExpiresAt = null);
public interface IStationRegistry
{
    Task<RegistryStatus> PairAsync(PairingInput input, AgentSnapshot snapshot, CancellationToken cancellationToken);
    Task<RegistryStatus> SynchronizeAsync(AgentSnapshot snapshot, CancellationToken cancellationToken);
    Task<RegistryStatus> RotateAsync(CancellationToken cancellationToken);
}

public static class InstallationFingerprint
{
    // Installation metadata only, no MAC, serial, Windows user, IP or hardware identifiers.
    // A full cloned directory cannot be distinguished by this marker alone; DPAPI remains machine/user bound.
    public static string For(AgentIdentity identity) => Convert.ToHexStringLower(SHA256.HashData(
        Encoding.UTF8.GetBytes($"atlas-install-v1:{identity.AgentId:D}:{identity.CreatedAt:O}")));
}
