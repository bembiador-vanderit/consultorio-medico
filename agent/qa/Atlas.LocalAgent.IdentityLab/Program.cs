using System.ServiceProcess;
using System.Text.Json;

namespace Atlas.LocalAgent.IdentityLab;

internal static class Program
{
    public static async Task<int> Main(string[] args)
    {
        if (args.Length != 2 || args[0] is not ("--prepare" or "--handoff" or "--verify" or "--candidate" or "--observer")) return 2;
        try
        {
            var root = LabOptions.ValidateRoot(args[1]); var options = LabOptions.Load(root); var probe = new LabProbe(root, options);
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(90));
            if (args[0] == "--prepare") { await probe.PrepareAsync(); Console.WriteLine("SyntheticUserPrepared"); }
            else if (args[0] == "--handoff") { await probe.HandoffAsync(timeout.Token); Console.WriteLine("SyntheticMemoryOnlyHandoffAcknowledged"); }
            else if (args[0] == "--verify") Console.WriteLine(JsonSerializer.Serialize(await probe.VerifyAsync(), LabOptions.Json));
            else ServiceBase.Run(new LabService(root, options, args[0] == "--observer")
                { ServiceName = args[0] == "--observer" ? options.ObserverName : options.CandidateName, AutoLog = false });
            return 0;
        }
        catch (Exception ex) { Console.Error.WriteLine("SyntheticLabDenied:" + ex.GetType().Name); return 1; }
    }
}

internal sealed class LabService(string root, LabOptions options, bool observer) : ServiceBase
{
    private readonly CancellationTokenSource _stop = new(TimeSpan.FromSeconds(90));
    protected override void OnStart(string[] args)
    {
        _ = Task.Run(async () =>
        {
            var path = Path.Combine(root, observer ? "observer-reports" : "reports", $"phase-{options.Phase}.json");
            var probe = new LabProbe(root, options);
            try
            {
                var result = observer ? await probe.ObserverAsync() : await probe.CandidateAsync(_stop.Token);
                result["Completed"] = true;
                await File.WriteAllTextAsync(path, JsonSerializer.Serialize(result, LabOptions.Json));
            }
            catch (Exception ex)
            {
                await File.WriteAllTextAsync(path, JsonSerializer.Serialize(new { Completed = false, ErrorCode = ex.GetType().Name,
                    probe.Stage, NativeCode = ex is System.ComponentModel.Win32Exception native ? native.NativeErrorCode : ex.HResult }));
            }
            finally { Stop(); }
        });
    }
    protected override void OnStop() => _stop.Cancel();
    protected override void Dispose(bool disposing) { if (disposing) _stop.Dispose(); base.Dispose(disposing); }
}
