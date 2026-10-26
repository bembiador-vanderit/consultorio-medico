using System.Net;
using System.Security.Cryptography;
using System.Text;
using Atlas.LocalAgent.Core;
using Atlas.LocalAgent.Service;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Atlas.LocalAgent.Tests;

[TestClass]
public sealed class FakeRoutingTests
{
    private string _root=null!;
    private readonly Guid _station=Guid.NewGuid();
    private static readonly byte[] Body=Encoding.UTF8.GetBytes("SYNTHETIC ONLY");
    [TestInitialize]public void Setup()=>_root=Directory.CreateTempSubdirectory("atlas-routing-qa-").FullName;
    [TestCleanup]public void Cleanup()=>Directory.Delete(_root,true);
    private DurablePrintJobStore Store()=>new(Path.Combine(_root,"inbox.sqlite"),_station,1,1);
    private RoutingDelivery Delivery(string origin="WEB_DESKTOP",int copies=1,DateTimeOffset? expiry=null)
    {
        var d=new RoutingDelivery(Guid.NewGuid(),Guid.NewGuid(),1,1,_station,"printer-fake",42,origin,null,
            "qa-general","synthetic_test","GENERAL","plain_text",copies,expiry??DateTimeOffset.UtcNow.AddMinutes(3),
            Convert.ToHexString(SHA256.HashData(Body)).ToLowerInvariant(),"","queued",true,false);
        return d with{IntentHash=PrintIntentFingerprint.Hash(d.Envelope())};
    }
    private sealed class Relay : IPrintJobRelay
    {
        public readonly List<string> States=[];
        public bool LostResponse,Corrupt,CancelDuringDownload;
        public string? CancelOn;
        public Task<RoutingDelivery?> PollAsync(CancellationToken token)=>Task.FromResult<RoutingDelivery?>(null);
        public Task<string> ProgressAsync(RoutingDelivery d,string state,CancellationToken token){States.Add(state);return Task.FromResult(state==CancelOn?"cancelled":state);}
        public Task<byte[]> DownloadAsync(RoutingDelivery d,CancellationToken token)
        {
            if(CancelDuringDownload){CancelOn="received";throw new HttpRequestException("Synthetic gone",null,HttpStatusCode.Gone);}
            return Task.FromResult(Corrupt?[1,2,3]:(byte[])Body.Clone());
        }
        public Task ReportAsync(RoutingDelivery d,DurablePrintState result,CancellationToken token)
        {if(LostResponse){LostResponse=false;throw new HttpRequestException("Synthetic dropped result.");}States.Add(result.Status);return Task.CompletedTask;}
    }

    [TestMethod][DataRow("WEB_DESKTOP")][DataRow("WEB_MOBILE")][DataRow("WEB_TABLET")]
    public async Task OriginsRouteThroughDurableStagesWithoutSource(string origin)
    {
        var relay=new Relay();var executor=new FakePrintExecutor();var d=Delivery(origin);
        var result=await new FakePrintRoutingWorker(Store(),relay,executor).HandleAsync(d);
        Assert.AreEqual("printed",result.Status);Assert.IsTrue(result.SpoolId>0);Assert.AreEqual(1,executor.Calls);
        CollectionAssert.AreEqual(new[]{"received","ready","printing","printed"},relay.States);
        Assert.IsNull(Store().Load(new(d.JobId)).Job.Origin!.SourceAgent);
    }
    [TestMethod]
    public async Task DuplicateConcurrentDeliveryIsOneExecutionAndRestartIsReceiptOnly()
    {
        var relay=new Relay();var executor=new FakePrintExecutor();var worker=new FakePrintRoutingWorker(Store(),relay,executor);var d=Delivery();
        await Task.WhenAll(Enumerable.Range(0,20).Select(_=>worker.HandleAsync(d with{DeliveryId=Guid.NewGuid()})));
        Assert.AreEqual(1,executor.Calls);
        var restarted=new FakePrintExecutor();
        Assert.AreEqual("printed",(await new FakePrintRoutingWorker(Store(),relay,restarted).HandleAsync(d)).Status);
        Assert.AreEqual(0,restarted.Calls);
    }
    [TestMethod]
    public async Task LostResponseAndRestartReturnsDurableReceiptWithoutSecondExecution()
    {
        var relay=new Relay{LostResponse=true};var first=new FakePrintExecutor();var d=Delivery();
        await Assert.ThrowsExactlyAsync<HttpRequestException>(()=>new FakePrintRoutingWorker(Store(),relay,first).HandleAsync(d));
        Assert.AreEqual("printed",Store().Read(new(d.JobId)).Status);
        var second=new FakePrintExecutor();
        var result=await new FakePrintRoutingWorker(Store(),relay,second).HandleAsync(d with{ReceiptOnly=true,Status="printing"});
        Assert.AreEqual("printed",result.Status);Assert.AreEqual(1,first.Calls);Assert.AreEqual(0,second.Calls);
    }
    [TestMethod][DataRow(FakePrintOutcome.Unknown)][DataRow(FakePrintOutcome.Timeout)]
    public async Task UncertainOutcomesNeverAutoRetry(FakePrintOutcome outcome)
    {
        var relay=new Relay();var fake=new FakePrintExecutor(outcome);var d=Delivery();
        Assert.AreEqual("unknown",(await new FakePrintRoutingWorker(Store(),relay,fake).HandleAsync(d)).Status);
        Assert.AreEqual("unknown",(await new FakePrintRoutingWorker(Store(),relay,fake).HandleAsync(d)).Status);
        Assert.AreEqual(1,fake.Calls);Assert.AreEqual("unknown",Store().Read(new(d.JobId)).Status);
    }
    [TestMethod][DataRow(false)][DataRow(true)]
    public async Task FailedPreflightOrUnavailableNeverReachesExecutor(bool unavailable)
    {
        var fake=new FakePrintExecutor(unavailable?FakePrintOutcome.Printed:FakePrintOutcome.Failed){PrinterAvailable=!unavailable};
        var result=await new FakePrintRoutingWorker(Store(),new Relay(),fake).HandleAsync(Delivery());
        Assert.AreEqual("failed",result.Status);Assert.AreEqual(0,fake.Calls);
        Assert.AreEqual(unavailable?"PRINTER_UNAVAILABLE":"INVALID_ARTIFACT",result.ErrorCode);
    }
    [TestMethod][DataRow("queued")][DataRow("received")][DataRow("ready")]
    public async Task CancellationBeforeBarrierNeverExecutes(string stage)
    {
        var d=Delivery();var relay=new Relay{CancelOn=stage};var fake=new FakePrintExecutor();
        if(stage=="queued")d=d with{Status="cancelled",ReceiptOnly=true};
        Assert.AreEqual("cancelled",(await new FakePrintRoutingWorker(Store(),relay,fake).HandleAsync(d)).Status);Assert.AreEqual(0,fake.Calls);
    }
    [TestMethod]
    public async Task ExpiredAndCorruptArtifactsCannotExecute()
    {
        var fake=new FakePrintExecutor();var relay=new Relay();
        Assert.AreEqual("expired",(await new FakePrintRoutingWorker(Store(),relay,fake).HandleAsync(Delivery(expiry:DateTimeOffset.UtcNow.AddSeconds(-1)))).Status);
        relay.Corrupt=true;
        Assert.AreEqual("failed",(await new FakePrintRoutingWorker(Store(),relay,fake).HandleAsync(Delivery())).Status);Assert.AreEqual(0,fake.Calls);
    }
    [TestMethod]
    public async Task CancellationWhileDownloadingRecoversAuthoritativeState()
    {
        var fake=new FakePrintExecutor();var relay=new Relay{CancelDuringDownload=true};
        Assert.AreEqual("cancelled",(await new FakePrintRoutingWorker(Store(),relay,fake).HandleAsync(Delivery())).Status);
        Assert.AreEqual(0,fake.Calls);
    }
    [TestMethod]
    public async Task CopiesAndNoFakeCancellationAfterPrinting()
    {
        var observed=0;var d=Delivery(copies:999);var store=Store();var fake=new FakePrintExecutor(observed:(_,_,copies)=>observed=copies);
        fake.DuringPrinting=()=>Assert.AreNotEqual("cancelled",store.Cancel(new(d.JobId)).Status);
        Assert.AreEqual("printed",(await new FakePrintRoutingWorker(store,new Relay(),fake).HandleAsync(d)).Status);
        Assert.AreEqual(999,observed);Assert.AreEqual(1,fake.Calls);
        Assert.ThrowsExactly<ArgumentException>(()=>Delivery(copies:1000));
    }
    [TestMethod]
    public async Task ChangedIntentAndForeignScopeAreRejected()
    {
        var relay=new Relay();var fake=new FakePrintExecutor();var d=Delivery();var worker=new FakePrintRoutingWorker(Store(),relay,fake);
        await worker.HandleAsync(d);
        var changed=d with{Copies=2};changed=changed with{IntentHash=PrintIntentFingerprint.Hash(changed.Envelope())};
        await Assert.ThrowsExactlyAsync<InvalidDataException>(()=>worker.HandleAsync(changed));
        var foreign=d with{TargetAgent=Guid.NewGuid()};foreign=foreign with{IntentHash=PrintIntentFingerprint.Hash(foreign.Envelope())};
        await Assert.ThrowsExactlyAsync<ArgumentException>(()=>worker.HandleAsync(foreign));Assert.AreEqual(1,fake.Calls);
    }
    [TestMethod]
    public void TransportCannotStartWithHttpOrCredentialInUrl()
    {
        using var http=new HttpClient{BaseAddress=new("http://localhost:18469/")};
        Assert.ThrowsExactly<ArgumentException>(()=>new HttpsPrintJobRelay(http,"fixture"));
        http.BaseAddress=new("https://user:secret@localhost:18469/");
        Assert.ThrowsExactly<ArgumentException>(()=>new HttpsPrintJobRelay(http,"fixture"));
    }
}
