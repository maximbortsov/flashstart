---
version: alpha
name: Окно
description: Отменённая запись мастера превращается в ссылку, по которой окно занимает первый клиент.
colors:
  primary: "#a3203b"
  primary-deep: "#7f1830"
  ink: "#1f1d24"
  ink-muted: "#55515e"
  surface: "#ffffff"
  surface-sunk: "#f3f2f5"
  line: "#d9d6de"
  field-border: "#8d8996"
  ok: "#1d6b45"
  ok-sunk: "#e7f3ec"
  error: "#b3261e"
typography:
  heading:
    fontFamily: "Golos Text, PT Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "1.625rem"
    fontWeight: 700
    lineHeight: 1.2
  subheading:
    fontFamily: "Golos Text, PT Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "1.1875rem"
    fontWeight: 650
    lineHeight: 1.3
  body:
    fontFamily: "Golos Text, PT Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  note:
    fontFamily: "Golos Text, PT Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.45
rounded:
  control: "8px"
  surface: "12px"
spacing:
  tight: "6px"
  base: "12px"
  loose: "24px"
  section: "40px"
  gutter: "16px"
components:
  action-main:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "12px 20px"
    height: "48px"
  field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    height: "48px"
  notice:
    backgroundColor: "{colors.surface-sunk}"
    rounded: "{rounded.surface}"
    padding: "24px 16px"
---

# Design System: Окно

<!-- Синтетический пример FlashStart.
     hypothesis: h-001
     mode: operate (панель мастера); persuade (страница окна для клиента) -->

## Overview
Инструмент для мастера маникюра, которым пользуются с телефона между клиентами, в светлом кабинете. Поэтому светлая тема, крупные поля и кнопки, никакой декоративности: мастер должен отметить окно и скопировать сообщение за минуту. Страница окна для клиента — одно решение и одно действие: что за окно, когда, «Занять окно». Характер — в одном цвете: глубокий ягодный, как лак на витрине мастера.

## Colors
- `primary` — главное действие и бренд. Белый текст на нём — 7.4:1.
- `primary-deep` — наведение на главное действие.
- `ink` / `ink-muted` — основной и вторичный текст (вторичный на белом — 7.7:1, на `surface-sunk` — 6.9:1).
- `surface` / `surface-sunk` — фон и блоки «сообщение готово», «результат».
- `ok` — только статус «Занято» и «Окно ваше», всегда вместе со словом.
- `error` — текст ошибки у поля, всегда вместе с пояснением.

## Typography
Один гротеск с кириллицей. Заголовок 26 px жирный, подзаголовок 19 px, текст 16 px, пометки 15 px. Время окна — табличные цифры.

## Layout
Одна колонка шириной до 34rem, поля 16 px по краям. Плотно внутри группы (6–12 px), свободно между разделами (40 px). Дата и время в форме — в две колонки, на экранах уже 352 px — в одну.

## Elevation & Depth
Без теней. Глубина — только фоном `surface-sunk` и линиями `line`.

## Shapes
Радиус 8 px у полей и кнопок, 12 px у блоков.

## Components
- **action-main** — главная кнопка, одна на экран, высота 48 px. Состояния: обычное, наведение (`primary-deep`), фокус (обводка 3 px `primary`), заблокирована после отправки.
- **field** — подпись над полем всегда видна, подсказка под полем, ошибка под подсказкой, обводка поля — цвет ошибки.
- **notice** — блок «Окно сохранено» с готовым сообщением и кнопкой копирования.
- **Список окон** — строки с разделителями, без карточек: время, услуга, статус словом.

## Do's and Don'ts
- Do: статус всегда словом («Ждёт клиента», «Занято», «Прошло»), цвет — только дополнение.
- Do: время с пометкой «по московскому времени» на странице клиента.
- Don't: карточки, тени, градиенты, иконки ради украшения.
- Don't: второе главное действие на экране.
- Шрифт Golos Text пока не подключён файлом — показывается запасной системный (см. `docs/fs/h-001/deferred.md`).
