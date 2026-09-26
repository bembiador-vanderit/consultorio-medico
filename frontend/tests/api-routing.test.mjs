import { after, before, test } from "node:test";
import assert from "node:assert/strict";
import { createServer as createHttpServer } from "node:http";
import { createServer } from "vite";
import { createBrowser } from "./browser.mjs";

const { dom } = createBrowser();
let backend, frontend, backendPort, frontendPort, received;
const previousTarget = process.env.API_PROXY_TARGET;
before(async () => {
  backend = createHttpServer((request, response) => {
    received = { url: request.url, authorization: request.headers.authorization, cookie: request.headers.cookie };
    response.setHeader("content-type", "application/json");
    response.setHeader("set-cookie", "consultorio_refresh=fixture-only; Path=/api/v1/auth; HttpOnly; SameSite=Lax");
    response.end(JSON.stringify({ ok: true }));
  });
  await new Promise(resolve => backend.listen(0, "127.0.0.1", resolve));
  backendPort = backend.address().port;
  process.env.API_PROXY_TARGET = `http://127.0.0.1:${backendPort}`;
  frontend = await createServer({ server: { host: "0.0.0.0", port: 0, ws: false }, optimizeDeps: { noDiscovery: true, include: [] } });
  await frontend.listen(); frontendPort = frontend.httpServer.address().port;
});
after(async () => {
  await frontend?.close();
  if (backend) { backend.closeAllConnections(); await new Promise(resolve => backend.close(resolve)); }
  if (previousTarget === undefined) delete process.env.API_PROXY_TARGET; else process.env.API_PROXY_TARGET = previousTarget;
  dom.window.close();
});

test("API uses current browser origin by default and keeps credential transport", async () => {
  const { api } = await frontend.ssrLoadModule("/src/services/api.ts");
  assert.equal(api.defaults.baseURL, "/api/v1"); assert.equal(api.defaults.withCredentials, true);
});
for (const hostname of ["localhost", "127.0.0.1"]) {
  test(`same-origin proxy forwards API path, query, auth and refresh cookies through ${hostname}`, async () => {
    const response = await fetch(`http://${hostname}:${frontendPort}/api/v1/patients?query=Ficticio&limit=100`, {
      headers: { authorization: "Bearer fixture-only", cookie: "consultorio_refresh=fixture-only" },
    });
    assert.equal(response.status, 200); assert.deepEqual(await response.json(), { ok: true });
    assert.equal(received.url, "/api/v1/patients?query=Ficticio&limit=100");
    assert.equal(received.authorization, "Bearer fixture-only"); assert.equal(received.cookie, "consultorio_refresh=fixture-only");
    assert.match(response.headers.get("set-cookie"), /HttpOnly; SameSite=Lax/);
    assert.equal(response.headers.get("access-control-allow-origin"), null);
  });
}
test("explicit VITE_API_URL override remains supported", async () => {
  const configured = await createServer({ server: { middlewareMode: true, ws: false }, define: { "import.meta.env.VITE_API_URL": JSON.stringify("https://api.example.test/api/v1") }, optimizeDeps: { noDiscovery: true, include: [] } });
  try { const { api } = await configured.ssrLoadModule("/src/services/api.ts"); assert.equal(api.defaults.baseURL, "https://api.example.test/api/v1"); }
  finally { await configured.close(); }
});
