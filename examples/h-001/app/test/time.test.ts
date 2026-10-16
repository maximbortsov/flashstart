import { test } from "node:test";
import assert from "node:assert/strict";
import { formatSlot, parseLocal, todayLocal } from "../src/time.ts";

test("время мастера переводится в UTC по Москве", () => {
  assert.equal(parseLocal("2026-10-20", "14:00"), "2026-10-20T11:00:00.000Z");
});

test("неверный формат — null", () => {
  assert.equal(parseLocal("20.10.2026", "14:00"), null);
  assert.equal(parseLocal("2026-10-20", "2 pm"), null);
  assert.equal(parseLocal("2026-02-31", "14:00"), null, "31 февраля не должно становиться 3 марта");
  assert.equal(parseLocal("2026-10-20", "25:00"), null);
});

test("показ — в поясе мастера", () => {
  assert.match(formatSlot("2026-10-20T11:00:00.000Z"), /20 октября, 14:00/);
});

test("сегодня — по Москве, а не по UTC", () => {
  assert.equal(todayLocal(new Date("2026-10-19T22:30:00Z")), "2026-10-20");
});
