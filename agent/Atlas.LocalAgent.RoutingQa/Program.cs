using System.Net.Security;
using System.Net.Http.Json;
using System.Security.Authentication;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text.Json;
using Atlas.LocalAgent.Service;

// Dedicated test harness. Never reads real pairing/DPAPI, enumerates Windows printers or loads a physical executor.
if(args is ["--create-test-cert",var directory]) {
    Directory.CreateDirectory(directory);
    using var rootKey=RSA.Create(2048);using var leafKey=RSA.Create(2048);
    var rootRequest=new CertificateRequest("CN=Ephemeral Routing QA Root",rootKey,HashAlgorithmName.SHA256,RSASignaturePadding.Pkcs1);
    rootRequest.CertificateExtensions.Add(new X509BasicConstraintsExtension(true,false,0,true));
    rootRequest.CertificateExtensions.Add(new X509KeyUsageExtension(X509KeyUsageFlags.KeyCertSign,true));
    using var rootCert=rootRequest.CreateSelfSigned(DateTimeOffset.UtcNow.AddMinutes(-5),DateTimeOffset.UtcNow.AddDays(1));
    var leafRequest=new CertificateRequest("CN=localhost",leafKey,HashAlgorithmName.SHA256,RSASignaturePadding.Pkcs1);
    var san=new SubjectAlternativeNameBuilder();san.AddDnsName("localhost");san.AddIpAddress(System.Net.IPAddress.Loopback);leafRequest.CertificateExtensions.Add(san.Build());
    leafRequest.CertificateExtensions.Add(new X509BasicConstraintsExtension(false,false,0,true));
    leafRequest.CertificateExtensions.Add(new X509EnhancedKeyUsageExtension(new OidCollection{new("1.3.6.1.5.5.7.3.1")},true));
    using var leaf=leafRequest.Create(rootCert,DateTimeOffset.UtcNow.AddMinutes(-1),DateTimeOffset.UtcNow.AddHours(12),RandomNumberGenerator.GetBytes(16));
    File.WriteAllText(Path.Combine(directory,"ca.pem"),rootCert.ExportCertificatePem());
    File.WriteAllText(Path.Combine(directory,"server.pem"),leaf.ExportCertificatePem());
    File.WriteAllText(Path.Combine(directory,"server-key.pem"),leafKey.ExportPkcs8PrivateKeyPem());
    Console.WriteLine("Ephemeral QA certificates created; no system trust modified.");return;
}
var options=args.Chunk(2).ToDictionary(x=>x[0],x=>x[1]);
var endpoint=new Uri(options["--endpoint"]);
if(endpoint.Scheme!="https" || endpoint.Host is not ("localhost" or "127.0.0.1") || endpoint.Port!=18469)
    throw new ArgumentException("Only isolated QA HTTPS listener 18469.");
var root=Path.GetFullPath(options["--data-dir"]);
if(!File.Exists(Path.Combine(root,"FAKE_ROUTING_QA_ONLY")) || Directory.Exists(Path.Combine(root,"secrets")) || File.Exists(Path.Combine(root,"identity.json")))
    throw new InvalidOperationException("Separate explicitly marked QA directory required.");
using var held=new FileStream(Path.Combine(root,"qa-process.lock"),FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.None);
using var ca=X509CertificateLoader.LoadCertificateFromFile(options["--ca"]);
using var handler=new SocketsHttpHandler{AllowAutoRedirect=false,UseCookies=false,UseProxy=false};
var trust=new X509ChainPolicy{TrustMode=X509ChainTrustMode.CustomRootTrust,RevocationMode=X509RevocationMode.NoCheck,VerificationFlags=X509VerificationFlags.NoFlag};
trust.CustomTrustStore.Add(ca);handler.SslOptions.CertificateChainPolicy=trust;handler.SslOptions.EnabledSslProtocols=SslProtocols.Tls12|SslProtocols.Tls13;
using var http=new HttpClient(handler){BaseAddress=endpoint,Timeout=TimeSpan.FromSeconds(10)};
var token=Environment.GetEnvironmentVariable("ATLAS_FAKE_AGENT_TOKEN") ?? throw new InvalidOperationException("QA credential required.");
var station=Guid.Parse(options["--station"]);
var transport=new HttpsPrintJobRelay(http,token);
IPrintJobRelay relay=options.ContainsKey("--lose-result-once")?new LoseResultOnce(transport):transport;
var outcome=Enum.Parse<FakePrintOutcome>(options.GetValueOrDefault("--outcome","Printed"),true);
var executor=new FakePrintExecutor(outcome,observed:(job,id,copies)=>File.AppendAllText(Path.Combine(root,"fake-executions.jsonl"),
    JsonSerializer.Serialize(new{JobId=job,SyntheticSpoolerId=id,Copies=copies})+Environment.NewLine));
var store=new DurablePrintJobStore(Path.Combine(root,"inbox.sqlite"),station,1,1);
var worker=new FakePrintRoutingWorker(store,relay,executor);
var lastHeartbeat=DateTimeOffset.MinValue;
using var stop=new CancellationTokenSource(TimeSpan.FromSeconds(int.Parse(options.GetValueOrDefault("--seconds","600"))));
Console.CancelKeyPress+=(_,e)=>{e.Cancel=true;stop.Cancel();};
if(options.TryGetValue("--job-id",out var jobId)){
    var delivery=await transport.RedeliverAsync(Guid.Parse(jobId),stop.Token);
    try{
        var results=await Task.WhenAll(Enumerable.Range(0,int.Parse(options.GetValueOrDefault("--duplicates","1")))
            .Select(_=>worker.HandleAsync(delivery,stop.Token)));
        Console.WriteLine(JsonSerializer.Serialize(new{delivery.JobId,Status=results[0].Status,executor.Calls}));
    }
    catch(SyntheticResponseLoss){Console.WriteLine(JsonSerializer.Serialize(new{delivery.JobId,Status="response_lost",executor.Calls}));}
    return;
}
while(!stop.IsCancellationRequested){
    try {
        if(DateTimeOffset.UtcNow-lastHeartbeat>TimeSpan.FromSeconds(30)){
            using var presence=await http.PostAsJsonAsync("api/v1/local-agents/device/heartbeat",new{agent_uuid=station,display_code="QA-FAKE",
                station_name="Estación fake QA",version="qa-only",protocol_version=3,fingerprint=new string('a',64),health="online"},stop.Token);
            presence.EnsureSuccessStatusCode();lastHeartbeat=DateTimeOffset.UtcNow;
        }
        var delivery=await relay.PollAsync(stop.Token);
        if(delivery is not null){var result=await worker.HandleAsync(delivery,stop.Token);Console.WriteLine(JsonSerializer.Serialize(new{delivery.JobId,result.Status,executor.Calls}));}
        await Task.Delay(150,stop.Token);
    }
    catch(OperationCanceledException) when(stop.IsCancellationRequested){break;}
    catch(HttpRequestException){await Task.Delay(300,stop.Token);}
}

// Test-only fault injection. The receipt is already in SQLite; no result request reaches the server.
sealed class SyntheticResponseLoss:Exception;
sealed class LoseResultOnce(IPrintJobRelay inner):IPrintJobRelay
{
    private bool _lost;
    public Task<RoutingDelivery?> PollAsync(CancellationToken t)=>inner.PollAsync(t);
    public Task<string> ProgressAsync(RoutingDelivery d,string s,CancellationToken t)=>inner.ProgressAsync(d,s,t);
    public Task<byte[]> DownloadAsync(RoutingDelivery d,CancellationToken t)=>inner.DownloadAsync(d,t);
    public Task ReportAsync(RoutingDelivery d,DurablePrintState s,CancellationToken t)
    {if(!_lost){_lost=true;throw new SyntheticResponseLoss();}return inner.ReportAsync(d,s,t);}
}
