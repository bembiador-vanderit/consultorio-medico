using System.Net;
using System.Text;
using System.Text.Json;
using Atlas.LocalAgent.Core;
using Atlas.LocalAgent.Service;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Atlas.LocalAgent.Tests;

[TestClass]
public sealed class OfficialRoutingTests
{
    private sealed class Secrets(byte[] bytes):ISecureSecretStore
    {
        public Task<SecretBuffer?> ReadAsync(string key,CancellationToken t=default)=>Task.FromResult<SecretBuffer?>(new((byte[])bytes.Clone()));
        public Task StoreAsync(string k,ReadOnlyMemory<byte> v,CancellationToken t=default)=>throw new NotSupportedException();
        public Task RemoveAsync(string k,CancellationToken t=default)=>throw new NotSupportedException();
    }
    [TestMethod][DataRow(false)][DataRow(true)]
    public async Task ProtectedCredentialIdentityAndExpiryAreEnforced(bool expired)
    {
        var id=Guid.NewGuid();var bytes=JsonSerializer.SerializeToUtf8Bytes(new{endpoint="https://atlas.example.test/",token="ala_"+new string('q',43),
            agent_uuid=id,expires_at=expired?DateTimeOffset.UtcNow.AddDays(-1):DateTimeOffset.UtcNow.AddDays(1),organization_id=1,center_id=2,workgroup_id=3});
        using var http=new HttpClient();var client=new AtlasRegistryClient(http,new Secrets(bytes));
        Assert.IsNull(await client.OpenPrintConnectionAsync(Guid.NewGuid(),default));
        using var connection=await client.OpenPrintConnectionAsync(id,default);
        if(expired)Assert.IsNull(connection);
        else {Assert.IsNotNull(connection);Assert.AreEqual(2,connection.Center);Assert.DoesNotContain(connection.ToString(),"ala_");}
    }
    [TestMethod]
    public async Task RoutingNeverInheritsDevelopmentHttpException()
    {
        var id=Guid.NewGuid();var bytes=JsonSerializer.SerializeToUtf8Bytes(new{endpoint="http://localhost:8001/",allow_loopback_http=true,
            token="ala_"+new string('q',43),agent_uuid=id,expires_at=DateTimeOffset.UtcNow.AddDays(1),organization_id=1,center_id=1,workgroup_id=1});
        using var http=new HttpClient();var client=new AtlasRegistryClient(http,new Secrets(bytes),CommunicationEnvironment.Development);
        await Assert.ThrowsExactlyAsync<ArgumentException>(()=>client.OpenPrintConnectionAsync(id,default));
    }
    [TestMethod][DataRow("document")][DataRow("station")][DataRow("center")][DataRow("format")]
    public void SafeGateRejectsForeignOrRealDocuments(string change)
    {
        var id=Guid.NewGuid();using var http=new HttpClient{BaseAddress=new("https://atlas.example.test/")};
        using var connection=new OfficialPrintConnection(http,new HttpsPrintJobRelay(http,"fixture","print-routing"),id,1,1);
        var d=new RoutingDelivery(Guid.NewGuid(),Guid.NewGuid(),1,1,id,"printer-qa",1,"WEB_DESKTOP",null,"qa-general","synthetic_test","GENERAL","plain_text",1,
            DateTimeOffset.UtcNow.AddMinutes(1),new string('a',64),new string('b',64),"queued",true,false);
        OfficialPrintConsumer.ValidateEnvelope(connection,d);
        var invalid=change switch{"document"=>d with{DocumentReference="patient-document"},"station"=>d with{TargetAgent=Guid.NewGuid()},
            "center"=>d with{CenterId=2},_=>d with{Format="pdf"}};
        Assert.ThrowsExactly<InvalidDataException>(()=>OfficialPrintConsumer.ValidateEnvelope(connection,invalid));
    }
    private sealed class Handler:HttpMessageHandler
    {
        public Uri? Uri;public string? Auth;
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage r,CancellationToken t)
        {Uri=r.RequestUri;Auth=r.Headers.Authorization?.Scheme;return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK){Content=new StringContent("null",Encoding.UTF8,"application/json")});}
    }
    [TestMethod]
    public async Task OfficialConsumerUsesAuthenticatedOfficialPollingRoute()
    {
        using var handler=new Handler();using var http=new HttpClient(handler){BaseAddress=new("https://atlas.example.test/")};
        Assert.IsNull(await new HttpsPrintJobRelay(http,"fixture","print-routing").PollAsync(default));
        Assert.AreEqual("/api/v1/print-routing/device/poll",handler.Uri!.AbsolutePath);Assert.AreEqual("Bearer",handler.Auth);
    }
}
