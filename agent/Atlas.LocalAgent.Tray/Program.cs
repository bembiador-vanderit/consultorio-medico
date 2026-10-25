using Atlas.LocalAgent.Core;

namespace Atlas.LocalAgent.Tray;

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        var root = AgentPaths.DefaultRoot;
        var managed = args.Length > 0 && args[0] == "--managed";
        var options = managed ? args[1..] : args;
        if (options.Length == 2 && options[0] == "--data-dir") root = Path.GetFullPath(options[1]);
        else if (options.Length != 0) return;
        ApplicationConfiguration.Initialize();
        using var panelMutex = managed ? new Mutex(false, ManualAgentLaunch.PanelMutex) : null;
        var ownsMutex = false;
        try { ownsMutex = panelMutex?.WaitOne(0) ?? false; }
        catch (AbandonedMutexException) { ownsMutex = true; }
        if (panelMutex is not null && !ownsMutex)
        {
            MessageBox.Show("Atlas Local Agent ya está abierto. Busca su icono junto al reloj de Windows.", "Atlas Local Agent");
            return;
        }
        try
        {
            using var host = managed ? ManagedAgentHost.Start(root) : null;
            Application.Run(new AgentWindow(new LocalAgentClient(root)));
        }
        catch (Exception)
        {
            MessageBox.Show("No se pudo iniciar Atlas Local Agent. Cierra otras ejecuciones del agente y vuelve a intentarlo. No se modificó tu vinculación ni se habilitó impresión.",
                "Atlas Local Agent", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
        finally { if (ownsMutex) panelMutex?.ReleaseMutex(); }
    }
}
