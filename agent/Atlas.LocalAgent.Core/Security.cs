using System.Security.Cryptography;

namespace Atlas.LocalAgent.Core;

public sealed class SecretBuffer(byte[] value) : IDisposable
{
    public ReadOnlyMemory<byte> Bytes => value;
    public override string ToString() => "[REDACTED]";
    public void Dispose() => CryptographicOperations.ZeroMemory(value);
}
public interface ISecureSecretStore
{
    Task StoreAsync(string key, ReadOnlyMemory<byte> secret, CancellationToken cancellationToken = default);
    Task<SecretBuffer?> ReadAsync(string key, CancellationToken cancellationToken = default);
    Task RemoveAsync(string key, CancellationToken cancellationToken = default);
}
public sealed record DeviceCredentialReference(string Key, DateTimeOffset ExpiresAt)
{
    public AuthenticationKind Kind { get; init; } = AuthenticationKind.AgentBearer;
    public override string ToString() => $"CredentialReference({Kind})";
}
public interface IDeviceCredentialLifecycle
{
    Task<bool> IsRevokedAsync(Guid agentId, CancellationToken cancellationToken);
    Task<DeviceCredentialReference> RotateAsync(Guid agentId, CancellationToken cancellationToken);
}
public sealed record AgentAuthorizationContext(Guid? SourceAgent, Guid TargetAgent, string OrganizationId,
    string CenterId, string Action, DeviceCredentialReference Credential)
{
    public PrintOrigin? Origin { get; init; }
    public bool TargetOnline { get; init; }
    public bool TargetRevoked { get; init; }
}
public sealed record AuthorizationDecision(bool Allowed, string Code);
public interface IAgentAuthorizationPolicy
{
    Task<AuthorizationDecision> AuthorizeAsync(AgentAuthorizationContext context, CancellationToken cancellationToken);
}
public sealed class DenyAllAuthorizationPolicy : IAgentAuthorizationPolicy
{
    public Task<AuthorizationDecision> AuthorizeAsync(AgentAuthorizationContext context, CancellationToken cancellationToken) =>
        Task.FromResult(new AuthorizationDecision(false, "PrintRoutingNotEnabled"));
}
