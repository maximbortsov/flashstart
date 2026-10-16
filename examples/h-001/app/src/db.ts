import { DatabaseSync } from "node:sqlite";
import { randomBytes } from "node:crypto";
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";

export type Slot = {
  id: string;
  master_id: string;
  starts_at: string;
  service: string;
  status: "open" | "filled";
  created_at: string;
  filled_at: string | null;
  client_name: string | null;
  client_phone: string | null;
};
export type Master = { id: string; token: string; name: string };
export type ClaimResult = "ok" | "taken" | "past" | "missing";

const SCHEMA = `
CREATE TABLE IF NOT EXISTS masters (
  id TEXT PRIMARY KEY, token TEXT NOT NULL UNIQUE, name TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS slots (
  id TEXT PRIMARY KEY, master_id TEXT NOT NULL REFERENCES masters(id),
  starts_at TEXT NOT NULL, service TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
  created_at TEXT NOT NULL, filled_at TEXT, client_name TEXT, client_phone TEXT
);
CREATE INDEX IF NOT EXISTS slots_master ON slots(master_id, starts_at);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, props TEXT NOT NULL, at TEXT NOT NULL
);`;

export function openDb(path: string): DatabaseSync {
  if (path !== ":memory:") mkdirSync(dirname(path), { recursive: true });
  const db = new DatabaseSync(path);
  db.exec("PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;");
  db.exec(SCHEMA);
  return db;
}

const newId = (bytes: number) => randomBytes(bytes).toString("base64url");

export function createMaster(db: DatabaseSync, name: string, now = new Date()): Master {
  const m = { id: newId(6), token: newId(24), name };
  db.prepare("INSERT INTO masters (id, token, name, created_at) VALUES (?, ?, ?, ?)").run(m.id, m.token, name, now.toISOString());
  return m;
}

export function masterByToken(db: DatabaseSync, token: string): Master | undefined {
  return db.prepare("SELECT id, token, name FROM masters WHERE token = ?").get(token) as Master | undefined;
}

export function masterById(db: DatabaseSync, id: string): Master | undefined {
  return db.prepare("SELECT id, token, name FROM masters WHERE id = ?").get(id) as Master | undefined;
}

export function createSlot(db: DatabaseSync, masterId: string, startsAt: string, service: string, now = new Date()): Slot {
  const id = newId(8);
  db.prepare("INSERT INTO slots (id, master_id, starts_at, service, created_at) VALUES (?, ?, ?, ?, ?)").run(
    id, masterId, startsAt, service, now.toISOString(),
  );
  return getSlot(db, id)!;
}

/** Открытое окно мастера на то же время — чтобы двойное нажатие не создавало дубль. */
export function findOpenSlot(db: DatabaseSync, masterId: string, startsAt: string): Slot | undefined {
  return db.prepare("SELECT * FROM slots WHERE master_id = ? AND starts_at = ? AND status = 'open'").get(masterId, startsAt) as Slot | undefined;
}

export function getSlot(db: DatabaseSync, id: string): Slot | undefined {
  return db.prepare("SELECT * FROM slots WHERE id = ?").get(id) as Slot | undefined;
}

export function listSlots(db: DatabaseSync, masterId: string): Slot[] {
  return db.prepare("SELECT * FROM slots WHERE master_id = ? ORDER BY starts_at").all(masterId) as Slot[];
}

/** Атомарный захват: окно получает только первый запрос, пока окно открыто и не наступило. */
export function claimSlot(db: DatabaseSync, id: string, name: string, phone: string, now = new Date()): ClaimResult {
  const res = db.prepare(
    `UPDATE slots SET status = 'filled', filled_at = ?, client_name = ?, client_phone = ?
     WHERE id = ? AND status = 'open' AND starts_at > ?`,
  ).run(now.toISOString(), name, phone, id, now.toISOString());
  if (Number(res.changes) === 1) return "ok";
  const slot = getSlot(db, id);
  if (!slot) return "missing";
  return slot.status === "filled" ? "taken" : "past";
}
