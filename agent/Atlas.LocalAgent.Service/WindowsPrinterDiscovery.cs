using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
using Atlas.LocalAgent.Core;

namespace Atlas.LocalAgent.Service;

public sealed class WindowsPrinterDiscovery : IPrinterDiscovery
{
    private readonly object _gate = new();
    private Task<IReadOnlyList<PrinterDevice>>? _pending;
    public Task<IReadOnlyList<PrinterDevice>> EnumerateAsync(CancellationToken cancellationToken)
    {
        lock (_gate)
        {
            // A hung third-party driver cannot spawn unbounded tasks on repeated refreshes.
            if (_pending is null || _pending.IsCompleted) _pending = Task.Run(EnumerateNative);
            return _pending.WaitAsync(TimeSpan.FromSeconds(15), cancellationToken);
        }
    }
    private static IReadOnlyList<PrinterDevice> EnumerateNative()
    {
        if (!OperatingSystem.IsWindows()) throw new PlatformNotSupportedException();
        _ = EnumPrinters(6, null, 2, IntPtr.Zero, 0, out var needed, out _);
        if (needed == 0)
        {
            var error = Marshal.GetLastWin32Error();
            if (error is not (0 or 122)) throw new Win32Exception(error);
            return [];
        }
        if (needed > 8 * 1024 * 1024) throw new InvalidDataException("Inventario demasiado grande.");
        var buffer = Marshal.AllocHGlobal(checked((int)needed));
        try
        {
            if (!EnumPrinters(6, null, 2, buffer, needed, out _, out var count)) throw new Win32Exception(Marshal.GetLastWin32Error());
            var size = Marshal.SizeOf<PrinterInfo2>();
            if (count > needed / size) throw new InvalidDataException("Inventario inválido.");
            var defaultPrinter = DefaultPrinter(); var result = new List<PrinterDevice>();
            for (var i = 0; i < count; i++)
            {
                var info = Marshal.PtrToStructure<PrinterInfo2>(IntPtr.Add(buffer, checked((int)i * size)));
                var name = Marshal.PtrToStringUni(info.PrinterName);
                if (string.IsNullOrWhiteSpace(name)) continue;
                var port = Marshal.PtrToStringUni(info.PortName);
                var connection = (info.Attributes & 0x10) != 0 ? PrinterConnection.Network : (info.Attributes & 0x40) != 0 ? PrinterConnection.Local : PrinterConnection.Unknown;
                result.Add(new(PrinterDevice.IdFor(name), name, Status(info.Status), string.Equals(name, defaultPrinter, StringComparison.OrdinalIgnoreCase),
                    connection, Marshal.PtrToStringUni(info.DriverName), Capabilities(name, port))
                { ReportedStatus = info.Status, IsVirtual = IsVirtualPrinter(name, port),
                    RegistryId = PrinterDevice.RegistryIdFor(name, port, Marshal.PtrToStringUni(info.DriverName),
                        Marshal.PtrToStringUni(info.ShareName), IsVirtualPrinter(name, port)) });
            }
            return DeviceCatalog.Unique(result);
        }
        finally { Marshal.FreeHGlobal(buffer); }
    }
    private static string? DefaultPrinter()
    {
        uint length = 0; _ = GetDefaultPrinter(null, ref length);
        if (length is 0 or > 32768) return null;
        var name = new StringBuilder(checked((int)length)); return GetDefaultPrinter(name, ref length) ? name.ToString() : null;
    }
    private static string Status(uint status) => status == 0 ? "Sin alertas reportadas" : $"{((status & 0x80) != 0 ? "Sin conexión" : (status & 2) != 0 ? "Error" : (status & 1) != 0 ? "Pausada" : "Estado informado por Windows")} (0x{status:X8})";
    private static bool IsVirtualPrinter(string name, string? port) =>
        (port?.Contains("FILE:", StringComparison.OrdinalIgnoreCase) ?? false) || (port?.Contains("PORTPROMPT", StringComparison.OrdinalIgnoreCase) ?? false)
        || new[] { "PDF", "XPS", "Fax", "AnyDesk", "RustDesk", "OneNote" }.Any(x => name.Contains(x, StringComparison.OrdinalIgnoreCase));
    private static PrinterCapabilities Capabilities(string name, string? port)
    {
        bool? Flag(ushort capability) { var result = DeviceCapabilities(name, port, capability, IntPtr.Zero, IntPtr.Zero); return result < 0 ? null : result != 0; }
        var copies = DeviceCapabilities(name, port, 18, IntPtr.Zero, IntPtr.Zero);
        var papers = new List<PaperSizeCapability>();
        var count = DeviceCapabilities(name, port, 16, IntPtr.Zero, IntPtr.Zero);
        if (count is > 0 and <= 512)
        {
            var names = Marshal.AllocHGlobal(512 * 64 * 2); var sizes = Marshal.AllocHGlobal(512 * 8); var ids = Marshal.AllocHGlobal(512 * 2);
            try
            {
                var returned = DeviceCapabilities(name, port, 16, names, IntPtr.Zero);
                var dimensions = DeviceCapabilities(name, port, 3, sizes, IntPtr.Zero);
                var idCount = DeviceCapabilities(name, port, 2, ids, IntPtr.Zero);
                if (returned is > 0 and <= 512)
                    for (var i = 0; i < returned; i++)
                    {
                        var label = (Marshal.PtrToStringUni(IntPtr.Add(names, i * 128), 64) ?? "").Split('\0')[0].Trim();
                        if (label.Length == 0) continue;
                        var width = dimensions > i ? Marshal.ReadInt32(sizes, i * 8) : 0;
                        var height = dimensions > i ? Marshal.ReadInt32(sizes, i * 8 + 4) : 0;
                        var rawKind = idCount > i && idCount <= 512 ? (ushort)Marshal.ReadInt16(ids, i * 2) : (int?)null;
                        papers.Add(new(label, width > 0 ? width : null, height > 0 ? height : null, rawKind));
                    }
            }
            finally { Marshal.FreeHGlobal(names); Marshal.FreeHGlobal(sizes); Marshal.FreeHGlobal(ids); }
        }
        return new(Flag(32), Flag(7), copies > 0 ? copies : null, papers);
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct PrinterInfo2
    {
        public IntPtr ServerName, PrinterName, ShareName, PortName, DriverName, Comment, Location, DevMode, SeparatorFile, PrintProcessor, DataType, Parameters, SecurityDescriptor;
        public uint Attributes, Priority, DefaultPriority, StartTime, UntilTime, Status, Jobs, AveragePagesPerMinute;
    }
    [DllImport("winspool.drv", EntryPoint = "EnumPrintersW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)] private static extern bool EnumPrinters(uint flags, string? name, uint level, IntPtr buffer, uint size, out uint needed, out uint returned);
    [DllImport("winspool.drv", EntryPoint = "GetDefaultPrinterW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)] private static extern bool GetDefaultPrinter(StringBuilder? name, ref uint size);
    [DllImport("winspool.drv", EntryPoint = "DeviceCapabilitiesW", CharSet = CharSet.Unicode)]
    private static extern int DeviceCapabilities(string device, string? port, ushort capability, IntPtr output, IntPtr devMode);
}
