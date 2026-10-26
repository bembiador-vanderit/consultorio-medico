using Atlas.LocalAgent.Core;

namespace Atlas.LocalAgent.Service;

internal static class Program
{
    public static async Task<int> Main(string[] args)
    {
        if (args.Length == 2 && args[0] is "--windows-service" or "--service-handoff" or "--service-copy-state" or "--service-inspect-state" or "--service-inspect-credential-binding")
            return await WindowsServiceEntry.RunAsync(args[0], args[1]);
        // A machine-owned binding must be checked BEFORE creating even a default-root UUID.
        if (File.Exists(ServiceConfiguration.MachineConfigPath))
        { Console.Error.WriteLine("Esta estación está administrada por AtlasLocalAgent. No se inicia otra instancia manual."); return 3; }
        var root = AgentPaths.DefaultRoot; var once = false; var probe = false; var allowPhysical = false; int? runSeconds = null;
        string? inspectPrinter = null; string? inspectBridgePrinter=null; string? physicalAuthorizationFile=null; var inspectFormat = SyntheticPageFormat.A4;
        var environment = CommunicationEnvironment.Production;
        var routingSafe=false;var stopOnStdinClose=false;Guid? replay=null,loseResult=null,unknownJob=null;
        for (var i = 0; i < args.Length; i++)
        {
            if (args[i] == "--data-dir" && i + 1 < args.Length) root = Path.GetFullPath(args[++i]);
            else if (args[i] == "--environment" && i + 1 < args.Length && args[i + 1] is "Production" or "Development")
                environment = args[++i] == "Development" ? CommunicationEnvironment.Development : CommunicationEnvironment.Production;
            else if (args[i] == "--once") once = true;
            else if (args[i] == "--probe") probe = true;
            else if (args[i] == "--allow-physical-print") allowPhysical = true;
            else if (args[i] == "--routing-safe-validation") routingSafe=true;
            else if (args[i] == "--stop-on-stdin-close") stopOnStdinClose=true;
            else if (args[i] == "--physical-authorization-file" && i+1<args.Length) physicalAuthorizationFile=args[++i];
            else if (args[i] == "--inspect-bridge-printer" && i+1<args.Length) inspectBridgePrinter=args[++i];
            else if (args[i] == "--routing-replay-job" && i+1<args.Length) replay=Guid.Parse(args[++i]);
            else if (args[i] == "--routing-lose-result-once" && i+1<args.Length) loseResult=Guid.Parse(args[++i]);
            else if (args[i] == "--routing-unknown-job" && i+1<args.Length) unknownJob=Guid.Parse(args[++i]);
            else if (args[i] == "--inspect-printer" && i + 1 < args.Length) inspectPrinter = args[++i];
            else if (args[i] == "--format" && i + 1 < args.Length && Enum.TryParse<SyntheticPageFormat>(args[++i], false, out var format) && Enum.IsDefined(format)) inspectFormat = format;
            else if (args[i] == "--run-for-seconds" && i + 1 < args.Length && int.TryParse(args[++i], out var seconds) && seconds is > 0 and <= 3600) runSeconds = seconds;
            else { Console.Error.WriteLine("Opciones: --data-dir RUTA --environment Production|Development --once --probe --run-for-seconds N --allow-physical-print --inspect-printer NOMBRE --format A4|Letter|Pos80"); return 2; }
        }
        if((routingSafe && allowPhysical) || (!routingSafe && (replay is not null || loseResult is not null || unknownJob is not null || physicalAuthorizationFile is not null)))
        {Console.Error.WriteLine("SafeValidation cannot enable physical printing.");return 2;}
        if(inspectBridgePrinter is not null)
        {
            var devices=await new WindowsPrinterDiscovery().EnumerateAsync(CancellationToken.None);
            var p=devices.Single(x=>x.Name==inspectBridgePrinter);
            Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new {Count=devices.Count,p.Name,p.Driver,p.RegistryId,
                p.IsDefault,p.Status,p.Capabilities,Fingerprint=PhysicalPrinterFingerprint.For(p),
                SpoolerAvailable=await new WindowsGdiPrintBackend().IsSpoolerAvailableAsync(CancellationToken.None),
                PhysicalExecutionAuthorized=false,PhysicalPrintsSent=0}));
            return 0;
        }
        if (probe)
        {
            try { var response = await new LocalAgentClient(root).SendAsync(new(LocalCommand.Snapshot)); Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(response, Wire.Options)); return response.Snapshot is null ? 1 : 0; }
            catch (Exception) { Console.Error.WriteLine("Proceso de fondo no disponible."); return 1; }
        }
        Directory.CreateDirectory(root);
        using var cancellation = new CancellationTokenSource();
        if (stopOnStdinClose && !Console.IsInputRedirected)
        { Console.Error.WriteLine("El arranque administrado requiere el canal privado de su panel."); return 2; }
        // Console.In may implement ReadAsync with a synchronous native read. Never block startup.
        var parentWatch = stopOnStdinClose ? Task.Run(() => ManualAgentLaunch.WatchParentAsync(Console.In, cancellation)) : Task.CompletedTask;
        if (runSeconds is not null) cancellation.CancelAfter(TimeSpan.FromSeconds(runSeconds.Value));
        ConsoleCancelEventHandler cancel = (_, e) => { e.Cancel = true; cancellation.Cancel(); };
        Console.CancelKeyPress += cancel;
        try
        {
            using var instance = new FileStream(Path.Combine(root, "service.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
            Directory.CreateDirectory(Path.Combine(root, "logs"));
            using var writer = new StreamWriter(Path.Combine(root, "logs", $"agent-{DateTime.UtcNow:yyyyMMdd}.jsonl"), append: true);
            var log = new JsonAgentLog(writer);
            using var registryHttp = AtlasRegistryClient.CreateHttpClient(environment);
            var registry = new AtlasRegistryClient(registryHttp, new WindowsSecretStore(root), environment);
            var runtime = new AgentRuntime(new(root), new WindowsPrinterDiscovery(), new MockCloudTransport(), new InMemoryLanDiscovery(), log, registry: registry);
            var printing = new SyntheticPrintCoordinator(new(root), new WindowsGdiPrintBackend(allowPhysical), new WindowsPrinterDiscovery(), () => runtime.Snapshot, log, allowPhysical);
            try
            {
                await runtime.StartAsync(cancellation.Token);
                printing.RecoverInterruptedJobs();
                var grant=PhysicalExecutionAuthorization.Load(physicalAuthorizationFile);
                if(grant.Enabled && (loseResult is not null || unknownJob is not null))
                    throw new InvalidDataException("Physical authorization cannot combine with fault injection flags.");
                var consumer=routingSafe?new OfficialPrintConsumer(root,runtime,registry,loseResult,unknownJob,grant):null;
                if(replay is not null){await consumer!.ReplayAsync(replay.Value,cancellation.Token);return 0;}
                if (inspectPrinter is not null)
                {
                    var printer = runtime.Snapshot.Printers.SingleOrDefault(p => p.Name == inspectPrinter);
                    var paper = printer is null ? null : SyntheticPaper.Match(printer, inspectFormat);
                    if (printer is null || paper is null) throw new LocalPrintException(PrintFailure.CapabilityMismatch);
                    var request = new SyntheticPrintRequest(PrintJobId.New(), runtime.Snapshot.Identity.AgentId, printer.DeviceId, inspectFormat);
                    var backend = new WindowsGdiPrintBackend();
                    var layout = await backend.InspectLayoutAsync(new(request.ToJob(), inspectFormat, printer, paper, runtime.Snapshot.Configuration.StationName, DateTimeOffset.Now), cancellation.Token);
                    Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new { Printer = printer.Name, Format = inspectFormat, Paper = paper,
                        Lines = layout.Lines.Count, BottomMillimeter = layout.EndMillimeter, SpoolerAvailable = await backend.IsSpoolerAvailableAsync(cancellation.Token), PhysicalJobsSubmitted = 0 }, Wire.Options));
                }
                else if (once) Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(runtime.Snapshot, Wire.Options));
                else
                {
                    var pipe = new LocalPipeServer(root, runtime, log, printing);
                    var tasks = new List<Task> { pipe.RunAsync(cancellation.Token), runtime.RunHeartbeatLoopAsync(TimeSpan.FromSeconds(30), cancellation.Token) };
                    if(consumer is not null)tasks.Add(consumer.RunAsync(cancellation.Token));
                    await Task.WhenAny(tasks); cancellation.Cancel(); await Task.WhenAll(tasks);
                }
            }
            catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { }
            finally { await printing.DrainAsync(); await runtime.StopAsync(); }
            return 0;
        }
        catch (LocalPrintException ex) { Console.Error.WriteLine(ex.Failure + ": " + PrintMessages.Error(ex.Failure)); return 1; }
        catch (Exception) { Console.Error.WriteLine("Atlas Local Agent: no se pudo iniciar. Revise el diagnóstico local; no se registran detalles sensibles."); return 1; }
        finally
        {
            cancellation.Cancel();
            // An independently cancelled child must not wait for a still-open parent stdin.
            if (parentWatch.IsCompleted) await parentWatch;
            Console.CancelKeyPress -= cancel;
        }
    }
}
