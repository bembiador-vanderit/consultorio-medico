using System.Security.Authentication;

namespace Atlas.LocalAgent.Core;

public enum AgentState { Unpaired, Pairing, Connected, Disconnected, Degraded, Revoked, Error }
public enum TransportRoute { Local, Cloud }
public sealed record SecureChannelRequirements(Uri Endpoint, bool RequireMutualAuthentication, DeviceCredentialReference Credential)
{
    public Guid? ExpectedPeerAgent { get; init; }
    public SslProtocols AllowedProtocols => SslProtocols.Tls12 | SslProtocols.Tls13;
    public SecureChannelRequirements Validate()
    {
        if (!Endpoint.IsAbsoluteUri || Endpoint.Scheme is not ("https" or "wss") || !string.IsNullOrEmpty(Endpoint.UserInfo)
            || !string.IsNullOrEmpty(Endpoint.Query) || !string.IsNullOrEmpty(Endpoint.Fragment))
            throw new ArgumentException("Se requiere HTTPS/WSS sin credenciales en URL.");
        if (string.IsNullOrWhiteSpace(Credential.Key) || Credential.ExpiresAt <= DateTimeOffset.UtcNow
            || !Enum.IsDefined(Credential.Kind) || Credential.Kind == AuthenticationKind.UserSession
            || (RequireMutualAuthentication && (Credential.Kind != AuthenticationKind.MutualTls || ExpectedPeerAgent is null || ExpectedPeerAgent == Guid.Empty)))
            throw new ArgumentException("Identidad/canal autenticado requerido.");
        return this;
    }
}
public sealed record DeviceSummary(int Printers, int DefaultPrinters);
public sealed record AgentHeartbeat(Guid AgentId, string Station, string AgentVersion, int ProtocolVersion,
    string OperatingSystem, AgentState Status, DateTimeOffset LastSeen, DeviceSummary Devices);
public interface ITransport : IAsyncDisposable
{
    TransportRoute Route { get; }
    bool IsAvailable { get; }
    bool IsSecure => false; // Availability/discovery alone is never sufficient.
    Guid? AuthenticatedPeerAgent => null;
    bool MutualAuthenticationVerified => false;
    Task ConnectAsync(SecureChannelRequirements requirements, CancellationToken cancellationToken);
    Task SendHeartbeatAsync(AgentHeartbeat heartbeat, CancellationToken cancellationToken);
}
public interface ILocalTransport : ITransport;
public interface ICloudTransport : ITransport;
public sealed record DiscoveredAgent(Guid AgentId, Uri Endpoint, DateTimeOffset ObservedAt);
public interface ILanDiscovery { Task<IReadOnlyList<DiscoveredAgent>> DiscoverAsync(CancellationToken cancellationToken); }
public sealed class InMemoryLanDiscovery(IReadOnlyList<DiscoveredAgent>? fixtures = null) : ILanDiscovery
{
    public Task<IReadOnlyList<DiscoveredAgent>> DiscoverAsync(CancellationToken cancellationToken) => Task.FromResult(fixtures ?? (IReadOnlyList<DiscoveredAgent>)[]);
}

public interface IRouteSelector
{
    Task<ITransport?> SelectAsync(AgentAuthorizationContext context, ILocalTransport local, ICloudTransport cloud, CancellationToken cancellationToken);
}
public sealed class AuthorizedRouteSelector(IAgentAuthorizationPolicy authorization) : IRouteSelector
{
    public async Task<ITransport?> SelectAsync(AgentAuthorizationContext context, ILocalTransport local, ICloudTransport cloud, CancellationToken cancellationToken)
    {
        var webOrigin = context.Origin?.Type is PrintOriginType.WebDesktop or PrintOriginType.WebMobile or PrintOriginType.WebTablet;
        var unhostedOrigin = (webOrigin && context.Credential.Kind == AuthenticationKind.UserSession)
            || (context.Origin?.Type == PrintOriginType.System && context.Credential.Kind == AuthenticationKind.ServiceIdentity);
        if (context.SourceAgent == Guid.Empty || context.TargetAgent == Guid.Empty || context.Credential.ExpiresAt <= DateTimeOffset.UtcNow
            || !context.TargetOnline || context.TargetRevoked
            || string.IsNullOrWhiteSpace(context.Credential.Key) || !Enum.IsDefined(context.Credential.Kind)
            || (context.Origin is not null && context.Origin.SourceAgent != context.SourceAgent)
            || string.IsNullOrWhiteSpace(context.OrganizationId) || string.IsNullOrWhiteSpace(context.CenterId)
            || (context.SourceAgent is null && !unhostedOrigin)
            || (context.SourceAgent is not null && context.Credential.Kind is not (AuthenticationKind.AgentBearer or AuthenticationKind.MutualTls))
            || !(await authorization.AuthorizeAsync(context, cancellationToken)).Allowed) return null;
        try { context.Origin?.Validate(); } catch (ArgumentException) { return null; }
        return context.SourceAgent is not null && local.IsAvailable && local.IsSecure && local.MutualAuthenticationVerified && local.AuthenticatedPeerAgent == context.TargetAgent
            ? local : cloud.IsAvailable && cloud.IsSecure ? cloud : null;
    }
}

// No sockets, listeners or Atlas requests. A simulated receipt never means paired/authorized.
public abstract class MockTransport(TransportRoute route) : ITransport
{
    public TransportRoute Route => route;
    public bool IsAvailable { get; private set; } = true;
    public bool IsSecure { get; private set; }
    public Guid? AuthenticatedPeerAgent { get; private set; }
    public bool MutualAuthenticationVerified { get; private set; }
    public AgentHeartbeat? LastHeartbeat { get; private set; }
    public Task ConnectAsync(SecureChannelRequirements requirements, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested(); requirements.Validate();
        if (!IsAvailable) throw new ObjectDisposedException(nameof(MockTransport));
        IsSecure = true; AuthenticatedPeerAgent = requirements.ExpectedPeerAgent;
        MutualAuthenticationVerified = requirements.RequireMutualAuthentication;
        return Task.CompletedTask;
    }
    public Task SendHeartbeatAsync(AgentHeartbeat heartbeat, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (!IsAvailable) throw new ObjectDisposedException(nameof(MockTransport));
        LastHeartbeat = heartbeat; return Task.CompletedTask;
    }
    public ValueTask DisposeAsync() { IsAvailable = false; return ValueTask.CompletedTask; }
}
public sealed class MockLocalTransport() : MockTransport(TransportRoute.Local), ILocalTransport;
public sealed class MockCloudTransport() : MockTransport(TransportRoute.Cloud), ICloudTransport;
