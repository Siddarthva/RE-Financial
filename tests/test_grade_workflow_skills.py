"""The flux-explanations and client-questions graders pass the real sample and fail each seeded defect."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "03_evals"))
import grade_workflow_skills as g  # noqa: E402

D = ROOT / "outputs" / "abc"
M = "2026-06"
FLUX = json.loads((D / f"flux_{M}.json").read_text(encoding="utf-8"))
REVIEW = json.loads((D / f"review_{M}.json").read_text(encoding="utf-8"))
PACKET = json.loads((D / f"review_packet_{M}.json").read_text(encoding="utf-8"))
FLUX_TXT = (D / f"flux_explanations_{M}.md").read_text(encoding="utf-8")
Q_TXT = (D / f"client_questions_{M}.md").read_text(encoding="utf-8")


def has(problems, needle):
    return any(needle in p for p in problems)


class FluxExplanations(unittest.TestCase):
    def test_sample_passes(self):
        self.assertEqual(g.grade_flux(FLUX_TXT, FLUX), [])

    def test_wrong_number(self):
        self.assertTrue(has(g.grade_flux(FLUX_TXT.replace("29,294.58", "29,924.58"), FLUX), "numbers not in the flux file"))

    def test_causal_word(self):
        txt = FLUX_TXT.replace("a change of +17,970.67", "a change of +17,970.67 because of a conference")
        self.assertTrue(has(g.grade_flux(txt, FLUX), "causal wording"))

    def test_two_questions(self):
        txt = FLUX_TXT.replace("and does it recur?", "and does it recur? Who approved it?")
        self.assertTrue(has(g.grade_flux(txt, FLUX), "exactly one question"))

    def test_no_question(self):
        self.assertTrue(has(g.grade_flux(FLUX_TXT.replace("and does it recur?", "and it recurs."), FLUX), "exactly one question"))

    def test_missing_item_and_missing_source_cell(self):
        lines = FLUX_TXT.splitlines()
        self.assertTrue(has(g.grade_flux("\n".join(l for l in lines if not l.startswith("5.")), FLUX), "Sales Commission: expected 1"))
        self.assertTrue(has(g.grade_flux(FLUX_TXT.replace("Income Statement!C31", "somewhere"), FLUX), "source cell"))


class ClientQuestions(unittest.TestCase):
    def grade(self, txt):
        return g.grade_questions(txt, FLUX, REVIEW, PACKET)

    def test_sample_passes(self):
        self.assertEqual(self.grade(Q_TXT), [])

    def test_untraceable_source(self):
        self.assertTrue(has(self.grade(Q_TXT.replace("flux:Sales Commission", "flux:Rent")), "traces to no flagged item"))

    def test_uncovered_flagged_item_and_reviewer_question(self):
        rows = [l for l in Q_TXT.splitlines()]
        self.assertTrue(has(self.grade("\n".join(l for l in rows if "| 4 |" not in l)), "flagged item not requested: Marketing"))
        self.assertTrue(has(self.grade("\n".join(l for l in rows if "| 6 |" not in l)), "reviewer question 3 not requested"))
        self.assertTrue(has(self.grade("\n".join(l for l in rows if "| 8 |" not in l)), "cash flag"))

    def test_duplicate_row(self):
        rows = Q_TXT.splitlines()
        dup = next(l for l in rows if l.startswith("| 3 |"))
        self.assertTrue(has(self.grade(Q_TXT + "\n" + dup.replace("| 3 |", "| 8 |")), "duplicate"))

    def test_priority_follows_materiality(self):
        self.assertTrue(has(self.grade(Q_TXT.replace("| Medium |\n| 4 ", "| High |\n| 4 ", 1)), "materiality rule"))
        self.assertTrue(has(self.grade(Q_TXT.replace("Event invoices and the events calendar for June | High", "Event invoices and the events calendar for June | Medium")), "materiality rule"))

    def test_wrong_number_and_causal_word(self):
        self.assertTrue(has(self.grade(Q_TXT.replace("13,126.41", "13,162.41")), "numbers not in"))
        self.assertTrue(has(self.grade(Q_TXT.replace("may reverse next month", "may reverse because of timing")), "causal wording"))


if __name__ == "__main__":
    unittest.main()
