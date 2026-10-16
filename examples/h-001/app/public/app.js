// Копирование сообщения одним нажатием. Без JavaScript текст можно выделить вручную.
document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-copy]");
  if (!btn) return;
  const field = document.getElementById(btn.dataset.copy);
  if (!field) return;
  try {
    await navigator.clipboard.writeText(field.value);
  } catch {
    field.select();
    document.execCommand("copy");
  }
  btn.textContent = "Скопировано";
  if (btn.dataset.ping && !btn.dataset.pinged) {
    btn.dataset.pinged = "1";
    fetch(btn.dataset.ping, { method: "POST", keepalive: true }).catch(() => {});
  }
});

// Двойное нажатие «Сохранить окно» не должно отправлять форму дважды.
document.addEventListener("submit", (e) => {
  const btn = e.target.querySelector("button[type=submit]");
  if (btn) setTimeout(() => { btn.disabled = true; }, 0);
});
