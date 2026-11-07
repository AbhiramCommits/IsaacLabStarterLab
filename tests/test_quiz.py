"""Knowledge-check grading tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from isaac_starter_lab.cli import build_quiz_parser, run_quiz
from isaac_starter_lab.quiz import (
    grade_answers,
    load_questions,
    normalize_answer,
)

ROOT = Path(__file__).resolve().parents[1]
CORRECT = {
    "q1": "A",
    "q2": "A",
    "q3": "C",
    "q4": "backproject_to_plane",
    "q5": "A",
    "q6": "D",
    "q7": "B",
    "q8": "LIFT",
}


def test_bank_contains_hashes_not_answers():
    data = yaml.safe_load((ROOT / "lab" / "knowledge_checks.yaml").read_text())
    assert data["schema"] == "isaac_starter_lab.knowledge_checks.v1"
    assert len(data["questions"]) == 8
    for question in data["questions"]:
        assert "answer" not in question
        assert "answers" not in question
        assert all(len(value) == 64 for value in question["answer_sha256"])
        assert question["explanation"]
    types = {question["type"] for question in data["questions"]}
    assert types == {"multiple_choice", "short_answer"}


def test_normalisation_is_forgiving_but_deterministic():
    assert normalize_answer("  LIFT.  ") == "lift"
    assert normalize_answer("A") == "a"
    assert normalize_answer("  backproject_to_plane ") == normalize_answer("backproject_to_plane")


def test_correct_answers_score_full_marks():
    questions = load_questions(ROOT / "lab" / "knowledge_checks.yaml")
    result = grade_answers(questions, CORRECT)
    assert result["score"] == 8
    assert result["total"] == 8
    assert all(entry["correct"] for entry in result["results"])


def test_wrong_and_missing_answers_fail():
    questions = load_questions(ROOT / "lab" / "knowledge_checks.yaml")
    result = grade_answers(questions, {"q1": "B"})
    assert result["score"] == 0  # q1 is wrong and all missing answers are wrong
    assert result["results"][0]["correct"] is False
    assert result["results"][1]["answered"] is False
    assert grade_answers(questions, {})["score"] == 0


def test_quiz_command_writes_result(tmp_path, monkeypatch):
    answers = tmp_path / "answers.yaml"
    answers.write_text(yaml.safe_dump({"answers": CORRECT}))
    monkeypatch.chdir(ROOT)
    args = build_quiz_parser().parse_args(
        ["--answers", str(answers), "--out", str(tmp_path / "quiz.json")]
    )
    assert run_quiz(args) == 0
    payload = json.loads((tmp_path / "quiz.json").read_text())
    assert payload["score"] == 8
    assert payload["percent"] == 100.0


def test_invalid_bank_is_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump({"questions": [{"id": "q1", "prompt": "x"}]}))
    with pytest.raises(ValueError, match="missing"):
        load_questions(bad)


def test_duplicate_ids_are_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    question = {
        "id": "q1",
        "prompt": "x",
        "answer_sha256": ["0" * 64],
        "explanation": "x",
    }
    bad.write_text(yaml.safe_dump({"questions": [question, question]}))
    with pytest.raises(ValueError, match="duplicate"):
        load_questions(bad)
