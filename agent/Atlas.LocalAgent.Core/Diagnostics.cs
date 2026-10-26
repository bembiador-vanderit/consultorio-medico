using System.Text.Json;

namespace Atlas.LocalAgent.Core;

public enum AgentLogEvent { Startup, Shutdown, StateChanged, Discovery, PrinterEnumeration, Heartbeat, Error, PrintJobChanged }
public enum AgentErrorCode { None, PrinterUnavailable, InvalidConfiguration, InvalidRequest, InternalError }
public sealed record AgentLogEntry(DateTimeOffset Timestamp, AgentLogEvent Event, Guid? AgentId, AgentState? State, int? Count, AgentErrorCode Error);
public sealed record PrintLogEntry(DateTimeOffset Timestamp, Guid JobId, string PrinterId, SyntheticPageFormat Format,
    PrintJobStatus Status, PrintFailure Error, int? SpoolJobId, string AgentVersion, AgentLogEvent Event = AgentLogEvent.PrintJobChanged);
public interface IAgentLog
{
    void Write(AgentLogEvent eventId, Guid? agentId = null, AgentState? state = null, int? count = null, AgentErrorCode error = AgentErrorCode.None);
    void WritePrint(Guid jobId, string printerId, SyntheticPageFormat format, PrintJobStatus status, PrintFailure error, int? spoolJobId);
}
// Allowlisted, typed metadata only. No arbitrary message, exception, token, printer name or document field.
public sealed class JsonAgentLog(TextWriter writer) : IAgentLog
{
    private readonly object _gate = new();
    public void Write(AgentLogEvent eventId, Guid? agentId = null, AgentState? state = null, int? count = null, AgentErrorCode error = AgentErrorCode.None)
    {
        lock (_gate) { writer.WriteLine(JsonSerializer.Serialize(new AgentLogEntry(DateTimeOffset.UtcNow, eventId, agentId, state, count, error), Wire.Options)); writer.Flush(); }
    }
    public void WritePrint(Guid jobId, string printerId, SyntheticPageFormat format, PrintJobStatus status, PrintFailure error, int? spoolJobId)
    {
        // Only the derived device ID is logged, never an arbitrary printer name or driver message.
        var safePrinter = printerId.StartsWith("printer-", StringComparison.Ordinal) && printerId.Length == 72
            && printerId[8..].All(Uri.IsHexDigit) ? printerId : "invalid-printer-id";
        lock (_gate) { writer.WriteLine(JsonSerializer.Serialize(new PrintLogEntry(DateTimeOffset.UtcNow, jobId, safePrinter, format,
            status, error, spoolJobId, AgentVersion.Current), Wire.Options)); writer.Flush(); }
    }
}
public sealed record AgentSnapshot(bool Running, AgentIdentity Identity, StationConfiguration Configuration, AgentState State,
    AgentHeartbeat Heartbeat, IReadOnlyList<PrinterDevice> Printers, AgentErrorCode LastError);
