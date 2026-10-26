using System.Buffers.Binary;
using System.ComponentModel;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Security.Principal;
using Microsoft.Win32.SafeHandles;

namespace Atlas.LocalAgent.IdentityLab;

// Separate QA-only pipe. The production current-user-only IPC is not changed.
internal static class LabPipe
{
    public static NamedPipeServerStream Create(LabOptions options)
    {
        if (WindowsIdentity.GetCurrent().User?.Value != options.CandidateSid) throw new UnauthorizedAccessException("WrongCandidate");
        var sddl = $"O:{options.CandidateSid}D:P(A;;GA;;;{options.CandidateSid})(A;;GA;;;{options.CreatorSid})";
        if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, out var descriptor, out _)) throw new Win32Exception();
        try
        {
            var attributes = new SecurityAttributes { Length = Marshal.SizeOf<SecurityAttributes>(), Descriptor = descriptor };
            // Duplex + overlapped + first-instance; PIPE_REJECT_REMOTE_CLIENTS.
            var handle = CreateNamedPipeW(@"\\.\pipe\" + options.PipeName, 0x40080003, 8, 1, 512, 512, 0, ref attributes);
            if (handle.IsInvalid) { var error = Marshal.GetLastWin32Error(); handle.Dispose(); throw new Win32Exception(error); }
            try { return new NamedPipeServerStream(PipeDirection.InOut, true, false, handle); }
            catch { handle.Dispose(); throw; }
        }
        finally { LocalFree(descriptor); }
    }
    public static async Task<byte[]> ReadAsync(Stream stream, CancellationToken token)
    {
        var header = new byte[4]; await stream.ReadExactlyAsync(header, token);
        var length = BinaryPrimitives.ReadInt32LittleEndian(header);
        if (length is < 1 or > 256) throw new InvalidDataException("InvalidSyntheticFrame");
        var value = new byte[length];
        try { await stream.ReadExactlyAsync(value, token); return value; }
        catch { System.Security.Cryptography.CryptographicOperations.ZeroMemory(value); throw; }
    }
    public static async Task WriteAsync(Stream stream, ReadOnlyMemory<byte> value, CancellationToken token)
    {
        if (value.Length is < 1 or > 256) throw new InvalidDataException("InvalidSyntheticFrame");
        var header = new byte[4]; BinaryPrimitives.WriteInt32LittleEndian(header, value.Length);
        await stream.WriteAsync(header, token); await stream.WriteAsync(value, token); await stream.FlushAsync(token);
    }
    [StructLayout(LayoutKind.Sequential)] private struct SecurityAttributes { public int Length; public IntPtr Descriptor; public int Inherit; }
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true, ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)] private static extern bool ConvertStringSecurityDescriptorToSecurityDescriptorW(string sddl, uint revision, out IntPtr descriptor, out uint size);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true, ExactSpelling = true)]
    private static extern SafePipeHandle CreateNamedPipeW(string name, uint mode, uint pipeMode, uint instances, uint output, uint input, uint timeout, ref SecurityAttributes attributes);
    [DllImport("kernel32.dll", ExactSpelling = true)] private static extern IntPtr LocalFree(IntPtr memory);
}
