import { after, test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

// Reuse the installed Vite TS loader and Node test runner; no extra test dependency.
const server = await createServer({
  server: { middlewareMode: true }, appType: "custom",
  // These are SSR tests: avoid a browser dependency scan racing server.close().
  optimizeDeps: { noDiscovery: true, include: [] },
});
after(() => server.close());
const navigation = await server.ssrLoadModule("/src/navigation/navigation.ts");
const ui = await server.ssrLoadModule("/src/ui/index.ts");
const render = (component, props, children) => renderToStaticMarkup(h(component, props, children));

test("navigation preserves baseline visibility for every combination of roles", () => {
  const roles = ["doctor", "secretary", "admin"];
  for (let mask = 0; mask < 8; mask++) {
    const selected = roles.filter((_, index) => mask & (1 << index));
    const expected = ["dashboard", "appointments", "reports", "patients"];
    if (selected.includes("doctor")) expected.push("follow-ups", "availability");
    if (selected.includes("doctor") || selected.includes("secretary")) expected.push("clinical-coverages");
    if (selected.includes("admin")) expected.push("users", "care-context");
    assert.deepEqual(navigation.getNavigationItems({ roles: selected }).map((item) => item.view), expected);
  }
  assert.deepEqual(navigation.getNavigationItems(null), []);
  assert.equal(navigation.getNavigationItems({ roles: ["unknown"] }).length, 4);
  assert.ok(!navigation.navigationItems.some((item) => item.view === "consultation"));
});

test("future visibility adapter can filter without changing descriptors", () => {
  assert.deepEqual(navigation.getNavigationItems({ roles: ["admin"] }, (item) => item.id === "patients").map((item) => item.id), ["patients"]);
});

test("FormField associates label, required, help and error with each control", () => {
  for (const Control of [ui.Input, ui.Textarea, ui.Select]) {
    const html = render(ui.FormField, { id: "sample", label: "Nombre", required: true, description: "Ayuda", error: "Revisa este campo" }, h(Control, { id: "ignored-override" }));
    assert.match(html, /for="sample"/);
    assert.match(html, /id="sample"/);
    assert.match(html, /aria-describedby="sample-help sample-error"/);
    assert.match(html, /aria-invalid="true"/);
    assert.match(html, /required=""/);
    assert.doesNotMatch(html, /ignored-override/);
  }
});

test("automatically generated field IDs are unique and match labels", () => {
  const html = renderToStaticMarkup(h("div", null, [1, 2].map((key) => h(ui.FormField, { key, label: `Campo ${key}` }, h(ui.Input)))));
  const labels = [...html.matchAll(/for="([^"]+)"/g)].map((match) => match[1]);
  const inputs = [...html.matchAll(/<input[^>]*id="([^"]+)"/g)].map((match) => match[1]);
  assert.equal(new Set(labels).size, 2);
  assert.deepEqual(inputs, labels);
});

test("loading actions cannot submit twice and icon actions retain names", () => {
  const html = render(ui.Button, { loading: true, type: "submit" }, "Guardar");
  assert.match(html, /disabled=""/);
  assert.match(html, /aria-busy="true"/);
  assert.match(html, /Procesando/);
  const icon = render(ui.IconButton, { label: "Agregar", loading: true }, "+");
  assert.match(icon, /aria-label="Agregar"/);
  assert.match(icon, /disabled=""/);
  assert.match(render(ui.Button, {}, "Ejemplo"), /type="button"/);
});

test("choice controls have programmatically associated labels", () => {
  for (const Choice of [ui.Checkbox, ui.Radio]) {
    const html = render(Choice, { id: "choice", label: "Opción", name: "group" });
    assert.match(html, /for="choice"/);
    assert.match(html, /id="choice"/);
  }
});

test("table exposes captions, headers and exclusive loading or empty state", () => {
  const props = { caption: "Ejemplos", columns: [{ id: "name", header: "Nombre", render: (row) => row.name }], rows: [], rowKey: (row) => row.id };
  const empty = render(ui.Table, props);
  assert.match(empty, /<caption>Ejemplos<\/caption>/);
  assert.match(empty, /scope="col"/);
  assert.match(empty, /No hay registros/);
  const loading = render(ui.Table, { ...props, loading: true });
  assert.match(loading, /aria-busy="true"/);
  assert.match(loading, /role="status"/);
  assert.doesNotMatch(loading, /No hay registros/);
});

test("tabs link selected tab and panel without exposing hidden content", () => {
  const html = render(ui.Tabs, { label: "Secciones", items: [{ id: "a", label: "A", content: "Uno" }, { id: "b", label: "B", content: "Dos" }], value: "a", onChange: () => {} });
  assert.match(html, /role="tablist" aria-label="Secciones"/);
  assert.equal((html.match(/aria-selected="true"/g) ?? []).length, 1);
  assert.equal((html.match(/hidden=""/g) ?? []).length, 1);
  const controls = [...html.matchAll(/aria-controls="([^"]+)"/g)].map((match) => match[1]);
  for (const id of controls) assert.ok(html.includes(`id="${id}"`));
});

test("semantic text and focus/control combinations meet contrast thresholds", async () => {
  const css = await readFile(new URL("../src/ui/tokens.css", import.meta.url), "utf8");
  const colors = Object.fromEntries([...css.matchAll(/--atlas-([\w-]+):\s*(#[\da-f]{6});/gi)].map((match) => [match[1], match[2]]));
  const aliases = Object.fromEntries([...css.matchAll(/--atlas-([\w-]+):\s*var\(--atlas-([\w-]+)\);/g)].map((match) => [match[1], match[2]]));
  const color = (name) => colors[name] ?? color(aliases[name]);
  function luminance(hex) {
    return hex.slice(1).match(/../g).map((part) => parseInt(part, 16) / 255).map((v) => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4).reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
  }
  const pairs = [["text-primary", "surface", 4.5], ["text-muted", "surface-secondary", 4.5], ["on-action", "action", 4.5], ["on-action", "danger", 4.5], ["success", "mint", 4.5], ["warning", "amber", 4.5], ["danger", "danger-surface", 4.5], ["info", "sky", 4.5], ["control-border", "surface", 3], ["focus", "surface-secondary", 3]];
  pairs.push(
    ["navigation-text", "navigation-bg", 4.5],
    ["navigation-text-muted", "navigation-bg", 4.5],
    ["navigation-text", "navigation-surface", 4.5],
    ["navigation-text", "navigation-hover", 4.5],
    ["navigation-active-text", "navigation-active", 4.5],
    ["navigation-active-indicator", "navigation-active", 3],
    ["navigation-focus", "navigation-bg", 3],
    ["navigation-focus", "navigation-surface", 3],
    ["navigation-focus", "navigation-hover", 3],
  );
  for (const [fg, bg, min] of pairs) {
    const values = [luminance(color(fg)), luminance(color(bg))].sort((a, b) => b - a);
    const ratio = (values[0] + .05) / (values[1] + .05);
    assert.ok(ratio >= min, `${fg}/${bg}: ${ratio.toFixed(2)} < ${min}`);
  }
});
