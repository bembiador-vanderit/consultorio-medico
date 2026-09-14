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
});

test("mobile heading stays unboxed while patient actions retain 44px and clinical hierarchy", async () => {
  const foundation = await read("ui/foundation.css");
  assert.match(foundation, /\.atlas-dialog-header h2\[tabindex="-1"\]:focus-visible\s*\{\s*outline:none/);
  const css = await read("pages/patients.css");
  assert.match(css, /patients-quick-actions>\.atlas-button\s*\{[^}]*min-height:44px/);
  assert.match(css, /patients-action--schedule,.patients-quick-actions>\.patients-action--history\s*\{\s*grid-column:1\/-1/);
  assert.match(css, /patients-action--insurance\s*\{[^}]*--atlas-violet-surface/);
  assert.match(css, /patients-action--history\s*\{[^}]*--atlas-success/);
});

test("desktop dashboard scales fluidly without changing compact mobile navigation", async () => {
  const css = await read("pages/dashboard.css");
  assert.match(css, /@media \(min-width:1280px\)/);
  assert.match(css, /min-height:clamp\(76px,[^;]*100px\)/);
  assert.match(css, /max-height:clamp\(21rem,35vh,29rem\)/);
  assert.match(css, /@media \(max-width:639px\)/);
  assert.match(css, /grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
});
