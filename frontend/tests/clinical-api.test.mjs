import { after, afterEach, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";

const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: "custom", optimizeDeps: { noDiscovery: true, include: [] } });
const { api } = await server.ssrLoadModule("/src/services/api.ts");
const { clinicalApi, clearClinicalCatalogCacheForTests } = await server.ssrLoadModule("/src/services/clinicalApi.ts");
const originalAdapter = api.defaults.adapter;
let calls = [];
let failCatalog = false;

function ok(config, data) { return { data, status: 200, statusText: "OK", headers: {}, config }; }
afterEach(() => { api.defaults.adapter = originalAdapter; clearClinicalCatalogCacheForTests(); });
after(async () => { await server.close(); });

test("cliente clínico conserva rutas, revisión, 409 y signal de lectura", async () => {
  const signal = new AbortController().signal;
  api.defaults.adapter = async (config) => { calls.push(config); if (config.url === "/clinical-history/9" && config.method === "get") return ok(config, { id: 9, revision: 4 }); const error = new Error("conflicto"); error.response = { status: 409, data: { detail: "Versión obsoleta" } }; throw error; };
  const history = await clinicalApi.getHistory(9, { signal });
  assert.equal(history.revision, 4); assert.equal(calls[0].signal, signal);
  await assert.rejects(clinicalApi.updateHistory(9, { consultation_date: "2026-09-16", reason_for_visit: null, current_illness: null, personal_history: null, family_history: null, allergies: null, current_medications: null, previous_surgeries: null, chronic_conditions: null, habits: null, clinical_notes: null, expected_revision: 4 }), (error) => error.response.status === 409 && error.response.data.detail === "Versión obsoleta");
  assert.equal(JSON.parse(calls.at(-1).data).expected_revision, 4);
});

test("catálogos deduplican, separan scopes y permiten reintento", async () => {
  calls = [];
  api.defaults.adapter = async (config) => { calls.push(config); if (failCatalog) { failCatalog = false; throw new Error("fallo temporal"); } return ok(config, []); };
  await Promise.all([clinicalApi.getStudyCatalog(1), clinicalApi.getStudyCatalog(1)]);
  await clinicalApi.getStudyCatalog(2); await clinicalApi.getStudyCatalog(1, true);
  assert.equal(calls.length, 3);
  clearClinicalCatalogCacheForTests(); failCatalog = true;
  await assert.rejects(clinicalApi.getLaboratoryCatalog());
  await clinicalApi.getLaboratoryCatalog();
  assert.equal(calls.filter((item) => item.url === "/laboratory-tests").length, 2);
});
