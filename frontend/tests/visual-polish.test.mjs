import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const read = path => readFile(new URL(`../src/${path}`, import.meta.url), "utf8");

test("five appointment states share one palette across cards, badges and legend", async () => {
  const css = await read("components/agenda/appointment-status.css");
  const expected = { scheduled:["#1684E8","#E4F1FF","#164468"], confirmed:["#20A83A","#E1F6E6","#1C5B2B"], completed:["#008C95","#D7F3F1","#075B61"], cancelled:["#EE4E69","#FCE8EC","#803442"], no_show:["#475569","#DCE2EA","#263445"] };
  for (const [status,colors] of Object.entries(expected)) {
    const rule = css.split("\n").find(line=>line.startsWith(`.appointment-status--${status},`));
    assert.ok(rule, status);
    for (const selector of ["agenda-appointment-card", "agenda-week-appointment-card", "agenda-status-legend-item"]) assert.ok(rule.includes(`.${selector}--${status}`));
    for (const color of colors) assert.ok(rule.includes(color));
    const rgb = hex => hex.slice(1).match(/../g).map(value=>parseInt(value,16)/255).map(value=>value<=.04045?value/12.92:((value+.055)/1.055)**2.4);
    const luminance = hex => rgb(hex).reduce((sum,value,index)=>sum+value*[.2126,.7152,.0722][index],0);
    assert.ok((luminance(colors[1])+.05)/(luminance(colors[2])+.05)>=4.5, `${status} text contrast`);
  }
  assert.match(css, /\.atlas-badge\[class\*="appointment-status--"\]/);
  const reports = await read("pages/AppointmentReports.tsx");
  assert.match(reports, /<AppointmentStatusBadge status=\{a.status\} \/>/);
  const oldCss = await read("index.css");
  assert.match(oldCss, /@import "\.\/components\/agenda\/appointment-status.css"/);
  assert.doesNotMatch(oldCss, /--completed\s*\{|--no_show\s*\{/);
});

test("desktop patient detail reserves 38 percent with bounded tracks and long text wrapping", async () => {
  const css = await read("pages/patients.css");
  assert.match(css, /grid-template-columns:minmax\(0,1.65fr\) minmax\(18rem,1fr\)/);
  assert.match(css, /\.patients-identity h3\s*\{[^}]*-webkit-line-clamp:3/);
  assert.match(css, /\.patients-facts dd\s*\{[^}]*overflow-wrap:anywhere/);
  assert.match(css, /\.patients-contact \.patients-facts\s*\{/);
  assert.match(css, /\.patients-master,.patients-detail\s*\{[^}]*min-width:0/);
  assert.match(css, /max-width:1023px[^\n]*grid-template-columns:minmax\(0,1fr\)/);
  assert.match(css, /\.patients-detail-scroll\s*\{[^}]*display:flex;[^}]*overflow:hidden/);
  assert.match(css, /\.patients-detail-fixed\s*\{[^}]*flex:0 0 auto;[^}]*flex-shrink:0/);
  assert.match(css, /\.patients-detail-body\s*\{[^}]*flex:1 1 auto;[^}]*min-height:0;[^}]*overflow-y:auto/);
  assert.doesNotMatch(css, /patients-detail-summary/);
});

test("mobile heading stays unboxed while patient actions retain 44px and clinical hierarchy", async () => {
  const foundation = await read("ui/foundation.css");
  assert.match(foundation, /\.atlas-dialog-header h2\[tabindex="-1"\]:focus-visible\s*\{\s*outline:none/);
  const css = await read("pages/patients.css");
  assert.match(css, /patients-quick-actions>\.atlas-button\s*\{[^}]*min-height:44px/);
  assert.match(css, /patients-action--schedule,.patients-quick-actions>\.patients-action--history\s*\{\s*grid-column:1\/-1/);
  assert.match(css, /patients-action--insurance\s*\{[^}]*--atlas-violet-surface/);
  assert.match(css, /patients-action--history\s*\{[^}]*--atlas-success/);
  assert.match(css, /\.atlas-dialog--drawer \.patients-quick-actions\s*\{[^}]*width:100%;[^}]*margin-inline:0;[^}]*grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(css, /\.atlas-dialog--drawer \.patients-quick-actions>\.atlas-button\s*\{[^}]*width:100%;[^}]*min-width:0;[^}]*margin:0;[^}]*justify-self:stretch/);
  assert.match(css, /\.atlas-dialog--drawer \.patients-action--schedule,.atlas-dialog--drawer \.patients-action--history\s*\{\s*grid-column:auto/);
  assert.match(css, /max-width:359px[^}]*\.atlas-dialog--drawer \.patients-quick-actions\s*\{[^}]*grid-template-columns:minmax\(0,1fr\)/);
  const agenda = await read("index.css");
  assert.match(agenda, /\.agenda-event-status\s*\{[^}]*font-size:clamp\(\.8125rem,\.85vw,\.9rem\);[^}]*font-weight:700;[^}]*line-height:1\.2/);
  assert.match(agenda, /grid-template-rows:repeat\(3,minmax\(0,1fr\)\) auto/);
});

test("patient registration uses the approved wide two-folder layout without obsolete tabs", async () => {
  const css = await read("pages/patients.css");
  const foundation = await read("ui/foundation.css");
  assert.match(css, /\.atlas-dialog:has\(\.patient-form\)\s*\{[^}]*width:min\(96rem,calc\(100vw - 2rem\)\);[^}]*max-height:calc\(100dvh - 2rem\)/);
  assert.match(css, /\.patient-form-columns\s*\{[^}]*grid-template-columns:minmax\(0,1fr\)/);
  assert.match(css, /@media \(min-width:1180px\)[\s\S]*?\.patient-form-columns\s*\{\s*grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(css, /\.patient-form-contact-email\s*\{\s*grid-column:1\/-1/);
  assert.match(css, /@media \(min-width:1366px\)[\s\S]*?patient-form-contact-section \.atlas-form-grid,.patient-form-contacts-section \.atlas-form-grid\s*\{\s*grid-template-columns:repeat\(3,minmax\(0,1fr\)\)/);
  assert.match(css, /@media \(max-width:839px\)[\s\S]*?\.patient-form-columns\s*\{\s*grid-template-columns:minmax\(0,1fr\)/);
  assert.match(foundation, /\.atlas-dialog-body\s*\{[^}]*overflow-y:\s*auto/);
  assert.doesNotMatch(css, /patient-form-tabs|patient-form-tab|section\[hidden\]/);
});

test("Vite watches the Windows bind mount so transformed modules cannot become stale", async () => {
  const vite = await readFile(new URL("../vite.config.ts", import.meta.url), "utf8");
  assert.match(vite, /watch:\s*\{\s*usePolling:\s*true,\s*interval:\s*300\s*\}/);
});

test("desktop dashboard scales fluidly without changing compact mobile navigation", async () => {
  const css = await read("pages/dashboard.css");
  assert.match(css, /@media \(min-width:1280px\)/);
  assert.match(css, /min-height:clamp\(76px,[^;]*100px\)/);
  assert.match(css, /max-height:clamp\(21rem,35vh,29rem\)/);
  assert.match(css, /@media \(max-width:639px\)/);
  assert.match(css, /grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
});
