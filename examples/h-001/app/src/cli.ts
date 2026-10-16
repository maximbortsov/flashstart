import { createMaster, openDb } from "./db.ts";

const name = process.argv.slice(2).join(" ").trim();
if (!name) {
  console.error('Укажите имя мастера: npm run create-master -- "Алина"');
  process.exit(1);
}
const db = openDb(process.env.DB_PATH ?? "data/okno.sqlite");
const master = createMaster(db, name);
const base = process.env.BASE_URL ?? `http://localhost:${process.env.PORT ?? 3000}`;
console.log(`Панель мастера ${name}: ${base}/m/${master.token}`);
console.log("Ссылка секретная: по ней открывается панель без пароля. Отправьте её только мастеру.");
