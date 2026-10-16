import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { DatabaseSync } from "node:sqlite";
import { claimSlot, createSlot, findOpenSlot, getSlot, listSlots, masterById, masterByToken, openDb } from "./db.ts";
import { hasEvent, track } from "./events.ts";
import { minutesBetween, parseLocal } from "./time.ts";
import { masterPanel, messagePage, offerPage, type FormErrors } from "./views.ts";

const MAX_BODY = 10_000;
const STATIC: Record<string, { file: string; type: string }> = {
  "/styles.css": { file: "../public/styles.css", type: "text/css; charset=utf-8" },
  "/app.js": { file: "../public/app.js", type: "text/javascript; charset=utf-8" },
};

export type AppOptions = { baseUrl: string; now?: () => Date };

function send(res: ServerResponse, status: number, body: string, type = "text/html; charset=utf-8"): void {
  res.writeHead(status, { "content-type": type, "x-content-type-options": "nosniff", "referrer-policy": "no-referrer" });
  res.end(body);
}

function redirect(res: ServerResponse, location: string): void {
  res.writeHead(303, { location });
  res.end();
}

async function readForm(req: IncomingMessage): Promise<Record<string, string>> {
  let size = 0;
  const chunks: Buffer[] = [];
  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BODY) throw new HttpError(413, "Слишком большой запрос");
    chunks.push(chunk);
  }
  return Object.fromEntries(new URLSearchParams(Buffer.concat(chunks).toString("utf8")));
}

class HttpError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function cookie(req: IncomingMessage, name: string): string | undefined {
  for (const part of (req.headers.cookie ?? "").split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === name) return v.join("=");
  }
  return undefined;
}

const notFound = (res: ServerResponse, what = "Страница не найдена") =>
  send(res, 404, messagePage(what, "Проверьте ссылку или попросите мастера прислать её ещё раз."));

export function createApp(db: DatabaseSync, opts: AppOptions): Server {
  const now = opts.now ?? (() => new Date());
  const here = fileURLToPath(new URL(".", import.meta.url));

  async function handle(req: IncomingMessage, res: ServerResponse): Promise<void> {
    const url = new URL(req.url ?? "/", "http://local");
    const path = url.pathname;
    const method = req.method ?? "GET";

    if (method === "GET" && STATIC[path]) {
      const s = STATIC[path];
      return send(res, 200, readFileSync(here + s.file, "utf8"), s.type);
    }
    if (method === "GET" && path === "/") {
      return send(res, 200, messagePage("Окно", "Сервис для мастеров: отменённая запись превращается в ссылку, по которой окно занимает первый клиент из листа ожидания."));
    }

    let m = path.match(/^\/m\/([\w-]{16,64})$/);
    if (m && method === "GET") {
      const master = masterByToken(db, m[1]);
      if (!master) return notFound(res);
      const newId = url.searchParams.get("new");
      const newSlot = newId ? getSlot(db, newId) : undefined;
      const own = newSlot && newSlot.master_id === master.id && newSlot.status === "open" ? newSlot : undefined;
      return send(res, 200, masterPanel({
        master, slots: listSlots(db, master.id), newSlot: own, link: own ? `${opts.baseUrl}/s/${own.id}` : undefined, now: now(),
      }));
    }

    m = path.match(/^\/m\/([\w-]{16,64})\/slots$/);
    if (m && method === "POST") {
      const master = masterByToken(db, m[1]);
      if (!master) return notFound(res);
      const form = await readForm(req);
      const values = { date: (form.date ?? "").trim(), time: (form.time ?? "").trim(), service: (form.service ?? "").trim() };
      const errors: FormErrors = {};
      const startsAt = parseLocal(values.date, values.time);
      if (!values.date) errors.date = "Укажите дату окна";
      if (!values.time) errors.time = "Укажите время окна";
      else if (!startsAt) errors.time = "Время в формате ЧЧ:ММ, например 14:00";
      else if (new Date(startsAt) <= now()) errors.time = "Это время уже прошло — укажите будущее";
      if (!values.service) errors.service = "Напишите, какая услуга: так клиенту проще решить";
      if (Object.keys(errors).length) {
        return send(res, 422, masterPanel({ master, slots: listSlots(db, master.id), errors, values, now: now() }));
      }
      const existing = findOpenSlot(db, master.id, startsAt!);
      if (existing) return redirect(res, `/m/${master.token}?new=${existing.id}`);
      const t = now();
      const slot = createSlot(db, master.id, startsAt!, values.service.slice(0, 80), t);
      track(db, "slot_released", { slot_id: slot.id, master_id: master.id, minutes_before_start: minutesBetween(t.toISOString(), new Date(startsAt!)) }, t);
      return redirect(res, `/m/${master.token}?new=${slot.id}`);
    }

    m = path.match(/^\/m\/([\w-]{16,64})\/slots\/([\w-]{6,32})\/copied$/);
    if (m && method === "POST") {
      const master = masterByToken(db, m[1]);
      const slot = master ? getSlot(db, m[2]) : undefined;
      if (!master || !slot || slot.master_id !== master.id) return notFound(res);
      // Считаем только первое копирование: повторные нажатия не должны искажать SC1.2.
      if (hasEvent(db, "offer_copied", slot.id)) {
        res.writeHead(204);
        return void res.end();
      }
      const t = now();
      track(db, "offer_copied", { slot_id: slot.id, seconds_since_release: Math.round((t.getTime() - new Date(slot.created_at).getTime()) / 1000) }, t);
      res.writeHead(204);
      return void res.end();
    }

    m = path.match(/^\/s\/([\w-]{1,64})$/);
    if (m) {
      const slot = getSlot(db, m[1]);
      const master = slot ? masterById(db, slot.master_id) : undefined;
      if (!slot || !master) return notFound(res, "Окно не найдено");
      if (method === "GET") {
        if (slot.status === "filled") {
          const mine = cookie(req, "okno_claimed") === slot.id;
          return send(res, 200, offerPage({ slot, master, state: mine ? "done" : "taken" }));
        }
        if (new Date(slot.starts_at) <= now()) return send(res, 410, offerPage({ slot, master, state: "past" }));
        track(db, "offer_opened", { slot_id: slot.id }, now());
        return send(res, 200, offerPage({ slot, master, state: "open" }));
      }
      if (method === "POST") {
        const form = await readForm(req);
        const values = { name: (form.name ?? "").trim(), phone: (form.phone ?? "").trim() };
        const errors: FormErrors = {};
        if (!values.name) errors.name = "Напишите имя, чтобы мастер знал, кого ждать";
        const digits = values.phone.replace(/\D/g, "");
        if (!values.phone) errors.phone = "Укажите телефон, чтобы мастер мог подтвердить запись";
        else if (!/^[+\d\s()-]+$/.test(values.phone) || digits.length < 10 || digits.length > 15) {
          errors.phone = "Проверьте номер: только цифры, пробелы, «+», скобки и дефисы, 10–15 цифр";
        }
        if (Object.keys(errors).length) {
          if (slot.status === "filled") return send(res, 409, offerPage({ slot, master, state: "taken" }));
          if (new Date(slot.starts_at) <= now()) return send(res, 410, offerPage({ slot, master, state: "past" }));
          return send(res, 422, offerPage({ slot, master, state: "open", errors, values }));
        }
        const t = now();
        const result = claimSlot(db, slot.id, values.name.slice(0, 60), values.phone.slice(0, 20), t);
        if (result === "ok") {
          track(db, "slot_filled", { slot_id: slot.id, minutes_to_fill: minutesBetween(slot.created_at, t) }, t);
          // Чтобы занявший клиент после обновления страницы видел «Окно ваше», а не «уже заняли».
          res.setHeader("set-cookie", `okno_claimed=${slot.id}; Path=/s/${slot.id}; Max-Age=604800; HttpOnly; SameSite=Lax`);
          return send(res, 200, offerPage({ slot, master, state: "done" }));
        }
        if (result === "taken") return send(res, 409, offerPage({ slot, master, state: "taken" }));
        if (result === "past") return send(res, 410, offerPage({ slot, master, state: "past" }));
        return notFound(res, "Окно не найдено");
      }
    }
    return notFound(res);
  }

  return createServer((req, res) => {
    handle(req, res).catch((err: unknown) => {
      if (err instanceof HttpError) return send(res, err.status, messagePage("Не получилось", err.message));
      console.error(err);
      send(res, 500, messagePage("Что-то сломалось", "Попробуйте ещё раз через минуту. Введённое не сохранилось."));
    });
  });
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const port = Number(process.env.PORT ?? 3000);
  const db = openDb(process.env.DB_PATH ?? "data/okno.sqlite");
  const baseUrl = process.env.BASE_URL ?? `http://localhost:${port}`;
  createApp(db, { baseUrl }).listen(port, () => console.log(`Окно: ${baseUrl}`));
}
