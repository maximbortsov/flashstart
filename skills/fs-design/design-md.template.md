---
version: alpha
name: <Название продукта>
description: <одна строка о продукте>
colors:
  primary: "#000000"
  neutral-bg: "#ffffff"
  neutral-text: "#111111"
typography:
  display:
    fontFamily: "<шрифт>, serif"
    fontWeight: 600
  body:
    fontFamily: "<шрифт>, sans-serif"
    fontSize: "1rem"
    lineHeight: 1.5
rounded:
  sm: "4px"
  md: "8px"
spacing:
  sm: "8px"
  md: "16px"
  lg: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.neutral-bg}"
    rounded: "{rounded.md}"
    padding: "12px 24px"
---

# Design System: <Название продукта>

<!-- Файл лежит в корне продукта. Формат — открытая спецификация DESIGN.md:
     токены во frontmatter (только ключи спецификации), разделы в стандартном порядке,
     неприменимые опускаются. Служебное FlashStart — в этом комментарии:
     hypothesis: h-NNN
     mode: operate   (persuade | operate | read — режим основного экрана) -->

## Overview
<характер интерфейса из PRODUCT.md: кто, в какой обстановке, что важнее — скорость задачи или убеждение>

## Colors
<роль каждого цвета; контраст текста ≥ 4.5:1>

## Typography
<иерархия: заголовок, подзаголовок, текст, подписи; длина строки>

## Layout
<сетка, отступы, поведение на мобильном>

## Elevation & Depth
<тени или границы — что одно из двух>

## Shapes
<радиусы и форма элементов>

## Components
<3–5 базовых компонентов и их состояния: обычное, наведение, фокус, disabled, загрузка, ошибка, пусто>

## Do's and Don'ts
<правила продукта; осознанные исключения из детектора — с причиной>
