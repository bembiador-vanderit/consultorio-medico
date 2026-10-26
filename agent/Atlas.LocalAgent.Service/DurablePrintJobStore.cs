using System.Text.Json;
using System.Text.RegularExpressions;
using Atlas.LocalAgent.Core;
using Microsoft.Data.Sqlite;

namespace Atlas.LocalAgent.Service;

public sealed record DurablePrintEnvelope(PrintJob Job, int OrganizationId, int CenterId, DateTimeOffset ExpiresAt, string ContentSha256);
public sealed record DurablePrintState(string Status, int? SpoolId = null, string? ErrorCode = null,string? EvidenceType=null);
public enum DurablePrintFailure { PrinterUnavailable, FormatUnsupported, InvalidArtifact, PhysicalDenied }
public sealed record PhysicalExecutionEvidence(Guid JobId,Guid DeliveryId,string PrinterId,string PageFormat,string PrinterFingerprint,
    int Copies,long StartedAt,int? SpoolId,long? AcceptedAt);

/// <summary>
/// Metadata-only durable inbox. One DB per station; no bytes, credentials or document contents.
/// SQLite transactions serialize independent processes as well as threads. Never delete tombstones
/// or retry a claimed job automatically: a spool handoff cannot be atomic with a local DB commit.
/// An additional physical evidence row is committed before any native executor may be called.
/// </summary>
public sealed class DurablePrintJobStore
{
    private readonly string _connectionString;
    private readonly Guid _station;
    private readonly int _organization;
    private readonly int _center;

    public DurablePrintJobStore(string databasePath, Guid station, int organizationId, int centerId)
    {
        if (station == Guid.Empty || organizationId <= 0 || centerId <= 0) throw new ArgumentException("Scope inválido.");
        _station = station; _organization = organizationId; _center = centerId;
        var path = Path.GetFullPath(databasePath);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        _connectionString = new SqliteConnectionStringBuilder { DataSource = path, Pooling = false, DefaultTimeout = 30 }.ToString();
        using var db = Open();
        using var command = db.CreateCommand();
        command.CommandText = """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS store_identity (
              singleton INTEGER PRIMARY KEY CHECK(singleton=1), station TEXT NOT NULL,
              organization INTEGER NOT NULL, center INTEGER NOT NULL, schema_version INTEGER NOT NULL CHECK(schema_version=2));
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY, intent_hash TEXT NOT NULL, intent_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL, expires_at INTEGER NOT NULL,
              state TEXT NOT NULL CHECK(state IN ('received','ready','printing','submitted','printed','unknown','failed','cancelled','expired')));
            CREATE TABLE IF NOT EXISTS deliveries (
              id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), received_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS results (
              job_id TEXT PRIMARY KEY REFERENCES jobs(id), outcome TEXT NOT NULL,
              spool_id INTEGER, error_code TEXT, recorded_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS physical_executions (
              job_id TEXT PRIMARY KEY REFERENCES jobs(id), delivery_id TEXT NOT NULL REFERENCES deliveries(id), printer_id TEXT NOT NULL,
              page_format TEXT NOT NULL, printer_fingerprint TEXT NOT NULL,
              copies INTEGER NOT NULL CHECK(copies=1), started_at INTEGER NOT NULL,
              spool_id INTEGER, accepted_at INTEGER);
            CREATE TABLE IF NOT EXISTS physical_observations (
              job_id TEXT PRIMARY KEY REFERENCES physical_executions(job_id), kind TEXT NOT NULL
                CHECK(kind IN ('OS_REPORTED_PRINTED','HUMAN_CONFIRMED_PRINTED','HUMAN_REPORTED_PROBLEM')),
              spool_id INTEGER NOT NULL, recorded_at INTEGER NOT NULL);
            """;
        command.ExecuteNonQuery();
        command.CommandText = "PRAGMA foreign_keys=OFF"; command.ExecuteNonQuery();
        using var tx = db.BeginTransaction();
        Run(db, tx, "INSERT OR IGNORE INTO store_identity VALUES(1,$station,$org,$center,2)",
            ("$station", station.ToString()), ("$org", organizationId), ("$center", centerId));
        using var check = Command(db, tx, "SELECT station,organization,center,schema_version FROM store_identity WHERE singleton=1");
        using var row = check.ExecuteReader();
        if (!row.Read() || row.GetString(0) != station.ToString() || row.GetInt32(1) != organizationId || row.GetInt32(2) != centerId || row.GetInt32(3) is not (1 or 2))
            throw new InvalidOperationException("El almacén pertenece a otro contexto.");
        var version = row.GetInt32(3);
        row.Close();
        if (version == 1) UpgradeV1(db, tx);
        Run(db, tx, """
            CREATE TRIGGER IF NOT EXISTS local_print_job_guard BEFORE UPDATE ON jobs
            WHEN NEW.id IS NOT OLD.id OR NEW.intent_hash IS NOT OLD.intent_hash OR NEW.intent_json IS NOT OLD.intent_json
              OR NEW.payload_sha256 IS NOT OLD.payload_sha256 OR NEW.expires_at IS NOT OLD.expires_at
              OR (OLD.state<>NEW.state AND NOT (
                (OLD.state='received' AND NEW.state IN ('ready','cancelled','expired','failed','unknown')) OR
                (OLD.state='ready' AND NEW.state IN ('printing','cancelled','expired','failed','unknown')) OR
                (OLD.state='printing' AND NEW.state IN ('submitted','unknown')) OR
                (OLD.state='submitted' AND NEW.state IN ('printed','unknown'))))
            BEGIN SELECT RAISE(ABORT,'immutable intent or invalid local print transition'); END;
            """);
        using var integrity = Command(db, tx, "PRAGMA foreign_key_check");
        using var invalid = integrity.ExecuteReader();
        if (invalid.Read()) throw new InvalidDataException("Referencias locales inconsistentes.");
        invalid.Close(); tx.Commit();
        command.CommandText = "PRAGMA foreign_keys=ON"; command.ExecuteNonQuery();
    }

    private static void UpgradeV1(SqliteConnection db, SqliteTransaction tx)
    {
        var rows = new List<(string Id, string Hash, string Json, long Expires, string State)>();
        using (var query = Command(db, tx, "SELECT id,intent_hash,intent_json,expires_at,state FROM jobs"))
        using (var reader = query.ExecuteReader())
            while (reader.Read()) rows.Add((reader.GetString(0), reader.GetString(1), reader.GetString(2), reader.GetInt64(3), reader.GetString(4)));
        // Atomic table rebuild, not a reset. Preserve v1 hashes, tombstones, attempts and receipts.
        Run(db, tx, """
            CREATE TABLE jobs_v2(id TEXT PRIMARY KEY,intent_hash TEXT NOT NULL,intent_json TEXT NOT NULL,
              payload_sha256 TEXT NOT NULL,expires_at INTEGER NOT NULL,
              state TEXT NOT NULL CHECK(state IN ('received','ready','printing','submitted','printed','unknown','failed','cancelled','expired')));
            """);
        foreach (var item in rows)
        {
            if (!string.Equals(item.Hash, PrintIntentFingerprint.Digest(item.Json), StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Journal v1 corrupto; no se migra ni se recrea.");
            Run(db, tx, "INSERT INTO jobs_v2 VALUES($id,$hash,$json,$payload,$expires,$state)", ("$id",item.Id),
                ("$hash",item.Hash), ("$json",item.Json), ("$payload",PrintIntentFingerprint.Digest(item.Json)), ("$expires",item.Expires), ("$state",item.State));
        }
        Run(db, tx, """
            DROP TABLE jobs;
            ALTER TABLE jobs_v2 RENAME TO jobs;
            CREATE TABLE store_identity_v2(singleton INTEGER PRIMARY KEY CHECK(singleton=1),station TEXT NOT NULL,
              organization INTEGER NOT NULL,center INTEGER NOT NULL,schema_version INTEGER NOT NULL CHECK(schema_version=2));
            INSERT INTO store_identity_v2 SELECT singleton,station,organization,center,2 FROM store_identity;
            DROP TABLE store_identity;
            ALTER TABLE store_identity_v2 RENAME TO store_identity;
            """);
    }

    private SqliteConnection Open()
    {
        var db = new SqliteConnection(_connectionString); db.Open();
        using var command = db.CreateCommand();
        command.CommandText = "PRAGMA foreign_keys=ON; PRAGMA synchronous=FULL;";
        command.ExecuteNonQuery();
        return db;
    }

    public PrintJobRegistration Accept(DurablePrintEnvelope envelope, Guid deliveryId)
    {
        envelope.Job.Validate();
        if (deliveryId == Guid.Empty || envelope.Job.TargetAgent != _station || envelope.OrganizationId != _organization || envelope.CenterId != _center)
            throw new ArgumentException("Entrega fuera del contexto autorizado.");
        // An opaque reference, never a URL/path/document body. Real content delivery is a later phase.
        if (!Regex.IsMatch(envelope.Job.DocumentReference, "\\A[A-Za-z0-9_:-]{1,128}\\z", RegexOptions.CultureInvariant)
            || !Regex.IsMatch(envelope.Job.TargetPrinter, "\\A[A-Za-z0-9_-]{1,100}\\z", RegexOptions.CultureInvariant)
            || !Regex.IsMatch(envelope.ContentSha256, "\\A[0-9a-f]{64}\\z", RegexOptions.CultureInvariant))
            throw new ArgumentException("Referencia no opaca.");
        var normalized = PrintIntentFingerprint.Normalize(envelope);
        var json = PrintIntentFingerprint.Metadata(normalized);
        var hash = PrintIntentFingerprint.Hash(normalized);
        var id = envelope.Job.Id.Value.ToString();
        using var db = Open(); using var tx = db.BeginTransaction(); // BEGIN IMMEDIATE, not deferred.
        using var lookup = Command(db, tx, "SELECT intent_hash FROM jobs WHERE id=$id", ("$id", id));
        var old = lookup.ExecuteScalar() as string;
        if (old is not null && old != hash) return PrintJobRegistration.Conflict;
        using var delivery = Command(db, tx, "SELECT job_id FROM deliveries WHERE id=$id", ("$id", deliveryId.ToString()));
        var oldJob = delivery.ExecuteScalar() as string;
        if (oldJob is not null && oldJob != id) return PrintJobRegistration.Conflict;
        if (old is null)
            Run(db, tx, "INSERT INTO jobs VALUES($id,$hash,$json,$payload,$expiry,$state)", ("$id", id), ("$hash", hash), ("$json", json),
                ("$payload",PrintIntentFingerprint.Digest(json)), ("$expiry", normalized.ExpiresAt.ToUnixTimeMilliseconds()),
                ("$state", normalized.ExpiresAt <= DateTimeOffset.UtcNow ? "expired" : normalized.Job.IntentVersion == 2 ? "received" : "ready"));
        Run(db, tx, "INSERT OR IGNORE INTO deliveries VALUES($delivery,$id,$now)", ("$delivery", deliveryId.ToString()), ("$id", id), ("$now", Now()));
        tx.Commit();
        return old is null ? PrintJobRegistration.Registered : PrintJobRegistration.Duplicate;
    }

    public DurablePrintEnvelope Load(PrintJobId id)
    {
        using var db = Open(); using var tx = db.BeginTransaction();
        using var command = Command(db, tx, "SELECT intent_json,intent_hash,payload_sha256 FROM jobs WHERE id=$id", ("$id", id.Value.ToString()));
        using var row = command.ExecuteReader();
        if (!row.Read()) throw new KeyNotFoundException("Trabajo no registrado.");
        var json = row.GetString(0);
        if (PrintIntentFingerprint.Digest(json) != row.GetString(2))
            throw new InvalidDataException("Metadatos locales inconsistentes.");
        var envelope = JsonSerializer.Deserialize<DurablePrintEnvelope>(json) ?? throw new InvalidDataException("Metadatos inválidos.");
        if (PrintIntentFingerprint.Hash(envelope) != row.GetString(1)) throw new InvalidDataException("Intención inconsistente.");
        if (envelope.Job.Id != id || envelope.Job.TargetAgent != _station || envelope.OrganizationId != _organization || envelope.CenterId != _center)
            throw new InvalidDataException("Contexto local inconsistente.");
        row.Close(); tx.Commit(); return envelope;
    }

    public IReadOnlyList<PrintJobId> Pending()
    {
        using var db = Open(); using var tx = db.BeginTransaction();
        using var command = Command(db, tx, "SELECT id FROM jobs WHERE state IN ('received','ready') AND expires_at>$now ORDER BY id", ("$now", Now()));
        using var rows = command.ExecuteReader(); var result = new List<PrintJobId>();
        while (rows.Read()) result.Add(new PrintJobId(Guid.Parse(rows.GetString(0))));
        rows.Close(); tx.Commit(); return result;
    }

    public DurablePrintState Read(PrintJobId id)
    {
        using var db = Open(); using var tx = db.BeginTransaction();
        Run(db, tx, "UPDATE jobs SET state='expired' WHERE id=$id AND state IN ('received','ready') AND expires_at<=$now", ("$id", id.Value.ToString()), ("$now", Now()));
        var state = Read(db, tx, id); tx.Commit(); return state;
    }

    private static DurablePrintState Read(SqliteConnection db, SqliteTransaction tx, PrintJobId id)
    {
        using var command = Command(db, tx, """
            SELECT j.state,r.spool_id,r.error_code,o.kind,e.job_id FROM jobs j LEFT JOIN results r ON r.job_id=j.id
              LEFT JOIN physical_executions e ON e.job_id=j.id LEFT JOIN physical_observations o ON o.job_id=j.id WHERE j.id=$id
            """, ("$id", id.Value.ToString()));
        using var row = command.ExecuteReader();
        if (!row.Read()) throw new KeyNotFoundException("Trabajo no registrado.");
        // 'printing' without a receipt is deliberately ambiguous, never permission to re-spool.
        return new(row.GetString(0) == "printing" ? "unknown" : row.GetString(0), row.IsDBNull(1) ? null : row.GetInt32(1),
            row.IsDBNull(2) ? (row.GetString(0) == "printing" ? "OUTCOME_UNKNOWN" : null) : row.GetString(2),
            !row.IsDBNull(3)?row.GetString(3):row.IsDBNull(4)?null:row.GetString(0) is "printing" or "unknown"?"UNKNOWN_AFTER_SPOOL":"SUBMITTED_TO_SPOOLER");
    }

    /// <summary>Callback must submit at most once. Tests supply fakes only; no automatic retries.</summary>
    public DurablePrintState ExecuteOnce(PrintJobId id, Func<int> submit, bool physical = false, Guid? deliveryId = null,
        SyntheticPageFormat? pageFormat=null,string? printerFingerprint=null)
    {
        ArgumentNullException.ThrowIfNull(submit);
        var envelope = Load(id); // Corrupt/foreign metadata must fail closed before any executor callback.
        using (var db = Open())
        using (var tx = db.BeginTransaction())
        {
            Run(db, tx, "UPDATE jobs SET state='expired' WHERE id=$id AND state IN ('received','ready') AND expires_at<=$now", ("$id", id.Value.ToString()), ("$now", Now()));
            var claimed = Run(db, tx, "UPDATE jobs SET state='printing' WHERE id=$id AND state='ready'", ("$id", id.Value.ToString()));
            if (claimed == 0) { var existing = Read(db, tx, id); tx.Commit(); return existing; }
            if(physical)
            {
                // Independent one-shot evidence, in the SAME transaction as the printing barrier.
                if(envelope.Job.Copies!=1 || deliveryId is null || pageFormat is null || !Enum.IsDefined(pageFormat.Value)
                    || printerFingerprint?.Length!=64)throw new InvalidDataException("Physical evidence is incomplete.");
                using var delivery=Command(db,tx,"SELECT job_id FROM deliveries WHERE id=$delivery",("$delivery",deliveryId.Value.ToString()));
                if(delivery.ExecuteScalar() as string!=id.Value.ToString())throw new InvalidDataException("Physical delivery mismatch.");
                Run(db,tx,"INSERT INTO physical_executions(job_id,delivery_id,printer_id,page_format,printer_fingerprint,copies,started_at) VALUES($id,$delivery,$printer,$format,$fingerprint,1,$now)",
                    ("$id",id.Value.ToString()),("$delivery",deliveryId.Value.ToString()),("$printer",envelope.Job.TargetPrinter),
                    ("$format",pageFormat.Value.ToString()),("$fingerprint",printerFingerprint),("$now",Now()));
            }
            tx.Commit(); // Durable barrier BEFORE any possible Windows spool call.
        }
        int spool;
        try
        {
            spool = submit();
            if (spool <= 0) throw new InvalidOperationException("Spool inválido.");
        }
        catch (Exception)
        {
            // Driver exceptions may occur AFTER acceptance. Never assume a safe automatic retry.
            return Finish(id, "unknown", physical?PhysicalEvidence(id)?.SpoolId:null, "OUTCOME_UNKNOWN");
        }
        // A failed receipt commit must also fail closed, never execute the callback again.
        if(physical)RecordSpoolAcceptance(id,spool);
        return Finish(id, "submitted", spool, null);
    }

    public void RecordSpoolAcceptance(PrintJobId id,int spoolId)
    {
        if(spoolId<=0)throw new ArgumentOutOfRangeException(nameof(spoolId));
        using var db=Open();using var tx=db.BeginTransaction();
        var changed=Run(db,tx,"UPDATE physical_executions SET spool_id=$spool,accepted_at=COALESCE(accepted_at,$now) WHERE job_id=$id AND (spool_id IS NULL OR spool_id=$spool)",
            ("$id",id.Value.ToString()),("$spool",spoolId),("$now",Now()));
        if(changed!=1)throw new InvalidDataException("Physical acceptance conflicts with durable evidence.");
        tx.Commit();
    }

    public PhysicalExecutionEvidence? PhysicalEvidence(PrintJobId id)
    {
        using var db=Open();using var tx=db.BeginTransaction();
        using var command=Command(db,tx,"SELECT delivery_id,printer_id,page_format,printer_fingerprint,copies,started_at,spool_id,accepted_at FROM physical_executions WHERE job_id=$id",("$id",id.Value.ToString()));
        using var row=command.ExecuteReader();
        return row.Read()?new(id.Value,Guid.Parse(row.GetString(0)),row.GetString(1),row.GetString(2),row.GetString(3),row.GetInt32(4),row.GetInt64(5),
            row.IsDBNull(6)?null:row.GetInt32(6),row.IsDBNull(7)?null:row.GetInt64(7)):null;
    }

    private DurablePrintState Finish(PrintJobId id, string outcome, int? spool, string? code)
    {
        using var db = Open(); using var tx = db.BeginTransaction();
        Run(db, tx, "INSERT INTO results VALUES($id,$outcome,$spool,$code,$now)", ("$id", id.Value.ToString()),
            ("$outcome", outcome), ("$spool", spool), ("$code", code), ("$now", Now()));
        Run(db, tx, "UPDATE jobs SET state=$outcome WHERE id=$id", ("$id", id.Value.ToString()), ("$outcome", outcome));
        tx.Commit(); return Read(id);
    }

    public DurablePrintState Cancel(PrintJobId id)
    {
        using var db = Open(); using var tx = db.BeginTransaction();
        Run(db, tx, "UPDATE jobs SET state='cancelled' WHERE id=$id AND state IN ('received','ready')", ("$id", id.Value.ToString()));
        var result = Read(db, tx, id); tx.Commit(); return result;
    }

    public DurablePrintState ExpireBeforeExecution(PrintJobId id)
    {
        using var db=Open(); using var tx=db.BeginTransaction();
        Run(db,tx,"UPDATE jobs SET state='expired' WHERE id=$id AND state IN ('received','ready')",("$id",id.Value.ToString()));
        var state=Read(db,tx,id);tx.Commit();return state;
    }

    public DurablePrintState RequireReview(PrintJobId id)
    {
        using var db=Open(); using var tx=db.BeginTransaction();
        var changed=Run(db,tx,"UPDATE jobs SET state='unknown' WHERE id=$id AND state IN ('received','ready','printing','submitted')",("$id",id.Value.ToString()));
        if(changed!=0) Run(db,tx,"INSERT INTO results VALUES($id,'unknown',NULL,'OUTCOME_UNKNOWN',$now) ON CONFLICT(job_id) DO NOTHING",("$id",id.Value.ToString()),("$now",Now()));
        var state=Read(db,tx,id);tx.Commit();return state;
    }

    public DurablePrintState MarkReady(PrintJobId id)
    {
        _ = Load(id);
        using var db = Open(); using var tx = db.BeginTransaction();
        var state = Read(db, tx, id);
        if (state.Status is not ("received" or "ready")) throw new InvalidOperationException("Transición local no permitida.");
        Run(db, tx, "UPDATE jobs SET state=CASE WHEN expires_at<=$now THEN 'expired' ELSE 'ready' END WHERE id=$id AND state IN ('received','ready')",
            ("$id",id.Value.ToString()), ("$now",Now()));
        var result = Read(db, tx, id); tx.Commit(); return result;
    }

    public DurablePrintState FailBeforeSpool(PrintJobId id, DurablePrintFailure failure)
    {
        var code = failure switch { DurablePrintFailure.PrinterUnavailable => "PRINTER_UNAVAILABLE",
            DurablePrintFailure.FormatUnsupported => "FORMAT_UNSUPPORTED", DurablePrintFailure.InvalidArtifact => "INVALID_ARTIFACT",
            DurablePrintFailure.PhysicalDenied => "PHYSICAL_DENIED", _ => throw new ArgumentOutOfRangeException(nameof(failure)) };
        using var db = Open(); using var tx = db.BeginTransaction();
        var changed = Run(db, tx, "UPDATE jobs SET state='failed' WHERE id=$id AND state IN ('received','ready')", ("$id", id.Value.ToString()));
        if (changed != 0)
            Run(db, tx, "INSERT INTO results VALUES($id,'failed',NULL,$code,$now)", ("$id", id.Value.ToString()), ("$code", code), ("$now", Now()));
        var result = Read(db, tx, id); tx.Commit(); return result;
    }

    // Caller must have a trustworthy spooler observation; this method does not infer paper output.
    public DurablePrintState RecordPrintedObservation(PrintJobId id, int spoolId)
    {
        if (spoolId <= 0) throw new ArgumentOutOfRangeException(nameof(spoolId));
        using var db = Open(); using var tx = db.BeginTransaction();
        var previous = Read(db, tx, id);
        if (previous.SpoolId != spoolId || previous.Status is not ("submitted" or "printed"))
            throw new InvalidOperationException("Observación incompatible con el recibo.");
        Run(db, tx, "UPDATE results SET outcome='printed' WHERE job_id=$id", ("$id", id.Value.ToString()));
        Run(db, tx, "UPDATE jobs SET state='printed' WHERE id=$id", ("$id", id.Value.ToString()));
        Run(db,tx,"INSERT INTO physical_observations SELECT job_id,'OS_REPORTED_PRINTED',$spool,$now FROM physical_executions WHERE job_id=$id ON CONFLICT(job_id) DO NOTHING",
            ("$id",id.Value.ToString()),("$spool",spoolId),("$now",Now()));
        tx.Commit(); return Read(id);
    }

    // Only an authenticated, scope-validated server delivery may provide human evidence.
    // Never invokes an executor or promotes UNKNOWN; backend owns actor/time/audit.
    public DurablePrintState RecordHumanConfirmation(PrintJobId id,int spoolId,bool confirmed)
    {
        using var db=Open();using var tx=db.BeginTransaction();var state=Read(db,tx,id);
        if(state.Status!="submitted" || state.SpoolId!=spoolId || spoolId<=0)
            throw new InvalidOperationException("Human evidence requires the same submitted spool receipt.");
        var kind=confirmed?"HUMAN_CONFIRMED_PRINTED":"HUMAN_REPORTED_PROBLEM";var target=confirmed?"printed":"unknown";
        Run(db,tx,"INSERT INTO physical_observations SELECT job_id,$kind,$spool,$now FROM physical_executions WHERE job_id=$id",
            ("$id",id.Value.ToString()),("$kind",kind),("$spool",spoolId),("$now",Now()));
        using var check=Command(db,tx,"SELECT kind FROM physical_observations WHERE job_id=$id",("$id",id.Value.ToString()));
        if(check.ExecuteScalar() as string!=kind)throw new InvalidDataException("Missing physical evidence.");
        Run(db,tx,"UPDATE jobs SET state=$state WHERE id=$id",("$id",id.Value.ToString()),("$state",target));
        Run(db,tx,"UPDATE results SET outcome=$state,error_code=$error WHERE job_id=$id",("$id",id.Value.ToString()),
            ("$state",target),("$error",confirmed?null:"HUMAN_REPORTED_PROBLEM"));
        tx.Commit();return Read(id);
    }

    private static long Now() => DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
    private static SqliteCommand Command(SqliteConnection db, SqliteTransaction tx, string sql, params (string Key, object? Value)[] values)
    {
        var command = db.CreateCommand(); command.Transaction = tx; command.CommandText = sql;
        foreach (var item in values) command.Parameters.AddWithValue(item.Key, item.Value ?? DBNull.Value);
        return command;
    }
    private static int Run(SqliteConnection db, SqliteTransaction tx, string sql, params (string Key, object? Value)[] values)
    {
        using var command = Command(db, tx, sql, values); return command.ExecuteNonQuery();
    }
}
