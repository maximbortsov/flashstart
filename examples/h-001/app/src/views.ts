import type { Master, Slot } from "./db.ts";
import { formatSlot, todayLocal } from "./time.ts";

export function esc(s: unknown): string {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}

export type FormErrors = Record<string, string>;
export type FormValues = Record<string, string>;

function page(title: string, body: string): string {
  return `<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title>
<link rel="stylesheet" href="/styles.css">
</head>
<body>
<main class="wrap">
${body}
</main>
<script src="/app.js" defer></script>
</body>
</html>`;
}

function field(name: string, label: string, input: string, errors: FormErrors, hint = ""): string {
  const err = errors[name];
  return `<div class="field${err ? " has-error" : ""}">
  <label for="${name}">${esc(label)}</label>
  ${input}
  ${hint ? `<p class="hint" id="${name}-hint">${esc(hint)}</p>` : ""}
  ${err ? `<p class="error" id="${name}-error" role="alert">${esc(err)}</p>` : ""}
</div>`;
}

function describedBy(name: string, errors: FormErrors, hint: boolean): string {
  const ids = [hint ? `${name}-hint` : "", errors[name] ? `${name}-error` : ""].filter(Boolean).join(" ");
  return ids ? ` aria-describedby="${ids}"` : "";
}

export function offerMessage(slot: Slot, link: string): string {
  return `Освободилось окно: ${formatSlot(slot.starts_at)}, ${slot.service}. Кто первый — того и запишу: ${link}`;
}

function slotRow(slot: Slot, now: Date): string {
  const when = esc(formatSlot(slot.starts_at));
  let status: string;
  if (slot.status === "filled") {
    status = `<span class="status status-filled">Занято</span>
      <span class="client">${esc(slot.client_name)}, <a href="tel:${esc(slot.client_phone)}">${esc(slot.client_phone)}</a></span>`;
  } else if (new Date(slot.starts_at) <= now) {
    status = `<span class="status status-past">Прошло</span>`;
  } else {
    status = `<span class="status status-open">Ждёт клиента</span>`;
  }
  return `<li class="slot"><div class="slot-main"><span class="slot-when">${when}</span><span class="slot-service">${esc(slot.service)}</span></div><div class="slot-status">${status}</div></li>`;
}

export function masterPanel(opts: {
  master: Master;
  slots: Slot[];
  newSlot?: Slot;
  link?: string;
  errors?: FormErrors;
  values?: FormValues;
  now?: Date;
}): string {
  const { master, slots, newSlot, link } = opts;
  const errors = opts.errors ?? {};
  const v = opts.values ?? {};
  const now = opts.now ?? new Date();
  const created = newSlot && link
    ? `<section class="notice" aria-labelledby="sent-title">
  <h2 id="sent-title">Окно сохранено — отправьте сообщение в чат</h2>
  <label class="visually-hidden" for="offer-text">Сообщение для чата</label>
  <textarea id="offer-text" class="message" rows="5" readonly>${esc(offerMessage(newSlot, link))}</textarea>
  <button type="button" class="button button-primary" data-copy="offer-text" data-ping="/m/${esc(master.token)}/slots/${esc(newSlot.id)}/copied">Скопировать сообщение</button>
  <p class="hint">Вставьте его в чат листа ожидания. Кто первый нажмёт «Занять окно», тот и записан.</p>
</section>`
    : "";
  const list = slots.length
    ? `<ul class="slots">${slots.map((s) => slotRow(s, now)).join("")}</ul>`
    : `<p class="empty">Здесь появятся окна, которые вы отметили. Отметьте первое — и получите сообщение со ссылкой для чата.</p>`;
  return page(`Окна — ${master.name}`, `
<header class="top"><p class="brand">Окно</p><p class="who">${esc(master.name)}</p></header>
${created}
<section aria-labelledby="new-title">
  <h1 id="new-title">Отменили запись? Отметьте окно</h1>
  <form method="post" action="/m/${esc(master.token)}/slots" class="form" novalidate>
    <div class="row">
      ${field("date", "Дата", `<input id="date" name="date" type="date" required value="${esc(v.date ?? todayLocal(now))}"${describedBy("date", errors, false)}>`, errors)}
      ${field("time", "Время", `<input id="time" name="time" type="time" required step="300" value="${esc(v.time)}"${describedBy("time", errors, false)}>`, errors)}
    </div>
    ${field("service", "Услуга", `<input id="service" name="service" type="text" required maxlength="80" autocomplete="off" value="${esc(v.service)}"${describedBy("service", errors, true)}>`, errors, "Например: маникюр с покрытием")}
    <button type="submit" class="button button-primary">Сохранить окно</button>
  </form>
</section>
<section aria-labelledby="list-title">
  <h2 id="list-title">Ваши окна</h2>
  ${list}
</section>`);
}

export type OfferState = "open" | "taken" | "past" | "done";

export function offerPage(opts: { slot: Slot; master: Master; state: OfferState; errors?: FormErrors; values?: FormValues }): string {
  const { slot, master, state } = opts;
  const errors = opts.errors ?? {};
  const v = opts.values ?? {};
  const head = `<p class="brand">Окно у мастера ${esc(master.name)}</p>
<h1 class="service-title">${esc(slot.service)}</h1>
<p class="when">${esc(formatSlot(slot.starts_at))} <span class="tz">по московскому времени</span></p>`;
  if (state === "done") {
    return page("Окно ваше", `${head}
<section class="result result-ok" role="status"><h2>Окно ваше</h2><p>${esc(master.name)} видит вашу запись и свяжется с вами по телефону, который вы указали.</p></section>`);
  }
  if (state === "taken") {
    return page("Окно уже заняли", `${head}
<section class="result" role="status"><h2>Это окно уже заняли</h2><p>Следующее свободное окно мастер пришлёт в тот же чат.</p></section>`);
  }
  if (state === "past") {
    return page("Окно уже прошло", `${head}
<section class="result" role="status"><h2>Окно уже прошло</h2><p>Время этого окна наступило. Следующее мастер пришлёт в тот же чат.</p></section>`);
  }
  return page(`${slot.service} — свободное окно`, `${head}
<form method="post" action="/s/${esc(slot.id)}" class="form" novalidate>
  ${field("name", "Ваше имя", `<input id="name" name="name" type="text" required maxlength="60" autocomplete="given-name" value="${esc(v.name)}"${describedBy("name", errors, false)}>`, errors)}
  ${field("phone", "Телефон", `<input id="phone" name="phone" type="tel" required maxlength="20" autocomplete="tel" inputmode="tel" value="${esc(v.phone)}"${describedBy("phone", errors, true)}>`, errors, "Например: +7 900 000-00-00. Его увидит только мастер.")}
  <button type="submit" class="button button-primary button-wide">Занять окно</button>
</form>
<p class="hint after-action">Окно достаётся тому, кто нажмёт первым.</p>`);
}

export function messagePage(title: string, text: string): string {
  return page(title, `<p class="brand">Окно</p><h1>${esc(title)}</h1><p>${esc(text)}</p>`);
}
