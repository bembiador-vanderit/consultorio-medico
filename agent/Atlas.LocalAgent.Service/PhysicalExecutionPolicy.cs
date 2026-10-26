using System.Text.Json;
using System.Text.Json.Serialization;
using Atlas.LocalAgent.Core;

namespace Atlas.LocalAgent.Service;

public enum PrintExecutionMode { SafeValidation, PhysicalDenied, PhysicalAllowed }
public sealed record PrintExecutionDecision(PrintExecutionMode Mode, string Reason,
    SyntheticPageFormat? PageFormat=null,string? PrinterFingerprint=null);

// Operational authorization, never accepted from a delivery or the local pipe/Web UI.
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record PhysicalExecutionAuthorization
{
    public bool Enabled { get; init; }
    public Guid? AllowedJobId { get; init; }
    public Guid? AllowedAgentId { get; init; }
    public string? AllowedPrinterId { get; init; }
    public string? ExpectedPrinterName { get; init; }
    public string? PrinterFingerprint { get; init; }
    public int OrganizationId { get; init; }
    public int CenterId { get; init; }
    public int MaxCopies { get; init; } = 1;
    public string? IntentHash { get; init; }
    public string? ContentSha256 { get; init; }
    public string ExecutionMode { get; init; } = "Disabled";
    public DateTimeOffset? ValidFrom { get; init; }
    public DateTimeOffset? ExpiresAt { get; init; }
    public SyntheticPageFormat PageFormat { get; init; } = SyntheticPageFormat.A4;

    public static PhysicalExecutionAuthorization Load(string? path)
    {
        if (path is null) return new();
        // Local explicit file only. Do not follow network paths or oversized config.
        if (!Path.IsPathFullyQualified(path) || path.StartsWith(@"\\", StringComparison.Ordinal)
            || new FileInfo(path).Length > 8192 || (File.GetAttributes(path)&FileAttributes.ReparsePoint)!=0)
            throw new InvalidDataException("Invalid physical authorization file.");
        return JsonSerializer.Deserialize<PhysicalExecutionAuthorization>(File.ReadAllBytes(path))
            ?? throw new InvalidDataException("Invalid physical authorization file.");
    }
}

public interface IPrintExecutionPolicy
{
    PrintExecutionDecision Evaluate(RoutingDelivery delivery, DurablePrintState state);
}

public sealed class SingleJobPhysicalExecutionPolicy(PhysicalExecutionAuthorization authorization,
    Func<DateTimeOffset>? clock = null) : IPrintExecutionPolicy
{
    public PrintExecutionDecision Evaluate(RoutingDelivery d, DurablePrintState state)
    {
        PrintExecutionDecision Deny(string code) => new(PrintExecutionMode.PhysicalDenied, "PHYSICAL_DENIED_" + code);
        if (d.DocumentType == "synthetic_test") return new(PrintExecutionMode.SafeValidation, "SAFE_VALIDATION");
        if (!authorization.Enabled) return Deny("DEFAULT");
        if (authorization.ExecutionMode != "PhysicalQa" || d.DocumentType != "physical_routing_qa"
            || d.DocumentReference != "physical-routing-qa" || d.Format != "plain_text"
            || d.SecurityClass != "GENERAL" || d.OriginType != "WEB_DESKTOP" || d.SourceAgent is not null)
            return Deny("DOCUMENT_MISMATCH");
        if (authorization.AllowedJobId is null || authorization.AllowedJobId == Guid.Empty
            || authorization.AllowedJobId != d.JobId) return Deny("JOB_MISMATCH");
        if (authorization.AllowedAgentId is null || authorization.AllowedAgentId == Guid.Empty
            || authorization.AllowedAgentId != d.TargetAgent || authorization.OrganizationId != d.OrganizationId
            || authorization.CenterId != d.CenterId) return Deny("AGENT_MISMATCH");
        if (string.IsNullOrWhiteSpace(authorization.AllowedPrinterId) || authorization.AllowedPrinterId != d.TargetPrinter)
            return Deny("PRINTER_MISMATCH");
        if(authorization.PrinterFingerprint?.Length!=64)return Deny("PRINTER_FINGERPRINT");
        if (d.Copies != 1 || authorization.MaxCopies != 1) return Deny("COPIES");
        if (authorization.IntentHash?.Length != 64 || authorization.IntentHash != d.IntentHash
            || authorization.ContentSha256?.Length != 64 || authorization.ContentSha256 != d.ContentSha256)
            return Deny("INTENT_MISMATCH");
        var now = clock?.Invoke() ?? DateTimeOffset.UtcNow;
        if (authorization.ValidFrom is not { } start || authorization.ExpiresAt is not { } end
            || end <= start || end - start > TimeSpan.FromMinutes(5) || now < start || now >= end
            || d.ExpiresAt <= now || !Enum.IsDefined(authorization.PageFormat)) return Deny("WINDOW");
        if (state.Status is not ("received" or "ready") || d.ReceiptOnly
            || d.Status is not ("queued" or "received" or "ready")) return Deny("DURABLE_RECEIPT");
        return new(PrintExecutionMode.PhysicalAllowed, "PHYSICAL_ALLOWED_SINGLE_JOB",authorization.PageFormat,authorization.PrinterFingerprint);
    }
}

public interface IRoutingPrintExecutor
{
    Task<DurablePrintFailure?> PreflightAsync(RoutingDelivery delivery, CancellationToken token);
    int Execute(PrintJob job);
    Task<bool> ConfirmPrintedAsync(RoutingDelivery delivery, int spoolId, CancellationToken token);
}
