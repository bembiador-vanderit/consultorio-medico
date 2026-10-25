using System.Text.Json;
using System.Text.RegularExpressions;

namespace Atlas.LocalAgent.Core;

public static class AgentVersion
{
    public const string Current = "1.2.0-dev";
    public const int Protocol = 3;
}

public sealed record AgentIdentity(Guid AgentId, DateTimeOffset CreatedAt);
public sealed record AtlasAssociation(string? OrganizationId = null, string? CenterId = null, string? WorkgroupId = null);
public sealed record StationConfiguration(string StationName, string DisplayCode, AtlasAssociation Association)
{
    public StationConfiguration Validate()
    {
        if (string.IsNullOrWhiteSpace(StationName) || StationName.Length > 100 || StationName.Any(char.IsControl))
            throw new ArgumentException("Nombre de estación inválido.");
        if (!Regex.IsMatch(DisplayCode, "^[A-Z0-9][A-Z0-9-]{1,31}$", RegexOptions.CultureInvariant))
            throw new ArgumentException("Código visible inválido.");
        if (Association is null || new[] { Association.OrganizationId, Association.CenterId, Association.WorkgroupId }
            .Any(x => x is not null && (x.Length > 100 || x.Any(char.IsControl))))
            throw new ArgumentException("Asociación inválida.");
        return this;
    }
}

public sealed class LocalIdentityStore(string root)
{
    private readonly string _root = Path.GetFullPath(root);

    public async Task<AgentIdentity> LoadOrCreateAsync(CancellationToken cancellationToken = default)
    {
        Directory.CreateDirectory(_root);
        using var held = await AcquireAsync(cancellationToken);
        var path = Path.Combine(_root, "identity.json");
        if (File.Exists(path))
        {
            var identity = Wire.Deserialize<AgentIdentity>(await File.ReadAllBytesAsync(path, cancellationToken));
            if (identity.AgentId == Guid.Empty || identity.CreatedAt == default)
                throw new InvalidDataException("Identidad inválida; no se reemplaza automáticamente.");
            return identity;
        }
        var created = new AgentIdentity(Guid.NewGuid(), DateTimeOffset.UtcNow);
        await AtomicWriteAsync(path, Wire.Serialize(created), cancellationToken);
        return created;
    }

    public async Task<StationConfiguration> LoadConfigurationAsync(AgentIdentity identity, CancellationToken cancellationToken = default)
    {
        using var held = await AcquireAsync(cancellationToken);
        var path = Path.Combine(_root, "station.json");
        if (File.Exists(path))
            return Wire.Deserialize<StationConfiguration>(await File.ReadAllBytesAsync(path, cancellationToken)).Validate();
        var configuration = new StationConfiguration(Environment.MachineName, "ATLAS-" + identity.AgentId.ToString("N")[..8].ToUpperInvariant(), new());
        await AtomicWriteAsync(path, Wire.Serialize(configuration.Validate()), cancellationToken);
        return configuration;
    }

    public async Task SaveConfigurationAsync(StationConfiguration configuration, CancellationToken cancellationToken = default)
    {
        configuration.Validate();
        using var held = await AcquireAsync(cancellationToken);
        await AtomicWriteAsync(Path.Combine(_root, "station.json"), Wire.Serialize(configuration), cancellationToken);
    }

    private async Task<FileStream> AcquireAsync(CancellationToken cancellationToken)
    {
        Directory.CreateDirectory(_root);
        for (var attempt = 0; ; attempt++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            try { return new FileStream(Path.Combine(_root, "identity.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None); }
            catch (IOException) when (attempt < 100) { await Task.Delay(50, cancellationToken); }
        }
    }

    private static async Task AtomicWriteAsync(string path, byte[] data, CancellationToken cancellationToken)
    {
        var temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            await File.WriteAllBytesAsync(temporary, data, cancellationToken);
            File.Move(temporary, path, overwrite: true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
}
