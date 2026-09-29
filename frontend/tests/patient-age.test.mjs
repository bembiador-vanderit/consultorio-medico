import { after, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "vite";

const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: "custom", optimizeDeps: { noDiscovery: true, include: [] } });
const { patientAge, pediatricAge, patientAgeLabel, todayDate } = await server.ssrLoadModule("/src/services/patientAge.ts");
after(async () => server.close());

test("calendar age uses the explicit reference, birthdays and leap boundaries", () => {
  assert.equal(patientAge("2000-09-20", "2026-09-19"), 25);
  assert.equal(patientAge("2000-09-20", "2026-09-20"), 26);
  assert.equal(patientAge("2000-09-20", "2001-09-19"), 0);
  assert.equal(patientAge("2000-02-29", "2025-02-28"), 24);
  assert.equal(patientAge("2000-02-29", "2025-03-01"), 25);
  assert.equal(patientAge("2000-02-29", "2024-02-29"), 24);
  assert.equal(patientAge("2000-12-31", "2001-01-01"), 0);
  assert.equal(patientAge("2000-12-31", "2001-12-31"), 1);
  assert.equal(patientAge("0001-01-01", "0002-01-01"), 1);
});
test("invalid, impossible and future calendar dates return no age", () => {
  for (const date of ["", "invalid", "2025-02-29", "2026-04-31", "2026-13-01", "2026-00-01", "2026-01-00", "0000-01-01", "2026-9-01", "2027-01-01"])
    assert.equal(patientAge(date, "2026-09-20"), null, date);
  assert.equal(patientAge("2000-01-01", "invalid"), null);
});
test("pediatric days, complete calendar months and years never persist age", () => {
  assert.deepEqual(pediatricAge("2026-09-20", "2026-09-20"), { value: 0, unit: "days" });
  assert.equal(patientAgeLabel("2026-09-19", "2026-09-20"), "1 día");
  assert.equal(patientAgeLabel("2026-08-21", "2026-09-20"), "30 días");
  assert.equal(patientAgeLabel("2026-08-20", "2026-09-20"), "1 mes");
  assert.equal(patientAgeLabel("2025-09-20", "2026-09-20"), "12 meses");
  assert.equal(patientAgeLabel("2024-09-20", "2026-09-19"), "23 meses");
  assert.equal(patientAgeLabel("2024-09-20", "2026-09-20"), "2 años");
  assert.equal(patientAgeLabel("2026-01-31", "2026-02-28"), "28 días");
  assert.equal(patientAgeLabel("2024-02-29", "2024-03-29"), "1 mes");
  assert.equal(patientAgeLabel("2026-03-07", "2026-03-09"), "2 días");
  assert.equal(patientAgeLabel("bad", "2026-03-09"), "Edad no disponible");
  assert.equal(todayDate(new Date(2026, 8, 20, 23, 59)), "2026-09-20");
});
