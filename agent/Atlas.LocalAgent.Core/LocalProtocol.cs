using System.Buffers.Binary;
using System.IO.Pipes;
using System.Runtime.Versioning;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Atlas.LocalAgent.Core;

public enum LocalCommand { Snapshot, Refresh, Configure, PrepareSyntheticTest, SubmitSyntheticTest, CancelSyntheticTest, ObserveSyntheticTest, PairWithAtlas, RotateCredential }
public sealed record LocalRequest(LocalCommand Command, string? StationName = null, string? DisplayCode = null,
    SyntheticPrintRequest? PrintRequest = null, PrintJobId? JobId = null, bool UserConfirmed = false, PairingInput? Pairing = null)
{
    public override string ToString() => $"LocalRequest({Command})";
}
public sealed record LocalResponse(AgentSnapshot? Snapshot, AgentErrorCode Error = AgentErrorCode.None,
    SyntheticPrintReply? PrintReply = null, LocalPrintDiagnostics? PrintDiagnostics = null, RegistryStatus? Registry = null);
public static class AgentPaths
{
    public static string DefaultRoot => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Atlas", "LocalAgent");
    public static string PipeName(string root) => "Atlas.LocalAgent." + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(Environment.UserName + "|" + Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar).ToUpperInvariant())))[..32];
}
public static class Wire
{
    public const int MaxFrameBytes = 1024 * 1024;
    public static JsonSerializerOptions Options { get; } = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase, UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        MaxDepth = 16, Converters = { new JsonStringEnumConverter(allowIntegerValues: false) }
    };
    public static byte[] Serialize<T>(T value) => JsonSerializer.SerializeToUtf8Bytes(value, Options);
    public static T Deserialize<T>(byte[] bytes) => JsonSerializer.Deserialize<T>(bytes, Options) ?? throw new InvalidDataException("Mensaje vacío.");
    public static async Task WriteAsync<T>(Stream stream, T value, CancellationToken cancellationToken)
    {
        var payload = Serialize(value);
        if (payload.Length > MaxFrameBytes) throw new InvalidDataException("Mensaje demasiado grande.");
        var header = new byte[4]; BinaryPrimitives.WriteInt32LittleEndian(header, payload.Length);
        await stream.WriteAsync(header, cancellationToken); await stream.WriteAsync(payload, cancellationToken); await stream.FlushAsync(cancellationToken);
    }
    public static async Task<T> ReadAsync<T>(Stream stream, CancellationToken cancellationToken)
    {
        var header = new byte[4]; await stream.ReadExactlyAsync(header, cancellationToken);
        var length = BinaryPrimitives.ReadInt32LittleEndian(header);
        if (length is < 1 or > MaxFrameBytes) throw new InvalidDataException("Tamaño de mensaje inválido.");
        var payload = new byte[length]; await stream.ReadExactlyAsync(payload, cancellationToken); return Deserialize<T>(payload);
    }
}
[SupportedOSPlatform("windows")]
public sealed class LocalAgentClient(string root)
{
    public async Task<LocalResponse> SendAsync(LocalRequest request, CancellationToken cancellationToken = default)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken); timeout.CancelAfter(TimeSpan.FromSeconds(20));
        await using var pipe = new NamedPipeClientStream(".", AgentPaths.PipeName(root), PipeDirection.InOut, PipeOptions.Asynchronous);
        await pipe.ConnectAsync(timeout.Token);
        using var identity = WindowsIdentity.GetCurrent();
        // Compare the user SID, not the token owner (which may be the Administrators group).
        if (pipe.GetAccessControl().GetOwner(typeof(SecurityIdentifier)) != identity.User)
            throw new UnauthorizedAccessException("Propietario del canal local no válido.");
        await Wire.WriteAsync(pipe, request, timeout.Token);
        var response = await Wire.ReadAsync<LocalResponse>(pipe, timeout.Token);
        // The server must not DisconnectNamedPipe until the whole response has been consumed.
        await pipe.WriteAsync(new byte[] { 1 }, timeout.Token); await pipe.FlushAsync(timeout.Token);
        return response;
    }
}
