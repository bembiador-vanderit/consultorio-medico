using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Data.Sqlite;
using Atlas.LocalAgent.Core;
using Atlas.LocalAgent.Service;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Atlas.LocalAgent.Tests;

[TestClass]
public sealed class PhysicalBridgeTests
{
    private string _root=null!;
    private readonly Guid _station=Guid.NewGuid();
    private static readonly byte[] Body=Encoding.UTF8.GetBytes("SYNTHETIC ONLY");
    private static readonly PrinterDevice Printer=new(PrinterDevice.IdFor("QA physical"),"QA physical","Ready",false,
        PrinterConnection.Local,"QA driver",new(false,false,1,[new("A4",2100,2970,9)]))
        {RegistryId=PrinterDevice.RegistryIdFor("QA physical","QA_PORT","QA driver",null,false)};
    [TestInitialize]public void Setup()=>_root=Directory.CreateTempSubdirectory("atlas-physical-bridge-tests-").FullName;
    [TestCleanup]public void Cleanup()=>Directory.Delete(_root,true);
    private DurablePrintJobStore Store()=>new(Path.Combine(_root,"inbox.sqlite"),_station,1,1);
    private RoutingDelivery Delivery()
    {
        var d=new RoutingDelivery(Guid.NewGuid(),Guid.NewGuid(),1,1,_station,Printer.RegistryId!,1,"WEB_DESKTOP",null,
            "physical-routing-qa","physical_routing_qa","GENERAL","plain_text",1,DateTimeOffset.UtcNow.AddMinutes(2),
            Convert.ToHexString(SHA256.HashData(Body)).ToLowerInvariant(),"","queued",true,false);
        return d with{IntentHash=PrintIntentFingerprint.Hash(d.Envelope())};
    }
    private static PhysicalExecutionAuthorization Grant(RoutingDelivery d)=>new() {
        Enabled=true,AllowedJobId=d.JobId,AllowedAgentId=d.TargetAgent,AllowedPrinterId=d.TargetPrinter,
        ExpectedPrinterName=Printer.Name,PrinterFingerprint=PhysicalPrinterFingerprint.For(Printer),OrganizationId=1,CenterId=1,
        IntentHash=d.IntentHash,ContentSha256=d.ContentSha256,ExecutionMode="PhysicalQa",
        ValidFrom=DateTimeOffset.UtcNow.AddSeconds(-5),ExpiresAt=DateTimeOffset.UtcNow.AddMinutes(2)};
    private AgentSnapshot Snapshot(AgentState state=AgentState.Connected)=>new(true,new(_station,DateTimeOffset.UtcNow),
        new("QA station","QA",new()),state,new(_station,"QA station",AgentVersion.Current,AgentVersion.Protocol,"QA",state,
        DateTimeOffset.UtcNow,new(1,0)),[Printer],AgentErrorCode.None);

    private sealed class Relay:IPrintJobRelay
    {
        public bool LoseAck,Cancel;public Action<string>? Progress { get; set; }
        public Task<RoutingDelivery?> PollAsync(CancellationToken t)=>Task.FromResult<RoutingDelivery?>(null);
        public Task<string> ProgressAsync(RoutingDelivery d,string s,CancellationToken t)
        {Progress?.Invoke(s);return Task.FromResult(Cancel?"cancelled":s);}
        public Task<byte[]> DownloadAsync(RoutingDelivery d,CancellationToken t)=>Task.FromResult((byte[])Body.Clone());
        public Task ReportAsync(RoutingDelivery d,DurablePrintState s,CancellationToken t)
        {if(LoseAck){LoseAck=false;throw new HttpRequestException("QA ACK lost");}return Task.CompletedTask;}
    }
    private sealed class SpyPhysical(DurablePrintJobStore store):IPhysicalPrintExecutor
    {
        public int Calls;public bool Unknown,Failed;
        public Task<DurablePrintFailure?> PreflightAsync(RoutingDelivery d,CancellationToken t)=>
            Task.FromResult<DurablePrintFailure?>(Failed?DurablePrintFailure.PrinterUnavailable:null);
        public int Execute(PrintJob job)
        {
            Interlocked.Increment(ref Calls);
            var evidence=store.PhysicalEvidence(job.Id);Assert.IsNotNull(evidence);Assert.AreEqual(1,evidence.Copies);
            Assert.AreEqual("A4",evidence.PageFormat);Assert.AreEqual(PhysicalPrinterFingerprint.For(Printer),evidence.PrinterFingerprint);
            Assert.AreEqual("unknown",store.Read(job.Id).Status); // persisted printing barrier is already irreversible
            if(Unknown)throw new TimeoutException("QA uncertain after handoff");
            store.RecordSpoolAcceptance(job.Id,123);return 123;
        }
        public Task<bool> ConfirmPrintedAsync(RoutingDelivery d,int id,CancellationToken t)=>Task.FromResult(true);
    }
    private PrintRoutingWorker Worker(DurablePrintJobStore store,Relay relay,IRoutingPrintExecutor physical,PhysicalExecutionAuthorization grant)=>
        new(store,relay,new FakePrintExecutor(),new SingleJobPhysicalExecutionPolicy(grant),physical);

    [TestMethod]
    public async Task DefaultDenyPhysicalAndSafeValidationPreserved()
    {
        var d=Delivery();var store=Store();var physical=new SpyPhysical(store);var relay=new Relay();
        Assert.AreEqual("failed",(await Worker(store,relay,physical,new()).HandleAsync(d)).Status);
        Assert.AreEqual(0,physical.Calls);
        var safe=d with{JobId=Guid.NewGuid(),DeliveryId=Guid.NewGuid(),DocumentType="synthetic_test",DocumentReference="qa-general"};
        safe=safe with{IntentHash=PrintIntentFingerprint.Hash(safe.Envelope())};
        Assert.AreEqual("printed",(await Worker(store,relay,physical,new()).HandleAsync(safe)).Status);
        Assert.AreEqual(0,physical.Calls);Assert.IsNull(store.PhysicalEvidence(new(safe.JobId)));
    }

    [TestMethod]
    [DataRow("job")][DataRow("agent")][DataRow("center")][DataRow("org")][DataRow("printer")]
    [DataRow("copies")][DataRow("intent")][DataRow("content")][DataRow("expired")][DataRow("future")]
    [DataRow("long-window")][DataRow("mode")][DataRow("reference")][DataRow("document")][DataRow("source")]
    [DataRow("cancelled")][DataRow("unknown")][DataRow("fingerprint")]
    public void AllMismatchesDeny(string change)
    {
        var d=Delivery();var grant=Grant(d);var state=new DurablePrintState("ready");
        switch(change) {
            case "job":grant=grant with{AllowedJobId=Guid.NewGuid()};break;
            case "agent":grant=grant with{AllowedAgentId=Guid.NewGuid()};break;
            case "center":grant=grant with{CenterId=2};break;
            case "org":grant=grant with{OrganizationId=2};break;
            case "printer":grant=grant with{AllowedPrinterId="other"};break;
            case "copies":d=d with{Copies=2};break;
            case "intent":grant=grant with{IntentHash=new string('b',64)};break;
            case "content":grant=grant with{ContentSha256=new string('b',64)};break;
            case "expired":grant=grant with{ExpiresAt=DateTimeOffset.UtcNow.AddMinutes(-1)};break;
            case "future":grant=grant with{ValidFrom=DateTimeOffset.UtcNow.AddMinutes(1)};break;
            case "long-window":grant=grant with{ExpiresAt=DateTimeOffset.UtcNow.AddHours(1)};break;
            case "mode":grant=grant with{ExecutionMode="Physical"};break;
            case "reference":d=d with{DocumentReference="arbitrary"};break;
            case "document":d=d with{DocumentType="invoice"};break;
            case "source":d=d with{SourceAgent=Guid.NewGuid()};break;
            case "cancelled":d=d with{Status="cancelled"};break;
            case "unknown":state=new("unknown");break;
            case "fingerprint":grant=grant with{PrinterFingerprint=null};break;
        }
        Assert.AreEqual(PrintExecutionMode.PhysicalDenied,new SingleJobPhysicalExecutionPolicy(grant).Evaluate(d,state).Mode);
    }
    [TestMethod]
    public async Task ExactGrantCallsMockOnceAndPreservesDurableReceiptAcrossRestartAndLostAck()
    {
        var d=Delivery();var store=Store();var first=new SpyPhysical(store);var relay=new Relay{LoseAck=true};
        await Assert.ThrowsExactlyAsync<HttpRequestException>(()=>Worker(store,relay,first,Grant(d)).HandleAsync(d));
        Assert.AreEqual(1,first.Calls);Assert.AreEqual("printed",store.Read(new(d.JobId)).Status);
        Assert.AreEqual(123,store.PhysicalEvidence(new(d.JobId))!.SpoolId);
        var reopened=Store();var second=new SpyPhysical(reopened);
        await Task.WhenAll(Enumerable.Range(0,10).Select(_=>Worker(reopened,relay,second,Grant(d)).HandleAsync(d with{DeliveryId=Guid.NewGuid(),ReceiptOnly=true,Status="printed"})));
        Assert.AreEqual(0,second.Calls);
    }
    [TestMethod]
    public async Task ConcurrentWorkersClaimOnePhysicalExecution()
    {
        var d=Delivery();var store=Store();var spy=new SpyPhysical(store);var relay=new Relay();
        await Task.WhenAll(Enumerable.Range(0,8).Select(_=>Worker(store,relay,spy,Grant(d)).HandleAsync(d with{DeliveryId=Guid.NewGuid()})));
        Assert.AreEqual(1,spy.Calls);
    }
    [TestMethod]
    public async Task UnknownAndInterruptedBarrierNeverReplayPhysical()
    {
        var d=Delivery();var store=Store();var spy=new SpyPhysical(store){Unknown=true};
        Assert.AreEqual("unknown",(await Worker(store,new(),spy,Grant(d)).HandleAsync(d)).Status);
        var reopened=Store();var second=new SpyPhysical(reopened);
        Assert.AreEqual("unknown",(await Worker(reopened,new(),second,Grant(d)).HandleAsync(d)).Status);
        Assert.AreEqual(0,second.Calls);
        // Simulates process death after durable barrier, before native result/receipt.
        var other=Delivery();store.Accept(other.Envelope(),other.DeliveryId);store.MarkReady(new(other.JobId));
        store.ExecuteOnce(new(other.JobId),()=>throw new IOException("QA interruption"),true,other.DeliveryId,SyntheticPageFormat.A4,PhysicalPrinterFingerprint.For(Printer));
        await Worker(Store(),new(),second,Grant(other)).HandleAsync(other);Assert.AreEqual(0,second.Calls);
    }
    [TestMethod]
    public async Task CrashAfterPreExecutionEvidenceAndBeforeResultNeverExecutesAfterRestart()
    {
        var d=Delivery();var store=Store();store.Accept(d.Envelope(),d.DeliveryId);store.MarkReady(new(d.JobId));
        using(var db=new SqliteConnection($"Data Source={Path.Combine(_root,"inbox.sqlite")};Pooling=False")) {
            db.Open();using var command=db.CreateCommand();command.CommandText="""
                UPDATE jobs SET state='printing' WHERE id=$id;
                INSERT INTO physical_executions(job_id,delivery_id,printer_id,page_format,printer_fingerprint,copies,started_at)
                VALUES($id,$delivery,$printer,'A4',$fingerprint,1,1);
                """;
            command.Parameters.AddWithValue("$id",d.JobId.ToString());command.Parameters.AddWithValue("$delivery",d.DeliveryId.ToString());
            command.Parameters.AddWithValue("$fingerprint",PhysicalPrinterFingerprint.For(Printer));
            command.Parameters.AddWithValue("$printer",d.TargetPrinter);command.ExecuteNonQuery();
        }
        var reopened=Store();var spy=new SpyPhysical(reopened);
        Assert.AreEqual("unknown",(await Worker(reopened,new(),spy,Grant(d)).HandleAsync(d)).Status);
        Assert.AreEqual(0,spy.Calls);Assert.IsNotNull(reopened.PhysicalEvidence(new(d.JobId)));
    }
    [TestMethod]
    public async Task SpoolIdSurvivesExceptionAfterNativeAcceptanceWithoutRetry()
    {
        var d=Delivery();var store=Store();store.Accept(d.Envelope(),d.DeliveryId);store.MarkReady(new(d.JobId));
        var state=store.ExecuteOnce(new(d.JobId),()=>{store.RecordSpoolAcceptance(new(d.JobId),777);throw new IOException("QA driver outcome uncertain");},
            true,d.DeliveryId,SyntheticPageFormat.A4,PhysicalPrinterFingerprint.For(Printer));
        Assert.AreEqual("unknown",state.Status);Assert.AreEqual(777,state.SpoolId);
        var spy=new SpyPhysical(Store());await Worker(Store(),new(),spy,Grant(d)).HandleAsync(d);Assert.AreEqual(0,spy.Calls);
    }
    [TestMethod]
    public async Task AuthorizationExpiringWhilePreparingCannotReachPhysicalExecutor()
    {
        var d=Delivery();var store=Store();var spy=new SpyPhysical(store);var relay=new Relay();var now=DateTimeOffset.UtcNow;
        var grant=Grant(d);var policy=new SingleJobPhysicalExecutionPolicy(grant,()=>now);
        relay.Progress=s=>{if(s=="ready")now=grant.ExpiresAt!.Value.AddSeconds(1);};
        var state=await new PrintRoutingWorker(store,relay,new FakePrintExecutor(),policy,spy).HandleAsync(d);
        Assert.AreEqual("failed",state.Status);Assert.AreEqual(0,spy.Calls);Assert.IsNull(store.PhysicalEvidence(new(d.JobId)));
    }
    [TestMethod]
    public async Task CancellationExpiryAndKnownFailureRemainBeforeSpool()
    {
        foreach(var scenario in new[]{"cancel","expiry","failure"}) {
            var d=Delivery();var store=Store();var spy=new SpyPhysical(store){Failed=scenario=="failure"};var grant=Grant(d);
            if(scenario=="expiry"){d=d with{ExpiresAt=DateTimeOffset.UtcNow.AddSeconds(-1)};d=d with{IntentHash=PrintIntentFingerprint.Hash(d.Envelope())};}
            var result=await Worker(store,new(){Cancel=scenario=="cancel"},spy,grant).HandleAsync(d);
            Assert.AreEqual(scenario=="cancel"?"cancelled":scenario=="expiry"?"expired":"failed",result.Status);
            Assert.AreEqual(0,spy.Calls);Assert.IsNull(store.PhysicalEvidence(new(d.JobId)));
        }
    }
    private sealed class Discovery(PrinterDevice printer):IPrinterDiscovery
    {public Task<IReadOnlyList<PrinterDevice>> EnumerateAsync(CancellationToken t)=>Task.FromResult<IReadOnlyList<PrinterDevice>>([printer]);}
    private sealed class Backend:ILocalPrintBackend
    {
        public int Calls;public SpoolState Observation=SpoolState.ReportedPrinted;
        public Task<bool> IsSpoolerAvailableAsync(CancellationToken t)=>Task.FromResult(true);
        public Task<SpoolSubmission> SubmitAsync(SyntheticPrintDocument d,Func<bool> begin,Action<int> accepted,CancellationToken t)
        {Assert.IsTrue(begin());Assert.IsTrue(d.OfficialRoutingQa);Calls++;accepted(456);return Task.FromResult(new SpoolSubmission(456));}
        public Task<SpoolObservation> ObserveAsync(string p,int id,PrintJobId job,CancellationToken t)=>Task.FromResult(new SpoolObservation(Observation));
    }
    [TestMethod]
    public async Task WindowsAdapterUsesExistingBackendThroughMockAndNeverInfersPrintedFromMissing()
    {
        var d=Delivery();var store=Store();var backend=new Backend();var grant=Grant(d);
        var adapter=new PhysicalPrintExecutor(grant,backend,new Discovery(Printer),()=>Snapshot(),store);
        Assert.AreEqual("printed",(await Worker(store,new(),adapter,grant).HandleAsync(d)).Status);Assert.AreEqual(1,backend.Calls);
        backend.Observation=SpoolState.Missing;Assert.IsFalse(await adapter.ConfirmPrintedAsync(d,456,default));
    }
    [TestMethod][DataRow("driver")][DataRow("paper")][DataRow("identity")][DataRow("revoked")][DataRow("station")]
    public async Task LocalIdentityCapabilitiesAndRevocationAreRevalidated(string change)
    {
        var d=Delivery();var grant=Grant(d);var printer=change switch {
            "driver"=>Printer with{Driver="different"},"paper"=>Printer with{Capabilities=new(false,false,1,[])},
            "identity"=>Printer with{RegistryId="different"},_=>Printer};
        var backend=new Backend();var snapshot=Snapshot(change=="revoked"?AgentState.Revoked:AgentState.Connected);
        if(change=="station")snapshot=snapshot with{Identity=new(Guid.NewGuid(),DateTimeOffset.UtcNow)};
        var adapter=new PhysicalPrintExecutor(grant,backend,new Discovery(printer),()=>snapshot,Store());
        Assert.AreEqual(DurablePrintFailure.PhysicalDenied,await adapter.PreflightAsync(d,default));Assert.AreEqual(0,backend.Calls);
    }
    [TestMethod]
    public void ConfigDefaultsAndUnknownFieldsFailClosed()
    {
        var grant=PhysicalExecutionAuthorization.Load(null);Assert.IsFalse(grant.Enabled);Assert.IsNull(grant.AllowedJobId);
        var file=Path.Combine(_root,"grant.json");File.WriteAllText(file,"{\"Enabled\":true,\"unsafeToggle\":true}");
        Assert.ThrowsExactly<JsonException>(()=>PhysicalExecutionAuthorization.Load(file));
        Assert.ThrowsExactly<InvalidDataException>(()=>PhysicalExecutionAuthorization.Load("https://example.test/config"));
    }
    [TestMethod][DataRow(true)][DataRow(false)]
    public async Task AuthenticatedHumanResultSynchronizesSubmittedWithoutAnyExecutor(bool yes)
    {
        var d=Delivery();var store=Store();var backend=new Backend{Observation=SpoolState.Missing};var grant=Grant(d);
        var adapter=new PhysicalPrintExecutor(grant,backend,new Discovery(Printer),()=>Snapshot(),store);
        var initial=await Worker(store,new(),adapter,grant).HandleAsync(d);
        Assert.AreEqual("submitted",initial.Status);Assert.AreEqual("SUBMITTED_TO_SPOOLER",initial.EvidenceType);
        Assert.AreEqual(1,backend.Calls);
        var reopened=Store();var spy=new SpyPhysical(reopened);
        var receipt=d with{ReceiptOnly=true,Status=yes?"printed":"unknown",ResultSpoolerId=456,HumanConfirmed=yes,
            PhysicalEvidence=yes?"HUMAN_CONFIRMED_PRINTED":"UNKNOWN_AFTER_SPOOL"};
        var result=await Worker(reopened,new(),spy,new()).HandleAsync(receipt);
        Assert.AreEqual(yes?"printed":"unknown",result.Status);
        Assert.AreEqual(yes?"HUMAN_CONFIRMED_PRINTED":"HUMAN_REPORTED_PROBLEM",result.EvidenceType);
        await Worker(Store(),new(),spy,new()).HandleAsync(receipt);Assert.AreEqual(0,spy.Calls);
    }
    [TestMethod]
    public async Task WindowsEvidenceIsDistinctAndUnknownCannotBePromotedByHumanMetadata()
    {
        var d=Delivery();var store=Store();var backend=new Backend();var grant=Grant(d);
        var adapter=new PhysicalPrintExecutor(grant,backend,new Discovery(Printer),()=>Snapshot(),store);
        var result=await Worker(store,new(),adapter,grant).HandleAsync(d);
        Assert.AreEqual("OS_REPORTED_PRINTED",result.EvidenceType);
        var uncertain=Delivery();var spy=new SpyPhysical(store){Unknown=true};
        await Worker(store,new(),spy,Grant(uncertain)).HandleAsync(uncertain);
        Assert.ThrowsExactly<InvalidOperationException>(()=>store.RecordHumanConfirmation(new(uncertain.JobId),123,true));
        Assert.AreEqual("unknown",Store().Read(new(uncertain.JobId)).Status);
    }
    [TestMethod]
    public async Task HumanMetadataForAnotherSpoolReceiptFailsClosed()
    {
        var d=Delivery();var store=Store();var backend=new Backend{Observation=SpoolState.Missing};
        await Worker(store,new(),new PhysicalPrintExecutor(Grant(d),backend,new Discovery(Printer),()=>Snapshot(),store),Grant(d)).HandleAsync(d);
        var spy=new SpyPhysical(Store());
        await Assert.ThrowsExactlyAsync<InvalidDataException>(()=>Worker(Store(),new(),spy,new()).HandleAsync(
            d with{ReceiptOnly=true,Status="printed",HumanConfirmed=true,ResultSpoolerId=999}));
        Assert.AreEqual("submitted",Store().Read(new(d.JobId)).Status);Assert.AreEqual(0,spy.Calls);
    }
}
