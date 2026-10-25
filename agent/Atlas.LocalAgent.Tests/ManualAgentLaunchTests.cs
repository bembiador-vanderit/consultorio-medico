using Atlas.LocalAgent.Core;
using System.Diagnostics;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Atlas.LocalAgent.Tests;

[TestClass]
public sealed class ManualAgentLaunchTests
{
    [TestMethod]
    public void ShortcutLaunchIsProductionAndCannotEnablePrintOrRouting()
    {
        var start = ManualAgentLaunch.StartInfo(@"C:\Program Files\Atlas\service.exe", @"C:\User Data\Atlas");
        CollectionAssert.AreEqual(new[] { "--data-dir", @"C:\User Data\Atlas", "--environment", "Production", "--stop-on-stdin-close" }, start.ArgumentList.ToArray());
        Assert.IsFalse(start.UseShellExecute);
        Assert.IsTrue(start.CreateNoWindow);
        Assert.IsTrue(start.RedirectStandardInput);
        Assert.IsFalse(start.Environment.ContainsKey("LOCAL_AGENT_ALLOW_LOOPBACK_HTTP"));
    }

    [TestMethod]
    public async Task ClosingParentChannelCancelsChildWithoutForceKill()
    {
        using var lifetime = new CancellationTokenSource();
        await ManualAgentLaunch.WatchParentAsync(new StringReader(""), lifetime);
        Assert.IsTrue(lifetime.IsCancellationRequested);
    }

    [TestMethod]
    public async Task ParentChannelContentCannotEnableFeatures()
    {
        using var lifetime = new CancellationTokenSource();
        await ManualAgentLaunch.WatchParentAsync(new StringReader("--allow-physical-print\n"), lifetime);
        Assert.IsTrue(lifetime.IsCancellationRequested);
    }

    [TestMethod]
    public void InstallerDoesNotContainRuntimeDataAutostartOrAutoPairing()
    {
        var script = File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "installer", "atlas-local-agent.iss"));
        StringAssert.Contains(script, "PrivilegesRequired=lowest");
        StringAssert.Contains(script, "Parameters: \"--managed\"");
        StringAssert.Contains(script, "CloseApplications=no");
        StringAssert.Contains(script, "AppMutex=Local\\Atlas.LocalAgent.InstalledPanel");
        foreach (var section in new[] { "[Run]\r", "[Run]\n", "[Registry]", "[UninstallDelete]", "[InstallDelete]" })
            Assert.IsFalse(script.Contains(section, StringComparison.Ordinal), section);
        var sources = script.Split('\n').Where(x => x.StartsWith("Source:", StringComparison.Ordinal)).ToArray();
        Assert.AreEqual(4, sources.Length);
        Assert.IsTrue(sources.All(x => x.Contains("{#PayloadDir}", StringComparison.Ordinal)));
        var build = File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "installer", "Build-Installer.ps1"));
        StringAssert.Contains(build, "never reuse a previous payload");
        StringAssert.Contains(build, "--self-contained true");
        StringAssert.Contains(build, "Runtime data or forbidden artifacts detected");
    }

    [TestMethod]
    [Timeout(60000)]
    public async Task RealChildStopsOnParentEofAndKeepsItsOwnIdentity()
    {
        var root = Directory.CreateTempSubdirectory("atlas-managed-child-test-").FullName;
        var dll = Path.Combine(AppContext.BaseDirectory, "Atlas.LocalAgent.Service.dll");
        var start = new ProcessStartInfo("dotnet") { UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true };
        start.ArgumentList.Add(dll);
        foreach (var argument in ManualAgentLaunch.StartInfo(dll, root).ArgumentList) start.ArgumentList.Add(argument);
        using var process = Process.Start(start)!;
        try
        {
            if (File.Exists(Atlas.LocalAgent.Service.ServiceConfiguration.MachineConfigPath))
            {
                using var rejected = new CancellationTokenSource(TimeSpan.FromSeconds(10));
                await process.WaitForExitAsync(rejected.Token);
                Assert.AreEqual(3, process.ExitCode);
                Assert.IsFalse(File.Exists(Path.Combine(root, "identity.json")));
                return;
            }
            using var ready = new CancellationTokenSource(TimeSpan.FromSeconds(35));
            var response = await new LocalAgentClient(root).SendAsync(new(LocalCommand.Snapshot), ready.Token);
            Assert.IsNotNull(response.Snapshot);
            Assert.AreEqual(AgentState.Unpaired, response.Snapshot.State);
            Assert.IsNull(response.Snapshot.Configuration.Association.OrganizationId);
            Assert.IsNotNull(response.PrintDiagnostics);
            Assert.IsFalse(response.PrintDiagnostics.PhysicalPrintingEnabled);
            var identity = File.ReadAllBytes(Path.Combine(root, "identity.json"));
            process.StandardInput.Close();
            using var stopped = new CancellationTokenSource(TimeSpan.FromSeconds(15));
            await process.WaitForExitAsync(stopped.Token);
            Assert.AreEqual(0, process.ExitCode);
            CollectionAssert.AreEqual(identity, File.ReadAllBytes(Path.Combine(root, "identity.json")));
            Assert.IsFalse(Directory.Exists(Path.Combine(root, "secrets")));
        }
        finally
        {
            process.StandardInput.Close();
            if (!process.HasExited) { process.Kill(); process.WaitForExit(); }
            Directory.Delete(root, true);
        }
    }
}
