using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace Atlas.LocalAgent.Service;

/// <summary>Cross-session kernel object plus canonical/source file locks. No thread-affine mutex ownership.</summary>
public sealed class StationInstanceLease : IDisposable
{
    private readonly SafeWaitHandle _handle;
    private readonly List<FileStream> _files = [];
    private StationInstanceLease(SafeWaitHandle handle) => _handle = handle;
    public static StationInstanceLease Acquire(Guid uuid, string serviceSid, params string[] roots)
    {
        if (uuid == Guid.Empty) throw new ArgumentException("EmptyUuid");
        _ = new System.Security.Principal.SecurityIdentifier(serviceSid);
        if (!ConvertStringSecurityDescriptorToSecurityDescriptorW($"D:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;GA;;;{serviceSid})", 1, out var descriptor, out _)) throw new Win32Exception();
        StationInstanceLease? lease = null;
        try
        {
            var attributes = new SecurityAttributes { Length = Marshal.SizeOf<SecurityAttributes>(), Descriptor = descriptor };
            var handle = CreateMutexW(ref attributes, false, @"Global\Atlas.LocalAgent.Station." + uuid.ToString("N"));
            var error = Marshal.GetLastWin32Error();
            if (handle.IsInvalid) { handle.Dispose(); throw new Win32Exception(error); }
            if (error == 183) { handle.Dispose(); throw new IOException("StationAlreadyRunning"); }
            lease = new(handle);
            foreach (var root in roots.Distinct(StringComparer.OrdinalIgnoreCase))
                lease._files.Add(new FileStream(Path.Combine(root, "service.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None));
            return lease;
        }
        catch { lease?.Dispose(); throw; }
        finally { _ = LocalFree(descriptor); }
    }
    public void Dispose() { foreach (var file in _files) file.Dispose(); _handle.Dispose(); }
    [StructLayout(LayoutKind.Sequential)] private struct SecurityAttributes { public int Length; public IntPtr Descriptor; public int Inherit; }
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true, ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)] private static extern bool ConvertStringSecurityDescriptorToSecurityDescriptorW(string text, uint revision, out IntPtr result, out uint size);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true, ExactSpelling = true)]
    private static extern SafeWaitHandle CreateMutexW(ref SecurityAttributes attributes, [MarshalAs(UnmanagedType.Bool)] bool owner, string name);
    [DllImport("kernel32.dll", ExactSpelling = true)] private static extern IntPtr LocalFree(IntPtr memory);
}
