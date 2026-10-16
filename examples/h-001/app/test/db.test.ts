import { test } from "node:test";
import assert from "node:assert/strict";
import { claimSlot, createMaster, createSlot, getSlot, openDb } from "../src/db.ts";

const NOW = new Date("2026-10-20T08:00:00Z");
const LATER = "2026-10-20T11:00:00.000Z";

function setup() {
  const db = openDb(":memory:");
  const m = createMaster(db, "Алина", NOW);
  return { db, m };
}

test("S1.2 AC1: окно получает только первый", () => {
  const { db, m } = setup();
  const s = createSlot(db, m.id, LATER, "маникюр", NOW);
  assert.equal(claimSlot(db, s.id, "Оля", "+79000000001", NOW), "ok");
  assert.equal(claimSlot(db, s.id, "Катя", "+79000000002", NOW), "taken");
  assert.equal(getSlot(db, s.id)!.client_name, "Оля");
});

test("S1.2 AC3: прошедшее окно не занимается", () => {
  const { db, m } = setup();
  const s = createSlot(db, m.id, "2026-10-20T07:00:00.000Z", "маникюр", NOW);
  assert.equal(claimSlot(db, s.id, "Оля", "+79000000001", NOW), "past");
  assert.equal(getSlot(db, s.id)!.status, "open");
});

test("S1.2 AC4: несуществующее окно", () => {
  const { db } = setup();
  assert.equal(claimSlot(db, "nope-nope", "Оля", "+79000000001", NOW), "missing");
});

test("токены и id не угадываются по порядку", () => {
  const { db } = setup();
  const a = createMaster(db, "А", NOW);
  const b = createMaster(db, "Б", NOW);
  assert.notEqual(a.token, b.token);
  assert.ok(a.token.length >= 32);
});
