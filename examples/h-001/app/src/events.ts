import type { DatabaseSync } from "node:sqlite";

export type EventName = "slot_released" | "offer_copied" | "offer_opened" | "slot_filled";
export type Props = Record<string, string | number>;

// Без персональных данных: в свойства попадают только идентификаторы и числа.
export function track(db: DatabaseSync, name: EventName, props: Props, now = new Date()): void {
  db.prepare("INSERT INTO events (name, props, at) VALUES (?, ?, ?)").run(name, JSON.stringify(props), now.toISOString());
  if (process.env.EVENTS_LOG !== "off") console.log(JSON.stringify({ event: name, ...props, at: now.toISOString() }));
}

export function hasEvent(db: DatabaseSync, name: EventName, slotId: string): boolean {
  return Boolean(db.prepare("SELECT 1 FROM events WHERE name = ? AND json_extract(props, '$.slot_id') = ?").get(name, slotId));
}

export function listEvents(db: DatabaseSync): { name: string; props: Props; at: string }[] {
  return (db.prepare("SELECT name, props, at FROM events ORDER BY id").all() as { name: string; props: string; at: string }[])
    .map((e) => ({ ...e, props: JSON.parse(e.props) }));
}
