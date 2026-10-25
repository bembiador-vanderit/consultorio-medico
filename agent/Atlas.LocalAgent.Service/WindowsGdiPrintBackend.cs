using System.Runtime.InteropServices;
using Atlas.LocalAgent.Core;

namespace Atlas.LocalAgent.Service;

/// <summary>One synthetic GDI page. No shell, PDF reader, RAW commands or persistent printer settings.</summary>
public sealed class WindowsGdiPrintBackend(bool allowPhysicalPrinting = false) : ILocalPrintBackend
{
    public Task<bool> IsSpoolerAvailableAsync(CancellationToken cancellationToken) => Task.Run(() =>
    {
        cancellationToken.ThrowIfCancellationRequested();
        var manager = OpenSCManagerW(null, null, 1); if (manager == IntPtr.Zero) return false;
        try
        {
            var service = OpenServiceW(manager, "Spooler", 4); if (service == IntPtr.Zero) return false;
            try { return QueryServiceStatus(service, out var status) && status.CurrentState == 4; }
            finally { CloseServiceHandle(service); }
        }
        finally { CloseServiceHandle(manager); }
    }, cancellationToken);

    public Task<SpoolSubmission> SubmitAsync(SyntheticPrintDocument document, Func<bool> beginSpooling,
        Action<int> spoolerAccepted, CancellationToken cancellationToken) => Task.Run(() =>
    {
        if (!allowPhysicalPrinting) throw new LocalPrintException(PrintFailure.PhysicalPrintingDisabled);
        if (document.Printer.IsVirtual || document.Job.Copies != 1 || document.Job.Format != PrintDocumentFormat.PlainText
            || !(document.OfficialRoutingQa
                ? document.Job.DocumentReference == "physical-routing-qa" && document.Job.DocumentType == "physical_routing_qa"
                : document.Job.DocumentReference == "atlas-synthetic-test-v1:" + document.Format)
            || document.Job.TargetPrinter != (document.OfficialRoutingQa ? document.Printer.RegistryId??document.Printer.DeviceId : document.Printer.DeviceId)
            || document.Paper != SyntheticPaper.Match(document.Printer, document.Format))
            throw new LocalPrintException(PrintFailure.InvalidSelection);
        cancellationToken.ThrowIfCancellationRequested();
        using var context = CreateContext(document);
        var layout = Plan(document, context.Dc);
        // No cancellation can be promised after this durable boundary, even if StartDoc blocks.
        cancellationToken.ThrowIfCancellationRequested();
        if (!beginSpooling()) throw new OperationCanceledException();
        var info = new DocInfo { Size = Marshal.SizeOf<DocInfo>(), Name = "Atlas Synthetic Test " + document.Job.Id.Value.ToString("N") };
        var jobId = StartDocW(context.Dc, ref info); if (jobId <= 0) throw new LocalPrintException(PrintFailure.DriverFailure);
        var completed = false;
        try
        {
            spoolerAccepted(jobId);
            if (StartPage(context.Dc) <= 0) throw new LocalPrintException(PrintFailure.DriverFailure);
            Render(document, layout, context.Dc);
            if (EndPage(context.Dc) <= 0 || EndDoc(context.Dc) <= 0) throw new LocalPrintException(PrintFailure.DriverFailure);
            completed = true; return new SpoolSubmission(jobId);
        }
        finally { if (!completed) _ = AbortDoc(context.Dc); }
    }, cancellationToken);

    // Driver/DC preflight is read-only and never calls StartDoc. Used to verify one-page geometry safely.
    public Task<SyntheticLayout> InspectLayoutAsync(SyntheticPrintDocument document, CancellationToken cancellationToken) => Task.Run(() =>
    { cancellationToken.ThrowIfCancellationRequested(); using var context = CreateContext(document); return Plan(document, context.Dc); }, cancellationToken);

    public Task<SpoolObservation> ObserveAsync(string printerName, int jobId, PrintJobId expectedJob, CancellationToken cancellationToken) => Task.Run(() =>
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (!OpenPrinterW(printerName, out var printer, IntPtr.Zero)) throw new LocalPrintException(PrintFailure.InvalidPrinter);
        try
        {
            _ = GetJobW(printer, checked((uint)jobId), 1, IntPtr.Zero, 0, out var needed);
            if (needed == 0) return new SpoolObservation(SpoolState.Missing);
            if (needed < Marshal.SizeOf<JobInfoPrefix>() || needed > 1024 * 1024) throw new LocalPrintException(PrintFailure.DriverFailure);
            var buffer = Marshal.AllocHGlobal(checked((int)needed));
            try
            {
                if (!GetJobW(printer, (uint)jobId, 1, buffer, needed, out _)) return new(SpoolState.Unknown);
                var header = Marshal.PtrToStructure<JobInfoPrefix>(buffer);
                // Spooler IDs may be reused after restart. Never attribute another document's status to this test.
                if (header.JobId != (uint)jobId || !string.Equals(Marshal.PtrToStringUni(header.Document),
                    "Atlas Synthetic Test " + expectedJob.Value.ToString("N"), StringComparison.Ordinal)) return new(SpoolState.Missing);
                var flags = header.Status;
                return new SpoolObservation((flags & (1 | 2 | 32 | 64 | 512 | 1024)) != 0 ? SpoolState.Error
                    : (flags & 128) != 0 ? SpoolState.ReportedPrinted : (flags & 16) != 0 ? SpoolState.Printing : SpoolState.Queued);
            }
            finally { Marshal.FreeHGlobal(buffer); }
        }
        finally { ClosePrinter(printer); }
    }, cancellationToken);

    private static PrintContext CreateContext(SyntheticPrintDocument document)
    {
        if (document.Printer.IsVirtual || document.Paper.RawKind is not (> 0 and <= short.MaxValue))
            throw new LocalPrintException(PrintFailure.CapabilityMismatch);
        if (!OpenPrinterW(document.Printer.Name, out var printer, IntPtr.Zero)) throw new LocalPrintException(PrintFailure.InvalidPrinter);
        var devMode = IntPtr.Zero;
        try
        {
            var bytes = DocumentPropertiesW(IntPtr.Zero, printer, document.Printer.Name, IntPtr.Zero, IntPtr.Zero, 0);
            if (bytes < Marshal.SizeOf<DevMode>() || bytes > 1024 * 1024) throw new LocalPrintException(PrintFailure.DriverFailure);
            devMode = Marshal.AllocHGlobal(bytes);
            if (DocumentPropertiesW(IntPtr.Zero, printer, document.Printer.Name, devMode, IntPtr.Zero, 2) != 1) throw new LocalPrintException(PrintFailure.DriverFailure);
            var settings = Marshal.PtrToStructure<DevMode>(devMode);
            if (settings.Size < Marshal.SizeOf<DevMode>() || settings.Size + settings.DriverExtra > bytes) throw new LocalPrintException(PrintFailure.DriverFailure);
            // Modify this job's private DEVMODE copy only; never SetPrinter/SetDefaultPrinter.
            settings.Fields = (settings.Fields & ~(4u | 8u | 65536u)) | 1u | 2u | 16u | 256u;
            settings.Orientation = 1; settings.PaperSize = checked((short)document.Paper.RawKind.Value);
            settings.PaperLength = 0; settings.PaperWidth = 0; settings.Scale = 100; settings.Copies = 1; settings.FormName = "";
            if (document.Printer.Capabilities.Duplex == true) { settings.Fields |= 4096; settings.Duplex = 1; }
            Marshal.StructureToPtr(settings, devMode, false);
            if (DocumentPropertiesW(IntPtr.Zero, printer, document.Printer.Name, devMode, devMode, 10) != 1) throw new LocalPrintException(PrintFailure.CapabilityMismatch);
            var checkedSettings = Marshal.PtrToStructure<DevMode>(devMode);
            if (checkedSettings.Copies != 1 || checkedSettings.Scale != 100 || checkedSettings.Orientation != 1)
                throw new LocalPrintException(PrintFailure.CapabilityMismatch);
            var dc = CreateDCW("WINSPOOL", document.Printer.Name, null, devMode);
            if (dc == IntPtr.Zero) throw new LocalPrintException(PrintFailure.DriverFailure);
            var context = new PrintContext(dc);
            try
            {
                var dpiX = GetDeviceCaps(dc, 88); var dpiY = GetDeviceCaps(dc, 90);
                if (dpiX <= 0 || dpiY <= 0) throw new LocalPrintException(PrintFailure.DriverFailure);
                var width = GetDeviceCaps(dc, 110) * 25.4 / dpiX; var height = GetDeviceCaps(dc, 111) * 25.4 / dpiY;
                if (Math.Abs(width * 10 - document.Paper.WidthTenthsMillimeter!.Value) > 10
                    || Math.Abs(height * 10 - document.Paper.HeightTenthsMillimeter!.Value) > 10)
                    throw new LocalPrintException(PrintFailure.CapabilityMismatch);
                return context;
            }
            catch { context.Dispose(); throw; }
        }
        finally { if (devMode != IntPtr.Zero) Marshal.FreeHGlobal(devMode); ClosePrinter(printer); }
    }
    private static SyntheticLayout Plan(SyntheticPrintDocument document, IntPtr dc)
    {
        var dpiX = GetDeviceCaps(dc, 88); var dpiY = GetDeviceCaps(dc, 90);
        var offsetX = GetDeviceCaps(dc, 112) * 25.4 / dpiX; var offsetY = GetDeviceCaps(dc, 113) * 25.4 / dpiY;
        var width = GetDeviceCaps(dc, 110) * 25.4 / dpiX; var height = GetDeviceCaps(dc, 111) * 25.4 / dpiY;
        var margin = document.Format == SyntheticPageFormat.Pos80 ? 3d : 15d;
        using var fonts = new PrintFonts(dc, dpiY, document.Format);
        return SyntheticPage.Layout(document, Math.Max(margin, offsetX), Math.Max(margin, offsetY),
            Math.Min(width - margin, offsetX + GetDeviceCaps(dc, 8) * 25.4 / dpiX),
            Math.Min(height - margin, offsetY + GetDeviceCaps(dc, 10) * 25.4 / dpiY), (text, heading) =>
            {
                fonts.Select(heading);
                if (!GetTextExtentPoint32W(dc, text, text.Length, out var size)) throw new LocalPrintException(PrintFailure.DriverFailure);
                var spacing = document.Format == SyntheticPageFormat.Pos80 ? (heading ? 5.5 : 4.8) : (heading ? 8 : 6);
                if (size.Height * 25.4 / dpiY > spacing) throw new LocalPrintException(PrintFailure.LayoutDoesNotFit);
                return size.Width * 25.4 / dpiX;
            });
    }
    private static void Render(SyntheticPrintDocument document, SyntheticLayout layout, IntPtr dc)
    {
        var dpiX = GetDeviceCaps(dc, 88); var dpiY = GetDeviceCaps(dc, 90); var offsetX = GetDeviceCaps(dc, 112); var offsetY = GetDeviceCaps(dc, 113);
        using var fonts = new PrintFonts(dc, dpiY, document.Format); _ = SetBkMode(dc, 1); _ = SetTextColor(dc, 0);
        foreach (var line in layout.Lines)
        {
            fonts.Select(line.Heading);
            if (line.Text.Length > 0 && !TextOutW(dc, (int)Math.Round(line.XMillimeter * dpiX / 25.4) - offsetX,
                (int)Math.Round(line.YMillimeter * dpiY / 25.4) - offsetY, line.Text, line.Text.Length)) throw new LocalPrintException(PrintFailure.DriverFailure);
        }
    }
    private sealed class PrintContext(IntPtr dc) : IDisposable
    { public IntPtr Dc => dc; public void Dispose() => DeleteDC(dc); }
    private sealed class PrintFonts : IDisposable
    {
        private readonly IntPtr _dc, _body, _heading, _original;
        public PrintFonts(IntPtr dc, int dpi, SyntheticPageFormat format)
        {
            _dc = dc; var pos = format == SyntheticPageFormat.Pos80;
            _body = CreateFontW(-(int)Math.Round((pos ? 9d : 11d) * dpi / 72), 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 0, "Arial");
            _heading = CreateFontW(-(int)Math.Round((pos ? 10d : 15d) * dpi / 72), 0, 0, 0, 700, 0, 0, 0, 1, 0, 0, 0, 0, "Arial");
            if (_body == IntPtr.Zero || _heading == IntPtr.Zero) { if (_body != IntPtr.Zero) DeleteObject(_body); if (_heading != IntPtr.Zero) DeleteObject(_heading); throw new LocalPrintException(PrintFailure.DriverFailure); }
            _original = SelectObject(dc, _body);
        }
        public void Select(bool heading) => SelectObject(_dc, heading ? _heading : _body);
        public void Dispose() { SelectObject(_dc, _original); DeleteObject(_body); DeleteObject(_heading); }
    }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] private struct DocInfo
    { public int Size; [MarshalAs(UnmanagedType.LPWStr)] public string Name; public IntPtr Output, DataType; public uint Type; }
    [StructLayout(LayoutKind.Sequential)] private struct ServiceStatus { public uint Type, CurrentState, Controls, Win32Exit, ServiceExit, CheckPoint, WaitHint; }
    [StructLayout(LayoutKind.Sequential)] private struct JobInfoPrefix
    { public uint JobId; public IntPtr Printer, Machine, User, Document, DataType, StatusText; public uint Status, Priority, Position, TotalPages, PagesPrinted; }
    [StructLayout(LayoutKind.Sequential)] private struct NativeSize { public int Width, Height; }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] private struct DevMode
    {
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string DeviceName;
        public ushort SpecVersion, DriverVersion, Size, DriverExtra; public uint Fields;
        public short Orientation, PaperSize, PaperLength, PaperWidth, Scale, Copies, Source, Quality, Color, Duplex, YResolution, TTOption, Collate;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string FormName;
        public ushort LogPixels; public uint BitsPerPel, PelsWidth, PelsHeight, DisplayFlags, DisplayFrequency, ICMMethod, ICMIntent, MediaType, DitherType, Reserved1, Reserved2, PanningWidth, PanningHeight;
    }
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)] private static extern IntPtr OpenSCManagerW(string? machine, string? database, uint access);
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)] private static extern IntPtr OpenServiceW(IntPtr manager, string name, uint access);
    [DllImport("advapi32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool QueryServiceStatus(IntPtr service, out ServiceStatus status);
    [DllImport("advapi32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool CloseServiceHandle(IntPtr handle);
    [DllImport("winspool.drv", CharSet = CharSet.Unicode, ExactSpelling = true)] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool OpenPrinterW(string name, out IntPtr handle, IntPtr defaults);
    [DllImport("winspool.drv")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool ClosePrinter(IntPtr handle);
    [DllImport("winspool.drv", CharSet = CharSet.Unicode, ExactSpelling = true)] private static extern int DocumentPropertiesW(IntPtr window, IntPtr printer, string name, IntPtr output, IntPtr input, uint mode);
    [DllImport("winspool.drv", CharSet = CharSet.Unicode, ExactSpelling = true)] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool GetJobW(IntPtr printer, uint job, uint level, IntPtr data, uint size, out uint needed);
    [DllImport("gdi32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)] private static extern IntPtr CreateDCW(string driver, string device, string? output, IntPtr mode);
    [DllImport("gdi32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool DeleteDC(IntPtr dc);
    [DllImport("gdi32.dll")] private static extern int GetDeviceCaps(IntPtr dc, int index);
    [DllImport("gdi32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)] private static extern int StartDocW(IntPtr dc, ref DocInfo info);
    [DllImport("gdi32.dll")] private static extern int StartPage(IntPtr dc);
    [DllImport("gdi32.dll")] private static extern int EndPage(IntPtr dc);
    [DllImport("gdi32.dll")] private static extern int EndDoc(IntPtr dc);
    [DllImport("gdi32.dll")] private static extern int AbortDoc(IntPtr dc);
    [DllImport("gdi32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool TextOutW(IntPtr dc, int x, int y, string text, int length);
    [DllImport("gdi32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool GetTextExtentPoint32W(IntPtr dc, string text, int length, out NativeSize size);
    [DllImport("gdi32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)] private static extern IntPtr CreateFontW(int height, int width, int escapement, int orientation, int weight, uint italic, uint underline, uint strikeout, uint charset, uint output, uint clip, uint quality, uint family, string face);
    [DllImport("gdi32.dll")] private static extern IntPtr SelectObject(IntPtr dc, IntPtr value);
    [DllImport("gdi32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool DeleteObject(IntPtr value);
    [DllImport("gdi32.dll")] private static extern int SetBkMode(IntPtr dc, int mode);
    [DllImport("gdi32.dll")] private static extern uint SetTextColor(IntPtr dc, uint color);
}
