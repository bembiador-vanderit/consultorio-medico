using System.Collections.Concurrent;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace Atlas.LocalAgent.Core;

public enum CommunicationEnvironment { Production, Development }
public enum PrintOriginType { WebDesktop, WebMobile, WebTablet, LocalAgent, System }
public enum DocumentSecurityClass { General, Administrative, Financial, Clinical, SensitiveClinical }
public enum AuthenticationKind { AgentBearer, UserSession, MutualTls, ServiceIdentity }
public sealed record PrintOrigin(PrintOriginType Type, string ActorReference, string ContextReference, Guid? SourceAgent = null)
{
    public PrintOrigin Validate()
    {
        if (!Enum.IsDefined(Type) || !Opaque(ActorReference) || !Opaque(ContextReference)
            || SourceAgent == Guid.Empty || (Type == PrintOriginType.LocalAgent && SourceAgent is null)
            || (Type != PrintOriginType.LocalAgent && SourceAgent is not null))
            throw new ArgumentException("Origen inválido; usar referencias opacas, no datos de paciente.");
        return this;
    }
    internal static bool Opaque(string value) => value is not null && Regex.IsMatch(value, "^[A-Za-z0-9_-]{1,128}$", RegexOptions.CultureInvariant);
    public override string ToString() => $"PrintOrigin({Type})";
}
public enum CommandType { AvailabilityNotification } // No print execution command in V1.
public sealed record CommandSecurityContext(string OrganizationId, string CenterId, string WorkgroupId,
    DocumentSecurityClass Classification, AuthenticationKind Authentication, string ValidationReference);
public sealed record CommandEnvelope(Guid CommandId, CommandType CommandType, PrintOrigin Source, Guid TargetAgent,
    DateTimeOffset IssuedAt, DateTimeOffset ExpiresAt, string PayloadReference, CommandSecurityContext SecurityContext)
{
    public CommandEnvelope Validate(DateTimeOffset now)
    {
        if (Source is null || SecurityContext is null) throw new ArgumentException("Contexto requerido.");
        Source.Validate();
        if (CommandId == Guid.Empty || TargetAgent == Guid.Empty || !Enum.IsDefined(CommandType)
            || !PrintOrigin.Opaque(PayloadReference) || !PrintOrigin.Opaque(SecurityContext.OrganizationId)
            || !PrintOrigin.Opaque(SecurityContext.CenterId) || !PrintOrigin.Opaque(SecurityContext.WorkgroupId)
            || !PrintOrigin.Opaque(SecurityContext.ValidationReference) || !Enum.IsDefined(SecurityContext.Classification)
            || !Enum.IsDefined(SecurityContext.Authentication) || IssuedAt > now.AddSeconds(30)
            || ExpiresAt <= now || ExpiresAt <= IssuedAt || ExpiresAt - IssuedAt > TimeSpan.FromMinutes(5))
            throw new ArgumentException("Envelope inválido o vencido.");
        var kind = SecurityContext.Authentication;
        if ((Source.Type is PrintOriginType.WebDesktop or PrintOriginType.WebMobile or PrintOriginType.WebTablet) && kind != AuthenticationKind.UserSession
            || Source.Type == PrintOriginType.LocalAgent && kind is not (AuthenticationKind.AgentBearer or AuthenticationKind.MutualTls)
            || Source.Type == PrintOriginType.System && kind != AuthenticationKind.ServiceIdentity)
            throw new ArgumentException("Origen y autenticación incompatibles.");
        return this;
    }
    public override string ToString() => $"Command({CommandId}, {CommandType})";
}
public interface ICommandAuthenticator
{
    // Implementations must bind authenticated actor, tenant, target and policy revision.
    // Supplied SecurityContext is a claim, NEVER authorization or a signature by itself.
    Task<bool> ValidateAsync(CommandEnvelope command, CancellationToken cancellationToken);
}
public enum CommandAcceptance { Accepted, Duplicate, Conflict, Denied }
public sealed class InMemoryCommandInbox(ICommandAuthenticator authenticator, TimeProvider? clock = null)
{
    private readonly ConcurrentDictionary<Guid, string> _accepted = new();
    private readonly object _gate = new();
    public async Task<CommandAcceptance> AcceptAsync(CommandEnvelope command, CancellationToken cancellationToken = default)
    {
        try { command.Validate((clock ?? TimeProvider.System).GetUtcNow()); }
        catch (ArgumentException) { return CommandAcceptance.Denied; }
        if (!await authenticator.ValidateAsync(command, cancellationToken)) return CommandAcceptance.Denied;
        cancellationToken.ThrowIfCancellationRequested();
        if (command.ExpiresAt <= (clock ?? TimeProvider.System).GetUtcNow()) return CommandAcceptance.Denied;
        // Metadata hash only; never stores a document, credential or free-text payload.
        var hash = Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(command)));
        lock (_gate)
        {
            if (_accepted.TryGetValue(command.CommandId, out var prior))
                return prior == hash ? CommandAcceptance.Duplicate : CommandAcceptance.Conflict;
            if (_accepted.Count >= 4096) return CommandAcceptance.Denied; // No eviction that could permit replay.
            _accepted[command.CommandId] = hash;
            return CommandAcceptance.Accepted;
        }
    }
    // Process-local foundation only: no execution, no persistence, no eviction/replay promise after restart.
}
public sealed class ReconnectBackoff(Func<double>? jitter = null)
{
    private int _failures;
    public TimeSpan FailureDelay()
    {
        var ceiling = Math.Min(300, 2 * Math.Pow(2, Math.Min(_failures++, 8)));
        var sample = Math.Clamp((jitter ?? Random.Shared.NextDouble)(), 0, 1);
        return TimeSpan.FromSeconds(ceiling * (0.5 + sample * 0.5));
    }
    public void Reset() => _failures = 0;
}
