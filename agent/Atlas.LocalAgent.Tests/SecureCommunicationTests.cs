using Atlas.LocalAgent.Core;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Atlas.LocalAgent.Tests;

[TestClass]
public sealed class SecureCommunicationTests
{
    private sealed class Clock : TimeProvider
    {
        public DateTimeOffset Now = DateTimeOffset.UtcNow;
        public override DateTimeOffset GetUtcNow() => Now;
    }
    private sealed class SlowAuth(Clock clock) : ICommandAuthenticator
    {
        public Task<bool> ValidateAsync(CommandEnvelope command, CancellationToken cancellationToken)
        { clock.Now=clock.Now.AddMinutes(10);return Task.FromResult(true); }
    }
    private sealed class Auth : ICommandAuthenticator, IAgentAuthorizationPolicy
    {
        public bool Allowed = true;
        public Task<bool> ValidateAsync(CommandEnvelope command, CancellationToken cancellationToken) =>
            Task.FromResult(Allowed && command.SecurityContext.OrganizationId == "org1");
        public Task<AuthorizationDecision> AuthorizeAsync(AgentAuthorizationContext context, CancellationToken cancellationToken) =>
            Task.FromResult(new AuthorizationDecision(Allowed && context.OrganizationId == "org1", "FixtureOnly"));
    }
    private static CommandEnvelope Envelope() => new(Guid.NewGuid(), CommandType.AvailabilityNotification,
        new(PrintOriginType.WebMobile, "user1", "session1"), Guid.NewGuid(), DateTimeOffset.UtcNow,
        DateTimeOffset.UtcNow.AddMinutes(2), "opaque1", new("org1","center1","group1",DocumentSecurityClass.Clinical,
            AuthenticationKind.UserSession,"policy1"));

    [TestMethod] public void ProductionRejectsDevHttpFlagForEveryNonTlsEndpoint()
    {
        foreach (var endpoint in new[]{"http://localhost:8001/","http://127.0.0.1/","http://192.168.1.2/","http://atlas.example.test/"})
            Assert.ThrowsExactly<ArgumentException>(()=>new PairingInput(endpoint,"",true).ValidateEndpoint());
        foreach(var endpoint in new[]{"http://192.168.1.2/","http://atlas.example.test/","http://127.0.0.2/","http://localhost.example.test/"})
            Assert.ThrowsExactly<ArgumentException>(()=>new PairingInput(endpoint,"",true).ValidateEndpoint(CommunicationEnvironment.Development));
    }
    [TestMethod] public void BackoffIsCappedJitteredAndResettable()
    {
        var low=new ReconnectBackoff(()=>0); var high=new ReconnectBackoff(()=>1);
        Assert.AreEqual(TimeSpan.FromSeconds(1),low.FailureDelay());
        Assert.AreEqual(TimeSpan.FromSeconds(2),high.FailureDelay());
        for(var i=0;i<30;i++) Assert.IsTrue(high.FailureDelay()<=TimeSpan.FromSeconds(300));
        high.Reset();Assert.AreEqual(TimeSpan.FromSeconds(2),high.FailureDelay());
    }
    [TestMethod] public async Task EnvelopeReplayConcurrentConflictAndExpiryAreFailClosed()
    {
        var auth=new Auth();var inbox=new InMemoryCommandInbox(auth);var command=Envelope();
        var results=await Task.WhenAll(Enumerable.Range(0,20).Select(_=>inbox.AcceptAsync(command)));
        Assert.AreEqual(1,results.Count(r=>r==CommandAcceptance.Accepted));
        Assert.AreEqual(19,results.Count(r=>r==CommandAcceptance.Duplicate));
        Assert.AreEqual(CommandAcceptance.Conflict,await inbox.AcceptAsync(command with {PayloadReference="other"}));
        Assert.AreEqual(CommandAcceptance.Denied,await inbox.AcceptAsync(command with {ExpiresAt=DateTimeOffset.UtcNow.AddSeconds(-1)}));
        Assert.AreEqual(CommandAcceptance.Denied,await inbox.AcceptAsync(command with {IssuedAt=DateTimeOffset.UtcNow.AddMinutes(1)}));
        Assert.AreEqual(CommandAcceptance.Denied,await inbox.AcceptAsync(command with {SecurityContext=command.SecurityContext with {OrganizationId="foreign"}}));
        Assert.AreEqual(CommandAcceptance.Denied,await inbox.AcceptAsync(command with {Source=null!}));
        Assert.AreEqual(CommandAcceptance.Denied,await inbox.AcceptAsync(command with {SecurityContext=command.SecurityContext with {Authentication=AuthenticationKind.AgentBearer}}));
        auth.Allowed=false;Assert.AreEqual(CommandAcceptance.Denied,await inbox.AcceptAsync(command));
        var clock=new Clock();
        Assert.AreEqual(CommandAcceptance.Denied,await new InMemoryCommandInbox(new SlowAuth(clock),clock).AcceptAsync(Envelope()));
    }
    [TestMethod] public async Task SecureRoutesRequireExplicitAuthorityIdentityAndLiveTarget()
    {
        var auth=new Auth();var selector=new AuthorizedRouteSelector(auth);var target=Guid.NewGuid();
        var context=new AgentAuthorizationContext(null,target,"org1","center1","availability",
            new("user-session-reference",DateTimeOffset.UtcNow.AddHours(1)){Kind=AuthenticationKind.UserSession})
            {Origin=new(PrintOriginType.WebMobile,"user1","session1"),TargetOnline=true};
        await using var lan=new MockLocalTransport();await using var cloud=new MockCloudTransport();
        Assert.IsNull(await selector.SelectAsync(context,lan,cloud,default)); // Discovery/availability is not TLS.
        var relayCredential=context.Credential with {Key="relay-reference",Kind=AuthenticationKind.ServiceIdentity};
        var peerCredential=context.Credential with {Key="certificate-reference",Kind=AuthenticationKind.MutualTls};
        await Assert.ThrowsExactlyAsync<ArgumentException>(()=>cloud.ConnectAsync(new(new("https://atlas.example.test"),false,context.Credential),default));
        await cloud.ConnectAsync(new(new("https://atlas.example.test"),false,relayCredential),default);
        Assert.AreSame(cloud,await selector.SelectAsync(context,lan,cloud,default)); // Different Wi-Fi/firewall.
        await lan.ConnectAsync(new(new("https://peer.example.test"),true,peerCredential){ExpectedPeerAgent=Guid.NewGuid()},default);
        Assert.AreSame(cloud,await selector.SelectAsync(context,lan,cloud,default));
        await lan.ConnectAsync(new(new("https://peer.example.test"),true,peerCredential){ExpectedPeerAgent=target},default);
        Assert.AreSame(cloud,await selector.SelectAsync(context,lan,cloud,default)); // A phone has no LAN agent.
        var source=Guid.NewGuid();
        var stationContext=context with {SourceAgent=source,Origin=new(PrintOriginType.LocalAgent,"station1","context1",source),
            Credential=context.Credential with {Kind=AuthenticationKind.AgentBearer}};
        Assert.AreSame(lan,await selector.SelectAsync(stationContext,lan,cloud,default));
        Assert.IsNull(await selector.SelectAsync(context with {TargetOnline=false},lan,cloud,default));
        Assert.IsNull(await selector.SelectAsync(context with {TargetRevoked=true},lan,cloud,default));
        Assert.IsNull(await selector.SelectAsync(context with {OrganizationId="foreign"},lan,cloud,default));
        auth.Allowed=false;Assert.IsNull(await selector.SelectAsync(context,lan,cloud,default));
    }
    [TestMethod] public void MobileTabletJobsHaveNoRequiredSourceAgentAndReferencesAreRedacted()
    {
        foreach(var kind in new[]{PrintOriginType.WebDesktop,PrintOriginType.WebMobile,PrintOriginType.WebTablet})
        {
            var origin=new PrintOrigin(kind,"user1","session1");
            var job=new PrintJob(PrintJobId.New(),Guid.NewGuid(),"printer1","document1",PrintDocumentFormat.Pdf,1){Origin=origin,SecurityClass=DocumentSecurityClass.SensitiveClinical};
            job.Validate();Assert.IsNull(job.Origin.SourceAgent);
            Assert.AreEqual(job,Wire.Deserialize<PrintJob>(Wire.Serialize(job)));
        }
        Assert.ThrowsExactly<ArgumentException>(()=>new PrintOrigin(PrintOriginType.WebMobile,"patient name","session1").Validate());
        Assert.IsFalse(Envelope().ToString().Contains("session1",StringComparison.Ordinal));
        Assert.IsFalse(new DeviceCredentialReference("secret-placeholder",DateTimeOffset.UtcNow).ToString().Contains("secret-placeholder",StringComparison.Ordinal));
    }
}
