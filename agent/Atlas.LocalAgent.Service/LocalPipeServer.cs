using System.Text.Json;
using Atlas.LocalAgent.Core;

namespace Atlas.LocalAgent.Service;

public sealed class LocalPipeServer(string root, AgentRuntime runtime, IAgentLog log, SyntheticPrintCoordinator? printing = null)
{
    public async Task RunAsync(CancellationToken cancellationToken)
    {
        await using var pipe = LocalOnlyPipe.Create(AgentPaths.PipeName(root));
        while (!cancellationToken.IsCancellationRequested)
        {
            await pipe.WaitForConnectionAsync(cancellationToken);
            using var requestTimeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            requestTimeout.CancelAfter(TimeSpan.FromSeconds(25));
            try
            {
                var request = await Wire.ReadAsync<LocalRequest>(pipe, requestTimeout.Token);
                var response = await DispatchAsync(request, requestTimeout.Token);
                await Wire.WriteAsync(pipe, response, requestTimeout.Token);
                var acknowledgement = new byte[1]; await pipe.ReadExactlyAsync(acknowledgement, requestTimeout.Token);
                if (acknowledgement[0] != 1) throw new InvalidDataException("Acuse inválido.");
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { throw; }
            catch (Exception ex) when (ex is IOException or InvalidDataException or JsonException or ArgumentException or OperationCanceledException)
            { log.Write(AgentLogEvent.Error, error: AgentErrorCode.InvalidRequest); }
            finally { if (pipe.IsConnected) pipe.Disconnect(); }
        }
    }
    public async Task<LocalResponse> DispatchAsync(LocalRequest request, CancellationToken cancellationToken)
    {
        try
        {
            SyntheticPrintReply? printReply = null;
            RegistryStatus? registry = null;
            switch (request.Command)
            {
                case LocalCommand.Snapshot: break;
                case LocalCommand.Refresh: await runtime.RefreshAsync(cancellationToken); break;
                case LocalCommand.PairWithAtlas when request.Pairing is not null:
                    registry = await runtime.PairAsync(request.Pairing, cancellationToken); break;
                case LocalCommand.RotateCredential:
                    registry = await runtime.RotateAsync(cancellationToken); break;
                case LocalCommand.Configure when request.StationName is not null && request.DisplayCode is not null:
                    await runtime.ConfigureAsync(request.StationName, request.DisplayCode, cancellationToken); break;
                case LocalCommand.PrepareSyntheticTest when printing is not null && request.PrintRequest is not null:
                    printReply = await printing.PrepareAsync(request.PrintRequest, cancellationToken); break;
                case LocalCommand.SubmitSyntheticTest when printing is not null && request.PrintRequest is not null:
                    printReply = await printing.SubmitAsync(request.PrintRequest, request.UserConfirmed, cancellationToken); break;
                case LocalCommand.CancelSyntheticTest when printing is not null && request.JobId is not null:
                    printReply = printing.Cancel(request.JobId.Value); break;
                case LocalCommand.ObserveSyntheticTest when printing is not null && request.JobId is not null:
                    printReply = await printing.ObserveAsync(request.JobId.Value, cancellationToken); break;
                default: return new(null, AgentErrorCode.InvalidRequest);
            }
            return new(runtime.Snapshot, PrintReply: printReply,
                PrintDiagnostics: printing is null ? null : await printing.DiagnoseAsync(cancellationToken), Registry: registry);
        }
        catch (ArgumentException) { return new(null, AgentErrorCode.InvalidConfiguration); }
        catch (Exception ex) when (ex is IOException or InvalidDataException or System.Text.Json.JsonException)
        { log.Write(AgentLogEvent.Error, error: AgentErrorCode.InternalError); return new(null, AgentErrorCode.InternalError); }
    }
}
