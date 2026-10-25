using Atlas.LocalAgent.Core;

namespace Atlas.LocalAgent.Tray;

internal sealed class SyntheticPrintPanel : UserControl
{
    private readonly LocalAgentClient _client;
    private readonly ComboBox _printers = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 650, AccessibleName = "Impresora para prueba sintética" };
    private readonly ComboBox _formats = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 400, AccessibleName = "Formato de la prueba" };
    private readonly Label _details = new() { AutoSize = true, MaximumSize = new Size(820, 0) };
    private readonly Label _status = new() { AutoSize = true, MaximumSize = new Size(820, 0), Text = "Ninguna prueba enviada." };
    private readonly Label _gate = new() { AutoSize = true, MaximumSize = new Size(820, 0) };
    private readonly Button _print = new() { Text = "Imprimir página de prueba", AutoSize = true, Enabled = false };
    private readonly Button _retry = new() { Text = "Consultar/reintentar mismo trabajo", AutoSize = true, Enabled = false };
    private readonly Button _cancel = new() { Text = "Cancelar antes del envío", AutoSize = true, Enabled = false };
    private readonly Button _new = new() { Text = "Nueva intención de prueba", AutoSize = true, Enabled = false };
    private AgentSnapshot? _snapshot;
    private LocalPrintDiagnostics? _diagnostics;
    private SyntheticPrintRequest? _request;
    private SyntheticPrintReceipt? _receipt;
    private bool _busy, _confirmed, _historyLoaded;
    private string? _inventory;
    public object Diagnostic => new { SelectedPrinter = (_printers.SelectedItem as PrinterChoice)?.Printer,
        SelectedFormat = (_formats.SelectedItem as FormatChoice)?.Format, LastResult = _receipt, Diagnostics = _diagnostics };

    public SyntheticPrintPanel(LocalAgentClient client)
    {
        _client = client; Dock = DockStyle.Fill;
        var layout = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, WrapContents = false, AutoScroll = true, Padding = new Padding(18) };
        layout.Controls.AddRange([new Label { Text = "Prueba local controlada · una página / una copia", AutoSize = true, Font = new Font(Font, FontStyle.Bold) },
            new Label { Text = "Solo contenido sintético. No acepta archivos, PDFs, pacientes ni documentos financieros.", AutoSize = true },
            _gate, new Label { Text = "Impresora (selección explícita)", AutoSize = true, Margin = new Padding(3, 20, 3, 3) }, _printers, _details,
            new Label { Text = "Formato", AutoSize = true, Margin = new Padding(3, 15, 3, 3) }, _formats]);
        var actions = new FlowLayoutPanel { AutoSize = true, MaximumSize = new Size(820, 0), WrapContents = true, Margin = new Padding(0, 18, 0, 12) };
        actions.Controls.AddRange([_print, _retry, _cancel, _new]); layout.Controls.Add(actions); layout.Controls.Add(_status);
        layout.Controls.Add(new Label { Text = "POS: diseño de 80 mm, sin orden de cutter. Entregado a Windows no garantiza salida física.\nNo se cambia la impresora predeterminada ni se guardan rutas de documentos.", AutoSize = true, MaximumSize = new Size(820, 0), Margin = new Padding(3, 18, 3, 3) });
        Controls.Add(layout);
        _printers.SelectedIndexChanged += (_, _) => SelectionChanged(true); _formats.SelectedIndexChanged += (_, _) => SelectionChanged(false);
        _print.Click += async (_, _) => await PrintAsync(); _retry.Click += async (_, _) => await RetryAsync();
        _cancel.Click += async (_, _) => { if (_request is not null) await SendAsync(new(LocalCommand.CancelSyntheticTest, JobId: _request.JobId)); };
        _new.Click += (_, _) => { _request = null; _receipt = null; _confirmed = false; _status.Text = "Nueva intención: necesita otra confirmación explícita."; Buttons(); };
    }
    public void Update(AgentSnapshot snapshot, LocalPrintDiagnostics? diagnostics)
    {
        _snapshot = snapshot; _diagnostics = diagnostics;
        _gate.Text = diagnostics?.PhysicalPrintingEnabled == true ? "Modo QA físico habilitado; cada envío exige confirmación."
            : "Impresión física bloqueada hasta autorización explícita de la prueba QA.";
        var oldId = (_printers.SelectedItem as PrinterChoice)?.Printer.DeviceId;
        var oldFormat = (_formats.SelectedItem as FormatChoice)?.Format;
        var inventory = System.Text.Json.JsonSerializer.Serialize(snapshot.Printers, Wire.Options); var changed = inventory != _inventory;
        if (changed)
        {
            _inventory = inventory;
            _printers.BeginUpdate(); _printers.Items.Clear(); foreach (var printer in snapshot.Printers) _printers.Items.Add(new PrinterChoice(printer));
            _printers.SelectedIndex = -1;
            if (oldId is not null) _printers.SelectedItem = _printers.Items.Cast<PrinterChoice>().FirstOrDefault(x => x.Printer.DeviceId == oldId);
            if (oldFormat is not null) _formats.SelectedItem = _formats.Items.Cast<FormatChoice>().FirstOrDefault(x => x.Format == oldFormat);
            _printers.EndUpdate();
        }
        if (!_historyLoaded && _request is null && _receipt is null && diagnostics?.LastJob is { } restored && restored.Job.TargetAgent == snapshot.Identity.AgentId)
        {
            _request = new(restored.Job.Id, restored.Job.TargetAgent, restored.Job.TargetPrinter, restored.PageFormat);
            _printers.SelectedItem = _printers.Items.Cast<PrinterChoice>().FirstOrDefault(x => x.Printer.DeviceId == restored.Job.TargetPrinter);
            _formats.SelectedItem = _formats.Items.Cast<FormatChoice>().FirstOrDefault(x => x.Format == restored.PageFormat);
            // A queued job reopened after UI restart needs a fresh confirmation, never an automatic submit.
            ShowReceipt(new(restored));
        }
        if (diagnostics is not null) _historyLoaded = true;
        if (_request is not null && diagnostics?.LastJob?.Job.Id == _request.JobId) ShowReceipt(new(diagnostics.LastJob));
        Buttons();
    }
    private void SelectionChanged(bool printerChanged)
    {
        if (printerChanged)
        {
            var printer = (_printers.SelectedItem as PrinterChoice)?.Printer; _formats.Items.Clear();
            if (printer is not null)
            {
                foreach (var format in Enum.GetValues<SyntheticPageFormat>()) _formats.Items.Add(new FormatChoice(format, SyntheticPaper.Match(printer, format) is not null));
                _details.Text = $"Driver: {printer.Driver ?? "No informado"} · Predeterminada: {(printer.IsDefault ? "Sí" : "No")}\n"
                    + $"Windows: {printer.Status} · Color: {Flag(printer.Capabilities.Color)} · Dúplex: {Flag(printer.Capabilities.Duplex)}\n"
                    + (printer.IsVirtual ? "Impresora virtual: no permitida para esta prueba física." : "Confirme que el papel elegido esté cargado.");
            }
            _formats.SelectedIndex = -1;
        }
        Buttons();
    }
    private void Buttons()
    {
        var printer = (_printers.SelectedItem as PrinterChoice)?.Printer; var compatible = (_formats.SelectedItem as FormatChoice)?.Supported == true;
        _print.Enabled = !_busy && _request is null && _snapshot is not null && printer is { IsVirtual: false } && compatible;
        _retry.Enabled = !_busy && _request is not null;
        _cancel.Enabled = !_busy && _receipt?.Status is PrintJobStatus.Queued or PrintJobStatus.Received or PrintJobStatus.Ready;
        _new.Enabled = !_busy && _request is not null && _receipt?.Status is PrintJobStatus.Failed or PrintJobStatus.Cancelled or PrintJobStatus.Submitted or PrintJobStatus.Printed;
        _printers.Enabled = !_busy && _request is null; _formats.Enabled = !_busy && _request is null;
    }
    private async Task PrintAsync()
    {
        if (_snapshot is null || _printers.SelectedItem is not PrinterChoice choice || _formats.SelectedItem is not FormatChoice format) return;
        _request = new(PrintJobId.New(), _snapshot.Identity.AgentId, choice.Printer.DeviceId, format.Format);
        var prepared = await SendAsync(new(LocalCommand.PrepareSyntheticTest, PrintRequest: _request));
        if (prepared?.Receipt?.Status != PrintJobStatus.Queued) return;
        if (!Confirm(choice.Printer.Name, format.Format)) { await SendAsync(new(LocalCommand.CancelSyntheticTest, JobId: _request.JobId)); return; }
        _confirmed = true;
        await SendAsync(new(LocalCommand.SubmitSyntheticTest, PrintRequest: _request, UserConfirmed: true));
    }
    private async Task RetryAsync()
    {
        if (_request is null) return;
        if (!_confirmed && _receipt?.Status is not (PrintJobStatus.Submitted or PrintJobStatus.Printed or PrintJobStatus.Failed or PrintJobStatus.Cancelled))
        {
            var prepared = await SendAsync(new(LocalCommand.PrepareSyntheticTest, PrintRequest: _request));
            var printer = _snapshot?.Printers.FirstOrDefault(x => x.DeviceId == _request.PrinterId);
            if (prepared?.Receipt?.Status != PrintJobStatus.Queued || printer is null) return;
            if (!Confirm(printer.Name, _request.PageFormat)) { await SendAsync(new(LocalCommand.CancelSyntheticTest, JobId: _request.JobId)); return; }
            _confirmed = true;
            await SendAsync(new(LocalCommand.SubmitSyntheticTest, PrintRequest: _request, UserConfirmed: true)); return;
        }
        // Same ID only. An interrupted IPC response never generates a second intent.
        await SendAsync(_confirmed && _receipt?.Status == PrintJobStatus.Queued
            ? new(LocalCommand.SubmitSyntheticTest, PrintRequest: _request, UserConfirmed: true)
            : new(LocalCommand.ObserveSyntheticTest, JobId: _request.JobId));
    }
    private async Task<SyntheticPrintReply?> SendAsync(LocalRequest request)
    {
        if (_busy) return null; _busy = true; Buttons();
        try
        {
            var response = await _client.SendAsync(request); _diagnostics = response.PrintDiagnostics;
            if (response.PrintReply is { } reply) { ShowReceipt(reply); return reply; }
            _status.Text = "No se pudo leer el registro local. No cree otra intención hasta comprobar el estado."; return null;
        }
        catch (Exception) { _status.Text = "Comunicación interrumpida. El resultado puede ser incierto: consulte el mismo trabajo, no cree otra copia."; return null; }
        finally { _busy = false; Buttons(); }
    }
    private void ShowReceipt(SyntheticPrintReply reply)
    {
        if (reply.Receipt is not null) _receipt = reply.Receipt;
        _status.Text = _receipt is null ? PrintMessages.Error(reply.Error) : $"Trabajo: {_receipt.Job.Id.Value}\n{PrintMessages.State(_receipt.Status)}\n"
            + $"Spooler ID: {_receipt.SpoolJobId?.ToString() ?? "—"} · Estado Windows: {_receipt.SpoolState}\n"
            + PrintMessages.Error(reply.Error != PrintFailure.None ? reply.Error : _receipt.Error);
    }
    private bool Confirm(string printer, SyntheticPageFormat format)
    {
        using var dialog = new Form { Text = "Confirmar prueba de impresión", Size = new Size(570, 320), StartPosition = FormStartPosition.CenterParent, MinimizeBox = false, MaximizeBox = false, FormBorderStyle = FormBorderStyle.FixedDialog };
        var text = new Label { Dock = DockStyle.Fill, Padding = new Padding(20), Text = $"Impresora: {printer}\n\nFormato: {SyntheticPaper.Label(format)}\n\nDocumento: Página sintética de prueba\nNo contiene datos de pacientes. Una página, una copia.\nVerifique que el papel indicado esté cargado." };
        var actions = new FlowLayoutPanel { Dock = DockStyle.Bottom, Height = 60, Padding = new Padding(18, 8, 8, 8), FlowDirection = FlowDirection.RightToLeft };
        var cancel = new Button { Text = "Cancelar", AutoSize = true, DialogResult = DialogResult.Cancel };
        var print = new Button { Text = "Imprimir", AutoSize = true, DialogResult = DialogResult.OK };
        actions.Controls.AddRange([cancel, print]); dialog.Controls.Add(text); dialog.Controls.Add(actions); dialog.CancelButton = cancel;
        dialog.Shown += (_, _) => cancel.Focus(); return dialog.ShowDialog(this) == DialogResult.OK;
    }
    private static string Flag(bool? flag) => flag is null ? "No informado" : flag.Value ? "Sí" : "No";
    private sealed record PrinterChoice(PrinterDevice Printer)
    { public override string ToString() => Printer.Name + (Printer.IsDefault ? " · predeterminada" : "") + (Printer.IsVirtual ? " · virtual" : ""); }
    private sealed record FormatChoice(SyntheticPageFormat Format, bool Supported)
    { public override string ToString() => SyntheticPaper.Label(Format) + (Supported ? "" : " · no anunciado por el driver"); }
}
