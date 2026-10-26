import { after, afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createServer } from "vite";
import { createBrowser } from "./browser.mjs";

const { dom } = createBrowser();
const { createElement: h, act } = await import("react");
const { createRoot } = await import("react-dom/client");
const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: "custom",
  define: { "import.meta.env.VITE_CLINICAL_FORM_DESIGNER_ENABLED": JSON.stringify("true") },
  optimizeDeps: { noDiscovery: true, include: [] } });
const { default: ClinicalDocumentsPanel } = await server.ssrLoadModule("/src/components/clinicalDocuments/ClinicalDocumentsPanel.tsx");
const { default: PhysicalExamSection } = await server.ssrLoadModule("/src/components/clinicalDocuments/PhysicalExamSection.tsx");
const { api } = await server.ssrLoadModule("/src/services/api.ts");
const originalAdapter = api.defaults.adapter;
const host = document.getElementById("root");
const doctor = { id: 2, full_name: "Médico QA", roles: ["doctor"], permissions: ["patients:access", "clinical:access", "clinical_documents:create", "clinical_documents:view", "clinical_documents:prepare", "clinical_documents:edit_clinical", "clinical_documents:sign"] };
const secretary = { id: 3, roles: ["secretary"], permissions: ["patients:access", "clinical_documents:view"] };
const context = { centerId: 4, doctorId: 2, appointmentId: 8, clinicalHistoryId: 10 };
let root, docs, calls, scopeResponse, secretaryCapabilities;
const result = (config, data) => ({ data, status: 200, statusText: "OK", headers: {}, config });
const full = (kind, status = "draft") => ({ kind, id: kind === "preoperative" ? 11 : 12, patient_id: 7, doctor_id: 2, center_id: 4,
  appointment_id: 8, clinical_history_id: 10, document_date: "2026-10-13", status, revision: 0,
  created_by_user_id: 3, created_by_name: "Secretaria QA", last_updated_by_user_id: 3, signed_by_user_id: null,
  signed_at: null, created_at: "2026-10-13T10:00:00", updated_at: "2026-10-13T10:00:00",
  patient_name: "Paciente QA", doctor_name: "Médico QA", center_name: "Centro QA", values: {},
  patient_profile: { patient_name: "Paciente QA", date_of_birth: "1990-01-01", phone: "8090000000", document_number: null, insurance_company: null } });
const versionedDefinition = { appearance: { show_logo: false, logo_data: null, doctor_heading: "Médico QA", specialty_heading: "Cardiología", center_heading: "Centro QA", header: "Evaluación médica preoperatoria", subtitle: "", footer: "", primary_color: "#24415c", font: "Helvetica", font_size: 9, density: "normal" }, pages: [
  { page_number: 1, sort_order: 1, title: "Evaluación", orientation: "portrait", page_size: "Letter", margins: { top: 12, bottom: 12, left: 12, right: 12 }, sections: [
    { key: "s1", title: "Síntomas", sort_order: 1, printable: true, fields: [
      { key: "dolor", label: "Dolor", type: "yes_no", required: false, label_uppercase: true, placeholder: "", help_text: "", default_value: null, unit: "", options: [], width: 12, row: 1, column: 1, colspan: 12, sort_order: 1, visible: true, printable: true, read_only: false, editable_by: "clinical", data_binding: null, validation: {} },
      { key: "conclusion", label: "Conclusión", type: "text_long", required: false, label_uppercase: true, placeholder: "", help_text: "", default_value: null, unit: "", options: [], width: 12, row: 2, column: 1, colspan: 12, sort_order: 2, visible: true, printable: true, read_only: false, editable_by: "clinical", data_binding: null, validation: {} },
    ] },
  ] },
] };

beforeEach(() => {
  root = createRoot(host); docs = []; calls = [];
  secretaryCapabilities = { start_preoperative: true, start_physical_exam: true, prepare_administrative: true };
  scopeResponse = { centers: [{ id: 4, name: "Centro QA" }], doctors: [{ id: 2, full_name: "Médico QA", center_ids: [4] }] };
  api.defaults.adapter = async (config) => {
    calls.push(config);
    if (config.url === "/clinical-forms/capabilities/me") return result(config, secretaryCapabilities);
    if (config.url === "/clinical-documents/patients/7") return result(config, docs.map(({ values, patient_profile, ...metadata }) => ({ ...metadata, values: null, patient_profile: null })));
    if (config.url === "/appointments/scope-options") return result(config, scopeResponse);
    if (config.url === "/clinical-documents/preoperative" && config.method === "post" || config.url === "/clinical-documents/physical_exam" && config.method === "post") {
      const kind = config.url.split("/").at(-1);
      const existing = docs.find((item) => item.kind === kind && ["draft", "pending_evaluation"].includes(item.status));
      const row = existing ?? full(kind);
      if (!docs.includes(row)) docs.push(row);
      return { ...result(config, row), status: existing ? 200 : 201 };
    }
    const parts = config.url.split("/");
    const row = docs.find((item) => item.kind === parts[2] && item.id === Number(parts[3]));
    if (!row) throw new Error(`Unexpected request: ${config.url}`);
    if (parts[4] === "link-context") {
      const body = JSON.parse(config.data);
      Object.assign(row, { appointment_id: body.appointment_id, clinical_history_id: body.clinical_history_id, revision: row.revision + 1 });
      return result(config, { ...row });
    }
    if (parts[4] === "pdf") return result(config, new Blob(["%PDF-QA"], { type: "application/pdf" }));
    if (config.method === "get") return result(config, row);
    const body = JSON.parse(config.data);
    if (config.method === "put") Object.assign(row, { values: { ...row.values, ...body.values }, revision: row.revision + 1 });
    else if (config.method === "post") Object.assign(row, { status: { submit: "pending_evaluation", complete: "completed", sign: "signed" }[parts[4]], revision: row.revision + 1 });
    return result(config, { ...row });
  };
});
afterEach(async () => { await act(async () => root.unmount()); api.defaults.adapter = originalAdapter; });
after(async () => { await server.close(); dom.window.close(); });
async function settle() { for (let index = 0; index < 4; index++) await act(async () => { await Promise.resolve(); }); }
async function click(label) { const button = [...host.querySelectorAll("button")].find((item) => item.textContent.includes(label)); assert.ok(button, label); await act(async () => button.click()); await settle(); }
async function enter(label, value) { const field = [...host.querySelectorAll("label")].find((item) => item.textContent.trim().startsWith(label)); assert.ok(field, label); const area = field.querySelector("textarea"); await act(async () => { Object.getOwnPropertyDescriptor(dom.window.HTMLTextAreaElement.prototype, "value").set.call(area, value); area.dispatchEvent(new dom.window.Event("input", { bubbles: true })); }); }

test("mismo panel crea evaluación y examen independientes desde Consulta; reutiliza examen físico y guarda borrador", async () => {
  await act(async () => root.render(h(ClinicalDocumentsPanel, { patientId: 7, patientName: "Paciente QA", user: doctor, context })));
  await settle();
  assert.match(host.textContent, /Nueva evaluación preoperatoria/);
  await click("Nueva evaluación preoperatoria");
  assert.equal(docs.length, 1);
  assert.match(host.textContent, /Hepatitis/);
  assert.match(host.textContent, /Glicemia/);
  assert.match(host.textContent, /Creatinina/);
  assert.match(host.textContent, /PCB/);
  assert.match(host.textContent, /IVY/);
  await enter("Hepatitis", "No");
  await click("Guardar borrador");
  assert.equal(docs[0].values.hepatitis, "No");
  assert.equal(calls.find((item) => item.url === "/clinical-documents/preoperative" && item.method === "post") !== undefined, true);
  await click("Nueva evaluación preoperatoria");
  assert.equal(docs.length, 1, "crear de nuevo continúa el borrador del contexto");
  assert.match(host.textContent, /Existe una evaluación pendiente/);
  await click("Nuevo examen físico");
  assert.equal(docs.length, 2);
  assert.ok(host.querySelector("[data-physical-exam-section]"));
  assert.doesNotMatch(host.textContent, /Glicemia/);
  assert.equal(docs[1].kind, "physical_exam");
});

test("secretaría ve estado y datos administrativos, no campos clínicos ni firma", async () => {
  docs.push({ ...full("preoperative"), values: { procedimiento: "Cirugía QA" }, patient_profile: null });
  await act(async () => root.render(h(ClinicalDocumentsPanel, { patientId: 7, patientName: "Paciente QA", user: secretary, context })));
  await settle(); await click("Continuar");
  assert.match(host.textContent, /Procedimiento previsto/);
  assert.equal(host.querySelector("[data-physical-exam-section]"), null);
  assert.doesNotMatch(host.textContent, /Firmar/);
  assert.doesNotMatch(host.textContent, /Descargar PDF/);
  await enter("Procedimiento previsto", "Procedimiento QA revisado");
  await click("Guardar borrador");
  assert.equal(docs[0].values.procedimiento, "Procedimiento QA revisado");
});

test("secretaría sin capacidades conserva lectura y no puede crear ni guardar documentos", async () => {
  secretaryCapabilities = { start_preoperative: false, start_physical_exam: false, prepare_administrative: false };
  docs.push({ ...full("preoperative"), values: { procedimiento: "Cirugía QA" }, patient_profile: null });
  await act(async () => root.render(h(ClinicalDocumentsPanel, { patientId: 7, patientName: "Paciente QA", user: secretary, context })));
  await settle(); await click("Continuar");
  assert.ok(calls.some(item => item.url === "/clinical-forms/capabilities/me"));
  assert.doesNotMatch(host.textContent, /Nueva evaluación|Nuevo examen|Guardar borrador|Enviar a evaluación|Completar|Firmar|Descargar PDF/);
  assert.ok([...host.querySelectorAll("textarea")].every(item => item.disabled));
  assert.equal(calls.filter(item => ["post", "put"].includes(item.method)).length, 0);
});

test("PhysicalExamSection reutilizable presenta PCB e IVY sin reinterpretarlos", async () => {
  await act(async () => root.render(h(PhysicalExamSection, { values: { pcb: "valor QA" }, onChange() {} })));
  assert.match(host.textContent, /PCB/); assert.match(host.textContent, /IVY/);
  assert.equal([...host.querySelectorAll("label")].find((item) => item.textContent.startsWith("PCB")).querySelector("textarea").value, "valor QA");
});

test("desde Paciente selecciona centro y médico, conserva prueba de selección y enlaza al paciente", async () => {
  await act(async () => root.render(h(ClinicalDocumentsPanel, { patientId: 7, patientName: "Paciente QA", user: secretary,
    patientIdentity: { dateOfBirth: "1990-01-01", documentNumber: "00112345674", phone: "8095551234" }, patientSelectionToken: "proof-qa" })));
  await settle();
  assert.match(host.textContent, /Confirmar paciente/);
  assert.match(host.textContent, /•••5674/);
  assert.doesNotMatch(host.textContent, /00112345674/);
  assert.equal([...host.querySelectorAll("button")].find((item) => item.textContent.includes("Nuevo examen físico")).disabled, true);
  await click("Confirmar paciente");
  const [center, physician] = host.querySelectorAll("select");
  await act(async () => { center.value = "4"; center.dispatchEvent(new dom.window.Event("change", { bubbles: true })); });
  await act(async () => { physician.value = "2"; physician.dispatchEvent(new dom.window.Event("change", { bubbles: true })); });
  await click("Nuevo examen físico");
  const post = calls.find((item) => item.url === "/clinical-documents/physical_exam" && item.method === "post");
  assert.ok(post);
  const body = JSON.parse(post.data);
  assert.equal(body.patient_id, 7);
  assert.equal(body.center_id, 4);
  assert.equal(body.doctor_id, 2);
  assert.equal(body.appointment_id, null);
  assert.equal(body.patient_selection_token, "proof-qa");
  assert.equal(host.querySelector('[data-clinical-document-form]')?.textContent.includes("Paciente QA"), true);
});

test("médico autenticado queda fijado y su único centro se resuelve sin selectores", async () => {
  await act(async () => root.render(h(ClinicalDocumentsPanel, { patientId: 7, patientName: "Paciente QA", user: doctor,
    patientIdentity: { dateOfBirth: "1990-01-01" } })));
  await settle();
  assert.match(host.textContent, /Médico responsable: Médico QA/);
  assert.match(host.textContent, /Centro: Centro QA/);
  assert.equal(host.querySelectorAll("select").length, 0);
  await click("Confirmar paciente");
  await click("Nuevo examen físico");
  const body = JSON.parse(calls.find((item) => item.url === "/clinical-documents/physical_exam" && item.method === "post").data);
  assert.equal(body.doctor_id, doctor.id);
  assert.equal(body.center_id, 4);
});

test("médico con varios centros elige centro, nunca otro médico", async () => {
  scopeResponse = { centers: [{ id: 4, name: "Centro QA" }, { id: 5, name: "Centro B" }],
    doctors: [{ id: 2, full_name: "Médico QA", center_ids: [4, 5] }, { id: 9, full_name: "Otro médico", center_ids: [5] }] };
  await act(async () => root.render(h(ClinicalDocumentsPanel, { patientId: 7, patientName: "Paciente QA", user: doctor,
    patientIdentity: { dateOfBirth: "1990-01-01" } })));
  await settle();
  assert.equal(host.querySelectorAll("select").length, 1);
  assert.match(host.textContent, /Médico responsable: Médico QA/);
  assert.doesNotMatch(host.querySelector("select").textContent, /Otro médico/);
});

test("Consulta ofrece vincular borrador preparado y no reutiliza otro contexto", async () => {
  docs.push({ ...full("preoperative"), appointment_id: null, clinical_history_id: null });
  await act(async () => root.render(h(ClinicalDocumentsPanel, { patientId: 7, patientName: "Paciente QA", user: doctor, context })));
  await settle();
  assert.match(host.textContent, /Existe un documento preparado/);
  assert.match(host.textContent, /No hay documentos clínicos en este contexto/);
  await click("Continuar Evaluación médica preoperatoria");
  assert.equal(docs.length, 1);
  assert.equal(docs[0].appointment_id, 8);
  assert.ok(calls.some((item) => item.url === "/clinical-documents/preoperative/11/link-context"));
});

test("varios borradores preparados requieren elección explícita; secretaría solo ve médicos de su alcance", async () => {
  docs.push({ ...full("preoperative"), appointment_id: null, clinical_history_id: null });
  docs.push({ ...full("physical_exam"), appointment_id: null, clinical_history_id: null });
  await act(async () => root.render(h(ClinicalDocumentsPanel, { patientId: 7, patientName: "Paciente QA", user: doctor, context })));
  await settle();
  assert.match(host.textContent, /Existen varios documentos preparados/);
  assert.equal(calls.filter((item) => item.url.includes("link-context")).length, 0);
  await act(async () => root.unmount());
  root = createRoot(host);
  docs = [];
  scopeResponse = { centers: [{ id: 4, name: "Centro QA" }, { id: 5, name: "Centro no autorizado" }],
    doctors: [{ id: 2, full_name: "Médico QA", center_ids: [4] }] };
  await act(async () => root.render(h(ClinicalDocumentsPanel, { patientId: 7, patientName: "Paciente QA", user: secretary,
    patientIdentity: { dateOfBirth: "1990-01-01" } })));
  await settle();
  assert.match(host.querySelector("select").textContent, /Centro QA/);
  assert.doesNotMatch(host.querySelector("select").textContent, /Centro no autorizado/);
});

test("firmado conserva historial y no presenta controles de edición", async () => {
  docs.push({ ...full("physical_exam", "signed"), values: { ta: "120/80" }, signed_by_user_id: 2, signed_at: "2026-10-13T12:00:00" });
  await act(async () => root.render(h(ClinicalDocumentsPanel, { patientId: 7, patientName: "Paciente QA", user: doctor, context })));
  await settle(); await click("Ver");
  assert.match(host.textContent, /Firmada/);
  assert.match(host.textContent, /Documento de solo lectura/);
  assert.equal(host.querySelector("[data-physical-exam-section] textarea").disabled, true);
  assert.doesNotMatch(host.textContent, /Guardar borrador/);
});

test("evaluación versionada abre hoja modal con scroll interno, acciones intactas y Sí/No accesibles", async () => {
  docs.push({ ...full("preoperative"), template_source: "versioned", template_definition: versionedDefinition });
  await act(async () => root.render(h(ClinicalDocumentsPanel, { patientId: 7, patientName: "Paciente QA", user: doctor, context })));
  await settle(); await click("Continuar");
  const dialog = host.querySelector('[data-clinical-document-form][role="dialog"]');
  assert.ok(dialog);
  assert.equal(dialog.getAttribute("aria-modal"), "true");
  assert.ok(dialog.querySelector(".clinical-document-overlay") === null);
  assert.ok(dialog.classList.contains("clinical-document-overlay"));
  const body = dialog.querySelector("[data-clinical-document-scroll]");
  const footer = dialog.querySelector(".clinical-document-footer");
  assert.ok(body); assert.ok(footer);
  assert.equal(body.contains(footer), false, "acciones permanecen fuera del área desplazable");
  assert.match(dialog.textContent, /Centro QA/);
  assert.match(dialog.textContent, /Cardiología/);
  assert.ok(body.querySelector(".clinical-form-paper"));
  assert.ok(body.querySelector(".clinical-form-section-title"));
  const yes = dialog.querySelector('.clinical-binary-option--yes');
  const no = dialog.querySelector('.clinical-binary-option--no');
  assert.equal(yes.getAttribute("aria-pressed"), "false");
  assert.equal(no.getAttribute("aria-pressed"), "false");
  await act(async () => yes.click());
  assert.equal(yes.getAttribute("aria-pressed"), "true");
  assert.equal(no.getAttribute("aria-pressed"), "false");
  await click("Guardar borrador");
  assert.equal(docs[0].values.dolor, "yes");
  assert.ok(footer.textContent.includes("Enviar a evaluación"));
  assert.ok(footer.textContent.includes("Completar"));
  assert.ok(footer.textContent.includes("Descargar PDF"));
  const modalCss = await readFile(new URL("../src/components/clinicalDocuments/clinicalDocumentsPanel.css", import.meta.url), "utf8");
  assert.match(modalCss, /\.clinical-document-scroll\s*\{[^}]*overflow-y:\s*auto/s);
  assert.match(modalCss, /@media \(max-width: 639px\)/);
});

test("evaluación preoperatoria histórica también abre modal sin alterar sus campos", async () => {
  docs.push(full("preoperative"));
  await act(async () => root.render(h(ClinicalDocumentsPanel, { patientId: 7, patientName: "Paciente QA", user: doctor, context })));
  await settle(); await click("Continuar");
  assert.ok(host.querySelector('[data-clinical-document-form][role="dialog"]'));
  assert.match(host.textContent, /Hepatitis/);
  assert.match(host.textContent, /Creatinina/);
});

test("borrador versionado se reabre y avanza por evaluación, completado, firma y PDF sin duplicarse", async () => {
  docs.push({ ...full("preoperative"), template_source: "versioned", template_version_id: 5,
    template_definition: versionedDefinition });
  await act(async () => root.render(h(ClinicalDocumentsPanel, { patientId: 7, patientName: "Paciente QA", user: doctor, context })));
  await settle(); await click("Continuar");
  await act(async () => host.querySelector('.clinical-binary-option--no').click());
  await enter("CONCLUSIÓN", "Texto clínico sintético");
  await click("Guardar borrador");
  assert.equal(docs[0].values.dolor, "no");
  assert.equal(docs[0].values.conclusion, "Texto clínico sintético");
  await click("Cerrar documento");
  await click("Continuar");
  assert.equal(host.querySelector('.clinical-binary-option--no').getAttribute("aria-pressed"), "true");
  assert.equal(host.querySelector('textarea').value, "Texto clínico sintético");
  await click("Enviar a evaluación");
  assert.match(host.textContent, /Pendiente de evaluación/);
  await click("Completar");
  assert.match(host.textContent, /Completada/);
  await click("Firmar");
  assert.match(host.textContent, /Firmada/);
  assert.equal(host.querySelector('.clinical-binary-option--no').disabled, true);
  assert.equal(docs.length, 1);
  const originalClick = dom.window.HTMLAnchorElement.prototype.click;
  let downloaded = false;
  dom.window.HTMLAnchorElement.prototype.click = function () { downloaded = true; };
  try {
    await click("Descargar PDF");
  } finally {
    dom.window.HTMLAnchorElement.prototype.click = originalClick;
  }
  assert.equal(downloaded, true);
  assert.ok(calls.some((item) => item.url === "/clinical-documents/preoperative/11/pdf"));
});
