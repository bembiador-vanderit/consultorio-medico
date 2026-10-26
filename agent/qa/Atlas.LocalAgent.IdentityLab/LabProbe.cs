using System.ComponentModel;
using System.IO.Pipes;
using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text.Json;
using Atlas.LocalAgent.Service;
using Microsoft.Data.Sqlite;

namespace Atlas.LocalAgent.IdentityLab;

public sealed class LabProbe(string root, LabOptions options)
{
    public string Stage { get; private set; } = "Identity";
    private string At(params string[] parts) => Path.Combine(new[] { root }.Concat(parts).ToArray());
    public async Task PrepareAsync()
    {
        RequireSid(options.CreatorSid);
        var bytes = options.SyntheticBytes();
        try { await new WindowsSecretStore(At("user")).StoreAsync("synthetic-user", bytes); }
        finally { CryptographicOperations.ZeroMemory(bytes); }
        File.Copy(At("user", "secrets", "secret.synthetic-user.bin"), At("exchange-a", "secrets", "secret.synthetic-user.bin"));
        await File.WriteAllTextAsync(At("user", "synthetic-identity.json"), JsonSerializer.Serialize(new { options.SyntheticAgentUuid, SyntheticOnly = true }));
    }
    public async Task HandoffAsync(CancellationToken token)
    {
        RequireSid(options.CreatorSid);
        using var pipe = new NamedPipeClientStream(".", options.PipeName, PipeDirection.InOut, PipeOptions.Asynchronous, TokenImpersonationLevel.Identification);
        await pipe.ConnectAsync(token);
        if (pipe.GetAccessControl().GetOwner(typeof(SecurityIdentifier))?.Value != options.CandidateSid) throw new UnauthorizedAccessException("WrongServerOwner");
        using var secret = await new WindowsSecretStore(At("user")).ReadAsync("synthetic-user", token) ?? throw new InvalidDataException();
        options.RequireSynthetic(secret.Bytes.Span);
        await LabPipe.WriteAsync(pipe, secret.Bytes, token);
        var ack = new byte[1]; await pipe.ReadExactlyAsync(ack, token);
        if (ack[0] != 1) throw new InvalidDataException("HandoffNotAcknowledged");
    }
    public async Task<Dictionary<string, object?>> CandidateAsync(CancellationToken token)
    {
        RequireSid(options.CandidateSid);
        var report = IdentityReport();
        Stage = "WrongUserCiphertext";
        report["WrongUserBlobDenied"] = await DecryptDeniedAsync(At("exchange-a"), "synthetic-user");
        report["OtherUserSecretsAclDenied"] = AccessDenied(At("user", "secrets", "secret.synthetic-user.bin"));
        if (options.Phase == 1)
        {
            Stage = "CreateSyntheticPipe";
            using var pipe = LabPipe.Create(options);
            await pipe.WaitForConnectionAsync(token);
            Stage = "IdentifySyntheticCaller";
            string? caller = null;
            pipe.RunAsClient(() => caller = WindowsIdentity.GetCurrent().User?.Value);
            if (caller != options.CreatorSid) throw new UnauthorizedAccessException("WrongBootstrapCaller");
            Stage = "ReadSyntheticFrame";
            var bytes = await LabPipe.ReadAsync(pipe, token);
            try { options.RequireSynthetic(bytes); Stage = "ProtectAsService"; await new WindowsSecretStore(At("service")).StoreAsync("synthetic-migrated", bytes, token); }
            finally { CryptographicOperations.ZeroMemory(bytes); }
            Stage = "ReadOwnServiceSecret";
            using var check = await new WindowsSecretStore(At("service")).ReadAsync("synthetic-migrated", token) ?? throw new InvalidDataException();
            options.RequireSynthetic(check.Bytes.Span);
            await pipe.WriteAsync(new byte[] { 1 }, token); await pipe.FlushAsync(token);
        }
        using (var secret = await new WindowsSecretStore(At("service")).ReadAsync("synthetic-migrated", token) ?? throw new InvalidDataException())
            options.RequireSynthetic(secret.Bytes.Span);
        report["SameServiceAccountDecrypt"] = true;
        report["RestartDpapiRecovered"] = options.Phase == 2;
        File.Copy(At("service", "secrets", "secret.synthetic-migrated.bin"), At("exchange-b", "secrets", "secret.synthetic-migrated.bin"), true);
        await File.WriteAllTextAsync(At("service", "data", "synthetic-identity.json"), JsonSerializer.Serialize(new { options.SyntheticAgentUuid, SyntheticOnly = true }), token);
        Stage = "SyntheticSqlite";
        Sqlite(report);
        Stage = "PrinterReadOnly";
        var printers = await new WindowsPrinterDiscovery().EnumerateAsync(token);
        var printer = printers.FirstOrDefault(p => !string.IsNullOrWhiteSpace(p.RegistryId)
            && !string.IsNullOrWhiteSpace(p.Driver) && OpenPrinterReadOnly(p.Name));
        report["PrinterCount"] = printers.Count; report["PrinterWithCapabilitiesFound"] = printer is not null;
        report["PrinterStableId"] = printer?.RegistryId; report["PrinterDriver"] = printer?.Driver;
        report["PrinterOpenReadApi"] = printer is not null;
        report["SpoolerQueryable"] = await new WindowsGdiPrintBackend().IsSpoolerAvailableAsync(token);
        Stage = "HttpsHealth";
        var endpoint = LabOptions.ValidateHealth(options.HealthEndpoint);
        report["DnsResolved"] = (await Dns.GetHostAddressesAsync(endpoint.Host, token)).Length > 0;
        using var http = AtlasRegistryClient.CreateHttpClient();
        using var response = await http.GetAsync(endpoint, HttpCompletionOption.ResponseHeadersRead, token);
        report["HttpsStatus"] = (int)response.StatusCode;
        report["HttpsCertificateValidation"] = "PlatformDefaultTls12Or13NoBypass";
        report["PhysicalPrintsSent"] = 0;
        return report;
    }
    public async Task<Dictionary<string, object?>> ObserverAsync()
    {
        RequireSid(options.ObserverSid);
        var report = IdentityReport();
        report["CandidateSecretsAclDenied"] = AccessDenied(At("service", "secrets", "secret.synthetic-migrated.bin"));
        report["CopiedCandidateBlobDenied"] = await DecryptDeniedAsync(At("exchange-b"), "synthetic-migrated");
        report["PhysicalPrintsSent"] = 0;
        return report;
    }
    public async Task<Dictionary<string, object?>> VerifyAsync()
    {
        RequireSid(options.CreatorSid);
        var report = IdentityReport();
        using (var own = await new WindowsSecretStore(At("user")).ReadAsync("synthetic-user") ?? throw new InvalidDataException()) options.RequireSynthetic(own.Bytes.Span);
        report["CreatorOwnDecrypt"] = true;
        report["CreatorCannotDecryptCandidateCopy"] = await DecryptDeniedAsync(At("exchange-b"), "synthetic-migrated");
        using var before = JsonDocument.Parse(File.ReadAllBytes(At("user", "synthetic-identity.json")));
        using var after = JsonDocument.Parse(File.ReadAllBytes(At("service", "data", "synthetic-identity.json")));
        report["SyntheticUuidPreserved"] = before.RootElement.GetProperty("SyntheticAgentUuid").GetGuid() == after.RootElement.GetProperty("SyntheticAgentUuid").GetGuid();
        var bytes = options.SyntheticBytes();
        try
        {
            // Private service-only ciphertext is mirrored, still encrypted, in exchange-b.
            // Do not take ownership or widen that ACL just to scan it as the administrator.
            report["NoPlaintextRuntimeArtifacts"] = Directory.EnumerateFiles(root, "*", new EnumerationOptions
                { RecurseSubdirectories = true, IgnoreInaccessible = true, AttributesToSkip = FileAttributes.ReparsePoint })
                .Where(p => !p.StartsWith(At("bin") + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                .All(p => File.ReadAllBytes(p).AsSpan().IndexOf(bytes) < 0);
        }
        finally { CryptographicOperations.ZeroMemory(bytes); }
        return report;
    }
    private Dictionary<string, object?> IdentityReport()
    {
        using var identity = WindowsIdentity.GetCurrent();
        var profile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        return new() { ["Phase"] = options.Phase, ["SyntheticAgentUuid"] = options.SyntheticAgentUuid,
            ["WindowsIdentity"] = identity.Name, ["WindowsSid"] = identity.User?.Value,
            ["IsAdministrator"] = new WindowsPrincipal(identity).IsInRole(WindowsBuiltInRole.Administrator),
            ["ProfilePath"] = profile, ["ProfileDirectoryPresent"] = Directory.Exists(profile),
            ["SafeValidation"] = true, ["PhysicalGlobal"] = false, ["AllowedJobId"] = null };
    }
    private void Sqlite(Dictionary<string, object?> report)
    {
        var path = At("service", "data", "synthetic.sqlite");
        if (options.Phase == 2 && !File.Exists(path)) throw new InvalidDataException("SyntheticSqliteMissingOnRestart");
        var connection = new SqliteConnectionStringBuilder { DataSource = path, Pooling = false, DefaultTimeout = 1 }.ToString();
        using var db = new SqliteConnection(connection); db.Open();
        using (var cmd = db.CreateCommand()) { cmd.CommandText = "CREATE TABLE IF NOT EXISTS lab_state(id INTEGER PRIMARY KEY, uuid TEXT NOT NULL, runs INTEGER NOT NULL)"; cmd.ExecuteNonQuery(); }
        using (var cmd = db.CreateCommand()) { cmd.CommandText = "INSERT OR IGNORE INTO lab_state VALUES(1,$uuid,0)"; cmd.Parameters.AddWithValue("$uuid", options.SyntheticAgentUuid.ToString()); cmd.ExecuteNonQuery(); }
        using (var tx = db.BeginTransaction())
        {
            using var read = db.CreateCommand(); read.Transaction = tx; read.CommandText = "SELECT uuid || ':' || runs FROM lab_state WHERE id=1";
            if ((string?)read.ExecuteScalar() != options.SyntheticAgentUuid + ":" + (options.Phase - 1)) throw new InvalidDataException("SyntheticSqliteStateMismatch");
            using var update = db.CreateCommand(); update.Transaction = tx; update.CommandText = "UPDATE lab_state SET runs=runs+1 WHERE id=1"; update.ExecuteNonQuery(); tx.Commit();
        }
        using (var tx = db.BeginTransaction())
        {
            using var update = db.CreateCommand(); update.Transaction = tx; update.CommandText = "UPDATE lab_state SET runs=runs+100 WHERE id=1"; update.ExecuteNonQuery();
            using var other = new SqliteConnection(connection); other.Open();
            try { using var conflict = other.BeginTransaction(); report["SqliteLockEnforced"] = false; }
            catch (SqliteException ex) when (ex.SqliteErrorCode == 5) { report["SqliteLockEnforced"] = true; }
            tx.Rollback();
        }
        using var check = db.CreateCommand(); check.CommandText = "SELECT runs FROM lab_state WHERE id=1";
        report["SqliteReadWriteRollback"] = (long)check.ExecuteScalar()! == options.Phase;
        report["SqliteRestartRecovered"] = options.Phase == 2;
    }
    private static async Task<bool> DecryptDeniedAsync(string store, string key)
    {
        try { using var value = await new WindowsSecretStore(store).ReadAsync(key); return false; }
        catch (Win32Exception) { return true; }
    }
    private static bool AccessDenied(string path)
    {
        try { using var file = File.OpenRead(path); return false; }
        catch (UnauthorizedAccessException) { return true; }
    }
    private static void RequireSid(string expected)
    {
        if (WindowsIdentity.GetCurrent().User?.Value != expected) throw new UnauthorizedAccessException("LabIdentityMismatch");
    }
    private static bool OpenPrinterReadOnly(string name)
    {
        if (!OpenPrinterW(name, out var printer, IntPtr.Zero)) return false;
        ClosePrinter(printer); return true;
    }
    [DllImport("winspool.drv", CharSet = CharSet.Unicode, SetLastError = true, ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)] private static extern bool OpenPrinterW(string name, out IntPtr printer, IntPtr defaults);
    [DllImport("winspool.drv", ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)] private static extern bool ClosePrinter(IntPtr printer);
}
