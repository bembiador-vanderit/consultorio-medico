using System.Collections.Concurrent;
using System.Text.Json.Serialization;

namespace Atlas.LocalAgent.Core;

public readonly record struct PrintJobId
{
    public Guid Value { get; }
    [JsonConstructor]
    public PrintJobId(Guid value) { if (value == Guid.Empty) throw new ArgumentException("PrintJobId vacío."); Value = value; }
    public static PrintJobId New() => new(Guid.NewGuid());
}
public enum PrintJobStatus { Queued, Received, Downloading, Ready, Printing, Printed, Failed, Cancelled, Submitted, Unknown, Expired }
public enum PrintDocumentFormat { Pdf, PlainText }
public sealed record PrintJob(PrintJobId Id, Guid TargetAgent, string TargetPrinter, string DocumentReference, PrintDocumentFormat Format, int Copies)
{
    public PrintJobStatus Status { get; init; } = PrintJobStatus.Queued;
    public PrintOrigin? Origin { get; init; } // Null only for legacy/local synthetic jobs.
    public DocumentSecurityClass SecurityClass { get; init; } = DocumentSecurityClass.General;
    public int IntentVersion { get; init; } = 1; // Historical contracts retain their original identity.
    public int? RequestedByUserId { get; init; }
    public string? DocumentType { get; init; }
    public override string ToString() => $"PrintJob({Id.Value}, {Format}, {Status})";
    public PrintJob Validate()
    {
        if (Id.Value == Guid.Empty || TargetAgent == Guid.Empty || string.IsNullOrWhiteSpace(TargetPrinter)
            || string.IsNullOrWhiteSpace(DocumentReference) || Copies is < 1 or > 999 || !Enum.IsDefined(Format))
            throw new ArgumentException("Contrato de impresión inválido.");
        Origin?.Validate();
        if (!Enum.IsDefined(SecurityClass)) throw new ArgumentException("Clasificación inválida.");
        if (IntentVersion is not (1 or 2)) throw new ArgumentException("Versión de intención no soportada.");
        if (IntentVersion == 2 && (RequestedByUserId is null or <= 0 || Origin is null
            || Origin.ActorReference != RequestedByUserId.Value.ToString(System.Globalization.CultureInfo.InvariantCulture)
            || DocumentType is null || !System.Text.RegularExpressions.Regex.IsMatch(DocumentType, "\\A[A-Za-z0-9_-]{1,64}\\z")))
            throw new ArgumentException("Contrato v2 requiere actor, origen y tipo de documento.");
        if (IntentVersion == 1 && (RequestedByUserId is not null || DocumentType is not null))
            throw new ArgumentException("No reinterpretar intención heredada como contrato v2.");
        return this;
    }
}
public enum PrintJobRegistration { Registered, Duplicate, Conflict }
public interface IPrintJobRegistry { PrintJobRegistration Register(PrintJob job); }
public sealed class InMemoryPrintJobRegistry : IPrintJobRegistry
{
    private readonly ConcurrentDictionary<PrintJobId, PrintJob> _jobs = new();
    public PrintJobRegistration Register(PrintJob job)
    {
        job.Validate();
        var intent = job with { Status = PrintJobStatus.Queued };
        return _jobs.TryAdd(job.Id, intent) ? PrintJobRegistration.Registered : _jobs[job.Id] == intent ? PrintJobRegistration.Duplicate : PrintJobRegistration.Conflict;
    }
}
