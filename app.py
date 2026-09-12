"""
Laboratorium Maya — Backend (FastAPI)

Wires together: LaMa AI (lama_engine), Quizeru (quiz_engine), the knowledge
base (knowledge.py), the AI provider abstraction (ai_provider.py), and
session memory (memory.py) behind a small REST API that index.html talks to
over fetch().

Run locally:
    uvicorn app:app --reload --port 8000
"""
import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import knowledge
import lama_engine
import memory as memory_mod
import quiz_engine

app = FastAPI(title="Laboratorium Maya API", version="1.0.0")

# ------------------------------------------------------------------
# CORS — dev defaults to localhost; production origins come from env
# ------------------------------------------------------------------
_default_dev_origins = [
    "http://localhost:5500", "http://127.0.0.1:5500",
    "http://localhost:3000", "http://127.0.0.1:3000",
    "http://localhost:8000", "http://127.0.0.1:8000",
    "http://localhost:8080", "http://127.0.0.1:8080",
    "null",  # index.html opened directly as a file:// origin
]
_env_origins = os.getenv("CORS_ORIGINS", "")
allow_origins = [o.strip() for o in _env_origins.split(",") if o.strip()] or _default_dev_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSION_COOKIE = "lm_session"


def _get_or_create_session(session_id: Optional[str], response: Response) -> str:
    if not session_id:
        session_id = memory_mod.new_session_id()
    response.set_cookie(SESSION_COOKIE, session_id, max_age=60 * 60 * 24 * 30, samesite="lax")
    return session_id


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str
    lang: str = "id"
    session_id: Optional[str] = None


class MemoryUpdateRequest(BaseModel):
    session_id: Optional[str] = None
    patch: dict


class QuizStartRequest(BaseModel):
    mode: str = "easy"
    lang: str = "id"
    session_id: Optional[str] = None


class QuizAnswerRequest(BaseModel):
    question_id: str
    selected_index: int
    lang: str = "id"
    session_id: Optional[str] = None


class QuizFinishRequest(BaseModel):
    mode: str
    correct: int
    wrong: int
    wrong_topics: list[str] = []
    lang: str = "id"
    session_id: Optional[str] = None


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------
@app.get("/api/health")
def health():
    import ai_provider as aip
    return {
        "status": "ok",
        "service": "Laboratorium Maya Backend",
        "ai_provider": aip.AI_PROVIDER,
        "ai_provider_ready": aip.provider_available(),
    }


# ------------------------------------------------------------------
# Material (knowledge base)
# ------------------------------------------------------------------
@app.get("/api/material")
def get_material(lang: str = "id"):
    lang = lang if lang in ("id", "en") else "id"
    return {"sections": knowledge.sections(lang)}


@app.get("/api/material/{section_id}")
def get_material_section(section_id: str, lang: str = "id"):
    lang = lang if lang in ("id", "en") else "id"
    section = knowledge.get_section_by_id(lang, section_id) or knowledge.get_section_by_number(
        lang, int(section_id) if section_id.isdigit() else -1
    )
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    return section


# ------------------------------------------------------------------
# Chat (LaMa AI)
# ------------------------------------------------------------------
@app.post("/api/chat")
def chat(req: ChatRequest, response: Response):
    lang = req.lang if req.lang in ("id", "en") else "id"
    session_id = _get_or_create_session(req.session_id, response)
    mem = memory_mod.get_memory(session_id)
    mem["lang"] = lang

    memory_mod.append_message(mem, "user", req.message)
    result = lama_engine.answer_question(req.message, mem, lang)
    memory_mod.append_message(mem, "assistant", result["text"])
    memory_mod.save_memory(session_id, mem)

    return {
        "session_id": session_id,
        "text": result["text"],
        "sectionNumber": result.get("sectionNumber"),
        "sectionTitle": result.get("sectionTitle"),
    }


# ------------------------------------------------------------------
# Memory
# ------------------------------------------------------------------
@app.get("/api/memory")
def read_memory(session_id: str):
    mem = memory_mod.get_memory(session_id)
    return mem


@app.post("/api/memory")
def update_memory(req: MemoryUpdateRequest, response: Response):
    session_id = _get_or_create_session(req.session_id, response)
    mem = memory_mod.get_memory(session_id)
    # only allow known, non-sensitive keys to be patched from the client
    allowed_keys = {"lang", "userName", "instructionStyle"}
    for k, v in req.patch.items():
        if k in allowed_keys:
            mem[k] = v
    memory_mod.save_memory(session_id, mem)
    return {"session_id": session_id, "memory": mem}


@app.delete("/api/memory")
def clear_memory(session_id: str):
    memory_mod.reset_memory(session_id)
    return {"status": "cleared", "session_id": session_id}


# ------------------------------------------------------------------
# Quizeru
# ------------------------------------------------------------------
@app.post("/api/quiz/start")
def quiz_start(req: QuizStartRequest, response: Response):
    lang = req.lang if req.lang in ("id", "en") else "id"
    session_id = _get_or_create_session(req.session_id, response)
    result = quiz_engine.start_quiz(lang, req.mode)

    mem = memory_mod.get_memory(session_id)
    mem["activeQuiz"] = {
        "mode": result["mode"],
        "usedIds": result["usedIds"],
        "correct": 0,
        "wrong": 0,
        "wrongTopics": [],
        "cursor": 0,
    }
    memory_mod.save_memory(session_id, mem)

    # strip correctIndex before sending to the client — evaluation happens
    # server-side in /api/quiz/answer so answers can't be read off the wire
    public_questions = [
        {k: v for k, v in q.items() if k != "correctIndex"} for q in result["questions"]
    ]
    return {"session_id": session_id, "mode": result["mode"], "totalQuestions": result["totalQuestions"], "questions": public_questions}


@app.post("/api/quiz/answer")
def quiz_answer(req: QuizAnswerRequest, response: Response):
    lang = req.lang if req.lang in ("id", "en") else "id"
    session_id = _get_or_create_session(req.session_id, response)
    result = quiz_engine.evaluate_answer(lang, req.question_id, req.selected_index)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    mem = memory_mod.get_memory(session_id)
    quiz_state = mem.get("activeQuiz") or {"correct": 0, "wrong": 0, "wrongTopics": []}
    if result["correct"]:
        quiz_state["correct"] = quiz_state.get("correct", 0) + 1
    else:
        quiz_state["wrong"] = quiz_state.get("wrong", 0) + 1
        quiz_state.setdefault("wrongTopics", []).append(result["sectionTitle"])
        memory_mod.record_wrong_topic(mem, result["sectionTitle"])
    mem["activeQuiz"] = quiz_state
    memory_mod.save_memory(session_id, mem)

    return {"session_id": session_id, **result}


@app.post("/api/quiz/next")
def quiz_next(req: QuizAnswerRequest, response: Response):
    """Advances the session's quiz cursor. Kept mostly for symmetry with the
    spec's endpoint list — the frontend can also just move to the next item
    in the array it already has from /api/quiz/start."""
    session_id = _get_or_create_session(req.session_id, response)
    mem = memory_mod.get_memory(session_id)
    quiz_state = mem.get("activeQuiz") or {"cursor": 0}
    quiz_state["cursor"] = quiz_state.get("cursor", 0) + 1
    mem["activeQuiz"] = quiz_state
    memory_mod.save_memory(session_id, mem)
    return {"session_id": session_id, "cursor": quiz_state["cursor"]}


@app.post("/api/quiz/finish")
def quiz_finish(req: QuizFinishRequest, response: Response):
    lang = req.lang if req.lang in ("id", "en") else "id"
    session_id = _get_or_create_session(req.session_id, response)
    summary = quiz_engine.build_result_summary(lang, req.mode, req.correct, req.wrong, req.wrong_topics)

    mem = memory_mod.get_memory(session_id)
    mem["quizHistory"] = summary
    mem.pop("activeQuiz", None)
    recommendation = quiz_engine.adaptive_recommendation(lang, mem.get("quizStats", {}))
    memory_mod.save_memory(session_id, mem)

    return {"session_id": session_id, "summary": summary, "recommendation": recommendation}
