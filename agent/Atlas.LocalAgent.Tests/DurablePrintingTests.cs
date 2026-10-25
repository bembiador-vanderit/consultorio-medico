using Atlas.LocalAgent.Core;
using Atlas.LocalAgent.Service;
using Microsoft.Data.Sqlite;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Atlas.LocalAgent.Tests;

[TestClass]
public sealed class DurablePrintingTests
{
    private string _directory = null!;
    private string Database => Path.Combine(_directory, "jobs.sqlite");
    private readonly Guid _station = Guid.NewGuid();
    private DurablePrintJobStore Store() => new(Database, _station, 1, 1);
    private DurablePrintEnvelope Job() => new(new PrintJob(PrintJobId.New(), _station, "printer-qa", "artifact-qa", PrintDocumentFormat.PlainText, 1), 1, 1, DateTimeOffset.UtcNow.AddMinutes(5), new string('a', 64));
    [TestInitialize] public void Setup() { _directory = Path.Combine(Path.GetTempPath(), "atlas-durable-" + Guid.NewGuid()); Directory.CreateDirectory(_directory); }
    [TestCleanup] public void Cleanup() { Directory.Delete(_directory, true); }

    [TestMethod]
    public void RestartAndLostResponseReusePersistedReceipt()
    {
        var job = Job(); var delivery = Guid.NewGuid(); var count = 0;
        Assert.AreEqual(PrintJobRegistration.Registered, Store().Accept(job, delivery));
        Assert.AreEqual(job, Store().Load(job.Job.Id));
        Assert.AreEqual("submitted", Store().ExecuteOnce(job.Job.Id, () => { count++; return 12; }).Status);
        var restarted = Store();
        Assert.AreEqual(PrintJobRegistration.Duplicate, restarted.Accept(job, Guid.NewGuid()));
        Assert.AreEqual(12, restarted.ExecuteOnce(job.Job.Id, () => { count++; return 13; }).SpoolId);
        Assert.AreEqual(1, count);
    }

    [TestMethod]
    public void PendingMetadataCanRecoverWithoutAnotherDelivery()
    {
        var job = Job(); Store().Accept(job, Guid.NewGuid());
        var restarted = Store(); Assert.AreEqual(job.Job.Id, restarted.Pending().Single());
        Assert.AreEqual(job, restarted.Load(job.Job.Id));
        restarted.ExecuteOnce(job.Job.Id, () => 8);
        Assert.AreEqual(0, Store().Pending().Count);
    }

    [TestMethod]
    public async Task ConcurrentIndependentConnectionsSubmitExactlyOnce()
    {
        var job = Job(); Store().Accept(job, Guid.NewGuid()); var count = 0;
        await Task.WhenAll(Enumerable.Range(0, 12).Select(_ => Task.Run(() => Store().ExecuteOnce(job.Job.Id,
            () => { Interlocked.Increment(ref count); Thread.Sleep(30); return 42; }))));
        Assert.AreEqual(1, count); Assert.AreEqual(42, Store().Read(job.Job.Id).SpoolId);
    }

    [TestMethod]
    public void ConflictingIntentAndDeliveryCannotReuseId()
    {
        var job = Job(); var delivery = Guid.NewGuid(); Store().Accept(job, delivery);
        Assert.AreEqual(PrintJobRegistration.Conflict, Store().Accept(job with { Job = job.Job with { Copies = 2 } }, Guid.NewGuid()));
        Assert.AreEqual(PrintJobRegistration.Conflict, Store().Accept(job with { ContentSha256 = new string('b', 64) }, Guid.NewGuid()));
        Assert.AreEqual(PrintJobRegistration.Conflict, Store().Accept(Job(), delivery));
    }

    [TestMethod]
    public void CrashAtSpoolBoundaryNeverResubmits()
    {
        var job = Job(); Store().Accept(job, Guid.NewGuid());
        // Simulate killed process after durable claim, before result commit.
        using (var db = new SqliteConnection($"Data Source={Database};Pooling=False"))
        { db.Open(); using var cmd = db.CreateCommand(); cmd.CommandText = "UPDATE jobs SET state='printing'"; cmd.ExecuteNonQuery(); }
        var calls = 0; var result = Store().ExecuteOnce(job.Job.Id, () => { calls++; return 1; });
        Assert.AreEqual("unknown", result.Status); Assert.AreEqual("OUTCOME_UNKNOWN", result.ErrorCode); Assert.AreEqual(0, calls);
    }

    [TestMethod]
    public void CorruptMetadataFailsClosedBeforeDispatch()
    {
        var job = Job(); Store().Accept(job, Guid.NewGuid());
        using (var db = new SqliteConnection($"Data Source={Database};Pooling=False"))
        { db.Open(); using var cmd = db.CreateCommand(); cmd.CommandText = "DROP TRIGGER local_print_job_guard; UPDATE jobs SET intent_hash='invalid'"; cmd.ExecuteNonQuery(); }
        var calls = 0;
        Assert.ThrowsExactly<InvalidDataException>(() => Store().ExecuteOnce(job.Job.Id, () => { calls++; return 1; }));
        Assert.AreEqual(0, calls);
    }

    [TestMethod]
    public void DriverErrorIsSanitizedAndNotRetried()
    {
        var job = Job(); Store().Accept(job, Guid.NewGuid()); var calls = 0;
        var result = Store().ExecuteOnce(job.Job.Id, () => { calls++; throw new IOException("SECRET patient document token"); });
        Assert.AreEqual("OUTCOME_UNKNOWN", result.ErrorCode);
        Store().ExecuteOnce(job.Job.Id, () => { calls++; return 7; }); Assert.AreEqual(1, calls);
        Assert.IsFalse(File.ReadAllText(Database).Contains("SECRET", StringComparison.Ordinal));
    }

    [TestMethod]
    public void CancellationAndExpiryBeforeSpoolAreDurable()
    {
        var job = Job(); Store().Accept(job, Guid.NewGuid()); Assert.AreEqual("cancelled", Store().Cancel(job.Job.Id).Status);
        Assert.AreEqual("cancelled", Store().ExecuteOnce(job.Job.Id, () => throw new AssertFailedException()).Status);
        var expired = Job() with { ExpiresAt = DateTimeOffset.UtcNow.AddSeconds(-1) }; Store().Accept(expired, Guid.NewGuid());
        Assert.AreEqual("expired", Store().ExecuteOnce(expired.Job.Id, () => throw new AssertFailedException()).Status);
    }

    [TestMethod]
    public void ScopeCannotBeChangedOrSpoofed()
    {
        var store = Store(); var job = Job();
        Assert.ThrowsExactly<ArgumentException>(() => store.Accept(job with { OrganizationId = 2 }, Guid.NewGuid()));
        Assert.ThrowsExactly<ArgumentException>(() => store.Accept(job with { Job = job.Job with { TargetAgent = Guid.NewGuid() } }, Guid.NewGuid()));
        Assert.ThrowsExactly<InvalidOperationException>(() => new DurablePrintJobStore(Database, _station, 1, 2));
        Assert.ThrowsExactly<ArgumentException>(() => store.Accept(job with { Job = job.Job with { DocumentReference = "https://unsafe/document" } }, Guid.NewGuid()));
    }

    [TestMethod]
    public void DeliberateNewIdAllowedAndLateCancellationCannotPromisePhysicalCancel()
    {
        var first = Job(); var second = Job(); var calls = 0;
        foreach (var job in new[] { first, second })
        { Store().Accept(job, Guid.NewGuid()); Store().ExecuteOnce(job.Job.Id, () => { calls++; return calls; }); }
        Assert.AreEqual(2, calls); Assert.AreEqual("submitted", Store().Cancel(first.Job.Id).Status);
    }

    [TestMethod]
    public void PreflightFailureAndConfirmedSpoolObservationAreDurable()
    {
        var failed = Job(); Store().Accept(failed, Guid.NewGuid());
        Assert.AreEqual("failed", Store().FailBeforeSpool(failed.Job.Id, DurablePrintFailure.PrinterUnavailable).Status);
        Assert.AreEqual("failed", Store().ExecuteOnce(failed.Job.Id, () => throw new AssertFailedException()).Status);
        var printed = Job(); Store().Accept(printed, Guid.NewGuid()); Store().ExecuteOnce(printed.Job.Id, () => 23);
        Assert.ThrowsExactly<InvalidOperationException>(() => Store().RecordPrintedObservation(printed.Job.Id, 24));
        Assert.AreEqual("printed", Store().RecordPrintedObservation(printed.Job.Id, 23).Status);
        Assert.AreEqual("printed", Store().ExecuteOnce(printed.Job.Id, () => throw new AssertFailedException()).Status);
    }
}
