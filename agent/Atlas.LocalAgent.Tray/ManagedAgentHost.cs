using System.Diagnostics;
using Atlas.LocalAgent.Core;

namespace Atlas.LocalAgent.Tray;

/// <summary>Owns only the manually started child; never attaches to or stops another agent.</summary>
internal sealed class ManagedAgentHost : IDisposable
{
    private readonly Process _process;
    private ManagedAgentHost(Process process) => _process = process;

    public static ManagedAgentHost Start(string root)
    {
        var executable = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "service", "Atlas.LocalAgent.Service.exe"));
        if (!File.Exists(executable)) throw new FileNotFoundException();
        Directory.CreateDirectory(root);
        // An existing manually started Agent 1 is not ours. Refuse instead of taking ownership.
        using (new FileStream(Path.Combine(root, "service.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None)) { }
        var process = Process.Start(ManualAgentLaunch.StartInfo(executable, root)) ?? throw new IOException();
        var host = new ManagedAgentHost(process);
        try
        {
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(30));
            var response = new LocalAgentClient(root).SendAsync(new(LocalCommand.Snapshot), timeout.Token).GetAwaiter().GetResult();
            if (response.Snapshot is null || process.HasExited) throw new IOException();
            return host;
        }
        catch { host.Dispose(); throw; }
    }

    public void Dispose()
    {
        // EOF cooperatively drains the child and disposes SQLite. No process-name kill.
        try
        {
            _process.StandardInput.Close();
            if (!_process.WaitForExit(15000))
                MessageBox.Show("El agente está terminando una operación local. Espera antes de actualizar o desinstalar; no fuerces su cierre.", "Atlas Local Agent");
        }
        catch (InvalidOperationException) { }
        finally { _process.Dispose(); }
    }
}
