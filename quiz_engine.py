"""
Quizeru — quiz engine wired to LaMa AI's knowledge base.

Modes: easy (5 soal), medium (10 soal), hard (15 soal) — per spec §24.
Questions are drawn from the tagged question bank in materi.json
(difficulty: easy/medium/hard), shuffled, with answer position randomized
and no repeats within a single quiz session (tracked per-session in memory).
"""
import random
from typing import Optional

import knowledge

MODE_COUNTS = {"easy": 5, "medium": 10, "hard": 15}


def _pool_for_mode(lang: str, mode: str) -> list:
    bank = knowledge.quiz_bank(lang)
    if mode == "easy":
        # Mostly easy, top up with medium if the bank is short.
        primary = [q for q in bank if q["difficulty"] == "easy"]
        fallback = [q for q in bank if q["difficulty"] == "medium"]
    elif mode == "hard":
        primary = [q for q in bank if q["difficulty"] == "hard"]
        fallback = [q for q in bank if q["difficulty"] in ("medium", "easy")]
    else:  # medium
        primary = [q for q in bank if q["difficulty"] in ("easy", "medium")]
        fallback = [q for q in bank if q["difficulty"] == "hard"]
    random.shuffle(primary)
    random.shuffle(fallback)
    return primary + fallback


def _shuffle_options(q: dict) -> dict:
    options = list(enumerate(q["options"]))
    random.shuffle(options)
    new_options = [text for _, text in options]
    new_correct = next(i for i, (orig_idx, _) in enumerate(options) if orig_idx == q["correct"])
    return {
        "id": q["id"],
        "section": q["section"],
        "difficulty": q["difficulty"],
        "question": q["q"],
        "options": new_options,
        "correctIndex": new_correct,
        "explain": q["explain"],
    }


def start_quiz(lang: str, mode: str) -> dict:
    mode = mode if mode in MODE_COUNTS else "easy"
    count = MODE_COUNTS[mode]
    pool = _pool_for_mode(lang, mode)
    chosen = pool[:count]
    questions = [_shuffle_options(q) for q in chosen]
    return {
        "mode": mode,
        "totalQuestions": len(questions),
        "questions": questions,          # includes correctIndex — quiz.answer still re-validates server-side by id
        "usedIds": [q["id"] for q in questions],
    }


def find_question_by_id(lang: str, question_id: str) -> Optional[dict]:
    for q in knowledge.quiz_bank(lang):
        if q["id"] == question_id:
            return q
    return None


def section_title_for(lang: str, section_number: int) -> str:
    s = knowledge.get_section_by_number(lang, section_number)
    return s["title"] if s else str(section_number)


def evaluate_answer(lang: str, question_id: str, selected_index: int) -> dict:
    """Re-validates against the source of truth (not client-supplied
    correctIndex) so answers can't be spoofed from the frontend."""
    q = find_question_by_id(lang, question_id)
    if not q:
        return {"error": "question_not_found"}
    correct = selected_index == q["correct"]
    return {
        "correct": correct,
        "correctIndex": q["correct"],
        "correctText": q["options"][q["correct"]],
        "explain": q["explain"],
        "sectionNumber": q["section"],
        "sectionTitle": section_title_for(lang, q["section"]),
    }


def score_category(score_pct: float, lang: str) -> str:
    if lang == "id":
        if score_pct >= 90:
            return "Luar Biasa"
        if score_pct >= 75:
            return "Sangat Baik"
        if score_pct >= 60:
            return "Baik"
        if score_pct >= 40:
            return "Cukup"
        return "Perlu Belajar Lagi"
    if score_pct >= 90:
        return "Outstanding"
    if score_pct >= 75:
        return "Great"
    if score_pct >= 60:
        return "Good"
    if score_pct >= 40:
        return "Fair"
    return "Needs Review"


def build_result_summary(lang: str, mode: str, correct: int, wrong: int, wrong_topics: list) -> dict:
    total = correct + wrong
    pct = round((correct / total) * 100) if total else 0
    top_wrong = None
    if wrong_topics:
        top_wrong = max(set(wrong_topics), key=wrong_topics.count)
    return {
        "mode": mode,
        "correct": correct,
        "wrong": wrong,
        "total": total,
        "score": pct,
        "category": score_category(pct, lang),
        "wrongTopics": sorted(set(wrong_topics)),
        "mostMissedTopic": top_wrong,
    }


def adaptive_recommendation(lang: str, quiz_stats: dict) -> Optional[str]:
    """quiz_stats: {section_title: wrong_count}. Recommends revisiting the
    section the user has missed most across quiz sessions (spec §31)."""
    if not quiz_stats:
        return None
    topic, count = max(quiz_stats.items(), key=lambda kv: kv[1])
    if count < 2:
        return None
    if lang == "id":
        return f"Konsep '{topic}' masih sering keliru. Materi tersebut dapat dipelajari kembali sebelum mencoba quiz berikutnya."
    return f"The concept '{topic}' is still often missed. Consider reviewing that material before trying the next quiz."
