using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Atlas.LocalAgent.Core;

namespace Atlas.LocalAgent.Service;

public static class PrintIntentFingerprint
{
    public static string Digest(string text) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(text))).ToLowerInvariant();

    public static DurablePrintEnvelope Normalize(DurablePrintEnvelope value)
    {
        value.Job.Validate();
        if (value.Job.IntentVersion == 2 && value.Job.Origin!.ContextReference != $"org-{value.OrganizationId}-center-{value.CenterId}")
            throw new ArgumentException("Origen fuera del contexto de la intención.");
        return value with { Job = value.Job with { Status = PrintJobStatus.Queued },
            ExpiresAt = value.Job.IntentVersion == 2 ? DateTimeOffset.FromUnixTimeMilliseconds(value.ExpiresAt.ToUnixTimeMilliseconds()) : value.ExpiresAt.ToUniversalTime() };
    }

    public static string Metadata(DurablePrintEnvelope value)
    {
        value = Normalize(value);
        if (value.Job.IntentVersion == 2) return JsonSerializer.Serialize(value);
        // Exact pre-extension JSON shape/order: retry hashes of existing v1 journals must not change.
        var j = value.Job;
        return JsonSerializer.Serialize(new { Job = new { j.Id, j.TargetAgent, j.TargetPrinter, j.DocumentReference,
            j.Format, j.Copies, j.Status, j.Origin, j.SecurityClass }, value.OrganizationId, value.CenterId, value.ExpiresAt, value.ContentSha256 });
    }

    public static string Hash(DurablePrintEnvelope value)
    {
        value = Normalize(value);
        if (value.Job.IntentVersion == 1) return Digest(Metadata(value)).ToUpperInvariant();
        var job = value.Job;
        var values = new SortedDictionary<string, object>(StringComparer.Ordinal)
        {
            ["version"]=2, ["job_id"]=job.Id.Value.ToString(), ["organization_id"]=value.OrganizationId,
            ["center_id"]=value.CenterId, ["requested_by"]=job.RequestedByUserId!.Value,
            ["origin_type"]=job.Origin!.Type switch { PrintOriginType.WebDesktop=>"WEB_DESKTOP", PrintOriginType.WebMobile=>"WEB_MOBILE",
                PrintOriginType.WebTablet=>"WEB_TABLET", PrintOriginType.LocalAgent=>"LOCAL_AGENT", _=>"SYSTEM" },
            ["source_agent"]=job.Origin.SourceAgent?.ToString() ?? "", ["document_reference"]=job.DocumentReference,
            ["document_type"]=job.DocumentType!, ["document_security_class"]=job.SecurityClass switch {
                DocumentSecurityClass.General=>"GENERAL", DocumentSecurityClass.Administrative=>"ADMINISTRATIVE",
                DocumentSecurityClass.Financial=>"FINANCIAL", DocumentSecurityClass.Clinical=>"CLINICAL", _=>"SENSITIVE_CLINICAL" },
            ["target_agent"]=job.TargetAgent.ToString(), ["target_printer"]=job.TargetPrinter,
            ["format"]=job.Format == PrintDocumentFormat.Pdf ? "pdf" : "plain_text", ["copies"]=job.Copies,
            ["content_sha256"]=value.ContentSha256, ["expires_at"]=value.ExpiresAt.UtcDateTime.ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'", System.Globalization.CultureInfo.InvariantCulture)
        };
        return Digest(JsonSerializer.Serialize(values));
    }
}
