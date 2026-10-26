using System.Text.Json;
using Atlas.LocalAgent.Core;

namespace Atlas.LocalAgent.Service;

public sealed class OfficialPrintConnection(HttpClient client,HttpsPrintJobRelay relay,Guid station,int organization,int center):IDisposable
{
    public HttpsPrintJobRelay Relay=>relay;
    public Guid Station=>station;
    public int Organization=>organization;
    public int Center=>center;
    public void Dispose()=>client.Dispose();
    public override string ToString()=>"[PRINT CONNECTION REDACTED]";
}

/// <summary>Outbound HTTPS consumer. SafeValidation default; physical QA requires an independent local one-job grant.</summary>
public sealed class OfficialPrintConsumer(string root,AgentRuntime runtime,AtlasRegistryClient registry,
    Guid? loseResultOnce=null,Guid? unknownJob=null,PhysicalExecutionAuthorization? authorization=null)
{
    public const string ExecutionMode="SafeValidation";
    private bool _lost;

    public async Task RunAsync(CancellationToken token)
    {
        while(!token.IsCancellationRequested)
        {
            try
            {
                if(runtime.Snapshot.State==AgentState.Connected)
                {
                    using var c=await registry.OpenPrintConnectionAsync(runtime.Snapshot.Identity.AgentId,token);
                    if(c is not null){var d=await c.Relay.PollAsync(token);if(d is not null)await HandleAsync(c,d,token);}
                }
            }
            catch(OperationCanceledException) when(token.IsCancellationRequested){break;}
            catch(Exception e) when(e is HttpRequestException or IOException or ArgumentException or System.Text.Json.JsonException
                or System.Security.Cryptography.CryptographicException or System.ComponentModel.Win32Exception or UnauthorizedAccessException)
            { /* Fail closed, keep SQLite receipt. Never print on errors or log credentials/content. */ }
            await Task.Delay(TimeSpan.FromSeconds(3),token);
        }
    }

    public async Task ReplayAsync(Guid id,CancellationToken token)
    {
        using var c=await registry.OpenPrintConnectionAsync(runtime.Snapshot.Identity.AgentId,token)
            ?? throw new InvalidOperationException("Protected routing connection unavailable.");
        await HandleAsync(c,await c.Relay.RedeliverAsync(id,token),token);
    }

    private async Task HandleAsync(OfficialPrintConnection c,RoutingDelivery d,CancellationToken token)
    {
        ValidateEnvelope(c,d);
        var directory=Path.Combine(Path.GetFullPath(root),"routing",$"{c.Organization}-{c.Center}");
        Directory.CreateDirectory(directory);
        var store=new DurablePrintJobStore(Path.Combine(directory,"inbox.sqlite"),c.Station,c.Organization,c.Center);
        var grant=authorization??new();
        var executor=new FakePrintExecutor(d.JobId==unknownJob?FakePrintOutcome.Unknown:FakePrintOutcome.Printed,
            observed:(job,receipt,copies)=>File.AppendAllText(Path.Combine(directory,"validation-executions.jsonl"),
                JsonSerializer.Serialize(new{JobId=job,ExecutionMode,SyntheticReceipt=receipt,Copies=copies,At=DateTimeOffset.UtcNow})+Environment.NewLine));
        IPrintJobRelay relay=new ResultGate(c.Relay,()=>{
            if(!_lost && loseResultOnce==d.JobId){_lost=true;return true;}return false;
        });
        // Native backend is lazy: constructing a disabled consumer never even constructs it.
        IPhysicalPrintExecutor? physical=grant.Enabled
            ?new PhysicalPrintExecutor(grant,new WindowsGdiPrintBackend(true),new WindowsPrinterDiscovery(),()=>runtime.Snapshot,store):null;
        var state=await new PrintRoutingWorker(store,relay,executor,new SingleJobPhysicalExecutionPolicy(grant),physical,
            decision=>File.AppendAllText(Path.Combine(directory,"execution-decisions.jsonl"),JsonSerializer.Serialize(new {
                d.JobId,ExecutionMode=decision.Mode.ToString(),decision.Reason,At=DateTimeOffset.UtcNow})+Environment.NewLine)).HandleAsync(d,token);
        Console.WriteLine(JsonSerializer.Serialize(new{d.JobId,ExecutionMode=d.DocumentType=="physical_routing_qa"?"PhysicalQa":"SafeValidation",state.Status,FakeExecutorCalls=executor.Calls}));
    }

    public static void ValidateEnvelope(OfficialPrintConnection c,RoutingDelivery d)
    {
        var safe=d.DocumentType=="synthetic_test" && d.DocumentReference is "qa-general" or "qa-financial" or "qa-clinical";
        var physical=d.DocumentType=="physical_routing_qa" && d.DocumentReference=="physical-routing-qa";
        if(d.TargetAgent!=c.Station || d.OrganizationId!=c.Organization || d.CenterId!=c.Center
            || d.Format!="plain_text" || !(safe||physical))
            throw new InvalidDataException("Only authorized validation artifacts are executable.");
    }

    private sealed class ResultGate(IPrintJobRelay inner,Func<bool> lose):IPrintJobRelay
    {
        public Task<RoutingDelivery?> PollAsync(CancellationToken t)=>inner.PollAsync(t);
        public Task<string> ProgressAsync(RoutingDelivery d,string s,CancellationToken t)=>inner.ProgressAsync(d,s,t);
        public Task<byte[]> DownloadAsync(RoutingDelivery d,CancellationToken t)=>inner.DownloadAsync(d,t);
        public Task ReportAsync(RoutingDelivery d,DurablePrintState s,CancellationToken t)
        {if(lose())throw new HttpRequestException("Validation ACK intentionally withheld; receipt preserved.");return inner.ReportAsync(d,s,t);}
    }
}
