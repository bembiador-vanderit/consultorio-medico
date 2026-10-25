using System.Text;
using System.Text.Json;
using Atlas.LocalAgent.Core;
using Atlas.LocalAgent.Service;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Atlas.LocalAgent.Tests;

[TestClass]
public sealed class LocalPrintingTests
{
    private string _root = null!;
    private readonly Guid _agentId = Guid.NewGuid();
    private StringWriter _log = null!;
    private static readonly PaperSizeCapability A4 = new("A4", 2100, 2970, 9);
    private static readonly PaperSizeCapability Letter = new("Letter", 2159, 2794, 1);
    private static readonly PaperSizeCapability Pos = new("80 x 300 mm", 800, 3000, 256);
    private static PrinterDevice Printer => new(PrinterDevice.IdFor("QA Printer"), "QA Printer", "Sin alertas reportadas", false,
        PrinterConnection.Local, "QA Driver", new(false, false, 1, [A4, Letter, Pos]));
    [TestInitialize] public void Setup() { _root = Directory.CreateTempSubdirectory("atlas-local-print-test-").FullName; _log = new(); }
    [TestCleanup] public void Cleanup() { _log.Dispose(); Directory.Delete(_root, true); }
    private SyntheticPrintRequest Request(SyntheticPageFormat format = SyntheticPageFormat.A4) => new(PrintJobId.New(), _agentId, Printer.DeviceId, format);
    private AgentSnapshot Snapshot() => new(true, new(_agentId, DateTimeOffset.UtcNow), new("QA Station", "QA-01", new()), AgentState.Unpaired,
        new(_agentId, "QA Station", AgentVersion.Current, AgentVersion.Protocol, "Windows QA", AgentState.Unpaired, DateTimeOffset.UtcNow, new(1, 0)), [Printer], AgentErrorCode.None);
    private SyntheticPrintCoordinator Coordinator(FakeBackend backend, FakeDiscovery? discovery = null, bool enabled = true, LocalPrintJobStore? store = null) =>
        new(store ?? new(_root), backend, discovery ?? new(), Snapshot, new JsonAgentLog(_log), enabled);

    [TestMethod] public void RequestRequiresExplicitPrinterFormatAndAgent()
    {
        var request = Request(); Assert.AreEqual(1, request.ToJob().Copies); Assert.AreEqual(PrintDocumentFormat.PlainText, request.ToJob().Format);
        foreach (var invalid in new[] { request with { PrinterId = "" }, request with { PrinterId = "patient-name" },
            request with { TargetAgent = Guid.Empty }, request with { PageFormat = (SyntheticPageFormat)999 }, request with { JobId = default } })
            Assert.ThrowsExactly<ArgumentException>(() => invalid.ToJob());
    }
    [TestMethod] public void WireRejectsDocumentsPathsCopiesAndRawPrintJobs()
    {
        var bytes = Wire.Serialize(Request()); var json = Encoding.UTF8.GetString(bytes).TrimEnd('}');
        foreach (var extra in new[] { "\"document\":\"SYNTHETIC-NOT-PHI\"", "\"path\":\"C:/secret.pdf\"", "\"copies\":2", "\"payload\":\"data\"" })
            Assert.ThrowsExactly<JsonException>(() => Wire.Deserialize<SyntheticPrintRequest>(Encoding.UTF8.GetBytes(json + "," + extra + "}")));
    }
    [TestMethod] public void CapabilitiesRequireDimensionsAndDriverPaperId()
    {
        Assert.AreEqual(A4, SyntheticPaper.Match(Printer, SyntheticPageFormat.A4));
        Assert.AreEqual(Letter, SyntheticPaper.Match(Printer, SyntheticPageFormat.Letter));
        Assert.AreEqual(Pos, SyntheticPaper.Match(Printer, SyntheticPageFormat.Pos80));
        foreach (var paper in new[] { new PaperSizeCapability("A4", null, null, 9), A4 with { RawKind = null }, A4 with { WidthTenthsMillimeter = 2000 } })
            Assert.IsNull(SyntheticPaper.Match(Printer with { Capabilities = new(false, false, 1, [paper]) }, SyntheticPageFormat.A4));
        Assert.IsNull(SyntheticPaper.Match(Printer with { Capabilities = new(false, false, 1, [Letter, A4]) }, SyntheticPageFormat.Pos80));
    }
    [TestMethod] public void ThreeLayoutsFitOnePageWithSeparatePosGeometry()
    {
        foreach (var format in Enum.GetValues<SyntheticPageFormat>())
        {
            var paper = SyntheticPaper.Match(Printer, format)!; var doc = new SyntheticPrintDocument(Request(format).ToJob(), format, Printer, paper, "QA Station", DateTimeOffset.Now);
            var pos = format == SyntheticPageFormat.Pos80; var margin = pos ? 3d : 15d;
            var layout = SyntheticPage.Layout(doc, margin, margin, paper.WidthTenthsMillimeter!.Value / 10d - margin,
                paper.HeightTenthsMillimeter!.Value / 10d - margin, (s, h) => s.Length * (pos ? 1.5 : 2));
            Assert.IsTrue(layout.EndMillimeter < paper.HeightTenthsMillimeter.Value / 10d - margin);
            Assert.IsTrue(layout.Lines.All(x => x.XMillimeter >= margin));
            Assert.IsTrue(layout.Lines.Any(x => x.Text.Contains("ATLAS", StringComparison.Ordinal)));
            Assert.IsTrue(layout.Lines.Any(x => x.Text == doc.Job.Id.Value.ToString()));
        }
    }
    [TestMethod] public void OfficialAcceptancePageContainsIdentityAndFitsOneA4()
    {
        var doc = new SyntheticPrintDocument(Request().ToJob(), SyntheticPageFormat.A4, Printer, A4, "QA Station", DateTimeOffset.Now)
            { OfficialRoutingQa = true };
        var lines = SyntheticPage.Content(doc).Select(x => x.Text).ToArray();
        Assert.IsTrue(lines.Contains("FINAL PHYSICAL PRINT QA"));
        Assert.IsTrue(lines.Contains("AGENT ID: " + _agentId));
        Assert.IsTrue(lines.Contains("COPIES: 1"));
        var layout = SyntheticPage.Layout(doc, 15, 15, 195, 282, (s, _) => s.Length * 2);
        Assert.IsTrue(layout.EndMillimeter < 282);
    }
    [TestMethod] public void LayoutRejectsClippingBeforeAnySpoolCall()
    {
        var doc = new SyntheticPrintDocument(Request().ToJob(), SyntheticPageFormat.A4, Printer, A4, new string('X', 100), DateTimeOffset.Now);
        Assert.ThrowsExactly<LocalPrintException>(() => SyntheticPage.Layout(doc, 0, 0, 30, 80, (s, h) => s.Length * 4));
    }
    [TestMethod] public async Task PreparationIsQueuedAndNeverPrints()
    {
        var backend = new FakeBackend(); var coordinator = Coordinator(backend); var request = Request();
        var reply = await coordinator.PrepareAsync(request, default); Assert.AreEqual(PrintJobStatus.Queued, reply.Receipt?.Status);
        Assert.AreEqual(0, backend.Calls); Assert.IsNull(reply.Receipt?.SpoolJobId);
    }
    [TestMethod] public async Task ConfirmationAndPhysicalGateBothRequired()
    {
        var backend = new FakeBackend(); var coordinator = Coordinator(backend, enabled: false); var request = Request();
        Assert.AreEqual(PrintFailure.ConfirmationRequired, (await coordinator.SubmitAsync(request, false, default)).Error);
        Assert.AreEqual(PrintFailure.PhysicalPrintingDisabled, (await coordinator.SubmitAsync(request, true, default)).Error);
        Assert.AreEqual(0, backend.Calls);
    }
    [TestMethod] public async Task NativeBackendIsFailClosedWithoutPhysicalFlag()
    {
        var request = Request(); var doc = new SyntheticPrintDocument(request.ToJob(), request.PageFormat, Printer, A4, "QA", DateTimeOffset.Now);
        var failure = await Assert.ThrowsExactlyAsync<LocalPrintException>(() => new WindowsGdiPrintBackend().SubmitAsync(doc, () => true, _ => { }, default));
        Assert.AreEqual(PrintFailure.PhysicalPrintingDisabled, failure.Failure);
    }
    [TestMethod] public async Task SameIdConcurrentRequestsSubmitExactlyOnce()
    {
        var backend = new FakeBackend(); var coordinator = Coordinator(backend); var request = Request();
        await Task.WhenAll(Enumerable.Range(0, 30).Select(_ => coordinator.SubmitAsync(request, true, default))); await coordinator.WaitForIdleAsync();
        Assert.AreEqual(1, backend.Calls); Assert.AreEqual(PrintJobStatus.Submitted, coordinator.Get(request.JobId).Receipt?.Status);
        Assert.AreEqual(401, coordinator.Get(request.JobId).Receipt?.SpoolJobId);
        await coordinator.SubmitAsync(request, true, default); Assert.AreEqual(1, backend.Calls);
        var submittedLogs = _log.ToString().Split('\n').Count(x => x.Contains("\"status\":\"Submitted\"", StringComparison.Ordinal)); Assert.AreEqual(1, submittedLogs);
    }
    [TestMethod] public async Task NewIdIsNewLegitimateIntent()
    {
        var backend = new FakeBackend(); var coordinator = Coordinator(backend);
        await coordinator.SubmitAsync(Request(), true, default); await coordinator.WaitForIdleAsync();
        await coordinator.SubmitAsync(Request(), true, default); await coordinator.WaitForIdleAsync(); Assert.AreEqual(2, backend.Calls);
    }
    [TestMethod] public async Task SameIdDifferentFormatConflictsWithoutSecondSubmission()
    {
        var backend = new FakeBackend(); var coordinator = Coordinator(backend); var request = Request();
        await coordinator.SubmitAsync(request, true, default); await coordinator.WaitForIdleAsync();
        Assert.AreEqual(PrintFailure.JobConflict, (await coordinator.SubmitAsync(request with { PageFormat = SyntheticPageFormat.Letter }, true, default)).Error);
        Assert.AreEqual(1, backend.Calls);
    }
    [TestMethod] public async Task RetryAfterRestartReturnsPersistedSpoolJob()
    {
        var backend = new FakeBackend(); var coordinator = Coordinator(backend); var request = Request();
        await coordinator.SubmitAsync(request, true, default); await coordinator.WaitForIdleAsync();
        var restarted = Coordinator(backend); restarted.RecoverInterruptedJobs();
        Assert.AreEqual(401, (await restarted.SubmitAsync(request, true, default)).Receipt?.SpoolJobId); Assert.AreEqual(1, backend.Calls);
    }
    [TestMethod] public async Task InterruptedSpoolingNeverAutoRetries()
    {
        var store = new LocalPrintJobStore(_root); var request = Request(); store.Register(request.ToJob());
        store.Update(request.JobId, x => x with { Job = x.Job with { Status = PrintJobStatus.Printing } });
        var backend = new FakeBackend(); var restarted = Coordinator(backend, store: store); restarted.RecoverInterruptedJobs();
        var reply = await restarted.SubmitAsync(request, true, default);
        Assert.AreEqual(PrintFailure.OutcomeUnknown, reply.Receipt?.Error); Assert.AreEqual(PrintJobStatus.Failed, reply.Receipt?.Status); Assert.AreEqual(0, backend.Calls);
    }
    [TestMethod] public async Task MissingSpoolJobDoesNotMeanPhysicalSuccessOrAllowRetry()
    {
        var backend = new FakeBackend { Observation = SpoolState.Missing }; var coordinator = Coordinator(backend); var request = Request();
        await coordinator.SubmitAsync(request, true, default); await coordinator.WaitForIdleAsync();
        var observed = await coordinator.ObserveAsync(request.JobId, default); Assert.AreEqual(PrintJobStatus.Submitted, observed.Receipt?.Status);
        Assert.AreEqual(SpoolState.Missing, observed.Receipt?.SpoolState); await coordinator.SubmitAsync(request, true, default); Assert.AreEqual(1, backend.Calls);
    }
    [TestMethod] public async Task InvalidPrinterAndCapabilityAreFailedWithoutPrinting()
    {
        var backend = new FakeBackend(); var coordinator = Coordinator(backend);
        var missing = await coordinator.SubmitAsync(Request() with { PrinterId = PrinterDevice.IdFor("does not exist") }, true, default);
        Assert.AreEqual(PrintFailure.InvalidPrinter, missing.Receipt?.Error); Assert.AreEqual(PrintJobStatus.Failed, missing.Receipt?.Status);
        var restricted = Coordinator(backend, new(Printer with { Capabilities = new(false, false, 1, [Letter]) }));
        var mismatch = await restricted.SubmitAsync(Request(), true, default); Assert.AreEqual(PrintFailure.CapabilityMismatch, mismatch.Receipt?.Error);
        Assert.AreEqual(0, backend.Calls);
    }
    [TestMethod] public async Task OfflineAndVirtualPrintersAreRejectedWithoutChangingWindows()
    {
        var backend = new FakeBackend();
        var offline = await Coordinator(backend, new(Printer with { ReportedStatus = 128 })).SubmitAsync(Request(), true, default);
        Assert.AreEqual(PrintFailure.PrinterOffline, offline.Receipt?.Error);
        var virtualResult = await Coordinator(backend, new(Printer with { IsVirtual = true })).SubmitAsync(Request(), true, default);
        Assert.AreEqual(PrintFailure.InvalidSelection, virtualResult.Receipt?.Error); Assert.AreEqual(0, backend.Calls);
    }
    [TestMethod] public async Task DriverFailureIsSanitizedAndNotRetried()
    {
        var backend = new FakeBackend { ThrowBefore = true }; var coordinator = Coordinator(backend); var request = Request();
        await coordinator.SubmitAsync(request, true, default); await coordinator.WaitForIdleAsync();
        Assert.AreEqual(PrintFailure.DriverFailure, coordinator.Get(request.JobId).Receipt?.Error);
        await coordinator.SubmitAsync(request, true, default); Assert.AreEqual(0, backend.Calls);
        Assert.IsFalse(_log.ToString().Contains("SYNTHETIC-SENSITIVE", StringComparison.Ordinal));
    }
    [TestMethod] public async Task FailureAfterSpoolAcceptanceIsUncertainAndNeverResubmits()
    {
        var backend = new FakeBackend { ThrowAfter = true }; var coordinator = Coordinator(backend); var request = Request();
        await coordinator.SubmitAsync(request, true, default); await coordinator.WaitForIdleAsync();
        Assert.AreEqual(PrintFailure.OutcomeUnknown, coordinator.Get(request.JobId).Receipt?.Error);
        Assert.AreEqual(401, coordinator.Get(request.JobId).Receipt?.SpoolJobId);
        await coordinator.SubmitAsync(request, true, default); Assert.AreEqual(1, backend.Calls);
    }
    [TestMethod] public async Task CancellationBeforeSpoolPreventsAcceptance()
    {
        var backend = new FakeBackend { Hold = new(TaskCreationOptions.RunContinuationsAsynchronously) }; var coordinator = Coordinator(backend); var request = Request();
        await coordinator.SubmitAsync(request, true, default); await backend.Entered.Task.WaitAsync(TimeSpan.FromSeconds(3));
        Assert.AreEqual(PrintJobStatus.Cancelled, coordinator.Cancel(request.JobId).Receipt?.Status);
        backend.Hold.SetResult(); await coordinator.WaitForIdleAsync(); Assert.AreEqual(0, backend.Calls);
        await coordinator.SubmitAsync(request, true, default); Assert.AreEqual(0, backend.Calls);
    }
    [TestMethod] public async Task CancellationAfterSpoolDoesNotClaimPhysicalCancellation()
    {
        var backend = new FakeBackend(); var coordinator = Coordinator(backend); var request = Request();
        await coordinator.SubmitAsync(request, true, default); await coordinator.WaitForIdleAsync();
        var cancelled = coordinator.Cancel(request.JobId); Assert.AreEqual(PrintFailure.TooLateToCancel, cancelled.Error);
        Assert.AreEqual(PrintJobStatus.Submitted, cancelled.Receipt?.Status);
    }
    [TestMethod] public async Task WrongAgentRejectedAndLogsContainNoContent()
    {
        var backend = new FakeBackend(); var coordinator = Coordinator(backend); var request = Request();
        Assert.AreEqual(PrintFailure.InvalidSelection, (await coordinator.SubmitAsync(request with { TargetAgent = Guid.NewGuid() }, true, default)).Error);
        await coordinator.SubmitAsync(request, true, default); await coordinator.WaitForIdleAsync();
        Assert.IsFalse(_log.ToString().Contains("Esta es una página", StringComparison.Ordinal)); Assert.IsFalse(_log.ToString().Contains("QA Printer", StringComparison.Ordinal));
        Assert.IsTrue(_log.ToString().Contains(request.JobId.Value.ToString(), StringComparison.Ordinal));
    }
    [TestMethod] public async Task DiagnosticsReportSpoolerAndSanitizedLastFailure()
    {
        var backend = new FakeBackend { Available = false }; var coordinator = Coordinator(backend); var request = Request();
        await coordinator.SubmitAsync(request, true, default); await coordinator.WaitForIdleAsync();
        var diagnostics = await coordinator.DiagnoseAsync(default); Assert.AreEqual(false, diagnostics.SpoolerAvailable);
        Assert.AreEqual(PrintFailure.SpoolerUnavailable, diagnostics.LastJob?.Error); Assert.AreEqual(0, backend.Calls);
    }
    [TestMethod] public void CorruptJournalFailsClosedInsteadOfRegeneratingIntent()
    {
        var store = new LocalPrintJobStore(_root); var request = Request(); store.Register(request.ToJob());
        var path = Path.Combine(_root, "print-jobs", request.JobId.Value.ToString("N") + ".json"); File.WriteAllText(path, "corrupt");
        Assert.ThrowsExactly<JsonException>(() => store.Register(request.ToJob())); Assert.AreEqual("corrupt", File.ReadAllText(path));
    }
    [TestMethod] public async Task LifecycleAndReportedSpoolStatusAreDistinctFromPhysicalValidation()
    {
        var backend = new FakeBackend { Observation = SpoolState.ReportedPrinted }; var coordinator = Coordinator(backend); var request = Request();
        await coordinator.PrepareAsync(request, default); await coordinator.SubmitAsync(request, true, default); await coordinator.WaitForIdleAsync();
        var observed = await coordinator.ObserveAsync(request.JobId, default); Assert.AreEqual(PrintJobStatus.Printed, observed.Receipt?.Status);
        Assert.IsTrue(PrintMessages.State(PrintJobStatus.Printed).Contains("verificar salida física", StringComparison.Ordinal));
        foreach (var state in new[] { "Queued", "Received", "Printing", "Submitted", "Printed" }) Assert.IsTrue(_log.ToString().Contains("\"status\":\"" + state + "\"", StringComparison.Ordinal));
    }
    [TestMethod] public async Task IpcPreparesCancelsAndRequiresConfirmationWithoutRealPrinter()
    {
        var runtime = new AgentRuntime(new(_root), new FakeDiscovery(), new MockCloudTransport(), new InMemoryLanDiscovery(), new JsonAgentLog(_log));
        await runtime.StartAsync(default); var backend = new FakeBackend();
        var coordinator = new SyntheticPrintCoordinator(new(_root), backend, new FakeDiscovery(), () => runtime.Snapshot, new JsonAgentLog(_log), true);
        var server = new LocalPipeServer(_root, runtime, new JsonAgentLog(_log), coordinator); using var cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(8));
        var serving = server.RunAsync(cancellation.Token);
        try
        {
            var request = Request() with { TargetAgent = runtime.Snapshot.Identity.AgentId }; var client = new LocalAgentClient(_root);
            var prepared = await client.SendAsync(new(LocalCommand.PrepareSyntheticTest, PrintRequest: request), cancellation.Token);
            Assert.AreEqual(PrintJobStatus.Queued, prepared.PrintReply?.Receipt?.Status);
            var notConfirmed = await client.SendAsync(new(LocalCommand.SubmitSyntheticTest, PrintRequest: request), cancellation.Token);
            Assert.AreEqual(PrintFailure.ConfirmationRequired, notConfirmed.PrintReply?.Error);
            var cancelled = await client.SendAsync(new(LocalCommand.CancelSyntheticTest, JobId: request.JobId), cancellation.Token);
            Assert.AreEqual(PrintJobStatus.Cancelled, cancelled.PrintReply?.Receipt?.Status); Assert.AreEqual(0, backend.Calls);
        }
        finally { cancellation.Cancel(); try { await serving; } catch (OperationCanceledException) { } await coordinator.DrainAsync(); await runtime.StopAsync(); }
    }
    [TestMethod] public async Task SpoolErrorKeepsIdentifierAndNeverRetriesUncertainJob()
    {
        var backend = new FakeBackend { Observation = SpoolState.Error }; var coordinator = Coordinator(backend); var request = Request();
        await coordinator.SubmitAsync(request, true, default); await coordinator.WaitForIdleAsync();
        var failed = await coordinator.ObserveAsync(request.JobId, default); Assert.AreEqual(PrintJobStatus.Failed, failed.Receipt?.Status);
        Assert.AreEqual(PrintFailure.OutcomeUnknown, failed.Receipt?.Error); Assert.AreEqual(401, failed.Receipt?.SpoolJobId);
        await coordinator.SubmitAsync(request, true, default); Assert.AreEqual(1, backend.Calls);
    }
    private sealed class FakeDiscovery(PrinterDevice? printer = null) : IPrinterDiscovery
    { public Task<IReadOnlyList<PrinterDevice>> EnumerateAsync(CancellationToken cancellationToken) => Task.FromResult<IReadOnlyList<PrinterDevice>>([printer ?? Printer]); }
    private sealed class FakeBackend : ILocalPrintBackend
    {
        public int Calls; public bool Available = true, ThrowBefore, ThrowAfter;
        public SpoolState Observation = SpoolState.Queued;
        public TaskCompletionSource? Hold;
        public TaskCompletionSource Entered = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public Task<bool> IsSpoolerAvailableAsync(CancellationToken cancellationToken) => Task.FromResult(Available);
        public async Task<SpoolSubmission> SubmitAsync(SyntheticPrintDocument document, Func<bool> beginSpooling, Action<int> spoolerAccepted, CancellationToken cancellationToken)
        {
            Entered.TrySetResult(); if (Hold is not null) await Hold.Task.WaitAsync(cancellationToken);
            if (ThrowBefore) throw new IOException("SYNTHETIC-SENSITIVE driver error");
            if (!beginSpooling()) throw new OperationCanceledException();
            var id = 400 + Interlocked.Increment(ref Calls); spoolerAccepted(id);
            if (ThrowAfter) throw new IOException("SYNTHETIC-SENSITIVE partial spool error");
            return new(id);
        }
        public Task<SpoolObservation> ObserveAsync(string printerName, int jobId, PrintJobId expectedJob, CancellationToken cancellationToken) => Task.FromResult(new SpoolObservation(Observation));
    }
}
