import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import type { AddressInfo } from "node:net";
import type { Server } from "node:http";
import { createMaster, openDb } from "../src/db.ts";
import { listEvents } from "../src/events.ts";
import { createApp } from "../src/server.ts";

process.env.EVENTS_LOG = "off";
let clock = new Date("2026-10-20T08:00:00Z");
const db = openDb(":memory:");
const master = createMaster(db, "Алина", clock);
let server: Server;
let base = "";

before(async () => {
  server = createApp(db, { baseUrl: "https://okno.example", now: () => clock });
  await new Promise<void>((r) => server.listen(0, r));
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});
after(() => server.close());

const form = (data: Record<string, string>) => ({
  method: "POST",
  headers: { "content-type": "application/x-www-form-urlencoded" },
  body: new URLSearchParams(data).toString(),
  redirect: "manual" as const,
});

async function releaseSlot(time = "14:00", service = "маникюр с покрытием"): Promise<string> {
  const res = await fetch(`${base}/m/${master.token}/slots`, form({ date: "2026-10-20", time, service }));
  assert.equal(res.status, 303);
  return new URL(res.headers.get("location")!, base).searchParams.get("new")!;
}

test("S1.1 AC1: мастер сохраняет окно и видит сообщение со ссылкой", async () => {
  const id = await releaseSlot();
  const html = await (await fetch(`${base}/m/${master.token}?new=${id}`)).text();
  assert.match(html, /Скопировать сообщение/);
  assert.ok(html.includes(`https://okno.example/s/${id}`));
  assert.match(html, /Освободилось окно: .*20 октября, 14:00, маникюр с покрытием/);
});

test("S1.1: пустая форма мастера — 422 и ошибки у полей, введённое сохранено", async () => {
  const res = await fetch(`${base}/m/${master.token}/slots`, form({ date: "2026-10-20", time: "", service: "педикюр" }));
  assert.equal(res.status, 422);
  const html = await res.text();
  assert.match(html, /Укажите время окна/);
  assert.match(html, /value="педикюр"/);
});

test("S1.1: прошедшее время мастер не сохраняет", async () => {
  const res = await fetch(`${base}/m/${master.token}/slots`, form({ date: "2026-10-20", time: "10:00", service: "маникюр" }));
  assert.equal(res.status, 422);
  assert.match(await res.text(), /уже прошло/);
});

test("S1.1 AC2–AC3: клиент занимает окно, мастер видит имя и телефон", async () => {
  const id = await releaseSlot("15:00");
  const offer = await fetch(`${base}/s/${id}`);
  assert.equal(offer.status, 200);
  const offerHtml = await offer.text();
  assert.match(offerHtml, /Занять окно/);
  assert.match(offerHtml, /20 октября, 15:00/);

  const bad = await fetch(`${base}/s/${id}`, form({ name: "Оля", phone: "" }));
  assert.equal(bad.status, 422);
  assert.match(await bad.text(), /Укажите телефон/);

  const ok = await fetch(`${base}/s/${id}`, form({ name: "Оля", phone: "+7 900 111-22-33" }));
  assert.equal(ok.status, 200);
  assert.match(await ok.text(), /Окно ваше/);

  const panel = await (await fetch(`${base}/m/${master.token}`)).text();
  assert.match(panel, /Занято/);
  assert.match(panel, /Оля, <a href="tel:\+7 900 111-22-33">/);
});

test("S1.2 AC1–AC2: второй клиент видит «уже заняли»", async () => {
  const id = await releaseSlot("16:00");
  const [a, b] = await Promise.all([
    fetch(`${base}/s/${id}`, form({ name: "Оля", phone: "+79001112233" })),
    fetch(`${base}/s/${id}`, form({ name: "Катя", phone: "+79004445566" })),
  ]);
  assert.deepEqual([a.status, b.status].sort(), [200, 409]);
  const again = await fetch(`${base}/s/${id}`);
  const html = await again.text();
  assert.match(html, /уже заняли/);
  assert.doesNotMatch(html, /Занять окно/);
});

test("S1.2 AC3: окно, время которого наступило, не занимается", async () => {
  const id = await releaseSlot("17:00");
  clock = new Date("2026-10-20T14:30:00Z"); // 17:30 по Москве
  try {
    const page = await fetch(`${base}/s/${id}`);
    assert.equal(page.status, 410);
    assert.match(await page.text(), /Окно уже прошло/);
    const post = await fetch(`${base}/s/${id}`, form({ name: "Оля", phone: "+79001112233" }));
    assert.equal(post.status, 410);
  } finally {
    clock = new Date("2026-10-20T08:00:00Z");
  }
});

test("S1.2 AC4 и чужие ссылки: 404 без подробностей", async () => {
  assert.equal((await fetch(`${base}/s/unknownslot`)).status, 404);
  assert.equal((await fetch(`${base}/m/${"x".repeat(32)}`)).status, 404);
});

test("S1.1 AC4: события отправлены и без персональных данных", async () => {
  const id = await releaseSlot("18:00");
  await fetch(`${base}/m/${master.token}/slots/${id}/copied`, { method: "POST" });
  await fetch(`${base}/s/${id}`);
  await fetch(`${base}/s/${id}`, form({ name: "Оля", phone: "+79001112233" }));
  const mine = listEvents(db).filter((e) => e.props.slot_id === id);
  assert.deepEqual(mine.map((e) => e.name), ["slot_released", "offer_copied", "offer_opened", "slot_filled"]);
  const raw = JSON.stringify(listEvents(db));
  assert.doesNotMatch(raw, /Оля|79001112233/);
  assert.equal(mine[3].props.minutes_to_fill, 0);
});

test("HTML пользователя экранируется", async () => {
  const id = await releaseSlot("19:00", "<script>alert(1)</script>");
  const html = await (await fetch(`${base}/s/${id}`)).text();
  assert.doesNotMatch(html, /<script>alert/);
  assert.match(html, /&lt;script&gt;/);
});

test("ревью: двойная отправка формы мастера не создаёт дубль", async () => {
  const a = await releaseSlot("20:00");
  const b = await releaseSlot("20:00");
  assert.equal(a, b);
});

test("ревью: offer_copied считается один раз на окно", async () => {
  const id = await releaseSlot("20:30");
  for (let i = 0; i < 3; i++) await fetch(`${base}/m/${master.token}/slots/${id}/copied`, { method: "POST" });
  assert.equal(listEvents(db).filter((e) => e.name === "offer_copied" && e.props.slot_id === id).length, 1);
});

test("ревью: занявший клиент после обновления видит «Окно ваше»", async () => {
  const id = await releaseSlot("21:00");
  const ok = await fetch(`${base}/s/${id}`, form({ name: "Оля", phone: "+79001112233" }));
  const setCookie = ok.headers.get("set-cookie")!;
  assert.match(setCookie, /HttpOnly/);
  const mine = await (await fetch(`${base}/s/${id}`, { headers: { cookie: setCookie.split(";")[0] } })).text();
  assert.match(mine, /Окно ваше/);
  const other = await (await fetch(`${base}/s/${id}`)).text();
  assert.match(other, /уже заняли/);
});

test("ревью: телефон с буквами отклоняется", async () => {
  const id = await releaseSlot("21:30");
  const res = await fetch(`${base}/s/${id}`, form({ name: "Оля", phone: "+7 900 abc 11 22 33" }));
  assert.equal(res.status, 422);
});

test("ревью: короткий неизвестный id окна — «Окно не найдено»", async () => {
  const res = await fetch(`${base}/s/abc`);
  assert.equal(res.status, 404);
  assert.match(await res.text(), /Окно не найдено/);
});
