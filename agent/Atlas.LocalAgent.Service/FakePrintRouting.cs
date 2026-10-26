using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text.Json;
using Atlas.LocalAgent.Core;

namespace Atlas.LocalAgent.Service;

public sealed record RoutingDelivery(Guid DeliveryId, Guid JobId, int OrganizationId, int CenterId, Guid TargetAgent,
    string TargetPrinter, int RequestedBy, string OriginType, Guid? SourceAgent, string DocumentReference,
    string DocumentType, string SecurityClass, string Format, int Copies, DateTimeOffset ExpiresAt,
    string ContentSha256, string IntentHash, string Status, bool PrinterAvailable, bool ReceiptOnly,
    string? PhysicalEvidence=null,int? ResultSpoolerId=null,bool? HumanConfirmed=null)
{
    public DurablePrintEnvelope Envelope() => new(new(new(JobId),TargetAgent,TargetPrinter,DocumentReference,
        Format=="plain_text"?PrintDocumentFormat.PlainText:PrintDocumentFormat.Pdf,Copies) {
            IntentVersion=2,RequestedByUserId=RequestedBy,DocumentType=DocumentType,
            Origin=new(Enum.Parse<PrintOriginType>(OriginType.Replace("_",""),true),RequestedBy.ToString(System.Globalization.CultureInfo.InvariantCulture),
                $"org-{OrganizationId}-center-{CenterId}",SourceAgent),
            SecurityClass=Enum.Parse<DocumentSecurityClass>(SecurityClass.Replace("_",""),true)},
        OrganizationId,CenterId,ExpiresAt,ContentSha256);
}

public interface IPrintJobRelay
{
    Task<RoutingDelivery?> PollAsync(CancellationToken token);
    Task<string> ProgressAsync(RoutingDelivery delivery,string state,CancellationToken token);
    Task<byte[]> DownloadAsync(RoutingDelivery delivery,CancellationToken token);
    Task ReportAsync(RoutingDelivery delivery,DurablePrintState result,CancellationToken token);
}

/// <summary>Same-origin HTTPS only; no URL/path from a document, redirects or plaintext fallback.</summary>
public sealed class HttpsPrintJobRelay : IPrintJobRelay
{
    private readonly HttpClient _http;
    private static readonly JsonSerializerOptions Json=new(){PropertyNamingPolicy=JsonNamingPolicy.SnakeCaseLower};
    private readonly string _prefix;
    public HttpsPrintJobRelay(HttpClient http,string credential,string route="print-jobs")
    {
        var endpoint=http.BaseAddress;
        if(endpoint is null || endpoint.Scheme!="https" || endpoint.UserInfo.Length!=0 || endpoint.Query.Length!=0 || endpoint.Fragment.Length!=0
            || endpoint.AbsolutePath!="/" || string.IsNullOrWhiteSpace(credential)) throw new ArgumentException("HTTPS endpoint required.");
        if(route is not ("print-jobs" or "print-routing"))throw new ArgumentException("Unknown routing API.");
        _prefix="api/v1/"+route;
        _http=http;_http.DefaultRequestHeaders.Authorization=new AuthenticationHeaderValue("Bearer",credential);
        _http.MaxResponseContentBufferSize=32768;
    }
    private string Path(RoutingDelivery d,string action)=>$"{_prefix}/device/{d.JobId:D}/{action}";
    public async Task<RoutingDelivery?> PollAsync(CancellationToken token)
    {
        using var response=await _http.GetAsync(_prefix+"/device/poll",token);response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<RoutingDelivery>(Json,token);
    }
    public async Task<RoutingDelivery> RedeliverAsync(Guid id,CancellationToken token)
    {
        using var response=await _http.GetAsync($"{_prefix}/device/{id:D}/delivery",token);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<RoutingDelivery>(Json,token) ?? throw new InvalidDataException();
    }
    public async Task<string> ProgressAsync(RoutingDelivery d,string state,CancellationToken token)
    {
        using var response=await _http.PostAsJsonAsync(Path(d,"progress"),new{d.DeliveryId,Status=state},Json,token);
        if(response.StatusCode==HttpStatusCode.Conflict)
        {
            using var retry=await _http.GetAsync(Path(d,"delivery"),token);retry.EnsureSuccessStatusCode();
            return (await retry.Content.ReadFromJsonAsync<RoutingDelivery>(Json,token))?.Status ?? throw new InvalidDataException();
        }
        response.EnsureSuccessStatusCode();using var body=await response.Content.ReadFromJsonAsync<JsonDocument>(cancellationToken:token);
        return body!.RootElement.GetProperty("status").GetString()!;
    }
    public async Task<byte[]> DownloadAsync(RoutingDelivery d,CancellationToken token)
    {
        using var response=await _http.GetAsync(Path(d,$"artifact?delivery_id={d.DeliveryId:D}"),token);response.EnsureSuccessStatusCode();
        var data=await response.Content.ReadAsByteArrayAsync(token);
        if(data.Length>8192) { CryptographicOperations.ZeroMemory(data);throw new InvalidDataException("Artifact too large."); }
        return data;
    }
    public async Task ReportAsync(RoutingDelivery d,DurablePrintState result,CancellationToken token)
    {
        using var response=await _http.PostAsJsonAsync(Path(d,"result"),new{d.DeliveryId,Outcome=result.Status,
            SyntheticSpoolerId=result.SpoolId,ErrorCode=result.ErrorCode},Json,token);response.EnsureSuccessStatusCode();
    }
}

public enum FakePrintOutcome { Printed, Accepted, Failed, Timeout, Unknown }
/// <summary>Cannot call Windows: only generates metadata and a synthetic numeric receipt.</summary>
public sealed class FakePrintExecutor(FakePrintOutcome outcome=FakePrintOutcome.Printed,Action<Guid,int,int>? observed=null) : IRoutingPrintExecutor
{
    private int _calls;
    public int Calls=>Volatile.Read(ref _calls);
    public FakePrintOutcome Outcome=>outcome;
    public bool PrinterAvailable {get;set;}=true;
    public Action? DuringPrinting {get;set;}
    public Task<DurablePrintFailure?> PreflightAsync(RoutingDelivery delivery,CancellationToken token) =>
        Task.FromResult<DurablePrintFailure?>(!PrinterAvailable ? DurablePrintFailure.PrinterUnavailable
            : outcome==FakePrintOutcome.Failed ? DurablePrintFailure.InvalidArtifact : null);
    public Task<bool> ConfirmPrintedAsync(RoutingDelivery delivery,int spoolId,CancellationToken token) =>
        Task.FromResult(outcome==FakePrintOutcome.Printed);
    public int Execute(PrintJob job)
    {
        Interlocked.Increment(ref _calls);
        var spool=100000+(int)(System.Buffers.Binary.BinaryPrimitives.ReadUInt32LittleEndian(SHA256.HashData(job.Id.Value.ToByteArray()))%1000000000);
        observed?.Invoke(job.Id.Value,spool,job.Copies);
        DuringPrinting?.Invoke();
        if(outcome is FakePrintOutcome.Timeout or FakePrintOutcome.Unknown) throw new TimeoutException("Synthetic uncertain result.");
        return spool;
    }
}

/// <summary>One workflow for both executors. Durable receipt is checked before any policy/executor.</summary>
public class PrintRoutingWorker(DurablePrintJobStore store,IPrintJobRelay relay,IRoutingPrintExecutor executor,
    IPrintExecutionPolicy? policy=null,IRoutingPrintExecutor? physicalExecutor=null,Action<PrintExecutionDecision>? decisionObserved=null)
{
    // A single process may have several worker instances/replays; do not mistake an
    // in-flight barrier for crash recovery. The per-root process lock is also retained.
    private static readonly SemaphoreSlim Gate=new(1,1);
    public async Task<DurablePrintState> HandleAsync(RoutingDelivery delivery,CancellationToken token=default)
    {
        await Gate.WaitAsync(token);
        try
        {
            var envelope=delivery.Envelope();envelope.Job.Validate();
            if(PrintIntentFingerprint.Hash(envelope)!=delivery.IntentHash)throw new InvalidDataException("Intent fingerprint mismatch.");
            if(store.Accept(envelope,delivery.DeliveryId)==PrintJobRegistration.Conflict)throw new InvalidDataException("Intent conflict.");
            var id=envelope.Job.Id;var state=store.Read(id);
            if(state.Status is not ("received" or "ready")) {
                if(state.Status=="unknown")state=store.RequireReview(id);
                if(state.Status=="submitted" && delivery.DocumentType=="physical_routing_qa" && delivery.HumanConfirmed is { } confirmed)
                {
                    if(!delivery.ReceiptOnly || delivery.ResultSpoolerId!=state.SpoolId || delivery.Status!=(confirmed?"printed":"unknown"))
                        throw new InvalidDataException("Human confirmation does not match the durable spool receipt.");
                    state=store.RecordHumanConfirmation(id,state.SpoolId!.Value,confirmed);
                }
                if(state.Status=="submitted" && delivery.DocumentType=="physical_routing_qa" && physicalExecutor is not null
                    && await physicalExecutor.ConfirmPrintedAsync(delivery,state.SpoolId!.Value,token))
                    state=store.RecordPrintedObservation(id,state.SpoolId.Value);
                await relay.ReportAsync(delivery,state,token);return state;
            }
            async Task<DurablePrintState?> Stop(string remote)
            {
                DurablePrintState? stopped=remote switch {"cancelled"=>store.Cancel(id),"expired"=>store.ExpireBeforeExecution(id),
                    "unknown" or "printing" or "submitted" or "printed"=>store.RequireReview(id),_=>null};
                if(stopped is not null)await relay.ReportAsync(delivery,stopped,token);
                return stopped;
            }
            if(delivery.ReceiptOnly)return await Stop(delivery.Status) ?? throw new InvalidDataException("Receipt without local result.");
            var decision=(policy ?? new SingleJobPhysicalExecutionPolicy(new())).Evaluate(delivery,state);
            decisionObserved?.Invoke(decision);
            var physical=decision.Mode==PrintExecutionMode.PhysicalAllowed;
            var selected=physical?physicalExecutor:executor;
            if(decision.Mode==PrintExecutionMode.PhysicalDenied || selected is null)
            {
                state=store.FailBeforeSpool(id,DurablePrintFailure.PhysicalDenied);
                await relay.ReportAsync(delivery,state,token);return state;
            }
            var stop=await Stop(await relay.ProgressAsync(delivery,"received",token));if(stop is not null)return stop;
            var failure=await selected.PreflightAsync(delivery,token);
            if(!delivery.PrinterAvailable || failure is not null)
            {
                state=store.FailBeforeSpool(id,failure??DurablePrintFailure.PrinterUnavailable);
                await relay.ReportAsync(delivery,state,token);return state;
            }
            byte[]? bytes=null;
            try
            {
                bytes=await relay.DownloadAsync(delivery,token);
                if(Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant()!=delivery.ContentSha256)
                    throw new InvalidDataException("Artifact hash mismatch.");
            }
            catch(HttpRequestException ex) when(ex.StatusCode==HttpStatusCode.Gone)
            {
                // A revoked/cancelled artifact is also gone. Recover the authoritative state first.
                var authoritative=await relay.ProgressAsync(delivery,"received",token);
                var stopped=await Stop(authoritative);if(stopped is not null)return stopped;
                throw;
            }
            catch(InvalidDataException)
            { state=store.FailBeforeSpool(id,DurablePrintFailure.InvalidArtifact);await relay.ReportAsync(delivery,state,token);return state; }
            finally {if(bytes is not null)CryptographicOperations.ZeroMemory(bytes);}
            state=store.MarkReady(id);
            if(state.Status=="expired") {await relay.ReportAsync(delivery,state,token);return state;}
            stop=await Stop(await relay.ProgressAsync(delivery,"ready",token));if(stop is not null)return stop;
            var remote=await relay.ProgressAsync(delivery,"printing",token);
            if(remote!="printing")return await Stop(remote) ?? throw new InvalidDataException("Printing denied.");
            // Revalidate time-limited local authorization immediately before the durable barrier.
            if(physical && policy!.Evaluate(delivery,store.Read(id)).Mode!=PrintExecutionMode.PhysicalAllowed)
            {state=store.FailBeforeSpool(id,DurablePrintFailure.PhysicalDenied);await relay.ReportAsync(delivery,state,token);return state;}
            state=store.ExecuteOnce(id,()=>selected.Execute(envelope.Job),physical,physical?delivery.DeliveryId:null,
                decision.PageFormat,decision.PrinterFingerprint);
            if(state.Status=="submitted" && await selected.ConfirmPrintedAsync(delivery,state.SpoolId!.Value,token))
                state=store.RecordPrintedObservation(id,state.SpoolId!.Value);
            // Lost response leaves this receipt durable. Next delivery only reports it.
            await relay.ReportAsync(delivery,state,token);return state;
        }
        finally {Gate.Release();}
    }
}

// Compatibility entry point for the isolated fake harness; never accepts a physical executor.
public sealed class FakePrintRoutingWorker(DurablePrintJobStore store,IPrintJobRelay relay,FakePrintExecutor executor)
    : PrintRoutingWorker(store,relay,executor);
