using System.Text.Json;
using Atlas.LocalAgent.Core;

namespace Atlas.LocalAgent.Tray;

internal sealed class AgentWindow : Form
{
    private readonly LocalAgentClient _client;
    private readonly Label _status = new() { AutoSize = true, Font = new Font(SystemFonts.MessageBoxFont?.FontFamily ?? FontFamily.GenericSansSerif, 14, FontStyle.Bold), Text = "Desconectado" };
    private readonly Label _station = new() { AutoSize = true, Text = "Estación: —" };
    private readonly Label _agentId = new() { AutoSize = true, Text = "Agent ID: —" };
    private readonly Label _notice = new() { AutoSize = true, MaximumSize = new Size(850, 0), Text = "Foundation V1 · Sin vincular a Atlas. Red LAN/cloud deshabilitada." };
    private readonly DataGridView _printers = new() { Dock = DockStyle.Fill, ReadOnly = true, AllowUserToAddRows = false, AllowUserToDeleteRows = false,
        AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill, SelectionMode = DataGridViewSelectionMode.FullRowSelect, MultiSelect = false, RowHeadersVisible = false, BackgroundColor = Color.White };
    private readonly TextBox _stationName = new() { Width = 360, MaxLength = 100, AccessibleName = "Nombre de estación" };
    private readonly TextBox _displayCode = new() { Width = 240, MaxLength = 32, AccessibleName = "Código visible" };
    private readonly Button _refresh = new() { Text = "Actualizar", AutoSize = true, MinimumSize = new Size(110, 36) };
    private readonly Button _diagnostic = new() { Text = "Diagnóstico", AutoSize = true, MinimumSize = new Size(110, 36) };
    private readonly Button _save = new() { Text = "Guardar configuración", AutoSize = true, MinimumSize = new Size(180, 36), Enabled = false };
    private readonly NotifyIcon _tray;
    private readonly System.Windows.Forms.Timer _timer = new() { Interval = 5000 };
    private bool _busy, _exit;
    private AgentSnapshot? _snapshot;
    private readonly SyntheticPrintPanel _printing;

    public AgentWindow(LocalAgentClient client)
    {
        _client = client; Text = "Atlas Local Agent"; Size = new Size(1000, 680); MinimumSize = new Size(800, 540); StartPosition = FormStartPosition.CenterScreen;
        Font = SystemFonts.MessageBoxFont; BackColor = Color.FromArgb(246, 249, 250);
        _printing = new SyntheticPrintPanel(client);
        var tabs = new TabControl { Dock = DockStyle.Fill, Padding = new Point(14, 8) };
        var dashboard = new TabPage("Estado e impresoras") { Padding = new Padding(18) };
        var configuration = new TabPage("Configuración") { Padding = new Padding(18) };
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 3 };
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize)); layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100)); layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        var header = new FlowLayoutPanel { AutoSize = true, FlowDirection = FlowDirection.TopDown, WrapContents = false, Dock = DockStyle.Fill, Padding = new Padding(0, 0, 0, 14) };
        header.Controls.AddRange([_status, _station, _agentId, _notice]);
        _printers.Columns.Add("Name", "Impresora"); _printers.Columns.Add("Status", "Estado Windows");
        _printers.Columns.Add("Default", "Predeterminada"); _printers.Columns.Add("Connection", "Conexión"); _printers.Columns.Add("Driver", "Driver");
        var actions = new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Fill, Padding = new Padding(0, 14, 0, 0) };
        var print = new Button { Text = "Prueba local", AutoSize = true, MinimumSize = new Size(110, 36) };
        print.Click += (_, _) => tabs.SelectedIndex = 2;
        var exitPanel = new Button { Text = "Salir del panel", AutoSize = true, MinimumSize = new Size(110, 36) };
        exitPanel.Click += (_, _) => { _exit = true; Close(); };
        actions.Controls.AddRange([_refresh, _diagnostic, print, exitPanel]);
        layout.Controls.Add(header, 0, 0); layout.Controls.Add(_printers, 0, 1); layout.Controls.Add(actions, 0, 2); dashboard.Controls.Add(layout);
        var fields = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, WrapContents = false, AutoScroll = true };
        fields.Controls.AddRange([new Label { AutoSize = true, Text = "Solo configuración no sensible. La identidad del agente no se puede editar." },
            new Label { AutoSize = true, Text = "Nombre de estación", Margin = new Padding(3, 24, 3, 3) }, _stationName,
            new Label { AutoSize = true, Text = "Código visible (letras, números y guiones)", Margin = new Padding(3, 18, 3, 3) }, _displayCode, _save]);
        configuration.Controls.Add(fields); var printingPage = new TabPage("Prueba de impresión"); printingPage.Controls.Add(_printing);
        var pairingPage = new TabPage("Vincular con Atlas"); pairingPage.Controls.Add(new PairingPanel(client));
        tabs.TabPages.AddRange([dashboard, configuration, printingPage, pairingPage]); Controls.Add(tabs);
        _tray = new NotifyIcon { Icon = SystemIcons.Information, Text = "Atlas Local Agent · Desconectado", Visible = true };
        var menu = new ContextMenuStrip(); menu.Items.Add("Mostrar", null, (_, _) => ShowWindow()); menu.Items.Add("Diagnóstico", null, (_, _) => ShowDiagnostics());
        menu.Items.Add("Salir del panel", null, (_, _) => { _exit = true; Close(); }); _tray.ContextMenuStrip = menu; _tray.DoubleClick += (_, _) => ShowWindow();
        _refresh.Click += async (_, _) => await UpdateAsync(LocalCommand.Refresh);
        _diagnostic.Click += (_, _) => ShowDiagnostics(); _save.Click += async (_, _) => await SaveAsync();
        _timer.Tick += async (_, _) => await UpdateAsync(LocalCommand.Snapshot);
        Shown += async (_, _) => { await UpdateAsync(LocalCommand.Snapshot); _timer.Start(); };
        FormClosing += (_, e) => { if (!_exit && e.CloseReason == CloseReason.UserClosing) { e.Cancel = true; Hide(); } };
    }
    private void ShowWindow() { Show(); WindowState = FormWindowState.Normal; Activate(); }
    private static string StateLabel(AgentState state) => state switch
    {
        AgentState.Unpaired => "Sin vincular", AgentState.Pairing => "Vinculando", AgentState.Connected => "Conectado",
        AgentState.Disconnected => "Desconectado", AgentState.Degraded => "Servicio degradado", AgentState.Revoked => "Revocado", _ => "Error"
    };
    private async Task UpdateAsync(LocalCommand command)
    {
        if (_busy) return; _busy = true; _refresh.Enabled = false;
        try
        {
            var response = await _client.SendAsync(new(command));
            if (response.Snapshot is null) throw new InvalidDataException();
            Render(response.Snapshot);
            _printing.Update(response.Snapshot, response.PrintDiagnostics);
        }
        catch (Exception)
        {
            _status.Text = "Desconectado"; _status.ForeColor = Color.DimGray; _save.Enabled = false;
            _notice.Text = "El proceso de fondo no está disponible. El panel no inicia ni detiene servicios automáticamente.";
            _tray.Text = "Atlas Local Agent · Desconectado";
        }
        finally { _busy = false; _refresh.Enabled = true; }
    }
    private void Render(AgentSnapshot snapshot)
    {
        _snapshot = snapshot;
        _status.Text = StateLabel(snapshot.State); _status.ForeColor = snapshot.State == AgentState.Connected ? Color.DarkGreen : snapshot.State is AgentState.Error or AgentState.Degraded or AgentState.Revoked ? Color.Firebrick : Color.FromArgb(49, 95, 109);
        _station.Text = $"Estación: {snapshot.Configuration.StationName} · {snapshot.Configuration.DisplayCode}";
        _agentId.Text = $"Agent ID: {snapshot.Identity.AgentId}";
        _notice.Text = $"Agente {AgentVersion.Current} · {StateLabel(snapshot.State)} · Última evaluación: {snapshot.Heartbeat.LastSeen.ToLocalTime():g}. Impresoras: {snapshot.Printers.Count}. Organización: {snapshot.Configuration.Association.OrganizationId ?? "—"} · Centro: {snapshot.Configuration.Association.CenterId ?? "—"} · Grupo: {snapshot.Configuration.Association.WorkgroupId ?? "—"}. Sin impresión remota.";
        _tray.Text = "Atlas Local Agent · " + StateLabel(snapshot.State);
        _printers.Rows.Clear(); foreach (var printer in snapshot.Printers)
            _printers.Rows.Add(printer.Name, printer.Status, printer.IsDefault ? "Sí" : "No", printer.Connection.ToString(), printer.Driver ?? "No informado");
        if (!_stationName.Focused && !_displayCode.Focused)
        { _stationName.Text = snapshot.Configuration.StationName; _displayCode.Text = snapshot.Configuration.DisplayCode; }
        _save.Enabled = true;
    }
    private async Task SaveAsync()
    {
        if (_busy) return; _busy = true; _save.Enabled = false;
        try
        {
            var response = await _client.SendAsync(new(LocalCommand.Configure, _stationName.Text, _displayCode.Text));
            if (response.Snapshot is not null) Render(response.Snapshot);
            else MessageBox.Show(this, "Revise el nombre y el código de estación. No se guardaron cambios.", "Configuración", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
        catch (Exception) { MessageBox.Show(this, "No se pudo contactar al proceso de fondo.", "Atlas Local Agent"); }
        finally { _busy = false; _save.Enabled = _snapshot is not null; }
    }
    private void ShowDiagnostics()
    {
        if (_snapshot is null) { MessageBox.Show(this, "No hay diagnóstico del proceso de fondo disponible.", "Atlas Local Agent"); return; }
        using var dialog = new Form { Text = "Atlas Local Agent · Diagnóstico local", Size = new Size(800, 580), StartPosition = FormStartPosition.CenterParent };
        dialog.Controls.Add(new TextBox { Dock = DockStyle.Fill, Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Both,
            Font = new Font("Consolas", 10), Text = JsonSerializer.Serialize(new { Agent = _snapshot, Printing = _printing.Diagnostic }, new JsonSerializerOptions(Wire.Options) { WriteIndented = true }), AccessibleName = "Diagnóstico del agente y capacidades de impresoras" });
        dialog.ShowDialog(this);
    }
    protected override void Dispose(bool disposing)
    {
        if (disposing) { _timer.Stop(); _timer.Dispose(); _tray.Visible = false; _tray.ContextMenuStrip?.Dispose(); _tray.Dispose(); }
        base.Dispose(disposing);
    }
}
