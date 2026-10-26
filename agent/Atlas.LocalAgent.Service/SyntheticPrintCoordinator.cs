using System.Collections.Concurrent;
using Atlas.LocalAgent.Core;

namespace Atlas.LocalAgent.Service;

public sealed class SyntheticPrintCoordinator(LocalPrintJobStore store, ILocalPrintBackend backend,
    IPrinterDiscovery discovery, Func<AgentSnapshot> snapshot, IAgentLog log, bool physicalPrintingEnabled = false)
{
    private readonly SemaphoreSlim _spoolGate = new(1, 1);
    private readonly SemaphoreSlim _requestGate = new(1, 1);
    private readonly object _dispatchGate = new();
    private readonly ConcurrentDictionary<PrintJobId, Task> _workers = new();
    private readonly CancellationTokenSource _shutdown = new();
    public bool PhysicalPrintingEnabled => physicalPrintingEnabled;
    public void RecoverInterruptedJobs()
    {
        foreach (var receipt in store.All().Where(x => x.Status is PrintJobStatus.Received or PrintJobStatus.Ready or PrintJobStatus.Printing))
            Change(receipt.Job.Id, x => x with { Job = x.Job with { Status = PrintJobStatus.Failed }, Error = PrintFailure.OutcomeUnknown });
    }
    public async Task<SyntheticPrintReply> PrepareAsync(SyntheticPrintRequest request, CancellationToken cancellationToken)
    {
        await _requestGate.WaitAsync(cancellationToken);
        try { return await PrepareCoreAsync(request, cancellationToken); }
        finally { _requestGate.Release(); }
    }
    private async Task<SyntheticPrintReply> PrepareCoreAsync(SyntheticPrintRequest request, CancellationToken cancellationToken)
    {
        if (request.TargetAgent != snapshot().Identity.AgentId) return new(null, PrintFailure.InvalidSelection);
        PrintJob job;
        try { job = request.ToJob(); } catch (ArgumentException) { return new(null, PrintFailure.InvalidSelection); }
        var registered = store.Register(job);
        if (registered == PrintJobRegistration.Conflict) return new(store.Get(job.Id), PrintFailure.JobConflict);
        if (registered == PrintJobRegistration.Duplicate) return new(store.Get(job.Id));
        log.WritePrint(job.Id.Value, job.TargetPrinter, request.PageFormat, PrintJobStatus.Queued, PrintFailure.None, null);
        var validation = await ValidatePrinterAsync(request, cancellationToken);
        var receipt = validation.Error == PrintFailure.None ? store.Get(job.Id) :
            Change(job.Id, x => x.Status == PrintJobStatus.Queued ? x with { Job = x.Job with { Status = PrintJobStatus.Failed }, Error = validation.Error } : x);
        return new(receipt, validation.Error);
    }
    public async Task<SyntheticPrintReply> SubmitAsync(SyntheticPrintRequest request, bool userConfirmed, CancellationToken cancellationToken)
    {
        var prepared = await PrepareAsync(request, cancellationToken);
        if (prepared.Error != PrintFailure.None || prepared.Receipt is null || prepared.Receipt.Status != PrintJobStatus.Queued) return prepared;
        if (!userConfirmed) return new(prepared.Receipt, PrintFailure.ConfirmationRequired);
        if (!physicalPrintingEnabled) return new(prepared.Receipt, PrintFailure.PhysicalPrintingDisabled);
        lock (_dispatchGate)
        {
            if (_shutdown.IsCancellationRequested) return new(prepared.Receipt, PrintFailure.PhysicalPrintingDisabled);
            var claimed = false;
            var receipt = Change(request.JobId, x =>
            {
                if (x.Status != PrintJobStatus.Queued) return x;
                claimed = true; return x with { Job = x.Job with { Status = PrintJobStatus.Received }, Error = PrintFailure.None };
            });
            if (claimed)
            {
                // Only the successful durable transition owns dispatch. A retry never starts a second worker.
                var worker = Task.Run(() => ExecuteAsync(request)); _workers[request.JobId] = worker;
                _ = worker.ContinueWith(_ => _workers.TryRemove(request.JobId, out var ignored), TaskScheduler.Default);
            }
            return new(receipt);
        }
    }
    public SyntheticPrintReply Cancel(PrintJobId id)
    {
        var tooLate = false;
        var receipt = Change(id, x =>
        {
            if (x.Status is PrintJobStatus.Queued or PrintJobStatus.Received or PrintJobStatus.Ready)
                return x with { Job = x.Job with { Status = PrintJobStatus.Cancelled }, Error = PrintFailure.None };
            tooLate = x.Status is PrintJobStatus.Printing or PrintJobStatus.Submitted or PrintJobStatus.Printed;
            return x;
        });
        return new(receipt, receipt is null ? PrintFailure.JobNotFound : tooLate ? PrintFailure.TooLateToCancel : PrintFailure.None);
    }
    public SyntheticPrintReply Get(PrintJobId id) => new(store.Get(id));
    public async Task<SyntheticPrintReply> ObserveAsync(PrintJobId id, CancellationToken cancellationToken)
    {
        var receipt = store.Get(id); if (receipt is null) return new(null, PrintFailure.JobNotFound);
        if (receipt.SpoolJobId is null || receipt.Status is not (PrintJobStatus.Submitted or PrintJobStatus.Printed)) return new(receipt);
        try
        {
            var printer = snapshot().Printers.FirstOrDefault(x => x.DeviceId == receipt.Job.TargetPrinter);
            if (printer is null) return new(receipt, PrintFailure.InvalidPrinter);
            var observed = await backend.ObserveAsync(printer.Name, receipt.SpoolJobId.Value, receipt.Job.Id, cancellationToken);
            return new(Change(id, x => x with { SpoolState = observed.State,
                Error = observed.State == SpoolState.Error ? PrintFailure.OutcomeUnknown : x.Error,
                Job = x.Job with { Status = observed.State == SpoolState.Error ? PrintJobStatus.Failed
                    : observed.State == SpoolState.ReportedPrinted ? PrintJobStatus.Printed : x.Status } }));
        }
        catch (Exception) { return new(receipt, PrintFailure.SpoolerUnavailable); }
    }
    public async Task<LocalPrintDiagnostics> DiagnoseAsync(CancellationToken cancellationToken)
    {
        bool? available;
        try { available = await backend.IsSpoolerAvailableAsync(cancellationToken); } catch (Exception) { available = null; }
        var all = store.All().OrderByDescending(x => x.UpdatedAt).ToArray();
        return new(physicalPrintingEnabled, available, all.FirstOrDefault(), all.Where(x => x.Error != PrintFailure.None).Take(10).Select(x => x.Error).ToArray());
    }
    public async Task DrainAsync()
    {
        Task[] workers;
        lock (_dispatchGate) { _shutdown.Cancel(); workers = _workers.Values.ToArray(); }
        await Task.WhenAll(workers);
    }
    public Task WaitForIdleAsync() => Task.WhenAll(_workers.Values);
    private async Task ExecuteAsync(SyntheticPrintRequest request)
    {
        var acquired = false;
        try
        {
            await _spoolGate.WaitAsync(_shutdown.Token); acquired = true;
            if (store.Get(request.JobId)?.Status != PrintJobStatus.Received) return;
            var validated = await ValidatePrinterAsync(request, _shutdown.Token);
            if (validated.Error != PrintFailure.None) throw new LocalPrintException(validated.Error);
            var printer = validated.Printer!; var paper = SyntheticPaper.Match(printer, request.PageFormat)!;
            if (!await backend.IsSpoolerAvailableAsync(_shutdown.Token)) throw new LocalPrintException(PrintFailure.SpoolerUnavailable);
            var station = snapshot().Configuration.StationName;
            var document = new SyntheticPrintDocument(request.ToJob(), request.PageFormat, printer, paper, station, DateTimeOffset.Now);
            var result = await backend.SubmitAsync(document, () =>
            {
                var started = false;
                Change(request.JobId, x =>
                {
                    if (x.Status != PrintJobStatus.Received || _shutdown.IsCancellationRequested) return x;
                    started = true; return x with { Job = x.Job with { Status = PrintJobStatus.Printing } };
                });
                return started;
            }, spoolId => Change(request.JobId, x => x with { SpoolJobId = spoolId, SpoolState = SpoolState.Queued }), _shutdown.Token);
            Change(request.JobId, x => x with { Job = x.Job with { Status = PrintJobStatus.Submitted }, SpoolJobId = result.JobId });
        }
        catch (OperationCanceledException)
        {
            Change(request.JobId, x => x.Status == PrintJobStatus.Cancelled ? x : x with
            { Job = x.Job with { Status = x.Status == PrintJobStatus.Printing ? PrintJobStatus.Failed : PrintJobStatus.Cancelled },
                Error = x.Status == PrintJobStatus.Printing ? PrintFailure.OutcomeUnknown : PrintFailure.None });
        }
        catch (Exception ex)
        {
            Change(request.JobId, x => x.Status == PrintJobStatus.Cancelled ? x : x with { Job = x.Job with { Status = PrintJobStatus.Failed },
                Error = x.SpoolJobId is not null ? PrintFailure.OutcomeUnknown : ex is LocalPrintException known ? known.Failure : PrintFailure.DriverFailure });
        }
        finally { if (acquired) _spoolGate.Release(); }
    }
    private async Task<(PrinterDevice? Printer, PrintFailure Error)> ValidatePrinterAsync(SyntheticPrintRequest request, CancellationToken cancellationToken)
    {
        try
        {
            var printer = (await discovery.EnumerateAsync(cancellationToken)).FirstOrDefault(x => x.DeviceId == request.PrinterId);
            if (printer is null) return (null, PrintFailure.InvalidPrinter);
            if (printer.IsVirtual || string.IsNullOrWhiteSpace(printer.Name) || printer.Name.Length > 256 || printer.Name.Any(char.IsControl)) return (null, PrintFailure.InvalidSelection);
            if ((printer.ReportedStatus & (1u | 2u | 8u | 16u | 128u | 2048u | 4096u | 4194304u)) != 0) return (null, PrintFailure.PrinterOffline);
            return (printer, SyntheticPaper.Match(printer, request.PageFormat) is null ? PrintFailure.CapabilityMismatch : PrintFailure.None);
        }
        catch (OperationCanceledException) { throw; }
        catch (Exception) { return (null, PrintFailure.DriverFailure); }
    }
    private SyntheticPrintReceipt? Change(PrintJobId id, Func<SyntheticPrintReceipt, SyntheticPrintReceipt> update)
    {
        return store.Update(id, update, result =>
            log.WritePrint(result.Job.Id.Value, result.Job.TargetPrinter, result.PageFormat, result.Status, result.Error, result.SpoolJobId));
    }
}
