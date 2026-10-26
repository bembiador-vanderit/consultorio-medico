using System.Text.Json;
using Atlas.LocalAgent.Core;
using Atlas.LocalAgent.Service;
using Microsoft.Data.Sqlite;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Atlas.LocalAgent.Tests;

[TestClass]
public sealed class PrintContractTests
{
    private string _root = null!;
    private readonly Guid _station = Guid.NewGuid();
    private string Database => Path.Combine(_root,"jobs.sqlite");
    private DurablePrintJobStore Store() => new(Database,_station,1,1);
    private DurablePrintEnvelope Job(PrintOriginType origin=PrintOriginType.WebMobile) => new(
        new PrintJob(PrintJobId.New(),_station,"printer-qa","artifact-qa",PrintDocumentFormat.Pdf,1) {
            IntentVersion=2, RequestedByUserId=42, DocumentType="report", SecurityClass=DocumentSecurityClass.Clinical,
            Origin=new PrintOrigin(origin,"42","org-1-center-1") },1,1,DateTimeOffset.UtcNow.AddMinutes(5),new string('a',64));
    [TestInitialize] public void Setup() { _root=Path.Combine(Path.GetTempPath(),"atlas-contract-"+Guid.NewGuid()); Directory.CreateDirectory(_root); }
    [TestCleanup] public void Cleanup() => Directory.Delete(_root,true);

    [TestMethod]
    public void CanonicalFingerprintMatchesSharedPythonVector()
    {
        var v=JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory,"print-intent-v2.json"))).RootElement;
        var job=new DurablePrintEnvelope(new PrintJob(new PrintJobId(Guid.Parse(v.GetProperty("job_id").GetString()!)),
            Guid.Parse(v.GetProperty("target_agent").GetString()!),v.GetProperty("target_printer").GetString()!,"artifact-qa",PrintDocumentFormat.Pdf,2) {
                IntentVersion=2, RequestedByUserId=42, DocumentType="report", SecurityClass=DocumentSecurityClass.Clinical,
                Origin=new PrintOrigin(PrintOriginType.WebMobile,"42","org-7-center-9") },7,9,
            DateTimeOffset.Parse(v.GetProperty("expires_at").GetString()!,System.Globalization.CultureInfo.InvariantCulture),new string('a',64));
        Assert.AreEqual(v.GetProperty("sha256").GetString(),PrintIntentFingerprint.Hash(job));
    }

    [TestMethod]
    public void ReceivedReadyAndTerminalProtectionAreDurable()
    {
        var job=Job(); Store().Accept(job,Guid.NewGuid());
        Assert.AreEqual("received",Store().Read(job.Job.Id).Status);
        Assert.AreEqual("ready",Store().MarkReady(job.Job.Id).Status);
        Store().Cancel(job.Job.Id);
        Assert.ThrowsExactly<InvalidOperationException>(()=>Store().MarkReady(job.Job.Id));
        Assert.AreEqual("cancelled",Store().Read(job.Job.Id).Status);
    }

    [TestMethod]
    public void MobileTabletNeedNoSourceAndChangedIdentityConflicts()
    {
        foreach(var origin in new[]{PrintOriginType.WebMobile,PrintOriginType.WebTablet})
        {
            var job=Job(origin); Store().Accept(job,Guid.NewGuid());
            Assert.IsNull(Store().Load(job.Job.Id).Job.Origin!.SourceAgent);
            foreach(var changed in new[] {
                job with {Job=job.Job with {RequestedByUserId=43, Origin=job.Job.Origin! with {ActorReference="43"}}},
                job with {Job=job.Job with {SecurityClass=DocumentSecurityClass.Financial}},
                job with {Job=job.Job with {DocumentReference="other-artifact"}},
                job with {Job=job.Job with {TargetPrinter="other-printer"}},
                job with {Job=job.Job with {DocumentType="receipt"}} })
                Assert.AreEqual(PrintJobRegistration.Conflict,Store().Accept(changed,Guid.NewGuid()));
            var differentOrigin=job with {Job=job.Job with {Origin=job.Job.Origin! with {
                Type=origin==PrintOriginType.WebMobile?PrintOriginType.WebTablet:PrintOriginType.WebMobile }}};
            Assert.AreEqual(PrintJobRegistration.Conflict,Store().Accept(differentOrigin,Guid.NewGuid()));
        }
    }

    [TestMethod]
    public void PrintingBoundaryAndRestartNeverBecomeFailedOrReady()
    {
        var job=Job(); Store().Accept(job,Guid.NewGuid()); Store().MarkReady(job.Job.Id);
        using(var db=new SqliteConnection($"Data Source={Database};Pooling=False"))
        { db.Open();using var c=db.CreateCommand();c.CommandText="UPDATE jobs SET state='printing'";c.ExecuteNonQuery(); }
        Assert.AreEqual("unknown",Store().Read(job.Job.Id).Status);
        Assert.AreEqual("unknown",Store().FailBeforeSpool(job.Job.Id,DurablePrintFailure.InvalidArtifact).Status);
        Assert.ThrowsExactly<InvalidOperationException>(()=>Store().MarkReady(job.Job.Id));
        Assert.AreEqual(PrintJobRegistration.Duplicate,Store().Accept(job,Guid.NewGuid()));
        using var connection=new SqliteConnection($"Data Source={Database};Pooling=False");connection.Open();
        using var invalid=connection.CreateCommand();invalid.CommandText="UPDATE jobs SET state='ready'";
        Assert.ThrowsExactly<SqliteException>(()=>invalid.ExecuteNonQuery());
    }

    [TestMethod]
    [DataRow(false)]
    [DataRow(true)]
    public void V1MigrationPreservesFingerprintReceiptAndNoReplay(bool corrupt)
    {
        var legacy=new DurablePrintEnvelope(new PrintJob(PrintJobId.New(),_station,"printer-qa","artifact-qa",PrintDocumentFormat.PlainText,1),
            1,1,DateTimeOffset.UtcNow.AddMinutes(5),new string('a',64));
        var json=PrintIntentFingerprint.Metadata(legacy); var hash=PrintIntentFingerprint.Hash(legacy);
        var id=legacy.Job.Id.Value.ToString();
        using(var db=new SqliteConnection($"Data Source={Database};Pooling=False"))
        {
            db.Open();using var c=db.CreateCommand();c.CommandText="""
              CREATE TABLE store_identity(singleton INTEGER PRIMARY KEY CHECK(singleton=1),station TEXT NOT NULL,organization INTEGER NOT NULL,center INTEGER NOT NULL,schema_version INTEGER NOT NULL CHECK(schema_version=1));
              CREATE TABLE jobs(id TEXT PRIMARY KEY,intent_hash TEXT NOT NULL,intent_json TEXT NOT NULL,expires_at INTEGER NOT NULL,state TEXT NOT NULL CHECK(state IN ('ready','printing','submitted','printed','unknown','failed','cancelled','expired')));
              CREATE TABLE deliveries(id TEXT PRIMARY KEY,job_id TEXT NOT NULL REFERENCES jobs(id),received_at INTEGER NOT NULL);
              CREATE TABLE results(job_id TEXT PRIMARY KEY REFERENCES jobs(id),outcome TEXT NOT NULL,spool_id INTEGER,error_code TEXT,recorded_at INTEGER NOT NULL);
              INSERT INTO store_identity VALUES(1,$station,1,1,1);
              INSERT INTO jobs VALUES($id,$hash,$json,$expiry,'submitted');
              INSERT INTO deliveries VALUES('old-delivery',$id,1);
              INSERT INTO results VALUES($id,'submitted',23,NULL,1);
              """;
            c.Parameters.AddWithValue("$station",_station.ToString()); c.Parameters.AddWithValue("$id",id);
            c.Parameters.AddWithValue("$hash",corrupt?"invalid":hash); c.Parameters.AddWithValue("$json",json); c.Parameters.AddWithValue("$expiry",legacy.ExpiresAt.ToUnixTimeMilliseconds());
            c.ExecuteNonQuery();
        }
        if(corrupt)
        {
            Assert.ThrowsExactly<InvalidDataException>(()=>Store());
            using var db=new SqliteConnection($"Data Source={Database};Pooling=False");db.Open();
            using var c=db.CreateCommand();c.CommandText="SELECT schema_version FROM store_identity";
            Assert.AreEqual(1L,c.ExecuteScalar());
            c.CommandText="SELECT count(*) FROM jobs";Assert.AreEqual(1L,c.ExecuteScalar());
            return;
        }
        Assert.AreEqual(legacy,Store().Load(legacy.Job.Id));
        Assert.AreEqual(PrintJobRegistration.Duplicate,Store().Accept(legacy,Guid.NewGuid()));
        Assert.AreEqual(23,Store().Read(legacy.Job.Id).SpoolId);
        using(var db=new SqliteConnection($"Data Source={Database};Pooling=False"))
        { db.Open();using var c=db.CreateCommand();c.CommandText="SELECT intent_hash FROM jobs";Assert.AreEqual(hash,c.ExecuteScalar()); }
    }
}
