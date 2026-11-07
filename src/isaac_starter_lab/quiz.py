"""Knowledge-check grading.

The question bank contains only sha256 hashes of normalised answers and a
per-question explanation, so reading the YAML does not reveal the answers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import yaml

__all__ = ["grade_answers", "load_questions", "normalize_answer", "run_quiz_command"]


def normalize_answer(value: object) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .,;:!?'\"`")


def _hash(value: object) -> str:
    return hashlib.sha256(normalize_answer(value).encode("utf-8")).hexdigest()


def load_questions(path: str | Path) -> list[dict]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "questions" not in data:
        raise ValueError("question bank must be a mapping with a 'questions' list")
    questions = data["questions"]
    if not isinstance(questions, list) or not questions:
        raise ValueError("question bank must contain at least one question")
    seen = set()
    for question in questions:
        for key in ("id", "prompt", "answer_sha256", "explanation"):
            if key not in question:
                raise ValueError(f"question {question.get('id', '?')} is missing {key!r}")
        if question["id"] in seen:
            raise ValueError(f"duplicate question id {question['id']!r}")
        seen.add(question["id"])
        hashes = question["answer_sha256"]
        if isinstance(hashes, str):
            hashes = [hashes]
        if not hashes or any(not re.fullmatch(r"[0-9a-f]{64}", str(h)) for h in hashes):
            raise ValueError(f"question {question['id']} has an invalid answer hash")
    return questions


def grade_answers(questions: list[dict], answers: dict) -> dict:
    results = []
    correct_count = 0
    for question in questions:
        given = answers.get(question["id"], "")
        hashes = question["answer_sha256"]
        if isinstance(hashes, str):
            hashes = [hashes]
        correct = bool(normalize_answer(given)) and _hash(given) in hashes
        if correct:
            correct_count += 1
        results.append(
            {
                "id": question["id"],
                "correct": correct,
                "answered": bool(normalize_answer(given)),
                "explanation": question["explanation"],
            }
        )
    total = len(questions)
    return {
        "schema": "isaac_starter_lab.quiz_result.v1",
        "score": correct_count,
        "total": total,
        "percent": 100.0 * correct_count / total if total else 0.0,
        "results": results,
    }


def run_quiz_command(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    questions_path = Path(args.questions)
    if not questions_path.is_absolute():
        questions_path = root / questions_path
    answers_path = Path(args.answers)
    if not answers_path.is_absolute():
        answers_path = root / answers_path
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out

    questions = load_questions(questions_path)
    raw = yaml.safe_load(answers_path.read_text(encoding="utf-8")) or {}
    answers = raw.get("answers", raw) if isinstance(raw, dict) else {}
    if not isinstance(answers, dict):
        raise ValueError("answers file must contain a mapping of question id to answer")
    result = grade_answers(questions, answers)

    print(f"knowledge checks: {len(questions)} questions")
    for entry in result["results"]:
        status = "PASS" if entry["correct"] else "FAIL"
        print(f"  {entry['id']}: {status} - {entry['explanation']}")
    print(f"score: {result['score']}/{result['total']} ({result['percent']:.1f}%)")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"result: {out}")
    return 0
