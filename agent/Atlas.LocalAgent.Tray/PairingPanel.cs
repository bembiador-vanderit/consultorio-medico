using Atlas.LocalAgent.Core;

namespace Atlas.LocalAgent.Tray;

internal sealed class PairingPanel : UserControl
{
    private readonly TextBox _endpoint = new() { Width = 460, AccessibleName = "Dirección HTTPS de Atlas", MaxLength = 500 };
    private readonly TextBox _code = new() { Width = 330, AccessibleName = "Código temporal", UseSystemPasswordChar = true, MaxLength = 40 };
    private readonly CheckBox _dev = new() { AutoSize = true, Text = "Desarrollo explícito: permitir HTTP solo en localhost" };
    private readonly Button _pair = new() { AutoSize = true, Text = "Vincular con Atlas" };
    private readonly Button _rotate = new() { AutoSize = true, Text = "Renovar credencial" };
    private readonly Label _result = new() { AutoSize = true, MaximumSize = new Size(700, 0), Text = "Sin vincular. Genere un código desde Administración → Agentes y dispositivos." };
    public PairingPanel(LocalAgentClient client)
    {
        Dock = DockStyle.Fill;
        var layout = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, WrapContents = false, AutoScroll = true, Padding = new Padding(20) };
        layout.Controls.AddRange([new Label { AutoSize = true, Text = "Vinculación saliente segura; no envía documentos ni habilita impresión remota." },
            new Label { AutoSize = true, Text = "Atlas HTTPS (sin rutas, usuario o contraseña)" }, _endpoint,
            new Label { AutoSize = true, Text = "Código temporal de un solo uso" }, _code, _dev, _pair, _rotate, _result]);
        Controls.Add(layout);
        _pair.Click += async (_, _) => await SendAsync(new(LocalCommand.PairWithAtlas,
            Pairing: new(_endpoint.Text.Trim(), _code.Text.Trim().ToUpperInvariant(), _dev.Checked)));
        _rotate.Click += async (_, _) =>
        {
            if (MessageBox.Show(this, "Se invalidará la credencial anterior. ¿Renovar?", "Atlas", MessageBoxButtons.OKCancel, MessageBoxIcon.Question) == DialogResult.OK)
                await SendAsync(new(LocalCommand.RotateCredential));
        };
        async Task SendAsync(LocalRequest request)
        {
            _pair.Enabled = _rotate.Enabled = false;
            try
            {
                var response = await client.SendAsync(request);
                _result.Text = response.Registry is { } status ? $"{status.State} · {status.Code}\nOrganización: {status.Association.OrganizationId ?? "—"} · Centro: {status.Association.CenterId ?? "—"} · Grupo: {status.Association.WorkgroupId ?? "—"}"
                    : "No se pudo vincular. Verifique dirección, código y diagnóstico.";
            }
            catch (Exception) { _result.Text = "Sin respuesta. Consulte el registro administrativo antes de repetir un emparejamiento."; }
            finally { _code.Clear(); _pair.Enabled = _rotate.Enabled = true; }
        }
    }
}
