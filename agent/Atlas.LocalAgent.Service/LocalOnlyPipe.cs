using System.ComponentModel;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Security.Principal;
using Microsoft.Win32.SafeHandles;

namespace Atlas.LocalAgent.Service;

internal static class LocalOnlyPipe
{
    // CurrentUserOnly by itself restricts the ACL, but does not reject remote SMB clients.
    private const uint DuplexOverlappedFirstInstance = 0x00000003 | 0x40000000 | 0x00080000;
    private const uint RejectRemoteClients = 0x00000008;

    public static NamedPipeServerStream Create(string name, string? authorizedLocalSid = null)
    {
        using var identity = WindowsIdentity.GetCurrent();
        var sid = identity.User?.Value ?? throw new InvalidOperationException("Identidad Windows no disponible.");
        if (authorizedLocalSid is not null) _ = new SecurityIdentifier(authorizedLocalSid);
        var extra = authorizedLocalSid is null ? "" : $"(A;;GA;;;{authorizedLocalSid})";
        if (!ConvertStringSecurityDescriptorToSecurityDescriptorW($"O:{sid}D:P(A;;GA;;;{sid}){extra}", 1, out var descriptor, out _))
            throw new Win32Exception(Marshal.GetLastWin32Error());
        try
        {
            var attributes = new SecurityAttributes { Length = Marshal.SizeOf<SecurityAttributes>(), Descriptor = descriptor };
            var handle = CreateNamedPipeW(@"\\.\pipe\" + name, DuplexOverlappedFirstInstance,
                RejectRemoteClients, 1, 4096, 4096, 0, ref attributes);
            if (handle.IsInvalid)
            {
                var error = Marshal.GetLastWin32Error(); handle.Dispose(); throw new Win32Exception(error);
            }
            try { return new NamedPipeServerStream(PipeDirection.InOut, isAsync: true, isConnected: false, handle); }
            catch { handle.Dispose(); throw; }
        }
        finally { LocalFree(descriptor); }
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct SecurityAttributes
    {
        public int Length;
        public IntPtr Descriptor;
        public int InheritHandle;
    }
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true, ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool ConvertStringSecurityDescriptorToSecurityDescriptorW(string descriptor, uint revision, out IntPtr result, out uint size);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true, ExactSpelling = true)]
    private static extern SafePipeHandle CreateNamedPipeW(string name, uint openMode, uint pipeMode, uint maxInstances,
        uint outBufferSize, uint inBufferSize, uint timeout, ref SecurityAttributes attributes);
    [DllImport("kernel32.dll", ExactSpelling = true)]
    private static extern IntPtr LocalFree(IntPtr memory);
}
