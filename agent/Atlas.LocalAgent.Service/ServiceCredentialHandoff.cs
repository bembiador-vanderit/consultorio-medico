using System.Buffers.Binary;
using System.IO.Pipes;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text.Json;

namespace Atlas.LocalAgent.Service;

/// <summary>One-shot authenticated local transfer; no plaintext file, CLI, environment or diagnostic payload.</summary>
public static class ServiceCredentialHandoff
{
    private const string Key = "atlas-registry-v1";
    public static byte[] PrepareProductionCopy(ReadOnlyMemory<byte> value, ServiceConfiguration configuration)
    {
        using var document = JsonDocument.Parse(value);
        using var memory = new MemoryStream();
        byte[]? copy = null;
        try
        {
            using (var writer = new Utf8JsonWriter(memory))
            {
                writer.WriteStartObject();
                foreach (var property in document.RootElement.EnumerateObject())
                    if (property.NameEquals("allow_loopback_http")) writer.WriteBoolean(property.Name, false);
                    else property.WriteTo(writer);
                writer.WriteEndObject(); writer.Flush();
            }
            copy = memory.ToArray(); ValidateCredential(copy, configuration); return copy;
        }
        catch { if (copy is not null) CryptographicOperations.ZeroMemory(copy); throw; }
        finally { CryptographicOperations.ZeroMemory(memory.GetBuffer()); }
    }
    public static void ValidateCredential(ReadOnlyMemory<byte> value, ServiceConfiguration configuration)
    {
        using var json = JsonDocument.Parse(value);
        var c = json.RootElement;
        if (c.GetProperty("agent_uuid").GetGuid() != configuration.AgentUuid
            || c.GetProperty("endpoint").GetString() != configuration.Endpoint
            || c.GetProperty("allow_loopback_http").GetBoolean()
            || c.GetProperty("expires_at").GetDateTimeOffset() <= DateTimeOffset.UtcNow
            || c.GetProperty("organization_id").GetInt32() < 1 || c.GetProperty("center_id").GetInt32() < 1
            || c.GetProperty("workgroup_id").GetInt32() < 1) throw new InvalidDataException("CredentialBindingRejected");
        // Validate the bearer in UTF-8 without creating another immutable managed token string.
        var reader = new Utf8JsonReader(value.Span); var tokenValid = false;
        while (reader.Read())
            if (reader.TokenType == JsonTokenType.PropertyName && reader.ValueTextEquals("token"))
            {
                if (!reader.Read() || reader.TokenType != JsonTokenType.String || reader.ValueIsEscaped
                    || reader.ValueSpan.Length is < 40 or > 128 || !reader.ValueSpan.StartsWith("ala_"u8)) throw new InvalidDataException("CredentialBindingRejected");
                tokenValid = true;
            }
        if (!tokenValid) throw new InvalidDataException("CredentialBindingRejected");
    }
    public static async Task SendAsync(ServiceConfiguration configuration, CancellationToken token)
    {
        RequireSid(configuration.SourceUserSid);
        configuration.VerifyIdentity(configuration.SourceRoot);
        using var pipe = new NamedPipeClientStream(".", configuration.PipeName, PipeDirection.InOut, PipeOptions.Asynchronous, TokenImpersonationLevel.Identification);
        await pipe.ConnectAsync(token);
        if (pipe.GetAccessControl().GetOwner(typeof(SecurityIdentifier))?.Value != configuration.ServiceSid) throw new UnauthorizedAccessException("WrongServicePipeOwner");
        using var secret = await new WindowsSecretStore(configuration.SourceRoot).ReadAsync(Key, token) ?? throw new InvalidDataException("SourceSecretMissing");
        var production = PrepareProductionCopy(secret.Bytes, configuration);
        try
        {
            var header = new byte[4]; BinaryPrimitives.WriteInt32LittleEndian(header, production.Length);
            await pipe.WriteAsync(header, token); await pipe.WriteAsync(production, token); await pipe.FlushAsync(token);
            var ack = new byte[1]; await pipe.ReadExactlyAsync(ack, token);
            if (ack[0] != 1) throw new InvalidDataException("HandoffNotAcknowledged");
        }
        finally { CryptographicOperations.ZeroMemory(production); }
    }
    public static async Task ReceiveAsync(ServiceConfiguration configuration, CancellationToken token)
    {
        RequireSid(configuration.ServiceSid);
        configuration.VerifyIdentity(configuration.DataPath);
        var store = new WindowsSecretStore(configuration.BasePath);
        using (var existing = await store.ReadAsync(Key, token))
            if (existing is not null) throw new InvalidOperationException("RefuseCredentialOverwrite");
        using var pipe = LocalOnlyPipe.Create(configuration.PipeName, configuration.SourceUserSid);
        await pipe.WaitForConnectionAsync(token);
        // Identification level only: no execution of source-user operations or SeImpersonatePrivilege.
        var identityByte = new byte[1];
        // The client writes its frame before identification. Peek/read one byte so the impersonation token exists.
        await pipe.ReadExactlyAsync(identityByte, token);
        string? caller = null;
        pipe.RunAsClient(() => caller = WindowsIdentity.GetCurrent().User?.Value);
        if (caller != configuration.SourceUserSid) throw new UnauthorizedAccessException("WrongHandoffCaller");
        var header = new byte[4]; header[0] = identityByte[0]; await pipe.ReadExactlyAsync(header.AsMemory(1), token);
        var length = BinaryPrimitives.ReadInt32LittleEndian(header);
        if (length is < 1 or > 16384) throw new InvalidDataException("InvalidCredentialFrame");
        var bytes = new byte[length];
        try
        {
            await pipe.ReadExactlyAsync(bytes, token);
            ValidateCredential(bytes, configuration);
            await store.StoreAsync(Key, bytes, token);
            using var readback = await store.ReadAsync(Key, token) ?? throw new InvalidDataException();
            if (!CryptographicOperations.FixedTimeEquals(bytes, readback.Bytes.Span)) throw new InvalidDataException("DpapiReadbackMismatch");
            await pipe.WriteAsync(new byte[] { 1 }, token); await pipe.FlushAsync(token);
        }
        finally { CryptographicOperations.ZeroMemory(bytes); }
    }
    public static async Task VerifyAsync(ServiceConfiguration configuration, CancellationToken token)
    {
        RequireSid(configuration.ServiceSid);
        using var secret = await new WindowsSecretStore(configuration.BasePath).ReadAsync(Key, token) ?? throw new InvalidDataException("ServiceSecretMissing");
        ValidateCredential(secret.Bytes, configuration);
    }
    public static void RequireSid(string expected)
    {
        using var identity = WindowsIdentity.GetCurrent();
        if (identity.User?.Value != expected) throw new UnauthorizedAccessException("WrongWindowsIdentity");
    }
}
