// Время окна хранится в UTC, вводится и показывается в поясе мастера.
// Москва и Казань живут в UTC+3 без перехода на летнее время.
export const TZ = "Europe/Moscow";
const OFFSET = "+03:00";

/** "2026-10-20" + "14:00" в поясе мастера → ISO в UTC; null, если формат неверный. */
export function parseLocal(date: string, time: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !/^\d{2}:\d{2}$/.test(time)) return null;
  const d = new Date(`${date}T${time}:00${OFFSET}`);
  if (Number.isNaN(d.getTime())) return null;
  // JavaScript молча переносит 31 февраля на 3 марта — сверяем дату обратно.
  if (todayLocal(d) !== date) return null;
  return d.toISOString();
}

/** Сегодняшняя дата в поясе мастера, для значения по умолчанию в форме. */
export function todayLocal(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("sv-SE", { timeZone: TZ }).format(now);
}

/** «вт, 20 октября, 14:00» */
export function formatSlot(iso: string): string {
  const d = new Date(iso);
  const day = new Intl.DateTimeFormat("ru-RU", { timeZone: TZ, weekday: "short", day: "numeric", month: "long" }).format(d);
  const time = new Intl.DateTimeFormat("ru-RU", { timeZone: TZ, hour: "2-digit", minute: "2-digit" }).format(d);
  return `${day}, ${time}`;
}

export function minutesBetween(fromIso: string, to: Date): number {
  return Math.round((to.getTime() - new Date(fromIso).getTime()) / 60000);
}
