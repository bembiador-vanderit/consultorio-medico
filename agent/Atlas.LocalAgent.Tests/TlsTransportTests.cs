using System.Net;
using System.Net.Security;
using System.Net.Sockets;
using System.Security.Authentication;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using Atlas.LocalAgent.Service;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Atlas.LocalAgent.Tests;

// Ephemeral in-memory certificates, never installed/trusted in Windows or used by Atlas.
[TestClass]
public sealed class TlsTransportTests
{
    private static async Task<bool> RequestAsync(string dnsName, bool expired, bool useProductionFactory)
    {
        using var rootKey=RSA.Create(2048); using var leafKey=RSA.Create(2048);
        var rootRequest=new CertificateRequest("CN=Ephemeral Atlas QA Root",rootKey,HashAlgorithmName.SHA256,RSASignaturePadding.Pkcs1);
        rootRequest.CertificateExtensions.Add(new X509BasicConstraintsExtension(true,false,0,true));
        rootRequest.CertificateExtensions.Add(new X509KeyUsageExtension(X509KeyUsageFlags.KeyCertSign,true));
        using var root=rootRequest.CreateSelfSigned(DateTimeOffset.UtcNow.AddDays(-10),DateTimeOffset.UtcNow.AddDays(10));
        var leafRequest=new CertificateRequest("CN="+dnsName,leafKey,HashAlgorithmName.SHA256,RSASignaturePadding.Pkcs1);
        var san=new SubjectAlternativeNameBuilder();san.AddDnsName(dnsName);leafRequest.CertificateExtensions.Add(san.Build());
        leafRequest.CertificateExtensions.Add(new X509BasicConstraintsExtension(false,false,0,true));
        leafRequest.CertificateExtensions.Add(new X509EnhancedKeyUsageExtension(new OidCollection {new("1.3.6.1.5.5.7.3.1")},true));
        using var publicLeaf=leafRequest.Create(root,DateTimeOffset.UtcNow.AddDays(-2),
            expired?DateTimeOffset.UtcNow.AddDays(-1):DateTimeOffset.UtcNow.AddDays(1),RandomNumberGenerator.GetBytes(16));
        using var ephemeralLeaf=publicLeaf.CopyWithPrivateKey(leafKey);
        var pfx=ephemeralLeaf.Export(X509ContentType.Pkcs12);
        // Schannel requires a provider-backed key. DefaultKeySet is temporary and disposed;
        // no certificate is added to a trust store and PersistKeySet is deliberately absent.
        using var leaf=X509CertificateLoader.LoadPkcs12(pfx,null,X509KeyStorageFlags.DefaultKeySet);
        CryptographicOperations.ZeroMemory(pfx);
        var listener=new TcpListener(IPAddress.Loopback,0);listener.Start();
        var port=((IPEndPoint)listener.LocalEndpoint).Port;
        using var stop=new CancellationTokenSource(TimeSpan.FromSeconds(8));
        var server=Task.Run(async()=>
        {
            try
            {
                using var tcp=await listener.AcceptTcpClientAsync(stop.Token);
                await using var ssl=new SslStream(tcp.GetStream());
                await ssl.AuthenticateAsServerAsync(new SslServerAuthenticationOptions {ServerCertificate=leaf,
                    EnabledSslProtocols=SslProtocols.Tls12|SslProtocols.Tls13},stop.Token);
                var buffer=new byte[4096];var length=await ssl.ReadAsync(buffer,stop.Token);
                if(length>0) await ssl.WriteAsync(Encoding.ASCII.GetBytes("HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK"),stop.Token);
            }
            catch(Exception ex) when(ex is AuthenticationException or IOException or OperationCanceledException or SocketException) { }
        });
        HttpClient client;
        if(useProductionFactory) client=AtlasRegistryClient.CreateHttpClient();
        else
        {
            // Test-local chain trust, still standard hostname/date/chain validation; no callback bypass.
            var policy=new X509ChainPolicy {TrustMode=X509ChainTrustMode.CustomRootTrust,RevocationMode=X509RevocationMode.NoCheck};
            policy.CustomTrustStore.Add(root);
            var handler=new SocketsHttpHandler {UseProxy=false};
            handler.SslOptions.EnabledSslProtocols=SslProtocols.Tls12|SslProtocols.Tls13;
            handler.SslOptions.CertificateChainPolicy=policy;
            client=new HttpClient(handler);
        }
        using(client)
        {
            client.Timeout=TimeSpan.FromSeconds(5);
            try { using var response=await client.GetAsync($"https://localhost:{port}/",stop.Token);return response.StatusCode==HttpStatusCode.OK; }
            catch(HttpRequestException ex)
            {
                Assert.IsInstanceOfType<AuthenticationException>(ex.InnerException);
                return false;
            }
            finally {stop.Cancel();listener.Stop();await server;}
        }
    }
    [TestMethod] public async Task ValidTrustedFixtureHttpsAccepted() => Assert.IsTrue(await RequestAsync("localhost",false,false));
    [TestMethod] public async Task ExpiredCertificateRejected() => Assert.IsFalse(await RequestAsync("localhost",true,false));
    [TestMethod] public async Task HostnameMismatchRejected() => Assert.IsFalse(await RequestAsync("wrong.example.test",false,false));
    [TestMethod] public async Task ProductionClientRejectsUntrustedCertificate() => Assert.IsFalse(await RequestAsync("localhost",false,true));
}
