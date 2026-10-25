using System.Globalization;

namespace Atlas.LocalAgent.Core;

public enum SyntheticPageFormat { Pos80, Letter, A4 }
public enum PrintFailure { None, InvalidSelection, InvalidPrinter, CapabilityMismatch, PrinterOffline, DriverFailure,
    SpoolerUnavailable, ConfirmationRequired, PhysicalPrintingDisabled, JobConflict, JobNotFound, OutcomeUnknown, TooLateToCancel, LayoutDoesNotFit }
public enum SpoolState { NotSubmitted, Queued, Printing, ReportedPrinted, Missing, Unknown, Error }
public sealed record SyntheticPrintRequest(PrintJobId JobId, Guid TargetAgent, string PrinterId, SyntheticPageFormat PageFormat)
{
    public PrintJob ToJob()
    {
        if (JobId.Value == Guid.Empty || TargetAgent == Guid.Empty || string.IsNullOrWhiteSpace(PrinterId)
            || PrinterId.Length != 72 || !PrinterId.StartsWith("printer-", StringComparison.Ordinal)
            || !PrinterId[8..].All(Uri.IsHexDigit) || !Enum.IsDefined(PageFormat)) throw new ArgumentException("Selección inválida.");
        return new(JobId, TargetAgent, PrinterId, "atlas-synthetic-test-v1:" + PageFormat, PrintDocumentFormat.PlainText, 1);
    }
}
public sealed record SyntheticPrintReceipt(PrintJob Job, SyntheticPageFormat PageFormat, DateTimeOffset CreatedAt,
    DateTimeOffset UpdatedAt, PrintFailure Error = PrintFailure.None, int? SpoolJobId = null, SpoolState SpoolState = SpoolState.NotSubmitted)
{
    public PrintJobStatus Status => Job.Status;
}
public sealed record LocalPrintDiagnostics(bool PhysicalPrintingEnabled, bool? SpoolerAvailable,
    SyntheticPrintReceipt? LastJob, IReadOnlyList<PrintFailure> RecentErrors);
public sealed record SyntheticPrintReply(SyntheticPrintReceipt? Receipt, PrintFailure Error = PrintFailure.None);
public sealed record SyntheticPrintDocument(PrintJob Job, SyntheticPageFormat Format, PrinterDevice Printer,
    PaperSizeCapability Paper, string StationName, DateTimeOffset LocalTime)
{
    public bool OfficialRoutingQa { get; init; }
}
public sealed record SpoolSubmission(int JobId);
public sealed record SpoolObservation(SpoolState State);
public interface ILocalPrintBackend
{
    Task<bool> IsSpoolerAvailableAsync(CancellationToken cancellationToken);
    Task<SpoolSubmission> SubmitAsync(SyntheticPrintDocument document, Func<bool> beginSpooling,
        Action<int> spoolerAccepted, CancellationToken cancellationToken);
    Task<SpoolObservation> ObserveAsync(string printerName, int jobId, PrintJobId expectedJob, CancellationToken cancellationToken);
}
public sealed class LocalPrintException(PrintFailure failure) : Exception("Error controlado de impresión.")
{
    public PrintFailure Failure => failure;
}
public static class SyntheticPaper
{
    public static string Label(SyntheticPageFormat format) => format switch
    { SyntheticPageFormat.Pos80 => "POS 80 mm", SyntheticPageFormat.Letter => "Letter 8.5 x 11", SyntheticPageFormat.A4 => "A4", _ => "Formato inválido" };
    public static PaperSizeCapability? Match(PrinterDevice printer, SyntheticPageFormat format) =>
        printer.Capabilities.PaperSizes.Where(p => p.RawKind is > 0 and <= short.MaxValue && p.WidthTenthsMillimeter is > 0 && p.HeightTenthsMillimeter is > 0)
            .Where(p => format switch
            {
                SyntheticPageFormat.Pos80 => Math.Abs(p.WidthTenthsMillimeter!.Value - 800) <= 5 && p.HeightTenthsMillimeter is >= 1800 and <= 6000,
                SyntheticPageFormat.Letter => Math.Abs(p.WidthTenthsMillimeter!.Value - 2159) <= 5 && Math.Abs(p.HeightTenthsMillimeter!.Value - 2794) <= 5,
                SyntheticPageFormat.A4 => Math.Abs(p.WidthTenthsMillimeter!.Value - 2100) <= 5 && Math.Abs(p.HeightTenthsMillimeter!.Value - 2970) <= 5,
                _ => false
            }).OrderBy(p => p.HeightTenthsMillimeter).FirstOrDefault();
}
public sealed record SyntheticLine(string Text, bool Heading = false);
public sealed record PlacedSyntheticLine(string Text, bool Heading, double XMillimeter, double YMillimeter);
public sealed record SyntheticLayout(IReadOnlyList<PlacedSyntheticLine> Lines, double EndMillimeter);
public static class SyntheticPage
{
    public static IReadOnlyList<SyntheticLine> Content(SyntheticPrintDocument document)
    {
        if (document.StationName.Length > 100 || document.Printer.Name.Length > 256
            || document.StationName.Any(char.IsControl) || document.Printer.Name.Any(char.IsControl))
            throw new LocalPrintException(PrintFailure.InvalidSelection);
        if(document.OfficialRoutingQa)
            return [new("ATLAS PÉRGAMO",true),new("FINAL PHYSICAL PRINT QA",true),new(""),
                new("PRINTJOB:"),new(document.Job.Id.Value.ToString()),new("STATION: "+document.StationName),
                new("AGENT ID: "+document.Job.TargetAgent),new("COPIES: 1"),
                new("PRINTER: "+document.Printer.Name),new("ORIGIN: WEB_DESKTOP"),new("EXECUTION: PHYSICAL QA"),
                new("TIMESTAMP: "+document.LocalTime.ToString("yyyy-MM-dd HH:mm:ss zzz",CultureInfo.InvariantCulture)),
                new(""),new("Página sintética. Sin datos clínicos ni financieros.")];
        return [new("ATLAS PÉRGAMO", true), new("PRUEBA DE IMPRESIÓN", true), new(""),
            new("Estación: " + document.StationName), new("Agente: " + AgentVersion.Current), new("Impresora: " + document.Printer.Name),
            new("Formato: " + SyntheticPaper.Label(document.Format)), new("Fecha/hora local: " + document.LocalTime.ToString("yyyy-MM-dd HH:mm:ss zzz", CultureInfo.InvariantCulture)),
            new("Código de prueba:"), new(document.Job.Id.Value.ToString()), new(""), new("------------------------------"),
            new("Esta es una página sintética de prueba."), new("No contiene información clínica ni financiera."),
            new("------------------------------"), new(""), new("ATLAS LOCAL AGENT", true)];
    }
    // Units are physical millimeters. POS has its own typography/margins, never a scaled office page.
    public static SyntheticLayout Layout(SyntheticPrintDocument document, double left, double top, double right, double bottom,
        Func<string, bool, double> measureWidth)
    {
        var width = right - left; var y = top; var placed = new List<PlacedSyntheticLine>();
        if (width < 30 || bottom - top < 80) throw new LocalPrintException(PrintFailure.LayoutDoesNotFit);
        foreach (var line in Content(document))
        {
            var remaining = line.Text; var spacing = document.Format == SyntheticPageFormat.Pos80 ? (line.Heading ? 5.5 : 4.8) : (line.Heading ? 8 : 6);
            do
            {
                var take = remaining.Length;
                while (take > 0 && measureWidth(remaining[..take], line.Heading) > width) take--;
                if (take == 0 && remaining.Length > 0) throw new LocalPrintException(PrintFailure.LayoutDoesNotFit);
                if (take < remaining.Length && remaining.LastIndexOf(' ', Math.Max(0, take - 1), take) is var split && split > take / 2) take = split;
                var text = remaining[..take].TrimEnd();
                if (y + spacing > bottom) throw new LocalPrintException(PrintFailure.LayoutDoesNotFit);
                var x = line.Heading ? left + (width - measureWidth(text, true)) / 2 : left;
                placed.Add(new(text, line.Heading, x, y)); y += spacing;
                remaining = remaining[take..].TrimStart();
            } while (remaining.Length > 0);
        }
        return new(placed, y);
    }
}
public static class PrintMessages
{
    public static string State(PrintJobStatus status) => status switch
    {
        PrintJobStatus.Queued => "Pendiente de confirmación", PrintJobStatus.Received or PrintJobStatus.Ready => "Aceptado, pendiente de envío",
        PrintJobStatus.Printing => "Enviando al spooler", PrintJobStatus.Submitted => "Entregado a Windows; salida física no confirmada",
        PrintJobStatus.Printed => "Windows informa impreso; verificar salida física", PrintJobStatus.Failed => "Fallido",
        PrintJobStatus.Cancelled => "Cancelado antes del envío", _ => status.ToString()
    };
    public static string Error(PrintFailure error) => error switch
    {
        PrintFailure.None => "Sin errores", PrintFailure.InvalidPrinter => "La impresora ya no existe o no está disponible.",
        PrintFailure.CapabilityMismatch => "El driver no anuncia un papel compatible con este formato.",
        PrintFailure.PrinterOffline => "Windows informa que la impresora está offline, pausada o con error.",
        PrintFailure.SpoolerUnavailable => "El spooler de Windows no está disponible.",
        PrintFailure.PhysicalPrintingDisabled => "La impresión física está bloqueada hasta autorizar esta prueba QA.",
        PrintFailure.ConfirmationRequired => "Confirme impresora, formato y página sintética antes de imprimir.",
        PrintFailure.JobConflict => "Este código ya pertenece a otra intención. No se imprimió otra copia.",
        PrintFailure.OutcomeUnknown => "Resultado incierto. Puede existir un trabajo en Windows; no se reenviará automáticamente.",
        PrintFailure.TooLateToCancel => "El envío ya comenzó. No puede garantizarse una cancelación física desde el agente.",
        PrintFailure.LayoutDoesNotFit => "El texto no cabe en el área imprimible. No se envió ninguna página.",
        PrintFailure.DriverFailure => "El driver no pudo procesar la prueba. Revise Windows antes de una nueva impresión.",
        PrintFailure.JobNotFound => "No se encontró el trabajo.", _ => "Seleccione explícitamente una impresora física y un formato válido."
    };
}
