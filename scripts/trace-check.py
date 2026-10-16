#!/usr/bin/env python3
"""FlashStart trace-check: проверка правил трассировки артефактов гипотезы.

Использование:
    python3 scripts/trace-check.py [ПУТЬ ...] [--json] [--state FILE]

ПУТЬ — папка гипотезы (docs/fs/h-001) или папка со множеством гипотез
(docs/fs). По умолчанию — docs/fs. Код выхода 1, если есть ошибки.

Только стандартная библиотека Python 3.10+. Если установлен PyYAML,
frontmatter разбирается им; иначе — встроенным парсером подмножества YAML,
которого достаточно для шаблонов FlashStart.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------
# Мини-парсер YAML (подмножество: блочные словари и списки, flow-коллекции,
# скаляры в кавычках и без, комментарии).
# --------------------------------------------------------------------------


class YamlError(ValueError):
    pass


def _strip_comment(line: str) -> str:
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
    return line.rstrip()


def _scalar(text: str):
    t = text.strip()
    if t == "" or t in ("~", "null", "Null", "NULL"):
        return None
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        body = t[1:-1]
        return body.replace("\\\"", "\"") if t[0] == '"' else body.replace("''", "'")
    if t in ("true", "True", "TRUE"):
        return True
    if t in ("false", "False", "FALSE"):
        return False
    if re.fullmatch(r"[-+]?\d+", t):
        return int(t)
    if re.fullmatch(r"[-+]?\d+\.\d+", t) and not re.fullmatch(r"\d+\.\d+\.\d+", t):
        return float(t)
    return t


class _Flow:
    def __init__(self, text: str):
        self.s = text
        self.i = 0

    def _ws(self):
        while self.i < len(self.s) and self.s[self.i] in " \t":
            self.i += 1

    def parse(self):
        v = self.value(stop=",]}")
        self._ws()
        if self.i != len(self.s):
            raise YamlError(f"лишние символы во flow-значении: {self.s!r}")
        return v

    def value(self, stop: str):
        self._ws()
        if self.i < len(self.s) and self.s[self.i] == "[":
            return self.seq()
        if self.i < len(self.s) and self.s[self.i] == "{":
            return self.map()
        return _scalar(self.token(stop))

    def token(self, stop: str) -> str:
        self._ws()
        start = self.i
        if self.i < len(self.s) and self.s[self.i] in "\"'":
            q = self.s[self.i]
            self.i += 1
            while self.i < len(self.s) and self.s[self.i] != q:
                self.i += 1
            if self.i >= len(self.s):
                raise YamlError(f"незакрытая кавычка: {self.s!r}")
            self.i += 1
            return self.s[start:self.i]
        while self.i < len(self.s) and self.s[self.i] not in stop:
            self.i += 1
        return self.s[start:self.i].strip()

    def seq(self):
        self.i += 1
        out = []
        self._ws()
        if self.i < len(self.s) and self.s[self.i] == "]":
            self.i += 1
            return out
        while True:
            out.append(self.value(stop=",]"))
            self._ws()
            if self.i >= len(self.s):
                raise YamlError(f"незакрытый список: {self.s!r}")
            ch = self.s[self.i]
            self.i += 1
            if ch == "]":
                return out
            if ch != ",":
                raise YamlError(f"ожидалась запятая: {self.s!r}")

    def map(self):
        self.i += 1
        out = {}
        self._ws()
        if self.i < len(self.s) and self.s[self.i] == "}":
            self.i += 1
            return out
        while True:
            key = _scalar(self.token(stop=":,}"))
            self._ws()
            if self.i >= len(self.s) or self.s[self.i] != ":":
                raise YamlError(f"ожидалось двоеточие: {self.s!r}")
            self.i += 1
            out[str(key)] = self.value(stop=",}")
            self._ws()
            if self.i >= len(self.s):
                raise YamlError(f"незакрытый словарь: {self.s!r}")
            ch = self.s[self.i]
            self.i += 1
            if ch == "}":
                return out
            if ch != ",":
                raise YamlError(f"ожидалась запятая: {self.s!r}")


def _value(text: str):
    t = text.strip()
    if t.startswith("[") or t.startswith("{"):
        return _Flow(t).parse()
    return _scalar(t)


def _split_key(content: str):
    m = re.match(r"""^("[^"]*"|'[^']*'|[^:]+?):(?:\s+(.*)|$)""", content)
    if not m:
        return None
    return str(_scalar(m.group(1))), (m.group(2) or "")


def mini_yaml(text: str):
    lines = []
    for raw in text.splitlines():
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise YamlError("табуляция в отступе")
        line = _strip_comment(raw)
        if line.strip():
            lines.append((len(line) - len(line.lstrip(" ")), line.strip()))
    if not lines:
        return {}
    value, pos = _block(lines, 0, lines[0][0])
    if pos != len(lines):
        raise YamlError(f"неожиданный отступ: {lines[pos][1]!r}")
    return value


def _block(lines, pos, indent):
    if lines[pos][1].startswith("- ") or lines[pos][1] == "-":
        out = []
        while pos < len(lines) and lines[pos][0] == indent and (
            lines[pos][1].startswith("- ") or lines[pos][1] == "-"
        ):
            item = lines[pos][1][1:].strip()
            pos += 1
            if item:
                out.append(_value(item))
            elif pos < len(lines) and lines[pos][0] > indent:
                v, pos = _block(lines, pos, lines[pos][0])
                out.append(v)
            else:
                out.append(None)
        return out, pos
    out = {}
    while pos < len(lines) and lines[pos][0] == indent:
        kv = _split_key(lines[pos][1])
        if kv is None:
            raise YamlError(f"ожидалось «ключ: значение»: {lines[pos][1]!r}")
        key, rest = kv
        pos += 1
        if rest.strip():
            out[key] = _value(rest)
        elif pos < len(lines) and lines[pos][0] > indent:
            out[key], pos = _block(lines, pos, lines[pos][0])
        elif pos < len(lines) and lines[pos][0] == indent and lines[pos][1].startswith("- "):
            out[key], pos = _block(lines, pos, indent)
        else:
            out[key] = None
    return out, pos


def load_yaml(text: str, force_builtin: bool = False):
    if not force_builtin:
        try:
            import yaml  # type: ignore

            return yaml.safe_load(text) or {}
        except ImportError:
            pass
    return mini_yaml(text)


# --------------------------------------------------------------------------
# Модель артефактов
# --------------------------------------------------------------------------

ID_PATTERNS = {
    "J": r"J\d+",
    "SC": r"SC\d+\.\d+",
    "A": r"A\d+",
    "FR": r"FR\d+",
    "EV": r"EV\d+",
    "E": r"E\d+",
    "S": r"S\d+\.\d+",
}
# Какие типы ID на какие типы могут ссылаться.
ALLOWED_REFS = {
    "SC": {"J"},
    "A": {"J", "SC"},
    "FR": {"SC"},
    "EV": {"SC"},
    "E": {"FR"},
    "S": {"FR", "EV"},
    "J": set(),
}
INACTIVE = {"dropped", "superseded"}
AC_RE = re.compile(r"\bAC\d+\b")
FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)(.*)\Z", re.S)


def id_type(ident: str) -> str | None:
    for kind, pat in ID_PATTERNS.items():
        if re.fullmatch(pat, ident):
            return kind
    return None


def id_num(ident: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", ident))


@dataclass
class Artifact:
    path: Path
    meta: dict
    body: str

    @property
    def kind(self) -> str:
        return str(self.meta.get("fs", ""))


@dataclass
class Finding:
    level: str  # error | warning
    rule: str
    message: str
    where: str = ""

    def as_dict(self):
        return {"level": self.level, "rule": self.rule, "message": self.message, "where": self.where}


@dataclass
class Report:
    hypothesis: str
    path: str
    track: str | None = None
    findings: list[Finding] = field(default_factory=list)
    debt: dict = field(default_factory=dict)
    counts: dict = field(default_factory=dict)

    def add(self, level, rule, message, where=""):
        self.findings.append(Finding(level, rule, message, str(where)))

    @property
    def errors(self):
        return [f for f in self.findings if f.level == "error"]

    @property
    def warnings(self):
        return [f for f in self.findings if f.level == "warning"]

    def as_dict(self):
        return {
            "hypothesis": self.hypothesis,
            "path": self.path,
            "track": self.track,
            "ok": not self.errors,
            "validation_debt": self.debt,
            "counts": self.counts,
            "findings": [f.as_dict() for f in self.findings],
        }


def read_artifact(path: Path, force_builtin=False) -> Artifact | None:
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    meta = load_yaml(m.group(1), force_builtin)
    if not isinstance(meta, dict) or "fs" not in meta:
        return None
    return Artifact(path, meta, m.group(2))


def find_state(start: Path) -> Path | None:
    for d in [start, *start.parents]:
        p = d / ".fs" / "state.yaml"
        if p.is_file():
            return p
    return None


def _as_list(v) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return [str(v)]


# --------------------------------------------------------------------------
# Проверки
# --------------------------------------------------------------------------


def check_hypothesis(hdir: Path, state_path: Path | None = None, force_builtin=False) -> Report:
    rep = Report(hypothesis=hdir.name, path=str(hdir))
    files = sorted(hdir.glob("*.md")) + sorted((hdir / "stories").glob("*.md"))
    arts: list[Artifact] = []
    for f in files:
        try:
            a = read_artifact(f, force_builtin)
        except Exception as e:  # noqa: BLE001 — любой сбой разбора — находка, а не падение
            rep.add("error", "I0", f"не удалось разобрать frontmatter: {e}", f)
            continue
        if a:
            arts.append(a)

    defs: dict[str, Artifact] = {}
    meta_of: dict[str, dict] = {}
    refs: dict[str, list[str]] = {}

    for a in arts:
        hyp = a.meta.get("hypothesis")
        if hyp and str(hyp) != hdir.name:
            rep.add("warning", "I6", f"hypothesis: {hyp} не совпадает с папкой {hdir.name}", a.path.name)
        for ident in _as_list(a.meta.get("ids")):
            if id_type(ident) is None:
                rep.add("error", "I3", f"неверный формат ID: {ident}", a.path.name)
                continue
            if ident in defs:
                rep.add("error", "I1", f"ID {ident} определён дважды: {defs[ident].path.name} и {a.path.name}", a.path.name)
                continue
            defs[ident] = a
        items = a.meta.get("items") or {}
        if not isinstance(items, dict):
            rep.add("error", "I0", "items должен быть словарём ID → свойства", a.path.name)
            items = {}
        for ident, props in items.items():
            if ident not in _as_list(a.meta.get("ids")):
                rep.add("error", "I2", f"items.{ident} есть, но ID не объявлен в ids", a.path.name)
            meta_of[ident] = props if isinstance(props, dict) else {}
        r = a.meta.get("refs") or {}
        if not isinstance(r, dict):
            rep.add("error", "I0", "refs должен быть словарём ID → [ID]", a.path.name)
            r = {}
        for src, targets in r.items():
            if src not in _as_list(a.meta.get("ids")):
                rep.add("error", "I2", f"refs.{src}: источник ссылки не объявлен в ids этого файла", a.path.name)
            refs.setdefault(src, []).extend(_as_list(targets))

    def active(ident: str) -> bool:
        return str(meta_of.get(ident, {}).get("status", "")).lower() not in INACTIVE

    def of_kind(kind: str) -> list[str]:
        return sorted((i for i in defs if id_type(i) == kind and active(i)), key=id_num)

    # Целостность ссылок
    for src, targets in refs.items():
        st = id_type(src)
        for t in targets:
            tt = id_type(t)
            if t not in defs:
                rep.add("error", "I2", f"{src} ссылается на несуществующий {t}", defs.get(src, Artifact(Path("?"), {}, "")).path.name)
            elif st and tt not in ALLOWED_REFS.get(st, set()):
                rep.add("error", "I5", f"{src} не может ссылаться на {t} (тип {tt})", defs[src].path.name)
            elif active(src) and not active(t):
                rep.add("warning", "I7", f"{src} ссылается на выведенный из работы {t}", defs[src].path.name)

    # Иерархия ID
    for sc in of_kind("SC"):
        parent = f"J{id_num(sc)[0]}"
        if parent not in defs:
            rep.add("error", "I4", f"{sc} относится к {parent}, но такого Job нет", defs[sc].path.name)
    for s in of_kind("S"):
        parent = f"E{id_num(s)[0]}"
        if parent not in defs:
            rep.add("error", "I4", f"история {s} относится к эпику {parent}, но его нет", defs[s].path.name)

    # Трек
    kinds = {a.kind: a for a in arts}
    track = None
    if "rat" in kinds and kinds["rat"].meta.get("track"):
        track = str(kinds["rat"].meta["track"]).upper()
    state = {}
    if state_path is None:
        state_path = find_state(hdir)
    if state_path and state_path.is_file():
        try:
            state = load_yaml(state_path.read_text(encoding="utf-8"), force_builtin) or {}
        except Exception as e:  # noqa: BLE001
            rep.add("warning", "I0", f"не удалось разобрать {state_path}: {e}", state_path)
        if str(state.get("hypothesis", hdir.name)) != hdir.name:
            state = {}
    if not track and state.get("track"):
        track = str(state["track"]).upper()
    rep.track = track

    # Правило гейта frame: у каждого SC есть способ измерения
    for sc in of_kind("SC"):
        if not meta_of.get(sc, {}).get("measure"):
            rep.add("warning", "G1", f"у {sc} нет способа измерения (items.{sc}.measure)", defs[sc].path.name)

    # 1. Каждый FR ссылается хотя бы на один SC
    for fr in of_kind("FR"):
        if not [t for t in refs.get(fr, []) if id_type(t) == "SC"]:
            rep.add("error", "R1", f"{fr} не ссылается ни на один SC", defs[fr].path.name)

    # 2. Каждый SC, на который ссылаются FR, имеет EV
    sc_from_fr = {t for fr in of_kind("FR") for t in refs.get(fr, []) if id_type(t) == "SC"}
    sc_with_ev = {t for ev in of_kind("EV") for t in refs.get(ev, []) if id_type(t) == "SC"}
    for sc in sorted(sc_from_fr - sc_with_ev, key=id_num):
        rep.add("error", "R2", f"на {sc} ссылаются FR, но нет EV, которое его измеряет", defs.get(sc, arts[0]).path.name if arts else "")

    # 3. Каждая история ссылается на FR и имеет AC
    for s in of_kind("S"):
        a = defs[s]
        if not [t for t in refs.get(s, []) if id_type(t) == "FR"]:
            rep.add("error", "R3", f"история {s} не ссылается ни на один FR", a.path.name)
        if a.kind == "story" and not AC_RE.search(a.body):
            rep.add("error", "R3", f"у истории {s} нет критериев приёмки (AC1, AC2, …)", a.path.name)

    # Когда в треке ожидаются эпики и истории
    stories_expected = (track == "M" and "spec" in kinds) or (track == "L" and "architecture" in kinds)

    # 4. Эпик Aha существует и стоит первым (треки M и L)
    if track in ("M", "L") and stories_expected:
        epics = of_kind("E")
        if not epics:
            rep.add("error", "R4", "эпиков нет, а в треке " + track + " они уже должны быть")
        else:
            ahas = [e for e in epics if meta_of.get(e, {}).get("aha") is True]
            if not ahas:
                rep.add("error", "R4", "нет эпика Aha Moment (items.E?.aha: true)")
            elif epics[0] not in ahas:
                rep.add("error", "R4", f"эпик Aha ({ahas[0]}) должен стоять первым, первым стоит {epics[0]}", defs[ahas[0]].path.name)

    # 5. У главного открытого A (максимальный приоритет) есть тест и kill-порог
    open_a = [a for a in of_kind("A") if str(meta_of.get(a, {}).get("status", "open")).lower() == "open"]
    top = top_assumption(open_a, meta_of)
    if top:
        if not all(_score(meta_of.get(a, {})) for a in open_a):
            rep.add("warning", "G2", "не у всех открытых A есть оценки p, impact, cost — главное определено неточно", defs[top].path.name)
        missing = [k for k in ("test", "kill") if not meta_of.get(top, {}).get(k)]
        if missing:
            rep.add("error", "R5", f"у главного допущения {top} нет: {', '.join(missing)}", defs[top].path.name)

    # 7. Каждый FR покрыт историей
    if stories_expected:
        covered = {t for s in of_kind("S") for t in refs.get(s, [])}
        for fr in of_kind("FR"):
            if fr not in covered:
                rep.add("error", "R7", f"{fr} не покрыт ни одной историей", defs[fr].path.name)

    # Spec на [head]-Job
    head_spec = 0
    if "spec" in kinds:
        jobs_used = {f"J{id_num(sc)[0]}" for sc in sc_from_fr}
        head_jobs = sorted((j for j in jobs_used if str(meta_of.get(j, {}).get("confidence", "")).lower() == "head"), key=id_num)
        if head_jobs:
            head_spec = 1
            rep.add("warning", "W1", f"spec опирается на Job из головы фаундера: {', '.join(head_jobs)} (+1 к validation debt)", kinds["spec"].path.name)

    # Гейт fs-test: у теста есть дата решения и проверяемое допущение с порогом
    if "test" in kinds:
        tart = kinds["test"]
        date = str(tart.meta.get("decision_date") or "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            rep.add("warning", "G3", "в 03-test.md нет даты решения (decision_date: ГГГГ-ММ-ДД)", tart.path.name)
        tested = _as_list(tart.meta.get("tests"))
        if not tested:
            rep.add("warning", "G3", "в 03-test.md не указано, какое допущение проверяем (tests: [A?])", tart.path.name)
        for a_id in tested:
            if a_id not in defs:
                rep.add("error", "I2", f"03-test.md проверяет несуществующее {a_id}", tart.path.name)
            elif not meta_of.get(a_id, {}).get("kill"):
                rep.add("warning", "G3", f"у проверяемого {a_id} нет kill-порога в 02-rat.md", tart.path.name)

    # 6. Validation debt
    skipped = state.get("skipped_gates") or []
    skipped_n = len(skipped) if isinstance(skipped, list) else 0
    rep.debt = {
        "open_assumptions": len(open_a),
        "skipped_gates": skipped_n,
        "head_spec": head_spec,
        "total": len(open_a) + skipped_n + head_spec,
    }
    rep.counts = {k: len(of_kind(k)) for k in ID_PATTERNS}
    return rep


def _score(props: dict) -> float | None:
    try:
        p, impact, cost = (float(props[k]) for k in ("p", "impact", "cost"))
    except (KeyError, TypeError, ValueError):
        return None
    return p * impact / cost if cost else None


def top_assumption(open_ids: list[str], meta_of: dict) -> str | None:
    """Главное допущение: максимальный приоритет p × impact / cost; при равенстве — меньший номер.
    Допущения без оценок идут после оценённых."""
    if not open_ids:
        return None
    return min(open_ids, key=lambda a: (-(_score(meta_of.get(a, {})) or -1), id_num(a)))


def discover(paths: list[Path]) -> list[Path]:
    out = []
    for p in paths:
        if not p.is_dir():
            continue
        if any(p.glob("*.md")) and re.fullmatch(r"h-\d+", p.name):
            out.append(p)
            continue
        subs = sorted(d for d in p.iterdir() if d.is_dir() and re.fullmatch(r"h-\d+", d.name))
        out.extend(subs or [p])
    return out


def render(rep: Report) -> str:
    lines = [f"■ {rep.hypothesis}  трек: {rep.track or '?'}  ({rep.path})"]
    c = rep.counts
    lines.append("  " + "  ".join(f"{k}:{c[k]}" for k in ID_PATTERNS))
    for f in rep.findings:
        mark = "✗" if f.level == "error" else "!"
        where = f"  [{f.where}]" if f.where else ""
        lines.append(f"  {mark} {f.rule} {f.message}{where}")
    d = rep.debt
    lines.append(
        f"  validation debt: {d['total']} (открытых допущений {d['open_assumptions']}, "
        f"пропущенных гейтов {d['skipped_gates']}, spec на [head] {d['head_spec']})"
    )
    lines.append("  ✓ зелёный" if not rep.errors else f"  ✗ ошибок: {len(rep.errors)}, предупреждений: {len(rep.warnings)}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="FlashStart trace-check")
    ap.add_argument("paths", nargs="*", default=["docs/fs"])
    ap.add_argument("--json", action="store_true", help="вывод в JSON")
    ap.add_argument("--state", type=Path, help="путь к .fs/state.yaml (по умолчанию ищется вверх по дереву)")
    ap.add_argument("--builtin-yaml", action="store_true", help="не использовать PyYAML")
    args = ap.parse_args(argv)

    hdirs = discover([Path(p) for p in args.paths])
    if not hdirs:
        print("гипотез не найдено: " + ", ".join(args.paths), file=sys.stderr)
        return 2
    reports = [check_hypothesis(h, args.state, args.builtin_yaml) for h in hdirs]
    if args.json:
        print(json.dumps([r.as_dict() for r in reports], ensure_ascii=False, indent=2))
    else:
        print("\n\n".join(render(r) for r in reports))
    return 1 if any(r.errors for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
