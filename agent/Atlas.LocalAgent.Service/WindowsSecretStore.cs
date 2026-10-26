using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text.RegularExpressions;
using Atlas.LocalAgent.Core;

namespace Atlas.LocalAgent.Service;

/// <summary>DPAPI CurrentUser; never machine-wide plaintext or shared service credentials.</summary>
public sealed class WindowsSecretStore(string root) : ISecureSecretStore
{
    private readonly string _root = Path.Combine(Path.GetFullPath(root), "secrets");
    private string SecretPath(string key)
    {
        if (!Regex.IsMatch(key, "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$", RegexOptions.CultureInvariant)) throw new ArgumentException("Clave inválida.");
        return Path.Combine(_root, "secret." + key + ".bin");
    }
    public async Task StoreAsync(string key, ReadOnlyMemory<byte> secret, CancellationToken cancellationToken = default)
    {
        var path = SecretPath(key);
        if (secret.Length is < 1 or > 16384) throw new ArgumentException("Tamaño de secreto inválido.");
        Directory.CreateDirectory(_root);
        using var identity = WindowsIdentity.GetCurrent();
        var owner = identity.User ?? throw new InvalidOperationException("Identidad Windows ausente.");
        var security = new DirectorySecurity(); security.SetAccessRuleProtection(true, false); security.SetOwner(owner);
        security.AddAccessRule(new FileSystemAccessRule(owner, FileSystemRights.FullControl, InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit, PropagationFlags.None, AccessControlType.Allow));
        new DirectoryInfo(_root).SetAccessControl(security);
        var encrypted = Transform(secret.Span, protect: true);
        var temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try { await File.WriteAllBytesAsync(temporary, encrypted, cancellationToken); File.Move(temporary, path, overwrite: true); }
        finally { if (File.Exists(temporary)) File.Delete(temporary); CryptographicOperations.ZeroMemory(encrypted); }
    }
    public async Task<SecretBuffer?> ReadAsync(string key, CancellationToken cancellationToken = default)
    {
        var path = SecretPath(key); if (!File.Exists(path)) return null;
        if (new FileInfo(path).Length > 32768) throw new InvalidDataException("Secreto protegido demasiado grande.");
        var encrypted = await File.ReadAllBytesAsync(path, cancellationToken);
        try
        {
            if (encrypted.Length > 32768) throw new InvalidDataException("Secreto protegido demasiado grande.");
            return new SecretBuffer(Transform(encrypted, protect: false));
        }
        finally { CryptographicOperations.ZeroMemory(encrypted); }
    }
    public Task RemoveAsync(string key, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested(); File.Delete(SecretPath(key)); return Task.CompletedTask;
    }
    private static byte[] Transform(ReadOnlySpan<byte> bytes, bool protect)
    {
        var input = new DataBlob { Length = bytes.Length, Data = Marshal.AllocHGlobal(bytes.Length) };
        var output = new DataBlob();
        var copy = bytes.ToArray();
        try
        {
            Marshal.Copy(copy, 0, input.Data, copy.Length);
            var succeeded = protect ? CryptProtectData(ref input, null, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, 1, out output)
                : CryptUnprotectData(ref input, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, 1, out output);
            if (!succeeded) throw new Win32Exception(Marshal.GetLastWin32Error());
            if (output.Length is < 1 or > 32768) throw new InvalidDataException("Respuesta DPAPI inválida.");
            var result = new byte[output.Length]; Marshal.Copy(output.Data, result, 0, result.Length); return result;
        }
        finally
        {
            CryptographicOperations.ZeroMemory(copy);
            for (var i = 0; i < input.Length; i++) Marshal.WriteByte(input.Data, i, 0);
            Marshal.FreeHGlobal(input.Data);
            if (output.Data != IntPtr.Zero)
            {
                for (var i = 0; i < output.Length; i++) Marshal.WriteByte(output.Data, i, 0);
                _ = LocalFree(output.Data);
            }
        }
    }
    [StructLayout(LayoutKind.Sequential)] private struct DataBlob { public int Length; public IntPtr Data; }
    [DllImport("crypt32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)] private static extern bool CryptProtectData(ref DataBlob input, string? description, IntPtr entropy, IntPtr reserved, IntPtr prompt, uint flags, out DataBlob output);
    [DllImport("crypt32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)] private static extern bool CryptUnprotectData(ref DataBlob input, IntPtr description, IntPtr entropy, IntPtr reserved, IntPtr prompt, uint flags, out DataBlob output);
    [DllImport("kernel32.dll")] private static extern IntPtr LocalFree(IntPtr memory);
}
