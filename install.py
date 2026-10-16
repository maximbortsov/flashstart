#!/usr/bin/env python3
"""Установщик FlashStart.

Ставит скиллы fs-* и scripts/trace-check.py в продуктовый репозиторий
(по умолчанию — текущая папка) или глобально для всех проектов.

    python3 install.py                 # в текущий проект
    python3 install.py путь/к/проекту  # в указанный проект
    python3 install.py --global        # в ~/.claude/skills для всех проектов
    python3 install.py --update        # подтянуть свежую версию FlashStart и переустановить
    python3 install.py --uninstall     # удалить установленное
    python3 install.py --dry-run       # показать, что будет сделано

Только стандартная библиотека Python 3.10+. Трогает лишь папки скиллов
FlashStart (с меткой .flashstart) и файл trace-check.py.
"""
from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
MARKER = ".flashstart"
MIN_PY = (3, 10)
MIN_NODE = (22, 6)


def say(msg: str) -> None:
    print(msg)


def skill_names() -> list[str]:
    return sorted(p.parent.name for p in (SRC / "skills").glob("*/SKILL.md") if p.parent.name == "fs" or p.parent.name.startswith("fs-"))


def version() -> str:
    try:
        out = subprocess.run(["git", "-C", str(SRC), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def check_env() -> list[str]:
    notes = []
    if sys.version_info < MIN_PY:
        raise SystemExit(f"Нужен Python {MIN_PY[0]}.{MIN_PY[1]}+, сейчас {sys.version.split()[0]}.")
    node = shutil.which("node")
    if not node:
        notes.append("Node.js не найден — понадобится для стека starter (трек M) и детектора Impeccable (npx). Нужен Node.js 22.6+.")
    else:
        try:
            raw = subprocess.run([node, "--version"], capture_output=True, text=True, check=True).stdout.strip().lstrip("v")
            ver = tuple(int(x) for x in raw.split(".")[:2])
            if ver < MIN_NODE:
                notes.append(f"Node.js {raw}: для стека starter нужен 22.6+.")
        except (OSError, subprocess.CalledProcessError, ValueError):
            pass
    return notes


def plan_targets(target: Path, global_: bool) -> tuple[Path, Path]:
    """Куда класть скиллы и trace-check.py."""
    if global_:
        skills_dir = Path.home() / ".claude" / "skills"
        return skills_dir, skills_dir / "fs" / "trace-check.py"
    return target / ".claude" / "skills", target / "scripts" / "trace-check.py"


def install(target: Path, global_: bool, force: bool, dry: bool) -> int:
    skills_dir, trace_dst = plan_targets(target, global_)
    names = skill_names()
    if not names:
        raise SystemExit(f"В {SRC / 'skills'} нет скиллов FlashStart — установщик запущен не из репозитория FlashStart?")

    conflicts = [n for n in names if (skills_dir / n).exists() and not (skills_dir / n / MARKER).exists()]
    if conflicts and not force:
        say("Остановлено: эти папки уже есть и созданы не установщиком FlashStart:")
        for n in conflicts:
            say(f"  {skills_dir / n}")
        say("Переименуйте их или запустите с --force, чтобы заменить.")
        return 1

    ver = version()
    say(f"FlashStart {ver} → {'глобально' if global_ else target}")
    for n in names:
        dst = skills_dir / n
        say(f"  скилл {n:10} → {dst}")
        if dry:
            continue
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(SRC / "skills" / n, dst, ignore=shutil.ignore_patterns(".gitkeep", "__pycache__"))
        (dst / MARKER).write_text(f"{ver}\n", encoding="utf-8")

    say(f"  trace-check     → {trace_dst}")
    if not dry:
        trace_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SRC / "scripts" / "trace-check.py", trace_dst)

    for note in check_env():
        say(f"! {note}")
    if dry:
        say("Пробный запуск: ничего не изменено.")
        return 0
    say("")
    say("Готово. Дальше: откройте Claude Code в папке проекта и наберите /fs-frame — опишите идею своими словами.")
    say("Статус и следующий шаг в любой момент: /fs")
    if global_:
        say(f"Проверка трассировки: python3 {trace_dst} docs/fs")
    return 0


def uninstall(target: Path, global_: bool, dry: bool) -> int:
    skills_dir, trace_dst = plan_targets(target, global_)
    removed = 0
    for n in skill_names():
        dst = skills_dir / n
        if (dst / MARKER).exists():
            say(f"  удаляю {dst}")
            if not dry:
                shutil.rmtree(dst)
            removed += 1
        elif dst.exists():
            say(f"  пропускаю {dst}: создана не установщиком FlashStart")
    if trace_dst.exists() and filecmp.cmp(trace_dst, SRC / "scripts" / "trace-check.py", shallow=False):
        say(f"  удаляю {trace_dst}")
        if not dry:
            trace_dst.unlink()
    elif trace_dst.exists():
        say(f"  пропускаю {trace_dst}: отличается от версии FlashStart")
    say(f"Удалено скиллов: {removed}. Артефакты гипотез (docs/fs, .fs, PRODUCT.md, DESIGN.md) не тронуты.")
    return 0


def update_self() -> None:
    if not (SRC / ".git").exists():
        raise SystemExit("--update работает, только если FlashStart получен через git clone.")
    say("Обновляю FlashStart…")
    res = subprocess.run(["git", "-C", str(SRC), "pull", "--ff-only"], text=True)
    if res.returncode != 0:
        raise SystemExit("git pull не удался — обновите папку FlashStart вручную и запустите установку снова.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Установка FlashStart")
    ap.add_argument("target", nargs="?", default=".", help="папка продуктового репозитория (по умолчанию — текущая)")
    ap.add_argument("--global", dest="global_", action="store_true", help="поставить скиллы в ~/.claude/skills для всех проектов")
    ap.add_argument("--update", action="store_true", help="подтянуть свежую версию FlashStart через git pull и переустановить")
    ap.add_argument("--uninstall", action="store_true", help="удалить установленные скиллы и trace-check.py")
    ap.add_argument("--force", action="store_true", help="заменить одноимённые папки скиллов, созданные не установщиком")
    ap.add_argument("--dry-run", action="store_true", help="показать, что будет сделано, ничего не меняя")
    args = ap.parse_args(argv)

    target = Path(args.target).expanduser().resolve()
    if not args.global_ and not target.is_dir():
        raise SystemExit(f"Папки {target} нет.")
    if not args.global_ and target == SRC:
        raise SystemExit("Это папка самого FlashStart. Укажите папку продуктового репозитория: python3 install.py путь/к/проекту")
    if args.uninstall:
        return uninstall(target, args.global_, args.dry_run)
    if args.update and not args.dry_run:
        update_self()
        # Перезапуск уже обновлённого установщика с теми же аргументами, но без --update.
        rest = [a for a in (argv if argv is not None else sys.argv[1:]) if a != "--update"]
        os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve()), *rest])
    return install(target, args.global_, args.force, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
