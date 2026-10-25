using System.Diagnostics;

namespace Atlas.LocalAgent.Core;

/// <summary>Installed shortcut policy: metadata/HTTPS only, no polling or physical executor.</summary>
public static class ManualAgentLaunch
{
    public const string PanelMutex = @"Local\Atlas.LocalAgent.InstalledPanel";

    public static ProcessStartInfo StartInfo(string executable, string dataRoot)
    {
        var start = new ProcessStartInfo(Path.GetFullPath(executable))
        {
            UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true,
            WorkingDirectory = Path.GetDirectoryName(Path.GetFullPath(executable))!
        };
        foreach (var argument in new[] { "--data-dir", Path.GetFullPath(dataRoot), "--environment", "Production", "--stop-on-stdin-close" })
            start.ArgumentList.Add(argument);
        // Defense in depth: never inherit the development switch from the shell.
        start.Environment.Remove("LOCAL_AGENT_ALLOW_LOOPBACK_HTTP");
        return start;
    }

    public static async Task WatchParentAsync(TextReader input, CancellationTokenSource lifetime)
    {
        var buffer = new char[1];
        try
        {
            while (await input.ReadAsync(buffer.AsMemory(), lifetime.Token) != 0) { }
            await lifetime.CancelAsync();
        }
        catch (OperationCanceledException) when (lifetime.IsCancellationRequested) { }
        catch (IOException) { await lifetime.CancelAsync(); }
    }
}
