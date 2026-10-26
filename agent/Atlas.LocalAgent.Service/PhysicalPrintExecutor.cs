using System.Security.Cryptography;
using System.Text.Json;
using Atlas.LocalAgent.Core;

namespace Atlas.LocalAgent.Service;

public interface IPhysicalPrintExecutor : IRoutingPrintExecutor { }

public static class PhysicalPrinterFingerprint
{
    public static string For(PrinterDevice printer) => Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(new {
        Id=printer.RegistryId??printer.DeviceId,printer.Driver,printer.Connection,printer.IsVirtual,
        printer.Capabilities.Color,printer.Capabilities.Duplex,printer.Capabilities.MaximumCopies,
        Papers=printer.Capabilities.PaperSizes.OrderBy(p=>p.RawKind).ThenBy(p=>p.WidthTenthsMillimeter)
            .ThenBy(p=>p.HeightTenthsMillimeter).ThenBy(p=>p.Name,StringComparer.Ordinal).ToArray()
    }))).ToLowerInvariant();
}

/// <summary>Adapter to the existing native backend, not a second spool engine/coordinator.
/// Only bounded synthetic QA layout is rendered; downloaded bytes are never passed to Windows.
/// </summary>
public sealed class PhysicalPrintExecutor(PhysicalExecutionAuthorization authorization, ILocalPrintBackend backend,
    IPrinterDiscovery discovery, Func<AgentSnapshot> snapshot, DurablePrintJobStore store) : IPhysicalPrintExecutor
{
    private RoutingDelivery? _prepared;
    private readonly SingleJobPhysicalExecutionPolicy _policy=new(authorization);

    public async Task<DurablePrintFailure?> PreflightAsync(RoutingDelivery delivery,CancellationToken token)
    {
        _prepared=null;
        try
        {
            _=await DocumentAsync(delivery,token);
            if(!await backend.IsSpoolerAvailableAsync(token))return DurablePrintFailure.PrinterUnavailable;
            _prepared=delivery;return null;
        }
        catch(OperationCanceledException){throw;}
        catch(Exception){return DurablePrintFailure.PhysicalDenied;}
    }

    private async Task<SyntheticPrintDocument> DocumentAsync(RoutingDelivery delivery,CancellationToken token)
    {
        var current=snapshot();
        if(!current.Running || current.State!=AgentState.Connected || current.Identity.AgentId!=delivery.TargetAgent
            || _policy.Evaluate(delivery,new("ready")).Mode!=PrintExecutionMode.PhysicalAllowed)
            throw new InvalidDataException("Physical execution denied.");
        var printers=await discovery.EnumerateAsync(token);
        var printer=printers.SingleOrDefault(p=>(p.RegistryId??p.DeviceId)==authorization.AllowedPrinterId);
        if(printer is null || printer.IsVirtual || PhysicalPrinterFingerprint.For(printer)!=authorization.PrinterFingerprint
            || (authorization.ExpectedPrinterName is not null && printer.Name!=authorization.ExpectedPrinterName)
            || (printer.ReportedStatus & (1u|2u|8u|16u|128u|2048u|4096u|4194304u))!=0)
            throw new InvalidDataException("Physical printer identity/capability mismatch.");
        var paper=SyntheticPaper.Match(printer,authorization.PageFormat)??throw new InvalidDataException("Unsupported paper.");
        return new(delivery.Envelope().Job,authorization.PageFormat,printer,paper,current.Configuration.StationName,DateTimeOffset.Now)
            {OfficialRoutingQa=true};
    }

    public int Execute(PrintJob job)
    {
        var delivery=_prepared??throw new InvalidOperationException("Physical preflight required.");
        if(job!=delivery.Envelope().Job)throw new InvalidDataException("Physical intent changed.");
        // Refresh native identity/capabilities and TTL immediately before invoking the backend.
        var document=DocumentAsync(delivery,CancellationToken.None).GetAwaiter().GetResult();
        var submitted=backend.SubmitAsync(document,
            ()=>_policy.Evaluate(delivery,new("ready")).Mode==PrintExecutionMode.PhysicalAllowed
                && snapshot().State==AgentState.Connected,
            spool=>store.RecordSpoolAcceptance(job.Id,spool),CancellationToken.None).GetAwaiter().GetResult();
        return submitted.JobId;
    }

    public async Task<bool> ConfirmPrintedAsync(RoutingDelivery delivery,int spoolId,CancellationToken token)
    {
        // A successful EndDoc or disappearing queue entry is NOT proof of printed paper.
        var printer=(await discovery.EnumerateAsync(token)).SingleOrDefault(p=>(p.RegistryId??p.DeviceId)==delivery.TargetPrinter);
        if(printer is null || PhysicalPrinterFingerprint.For(printer)!=authorization.PrinterFingerprint)return false;
        var observation=await backend.ObserveAsync(printer.Name,spoolId,new(delivery.JobId),token);
        return observation.State==SpoolState.ReportedPrinted;
    }
}
