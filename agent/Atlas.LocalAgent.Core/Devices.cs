using System.Security.Cryptography;
using System.Text;

namespace Atlas.LocalAgent.Core;

public enum DeviceKind { Printer }
public enum PrinterConnection { Unknown, Local, Network }
public sealed record PaperSizeCapability(string Name, int? WidthTenthsMillimeter, int? HeightTenthsMillimeter, int? RawKind = null);
public sealed record PrinterCapabilities(bool? Color, bool? Duplex, int? MaximumCopies, IReadOnlyList<PaperSizeCapability> PaperSizes);
public interface IAtlasDevice { string DeviceId { get; } string Name { get; } DeviceKind Kind { get; } }
public interface IPrinterDevice : IAtlasDevice
{
    uint ReportedStatus { get; }
    bool IsVirtual { get; }
    string Status { get; }
    bool IsDefault { get; }
    PrinterConnection Connection { get; }
    string? Driver { get; }
    PrinterCapabilities Capabilities { get; }
}
public sealed record PrinterDevice(string DeviceId, string Name, string Status, bool IsDefault,
    PrinterConnection Connection, string? Driver, PrinterCapabilities Capabilities) : IPrinterDevice
{
    public uint ReportedStatus { get; init; }
    public bool IsVirtual { get; init; }
    public string? RegistryId { get; init; }
    public DeviceKind Kind => DeviceKind.Printer;
    public static string IdFor(string name) => "printer-" + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(name.Trim().ToUpperInvariant())));
    public static string RegistryIdFor(string name, string? port, string? driver, string? share, bool isVirtual) =>
        IdFor("registry-v1|" + (string.IsNullOrWhiteSpace(port) ? "fallback:" + name : port)
            + "|" + driver + "|" + share + (isVirtual ? "|virtual:" + name : ""));
}
public interface IPrinterDiscovery { Task<IReadOnlyList<PrinterDevice>> EnumerateAsync(CancellationToken cancellationToken); }
public static class DeviceCatalog
{
    public static IReadOnlyList<PrinterDevice> Unique(IEnumerable<PrinterDevice> devices) =>
        devices.GroupBy(x => x.DeviceId, StringComparer.OrdinalIgnoreCase).Select(x => x.First()).OrderBy(x => x.Name, StringComparer.OrdinalIgnoreCase).ToArray();
}
