using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Data.Sqlite;

namespace Atlas.LocalAgent.Service;

public static class ServiceStateMigration
{
    public static void Copy(ServiceConfiguration configuration)
    {
        ServiceCredentialHandoff.RequireSid(configuration.SourceUserSid);
        configuration.VerifyIdentity(configuration.SourceRoot);
        if (Directory.Exists(configuration.DataPath) && Directory.EnumerateFileSystemEntries(configuration.DataPath).Any())
            throw new InvalidOperationException("RefuseNonemptyDestination");
        using var locked = new FileStream(Path.Combine(configuration.SourceRoot, "service.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        CopyDirectory(configuration.SourceRoot, configuration.DataPath);
        configuration.VerifyIdentity(configuration.DataPath);
        foreach (var source in Directory.EnumerateFiles(configuration.SourceRoot, "*.sqlite", SearchOption.AllDirectories))
        {
            if ((File.GetAttributes(source) & FileAttributes.ReparsePoint) != 0) throw new InvalidDataException("SqliteLinkDenied");
            var target = Path.Combine(configuration.DataPath, Path.GetRelativePath(configuration.SourceRoot, source));
            using (var from = Open(source, SqliteOpenMode.ReadOnly))
            using (var to = Open(target, SqliteOpenMode.ReadWriteCreate)) from.BackupDatabase(to);
            if (LogicalFingerprint(source) != LogicalFingerprint(target)) throw new InvalidDataException("SqliteCopyMismatch");
        }
    }
    private static void CopyDirectory(string source, string target)
    {
        if ((File.GetAttributes(source) & FileAttributes.ReparsePoint) != 0) throw new InvalidDataException("SourceLinkDenied");
        Directory.CreateDirectory(target);
        foreach (var file in Directory.EnumerateFiles(source))
        {
            var name = Path.GetFileName(file);
            if (name.EndsWith(".lock", StringComparison.OrdinalIgnoreCase) || name.EndsWith(".sqlite", StringComparison.OrdinalIgnoreCase)
                || name.EndsWith(".sqlite-wal", StringComparison.OrdinalIgnoreCase) || name.EndsWith(".sqlite-shm", StringComparison.OrdinalIgnoreCase)) continue;
            if ((File.GetAttributes(file) & FileAttributes.ReparsePoint) != 0) throw new InvalidDataException("SourceFileLinkDenied");
            File.Copy(file, Path.Combine(target, name), false);
        }
        foreach (var directory in Directory.EnumerateDirectories(source))
            // The only real credential transfer is memory-only under the destination identity.
            if (Path.GetFileName(directory) is not ("secrets" or "logs")) CopyDirectory(directory, Path.Combine(target, Path.GetFileName(directory)));
    }
    public static string LogicalFingerprint(string path)
    {
        using var db = Open(path, SqliteOpenMode.ReadOnly);
        using var tx = db.BeginTransaction();
        using var integrity = db.CreateCommand(); integrity.Transaction = tx; integrity.CommandText = "PRAGMA integrity_check";
        if (integrity.ExecuteScalar() as string != "ok") throw new InvalidDataException("SqliteIntegrityFailure");
        using var names = db.CreateCommand(); names.Transaction = tx;
        names.CommandText = "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name";
        var schema = new List<(string, string?)>();
        using (var rows = names.ExecuteReader()) while (rows.Read()) schema.Add((rows.GetString(0), rows.IsDBNull(1) ? null : rows.GetString(1)));
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        foreach (var (name, sql) in schema)
        {
            hash.AppendData(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new { name, sql }) + "\n"));
            if (sql is null || !sql.StartsWith("CREATE TABLE", StringComparison.OrdinalIgnoreCase)) continue;
            using var command = db.CreateCommand(); command.Transaction = tx;
            command.CommandText = "SELECT * FROM \"" + name.Replace("\"", "\"\"", StringComparison.Ordinal) + "\"";
            var serialized = new List<string>();
            using (var rows = command.ExecuteReader())
                while (rows.Read())
                {
                    var values = new object[rows.FieldCount]; rows.GetValues(values);
                    serialized.Add(JsonSerializer.Serialize(values.Select(v => v is DBNull ? null : v).ToArray()));
                }
            foreach (var row in serialized.Order(StringComparer.Ordinal)) hash.AppendData(Encoding.UTF8.GetBytes(row + "\n"));
        }
        tx.Commit(); return Convert.ToHexStringLower(hash.GetHashAndReset());
    }
    private static SqliteConnection Open(string path, SqliteOpenMode mode)
    {
        var db = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = path, Mode = mode, Pooling = false }.ToString()); db.Open(); return db;
    }
}
