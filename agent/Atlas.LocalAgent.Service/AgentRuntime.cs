using Atlas.LocalAgent.Core;

namespace Atlas.LocalAgent.Service;

public sealed class AgentRuntime(LocalIdentityStore identityStore, IPrinterDiscovery printers, ICloudTransport cloud,
    ILanDiscovery discovery, IAgentLog log, TimeProvider? clock = null, IStationRegistry? registry = null)
{
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly TimeProvider _clock = clock ?? TimeProvider.System;
    private AgentSnapshot? _snapshot;
    public AgentSnapshot Snapshot => Volatile.Read(ref _snapshot) ?? throw new InvalidOperationException("Iniciando agente.");

    public async Task StartAsync(CancellationToken cancellationToken)
    {
        var identity = await identityStore.LoadOrCreateAsync(cancellationToken);
        var configuration = await identityStore.LoadConfigurationAsync(identity, cancellationToken);
        var heartbeat = new AgentHeartbeat(identity.AgentId, configuration.StationName, AgentVersion.Current, AgentVersion.Protocol,
            Environment.OSVersion.VersionString, AgentState.Unpaired, _clock.GetUtcNow(), new(0, 0));
        Volatile.Write(ref _snapshot, new(true, identity, configuration, AgentState.Unpaired, heartbeat, [], AgentErrorCode.None));
        log.Write(AgentLogEvent.Startup, identity.AgentId, AgentState.Unpaired);
        await RefreshAsync(cancellationToken);
    }
    public async Task RefreshAsync(CancellationToken cancellationToken)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var prior = Snapshot; var state = AgentState.Unpaired; var error = AgentErrorCode.None; var devices = prior.Printers;
            try
            {
                devices = DeviceCatalog.Unique(await printers.EnumerateAsync(cancellationToken));
                log.Write(AgentLogEvent.PrinterEnumeration, prior.Identity.AgentId, count: devices.Count);
                var candidates = await discovery.DiscoverAsync(cancellationToken);
                log.Write(AgentLogEvent.Discovery, prior.Identity.AgentId, count: candidates.Count);
                // Discovery metadata is never added to authorization, jobs or credentials.
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { throw; }
            catch (Exception) { state = AgentState.Degraded; error = AgentErrorCode.PrinterUnavailable; log.Write(AgentLogEvent.Error, prior.Identity.AgentId, state, error: error); }
            var heartbeat = prior.Heartbeat with { Station = prior.Configuration.StationName, Status = state, LastSeen = _clock.GetUtcNow(), Devices = new(devices.Count, devices.Count(x => x.IsDefault)) };
            var association = prior.Configuration.Association;
            if (registry is null) await cloud.SendHeartbeatAsync(heartbeat, cancellationToken);
            else
            {
                var connection = await registry.SynchronizeAsync(prior with { Printers = devices, LastError = error }, cancellationToken);
                state = connection.State; association = connection.Association;
                heartbeat = heartbeat with { Status = state };
            }
            Volatile.Write(ref _snapshot, prior with { State = state, Heartbeat = heartbeat, Printers = devices,
                Configuration = prior.Configuration with { Association = association }, LastError = error });
            log.Write(AgentLogEvent.Heartbeat, prior.Identity.AgentId, state, devices.Count);
            if (state != prior.State) log.Write(AgentLogEvent.StateChanged, prior.Identity.AgentId, state);
        }
        finally { _gate.Release(); }
    }
    public async Task ConfigureAsync(string name, string code, CancellationToken cancellationToken)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var prior = Snapshot; var configuration = (prior.Configuration with { StationName = name.Trim(), DisplayCode = code.Trim().ToUpperInvariant() }).Validate();
            await identityStore.SaveConfigurationAsync(configuration, cancellationToken);
            Volatile.Write(ref _snapshot, prior with { Configuration = configuration, Heartbeat = prior.Heartbeat with { Station = configuration.StationName } });
        }
        finally { _gate.Release(); }
    }
    public async Task<RegistryStatus> PairAsync(PairingInput input, CancellationToken cancellationToken)
    {
        if (registry is null) return new(AgentState.Unpaired, "RegistryUnavailable", new());
        var result = await registry.PairAsync(input, Snapshot, cancellationToken);
        await RefreshAsync(cancellationToken);
        return result;
    }
    public Task<RegistryStatus> RotateAsync(CancellationToken cancellationToken) => registry is null
        ? Task.FromResult(new RegistryStatus(AgentState.Unpaired, "RegistryUnavailable", new()))
        : registry.RotateAsync(cancellationToken);
    public async Task RunHeartbeatLoopAsync(TimeSpan interval, CancellationToken cancellationToken)
    {
        var retry = new ReconnectBackoff();
        while (!cancellationToken.IsCancellationRequested)
        {
            // A degraded printer inventory must not make a connected station miss presence TTL.
            var failed = Snapshot.State is AgentState.Disconnected or AgentState.Error;
            if (!failed) retry.Reset();
            await Task.Delay(failed ? retry.FailureDelay() : interval, _clock, cancellationToken);
            await RefreshAsync(cancellationToken);
        }
    }
    public async Task StopAsync()
    {
        await _gate.WaitAsync();
        try
        {
            if (_snapshot is { Running: true } prior)
            {
                Volatile.Write(ref _snapshot, prior with { Running = false, State = AgentState.Disconnected });
                log.Write(AgentLogEvent.Shutdown, prior.Identity.AgentId, AgentState.Disconnected);
            }
            await cloud.DisposeAsync();
        }
        finally { _gate.Release(); }
    }
}
