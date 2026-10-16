"""Тесты scripts/trace-check.py. Запуск: python3 -m unittest discover tests"""
import importlib.util
import io
import json
import re
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("trace_check", ROOT / "scripts" / "trace-check.py")
tc = importlib.util.module_from_spec(_spec)
sys.modules["trace_check"] = tc
_spec.loader.exec_module(tc)

try:
    import yaml  # noqa: F401

    HAVE_PYYAML = True
except ImportError:
    HAVE_PYYAML = False


def fm(meta: str, body: str = "") -> str:
    return "---\n" + textwrap.dedent(meta).strip() + "\n---\n" + textwrap.dedent(body)


FRAME = fm("""
    fs: frame
    hypothesis: h-001
    ids: [J1, J2, SC1.1, SC1.2]
    refs: {SC1.1: [J1], SC1.2: [J1]}
    items:
      J1: {level: core, confidence: interview}
      J2: {level: big, confidence: interview}
      SC1.1: {measure: "время до результата < 5 мин"}
      SC1.2: {measure: "≥ 3 повторных визита за неделю"}
    """)
RAT = fm("""
    fs: rat
    hypothesis: h-001
    ids: [A1, A2]
    refs: {A1: [J1]}
    items:
      A1: {status: open, p: 4, impact: 5, cost: 1, test: "10 писем", kill: "< 2 ответов"}
      A2: {status: confirmed}
    track: M
    """)
SPEC = fm("""
    fs: spec
    hypothesis: h-001
    ids: [FR1, FR2, EV1, EV2]
    refs: {FR1: [SC1.1], FR2: [SC1.2], EV1: [SC1.1], EV2: [SC1.2]}
    """)
EPIC1 = fm("""
    fs: epic
    hypothesis: h-001
    ids: [E1]
    refs: {E1: [FR1]}
    items:
      E1: {aha: true}
    """)
EPIC2 = fm("""
    fs: epic
    hypothesis: h-001
    ids: [E2]
    refs: {E2: [FR2]}
    """)
STORY11 = fm("""
    fs: story
    hypothesis: h-001
    ids: [S1.1]
    refs: {S1.1: [FR1, EV1]}
    """, """
    # S1.1
    - **AC1** Дано пустой список, когда пользователь добавляет запись, тогда она видна.
    """)
STORY21 = fm("""
    fs: story
    hypothesis: h-001
    ids: [S2.1]
    refs: {S2.1: [FR2]}
    """, """
    - **AC1** Given a user, when they return, then the list is kept.
    """)


def green_files():
    return {
        "01-frame.md": FRAME,
        "02-rat.md": RAT,
        "04-spec.md": SPEC,
        "stories/E1.md": EPIC1,
        "stories/E2.md": EPIC2,
        "stories/S1.1.md": STORY11,
        "stories/S2.1.md": STORY21,
    }


class Base(unittest.TestCase):
    builtin = False

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.hdir = self.root / "docs" / "fs" / "h-001"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, files: dict, state: str | None = None):
        for name, text in files.items():
            p = self.hdir / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        if state is not None:
            (self.root / ".fs").mkdir(exist_ok=True)
            (self.root / ".fs" / "state.yaml").write_text(textwrap.dedent(state), encoding="utf-8")

    def check(self, files=None, state=None):
        self.write(files if files is not None else green_files(), state)
        return tc.check_hypothesis(self.hdir, force_builtin=self.builtin)

    def rules(self, rep, level="error"):
        return sorted({f.rule for f in rep.findings if f.level == level})


class GreenPath(Base):
    def test_green_hypothesis_has_no_errors(self):
        rep = self.check()
        self.assertEqual(rep.errors, [], [f.message for f in rep.errors])
        self.assertEqual(rep.track, "M")
        self.assertEqual(rep.counts["FR"], 2)
        self.assertEqual(rep.debt, {"open_assumptions": 1, "skipped_gates": 0, "head_spec": 0, "total": 1})


class TraceRules(Base):
    def test_r1_fr_without_sc(self):
        files = green_files()
        files["04-spec.md"] = SPEC.replace("FR2: [SC1.2], ", "")
        rep = self.check(files)
        self.assertIn("R1", self.rules(rep))

    def test_r2_sc_without_ev(self):
        files = green_files()
        files["04-spec.md"] = SPEC.replace(", EV2: [SC1.2]", "")
        rep = self.check(files)
        self.assertIn("R2", self.rules(rep))
        self.assertTrue(any("SC1.2" in f.message for f in rep.errors))

    def test_r3_story_without_fr(self):
        files = green_files()
        files["stories/S1.1.md"] = STORY11.replace("refs: {S1.1: [FR1, EV1]}", "refs: {S1.1: [EV1]}")
        rep = self.check(files)
        self.assertIn("R3", self.rules(rep))

    def test_r3_story_without_ac(self):
        files = green_files()
        files["stories/S2.1.md"] = STORY21.replace("**AC1** ", "")
        rep = self.check(files)
        self.assertIn("R3", self.rules(rep))

    def test_r4_no_aha_epic(self):
        files = green_files()
        files["stories/E1.md"] = EPIC1.replace("items:\n  E1: {aha: true}\n", "")
        rep = self.check(files)
        self.assertIn("R4", self.rules(rep))

    def test_r4_aha_not_first(self):
        files = green_files()
        files["stories/E1.md"] = EPIC1.replace("{aha: true}", "{aha: false}")
        files["stories/E2.md"] = EPIC2.replace("refs: {E2: [FR2]}", "refs: {E2: [FR2]}\nitems:\n  E2: {aha: true}")
        rep = self.check(files)
        self.assertIn("R4", self.rules(rep))
        self.assertTrue(any("первым" in f.message for f in rep.errors))

    def test_r4_epics_missing_when_expected(self):
        files = {k: v for k, v in green_files().items() if not k.startswith("stories/")}
        rep = self.check(files)
        self.assertIn("R4", self.rules(rep))
        self.assertIn("R7", self.rules(rep))

    def test_r5_open_assumption_without_kill(self):
        files = green_files()
        files["02-rat.md"] = RAT.replace(', kill: "< 2 ответов"', "")
        rep = self.check(files)
        self.assertIn("R5", self.rules(rep))

    def test_r5_default_status_is_open(self):
        files = green_files()
        files["02-rat.md"] = RAT.replace("A2: {status: confirmed}", "A2: {p: 2}")
        rep = self.check(files)
        self.assertEqual(rep.debt["open_assumptions"], 2)
        self.assertNotIn("R5", self.rules(rep))
        self.assertIn("G2", self.rules(rep, "warning"))

    def test_r5_only_top_assumption_checked(self):
        files = green_files()
        files["02-rat.md"] = RAT.replace("A2: {status: confirmed}", "A2: {status: open, p: 2, impact: 2, cost: 4}")
        rep = self.check(files)
        self.assertNotIn("R5", self.rules(rep))
        self.assertNotIn("G2", self.rules(rep, "warning"))

    def test_r5_top_is_highest_priority_not_lowest_number(self):
        files = green_files()
        files["02-rat.md"] = RAT.replace(
            "A2: {status: confirmed}", "A2: {status: open, p: 5, impact: 5, cost: 1}"
        )
        rep = self.check(files)
        self.assertIn("R5", self.rules(rep))
        self.assertTrue(any("A2" in f.message for f in rep.errors))

    def test_top_assumption_tie_breaks_by_number(self):
        meta = {"A3": {"p": 2, "impact": 2, "cost": 1}, "A1": {"p": 4, "impact": 1, "cost": 1}, "A2": {}}
        self.assertEqual(tc.top_assumption(["A3", "A1", "A2"], meta), "A1")
        self.assertEqual(tc.top_assumption(["A2"], meta), "A2")
        self.assertIsNone(tc.top_assumption([], meta))

    def test_r7_fr_not_covered(self):
        files = green_files()
        del files["stories/S2.1.md"]
        rep = self.check(files)
        self.assertEqual(self.rules(rep), ["R7"])

    def test_track_l_expects_stories_only_after_architecture(self):
        files = {k: v for k, v in green_files().items() if not k.startswith("stories/")}
        files["02-rat.md"] = RAT.replace("track: M", "track: L")
        rep = self.check(files)
        self.assertEqual(rep.errors, [])
        files["05-architecture.md"] = fm("fs: architecture\nhypothesis: h-001\nids: []")
        rep = self.check(files)
        self.assertIn("R7", self.rules(rep))

    def test_track_s_skips_epic_rules(self):
        files = {"01-frame.md": FRAME, "02-rat.md": RAT.replace("track: M", "track: S")}
        rep = self.check(files)
        self.assertEqual(rep.errors, [])

    def test_dropped_fr_ignored(self):
        files = green_files()
        files["04-spec.md"] = SPEC.replace("ids: [FR1, FR2, EV1, EV2]", "ids: [FR1, FR2, FR3, EV1, EV2]") + ""
        files["04-spec.md"] = files["04-spec.md"].replace("---\n", "---\n", 1).replace(
            "refs:", "items:\n  FR3: {status: dropped}\nrefs:"
        )
        rep = self.check(files)
        self.assertEqual(rep.errors, [], [f.message for f in rep.errors])

    def test_track_from_state_when_rat_has_none(self):
        files = green_files()
        files["02-rat.md"] = RAT.replace("track: M\n", "")
        rep = self.check(files, state="hypothesis: h-001\ntrack: L\n")
        self.assertEqual(rep.track, "L")


class TestArtifact(Base):
    TEST = fm("""
        fs: test
        hypothesis: h-001
        ids: []
        tests: [A1]
        decision_date: 2026-11-01
        """)

    def files(self, test_text):
        return {"01-frame.md": FRAME, "02-rat.md": RAT.replace("track: M", "track: S"), "03-test.md": test_text}

    def test_green(self):
        rep = self.check(self.files(self.TEST))
        self.assertEqual(rep.findings, [])

    def test_placeholder_date_warns(self):
        rep = self.check(self.files(self.TEST.replace("2026-11-01", "YYYY-MM-DD")))
        self.assertIn("G3", self.rules(rep, "warning"))
        self.assertEqual(rep.errors, [])

    def test_unknown_assumption_is_error(self):
        rep = self.check(self.files(self.TEST.replace("tests: [A1]", "tests: [A9]")))
        self.assertIn("I2", self.rules(rep))

    def test_tested_assumption_without_kill_warns(self):
        files = self.files(self.TEST.replace("tests: [A1]", "tests: [A2]"))
        rep = self.check(files)
        self.assertIn("G3", self.rules(rep, "warning"))


class Debt(Base):
    def test_debt_counts_skipped_gates_and_head_spec(self):
        files = green_files()
        files["01-frame.md"] = FRAME.replace("J1: {level: core, confidence: interview}", "J1: {level: core, confidence: head}")
        state = """
            hypothesis: h-001
            track: M
            skipped_gates:
              - {gate: fs-rat, reason: "нет времени"}
              - {gate: fs-design}
        """
        rep = self.check(files, state)
        self.assertEqual(rep.debt, {"open_assumptions": 1, "skipped_gates": 2, "head_spec": 1, "total": 4})
        self.assertIn("W1", self.rules(rep, "warning"))

    def test_state_of_other_hypothesis_ignored(self):
        rep = self.check(state="hypothesis: h-002\nskipped_gates: [x, y]\n")
        self.assertEqual(rep.debt["skipped_gates"], 0)


class Integrity(Base):
    def test_duplicate_id(self):
        files = green_files()
        files["stories/E2.md"] = EPIC2.replace("ids: [E2]", "ids: [E1]").replace("{E2:", "{E1:")
        rep = self.check(files)
        self.assertIn("I1", self.rules(rep))

    def test_dangling_ref(self):
        files = green_files()
        files["04-spec.md"] = SPEC.replace("FR1: [SC1.1]", "FR1: [SC1.1, SC9.9]")
        rep = self.check(files)
        self.assertIn("I2", self.rules(rep))

    def test_bad_id_format(self):
        files = green_files()
        files["04-spec.md"] = SPEC.replace("ids: [FR1,", "ids: [FR-1, FR1,")
        rep = self.check(files)
        self.assertIn("I3", self.rules(rep))

    def test_sc_without_job(self):
        files = green_files()
        files["01-frame.md"] = FRAME.replace("ids: [J1, J2, SC1.1, SC1.2]", "ids: [J1, J2, SC1.1, SC1.2, SC3.1]")
        rep = self.check(files)
        self.assertIn("I4", self.rules(rep))

    def test_wrong_ref_type(self):
        files = green_files()
        files["04-spec.md"] = SPEC.replace("FR1: [SC1.1]", "FR1: [SC1.1, J1]")
        rep = self.check(files)
        self.assertIn("I5", self.rules(rep))

    def test_broken_frontmatter_is_a_finding(self):
        files = green_files()
        files["04-spec.md"] = "---\nfs: spec\nids: [FR1\n---\n"
        rep = self.check(files)
        self.assertIn("I0", self.rules(rep))

    def test_sc_without_measure_warns(self):
        files = green_files()
        files["01-frame.md"] = FRAME.replace('SC1.2: {measure: "≥ 3 повторных визита за неделю"}', "SC1.2: {}")
        rep = self.check(files)
        self.assertIn("G1", self.rules(rep, "warning"))
        self.assertEqual(rep.errors, [])


class BuiltinYamlVariants(GreenPath, TraceRules, TestArtifact, Debt, Integrity):
    """Те же сценарии без PyYAML."""

    builtin = True


class MiniYaml(unittest.TestCase):
    def test_flow_and_block(self):
        text = textwrap.dedent("""
            fs: spec   # комментарий
            ids: [FR1, "FR2"]
            refs: {FR1: [SC1.1, SC1.2], FR2: []}
            items:
              A1: {status: open, test: "письма # не комментарий", kill: 'порог: 2'}
              E1:
                aha: true
            list:
              - a
              - {gate: x}
            empty:
            n: 3
            f: 1.5
        """)
        self.assertEqual(
            tc.mini_yaml(text),
            {
                "fs": "spec",
                "ids": ["FR1", "FR2"],
                "refs": {"FR1": ["SC1.1", "SC1.2"], "FR2": []},
                "items": {"A1": {"status": "open", "test": "письма # не комментарий", "kill": "порог: 2"}, "E1": {"aha": True}},
                "list": ["a", {"gate": "x"}],
                "empty": None,
                "n": 3,
                "f": 1.5,
            },
        )

    def test_ids_stay_strings(self):
        self.assertEqual(tc.mini_yaml("ids: [SC1.1, S2.3]")["ids"], ["SC1.1", "S2.3"])

    def test_errors(self):
        for bad in ("ids: [FR1", "refs: {FR1 [x]}", "a: 1\n   b: 2"):
            with self.assertRaises(tc.YamlError, msg=bad):
                tc.mini_yaml(bad)


class Templates(unittest.TestCase):
    TEMPLATES = sorted((ROOT / "skills").rglob("*template*.md"))

    def frontmatter(self, path):
        m = tc.FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
        return m.group(1) if m else None

    def test_templates_exist(self):
        names = {p.relative_to(ROOT / "skills").as_posix() for p in self.TEMPLATES}
        for expected in (
            "fs-frame/template.md", "fs-rat/template.md", "fs-test/template.md", "fs-spec/template.md",
            "fs-spec/product-md.template.md", "fs-plan/architecture.template.md", "fs-plan/epic.template.md",
            "fs-plan/story.template.md", "fs-design/design-md.template.md", "fs-ship/template.md",
            "fs-learn/template.md",
        ):
            self.assertIn(expected, names)

    def test_frontmatter_parses_with_builtin_parser(self):
        for p in self.TEMPLATES:
            fmtext = self.frontmatter(p)
            if fmtext is None:
                continue
            with self.subTest(template=p.name):
                data = tc.mini_yaml(fmtext)
                self.assertIsInstance(data, dict)
                if HAVE_PYYAML:
                    import yaml

                    self.assertEqual(data, yaml.safe_load(fmtext))

    def test_artifact_templates_declare_type_and_valid_ids(self):
        for p in self.TEMPLATES:
            if p.name in ("design-md.template.md", "project-context.template.md"):
                continue
            with self.subTest(template=p.name):
                data = tc.mini_yaml(self.frontmatter(p))
                self.assertIn("fs", data)
                for ident in data.get("ids") or []:
                    self.assertIsNotNone(tc.id_type(ident), ident)

    def test_design_md_uses_only_spec_keys(self):
        data = tc.mini_yaml(self.frontmatter(ROOT / "skills/fs-design/design-md.template.md"))
        allowed = {"version", "name", "description", "omitted", "colors", "typography", "rounded", "spacing", "components"}
        self.assertLessEqual(set(data), allowed)
        self.assertIn("primary", data["colors"])

    def test_product_md_has_platform(self):
        text = (ROOT / "skills/fs-spec/product-md.template.md").read_text(encoding="utf-8")
        lines = [ln.strip() for ln in text.splitlines()]
        i = lines.index("## Platform")
        nxt = next(ln for ln in lines[i + 1:] if ln)
        self.assertIn(nxt, {"web", "ios", "android", "adaptive"})

    def test_state_template(self):
        data = tc.mini_yaml((ROOT / "skills/fs/state.template.yaml").read_text(encoding="utf-8"))
        self.assertEqual(set(data), {"hypothesis", "track", "stage", "validation_debt", "skipped_gates", "next"})


class Skills(unittest.TestCase):
    def test_skill_files_valid(self):
        for p in sorted((ROOT / "skills").glob("*/SKILL.md")):
            with self.subTest(skill=p.parent.name):
                text = p.read_text(encoding="utf-8")
                self.assertLessEqual(len(text.splitlines()), 300)
                m = tc.FRONTMATTER_RE.match(text)
                self.assertIsNotNone(m)
                data = tc.mini_yaml(m.group(1))
                self.assertEqual(data["name"], p.parent.name)
                self.assertTrue(data.get("description"))
                for ref in re.findall(r"`(references/[\w.-]+|[\w.-]*template[\w.-]*)`", text):
                    self.assertTrue((p.parent / ref).exists() or (ROOT / "skills/fs" / ref).exists(), ref)


class Cli(Base):
    def run_cli(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = tc.main(list(args))
        return code, buf.getvalue()

    def test_green_exit_zero_and_discovers_parent(self):
        self.write(green_files())
        code, out = self.run_cli(str(self.root / "docs" / "fs"))
        self.assertEqual(code, 0)
        self.assertIn("зелёный", out)

    def test_errors_exit_one_json(self):
        files = green_files()
        del files["stories/S2.1.md"]
        self.write(files)
        code, out = self.run_cli(str(self.hdir), "--json")
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertFalse(data[0]["ok"])
        self.assertEqual(data[0]["findings"][0]["rule"], "R7")

    def test_no_hypotheses(self):
        code, _ = self.run_cli(str(self.root / "nothing"))
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
