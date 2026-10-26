using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using Atlas.LocalAgent.Core;

namespace Atlas.LocalAgent.Service;

/// <summary>Outbound HTTPS registry and protected routing connection factory; no LAN sockets or document logs.</summary>
public sealed class AtlasRegistryClient(HttpClient http, ISecureSecretStore secrets,
    CommunicationEnvironment environment = CommunicationEnvironment.Production) : IStationRegistry
{
    private const string SecretKey = "atlas-registry-v1";
    private static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower, MaxDepth = 16 };
    private readonly SemaphoreSlim _gate = new(1, 1);
    private bool _invalid;

    private sealed record Credential(string Endpoint, bool AllowLoopbackHttp, string Token, Guid AgentUuid,
        DateTimeOffset ExpiresAt, int OrganizationId, int CenterId, int WorkgroupId)
    {
        public override string ToString() => "[CREDENTIAL REDACTED]";
    }
    private sealed record CredentialReply(string Credential, DateTimeOffset ExpiresAt, Guid AgentUuid,
        int OrganizationId, int CenterId, int WorkgroupId)
    {
        public override string ToString() => "[CREDENTIAL REPLY REDACTED]";
    }
    private sealed record HeartbeatReply(int OrganizationId, int CenterId, int WorkgroupId);

    public static HttpClient CreateHttpClient(CommunicationEnvironment environment = CommunicationEnvironment.Production) => new(new HttpClientHandler { AllowAutoRedirect = false, UseCookies = false,
        UseProxy = environment != CommunicationEnvironment.Development,
        CheckCertificateRevocationList = true,
        SslProtocols = System.Security.Authentication.SslProtocols.Tls12 | System.Security.Authentication.SslProtocols.Tls13 })
    { Timeout = TimeSpan.FromSeconds(10), MaxResponseContentBufferSize = 1024 * 1024 };

    private static RegistryStatus Status(Credential credential, AgentState state, string code) => new(state, code,
        new(credential.OrganizationId.ToString(System.Globalization.CultureInfo.InvariantCulture),
            credential.CenterId.ToString(System.Globalization.CultureInfo.InvariantCulture),
            credential.WorkgroupId.ToString(System.Globalization.CultureInfo.InvariantCulture)), credential.ExpiresAt);

    public async Task<RegistryStatus> PairAsync(PairingInput input, AgentSnapshot snapshot, CancellationToken cancellationToken)
    {
        var uri = input.ValidateEndpoint(environment);
        if (!System.Text.RegularExpressions.Regex.IsMatch(input.Code, "^[A-Z2-7-]{26,40}$", System.Text.RegularExpressions.RegexOptions.CultureInvariant))
            return new(AgentState.Unpaired, "InvalidPairingCode", new());
        await _gate.WaitAsync(cancellationToken);
        try
        {
            using var existing = await secrets.ReadAsync(SecretKey, cancellationToken);
            if (existing is not null) return new(AgentState.Error, "AlreadyPaired", new());
            var body = Station(snapshot).ToDictionary(x => x.Key, x => x.Value);
            body["code"] = input.Code;
            using var response = await SendAsync(uri, "pair", HttpMethod.Post, body, null, cancellationToken);
            if (!response.IsSuccessStatusCode) return new(AgentState.Unpaired, "PairingRejected", new());
            var reply = await ReadReplyAsync(response, snapshot.Identity.AgentId, cancellationToken);
            var credential = new Credential(uri.AbsoluteUri, input.AllowLoopbackHttp, reply.Credential, reply.AgentUuid,
                reply.ExpiresAt, reply.OrganizationId, reply.CenterId, reply.WorkgroupId);
            await secrets.StoreAsync(SecretKey, JsonSerializer.SerializeToUtf8Bytes(credential, Json), cancellationToken);
            _invalid = false;
            return Status(credential, AgentState.Connected, "Paired");
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or JsonException or IOException or InvalidDataException
            or System.ComponentModel.Win32Exception or UnauthorizedAccessException)
        { return new(AgentState.Disconnected, "PairingUncertainCheckRegistry", new()); }
        finally { _gate.Release(); }
    }

    public async Task<RegistryStatus> SynchronizeAsync(AgentSnapshot snapshot, CancellationToken cancellationToken)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var credential = await LoadAsync(cancellationToken);
            if (credential is null) return new(AgentState.Unpaired, "Unpaired", new());
            if (_invalid || credential.ExpiresAt <= DateTimeOffset.UtcNow)
                return Status(credential, AgentState.Revoked, "CredentialInvalidOrExpired");
            if (credential.AgentUuid != snapshot.Identity.AgentId)
                return Status(credential, AgentState.Error, "IdentityConflict");
            var uri = new PairingInput(credential.Endpoint, "", credential.AllowLoopbackHttp).ValidateEndpoint(environment);
            var heartbeat = Station(snapshot).ToDictionary(x => x.Key, x => x.Value);
            heartbeat["health"] = snapshot.LastError == AgentErrorCode.None ? "online" : "degraded";
            heartbeat["device_summary"] = new DeviceSummary(snapshot.Printers.Count, snapshot.Printers.Count(p => p.IsDefault));
            using var response = await SendAsync(uri, "device/heartbeat", HttpMethod.Post, heartbeat, credential.Token, cancellationToken);
            if (response.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden)
            { _invalid = true; return Status(credential, AgentState.Revoked, "CredentialRejected"); }
            if (!response.IsSuccessStatusCode) return Status(credential, AgentState.Degraded, "RegistryRejected");
            var scope = await response.Content.ReadFromJsonAsync<HeartbeatReply>(Json, cancellationToken);
            if (scope is null || scope.OrganizationId != credential.OrganizationId || scope.CenterId < 1 || scope.WorkgroupId < 1)
                return Status(credential, AgentState.Error, "RegistryContextConflict");
            if (scope.CenterId != credential.CenterId || scope.WorkgroupId != credential.WorkgroupId)
            {
                credential = credential with { CenterId = scope.CenterId, WorkgroupId = scope.WorkgroupId };
                await secrets.StoreAsync(SecretKey, JsonSerializer.SerializeToUtf8Bytes(credential, Json), cancellationToken);
            }
            // No partial enumeration is sent: on local discovery failure, retain previous remote inventory.
            if (snapshot.LastError != AgentErrorCode.None) return Status(credential, AgentState.Degraded, "DiscoveryUnavailable");
            var printers = new { Printers = snapshot.Printers.Select(p => new
            {
                LocalId = p.RegistryId ?? p.DeviceId, DisplayName = p.Name, Driver = p.Driver, p.IsDefault,
                Connection = p.Connection.ToString(), p.IsVirtual, p.Status,
                Papers = p.Capabilities.PaperSizes.Select(s => new { s.Name, s.WidthTenthsMillimeter, s.HeightTenthsMillimeter, s.RawKind })
            }).ToArray() };
            using var sync = await SendAsync(uri, "device/printers", HttpMethod.Put, printers, credential.Token, cancellationToken);
            if (sync.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden)
            { _invalid = true; return Status(credential, AgentState.Revoked, "CredentialRejected"); }
            return Status(credential, sync.IsSuccessStatusCode ? AgentState.Connected : AgentState.Degraded,
                sync.IsSuccessStatusCode ? "Synchronized" : "InventoryRejected");
        }
        catch (ArgumentException) { return new(AgentState.Disconnected, "TransportPolicyDenied", new()); }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or JsonException or IOException or InvalidDataException
            or System.ComponentModel.Win32Exception or UnauthorizedAccessException or System.Security.Cryptography.CryptographicException)
        { return new(AgentState.Disconnected, "RegistryUnavailable", new()); }
        finally { _gate.Release(); }
    }

    public async Task<RegistryStatus> RotateAsync(CancellationToken cancellationToken)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var credential = await LoadAsync(cancellationToken);
            if (credential is null) return new(AgentState.Unpaired, "Unpaired", new());
            if (_invalid) return Status(credential, AgentState.Revoked, "CredentialRejected");
            var uri = new PairingInput(credential.Endpoint, "", credential.AllowLoopbackHttp).ValidateEndpoint(environment);
            using var response = await SendAsync(uri, "device/rotate", HttpMethod.Post, new { }, credential.Token, cancellationToken);
            if (!response.IsSuccessStatusCode) return Status(credential, AgentState.Error, "RotationRejected");
            var reply = await ReadReplyAsync(response, credential.AgentUuid, cancellationToken);
            credential = credential with { Token = reply.Credential, ExpiresAt = reply.ExpiresAt,
                OrganizationId = reply.OrganizationId, CenterId = reply.CenterId, WorkgroupId = reply.WorkgroupId };
            await secrets.StoreAsync(SecretKey, JsonSerializer.SerializeToUtf8Bytes(credential, Json), cancellationToken);
            return Status(credential, AgentState.Connected, "CredentialRotated");
        }
        catch (ArgumentException) { return new(AgentState.Disconnected, "TransportPolicyDenied", new()); }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or JsonException or IOException or InvalidDataException
            or System.ComponentModel.Win32Exception or UnauthorizedAccessException)
        { return new(AgentState.Error, "RotationUncertainContactAdministrator", new()); }
        finally { _gate.Release(); }
    }

    private static Dictionary<string, object> Station(AgentSnapshot snapshot) => new()
    {
        ["agent_uuid"] = snapshot.Identity.AgentId, ["station_name"] = snapshot.Configuration.StationName,
        ["display_code"] = snapshot.Configuration.DisplayCode, ["version"] = AgentVersion.Current,
        ["protocol_version"] = AgentVersion.Protocol, ["fingerprint"] = InstallationFingerprint.For(snapshot.Identity)
    };
    private async Task<Credential?> LoadAsync(CancellationToken cancellationToken)
    {
        using var secret = await secrets.ReadAsync(SecretKey, cancellationToken);
        return secret is null ? null : JsonSerializer.Deserialize<Credential>(secret.Bytes.Span, Json)
            ?? throw new InvalidDataException("Protected credential invalid.");
    }
    public async Task<OfficialPrintConnection?> OpenPrintConnectionAsync(Guid identity,CancellationToken token)
    {
        await _gate.WaitAsync(token);
        try
        {
            var c=await LoadAsync(token);
            if(c is null || _invalid || c.AgentUuid!=identity || c.ExpiresAt<=DateTimeOffset.UtcNow)return null;
            // Printing transport never inherits the registry's development HTTP exception.
            var endpoint=new PairingInput(c.Endpoint,"",false).ValidateEndpoint(CommunicationEnvironment.Production);
            if(endpoint.Scheme!="https")throw new InvalidDataException("HTTPS required.");
            var client=CreateHttpClient();client.BaseAddress=endpoint;
            return new(client,new HttpsPrintJobRelay(client,c.Token,"print-routing"),c.AgentUuid,c.OrganizationId,c.CenterId);
        }
        finally{_gate.Release();}
    }
    private async Task<HttpResponseMessage> SendAsync(Uri uri, string route, HttpMethod method, object body, string? token, CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(method, new Uri(uri, "api/v1/local-agents/" + route))
        { Content = JsonContent.Create(body, options: Json) };
        if (token is not null) request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        return await http.SendAsync(request, HttpCompletionOption.ResponseContentRead, cancellationToken);
    }
    private static async Task<CredentialReply> ReadReplyAsync(HttpResponseMessage response, Guid expected, CancellationToken cancellationToken)
    {
        var reply = await response.Content.ReadFromJsonAsync<CredentialReply>(Json, cancellationToken)
            ?? throw new InvalidDataException("Registry response invalid.");
        if (reply.AgentUuid != expected || string.IsNullOrEmpty(reply.Credential) || !reply.Credential.StartsWith("ala_", StringComparison.Ordinal)
            || reply.Credential.Length is < 40 or > 128 || reply.ExpiresAt <= DateTimeOffset.UtcNow
            || reply.OrganizationId < 1 || reply.CenterId < 1 || reply.WorkgroupId < 1)
            throw new InvalidDataException("Registry identity invalid.");
        return reply;
    }
}
