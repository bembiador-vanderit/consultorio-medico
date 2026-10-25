using Atlas.LocalAgent.Core;

namespace Atlas.LocalAgent.Service;

// One host per data root is enforced by service.lock. Receipts are not print payloads.
public sealed class LocalPrintJobStore : IPrintJobRegistry
{
    private readonly string _directory;
    private readonly object _gate = new();
    public LocalPrintJobStore(string root)
    {
        _directory = Path.Combine(Path.GetFullPath(root), "print-jobs"); Directory.CreateDirectory(_directory);
    }
    private string FileFor(PrintJobId id) => id.Value == Guid.Empty ? throw new ArgumentException("ID vacío.") : Path.Combine(_directory, id.Value.ToString("N") + ".json");
    public PrintJobRegistration Register(PrintJob job)
    {
        job.Validate();
        lock (_gate)
        {
            var prior = Get(job.Id);
            if (prior is not null) return (prior.Job with { Status = PrintJobStatus.Queued }) == (job with { Status = PrintJobStatus.Queued })
                ? PrintJobRegistration.Duplicate : PrintJobRegistration.Conflict;
            if (!Enum.TryParse<SyntheticPageFormat>(job.DocumentReference.Replace("atlas-synthetic-test-v1:", "", StringComparison.Ordinal), out var format)
                || job.DocumentReference != "atlas-synthetic-test-v1:" + format || !Enum.IsDefined(format)
                || job.Copies != 1 || job.Format != PrintDocumentFormat.PlainText) throw new ArgumentException("Solo prueba sintética.");
            var now = DateTimeOffset.UtcNow; Save(new(job with { Status = PrintJobStatus.Queued }, format, now, now));
            return PrintJobRegistration.Registered;
        }
    }
    public SyntheticPrintReceipt? Get(PrintJobId id)
    {
        lock (_gate)
        {
            var path = FileFor(id); if (!File.Exists(path)) return null;
            if (new FileInfo(path).Length > 16384) throw new InvalidDataException("Registro local inválido.");
            var record = Wire.Deserialize<SyntheticPrintReceipt>(File.ReadAllBytes(path));
            if (record.Job.Id != id || record.Job.DocumentReference != "atlas-synthetic-test-v1:" + record.PageFormat
                || record.Job.Copies != 1 || record.Job.Format != PrintDocumentFormat.PlainText) throw new InvalidDataException("Registro local inválido.");
            record.Job.Validate(); return record;
        }
    }
    public SyntheticPrintReceipt? Update(PrintJobId id, Func<SyntheticPrintReceipt, SyntheticPrintReceipt> change, Action<SyntheticPrintReceipt>? afterSaved = null)
    {
        lock (_gate)
        {
            var prior = Get(id); if (prior is null) return null;
            var updated = change(prior);
            if (updated == prior) return prior;
            if ((updated.Job with { Status = PrintJobStatus.Queued }) != (prior.Job with { Status = PrintJobStatus.Queued })
                || updated.PageFormat != prior.PageFormat) throw new InvalidOperationException("Intención inmutable.");
            updated = updated with { UpdatedAt = DateTimeOffset.UtcNow }; Save(updated); afterSaved?.Invoke(updated); return updated;
        }
    }
    public IReadOnlyList<SyntheticPrintReceipt> All()
    {
        lock (_gate)
        {
            var paths = Directory.GetFiles(_directory, "*.json");
            if (paths.Length > 10000) throw new InvalidDataException("Inventario de pruebas demasiado grande.");
            return paths.Select(x => Get(new(Guid.ParseExact(Path.GetFileNameWithoutExtension(x), "N")))!).ToArray();
        }
    }
    private void Save(SyntheticPrintReceipt receipt)
    {
        var path = FileFor(receipt.Job.Id); var temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            using (var file = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None, 4096, FileOptions.WriteThrough))
            { file.Write(Wire.Serialize(receipt)); file.Flush(flushToDisk: true); }
            File.Move(temporary, path, overwrite: true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
}
