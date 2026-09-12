"""
Knowledge base loader + search engine for Laboratorium Maya.
Loads knowledge_base/materi.json and exposes lookup/search helpers used by
both the LaMa AI chat engine and Quizeru.
"""
import json
import re
import unicodedata
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
MATERI_PATH = BASE_DIR / "knowledge_base" / "materi.json"

with open(MATERI_PATH, encoding="utf-8") as f:
    _MATERI = json.load(f)


def sections(lang: str) -> list:
    lang = lang if lang in _MATERI else "id"
    return _MATERI[lang]["sections"]


def quiz_bank(lang: str) -> list:
    lang = lang if lang in _MATERI else "id"
    return _MATERI[lang]["quiz"]


def get_section_by_number(lang: str, number: int) -> Optional[dict]:
    for s in sections(lang):
        if s["number"] == number:
            return s
    return None


def get_section_by_id(lang: str, section_id: str) -> Optional[dict]:
    for s in sections(lang):
        if s["id"] == section_id:
            return s
    return None


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return re.sub(r"[^\w\s]", " ", text.lower(), flags=re.UNICODE)


_STOPWORDS = {
    "id": {"yang", "dan", "atau", "itu", "ini", "di", "ke", "dari", "untuk",
           "dengan", "pada", "adalah", "apa", "apakah", "bagaimana", "saya",
           "kamu", "aku", "kalau", "juga", "jadi", "bisa", "akan", "the",
           "and", "for", "with"},
    "en": {"the", "is", "are", "a", "an", "of", "to", "in", "on", "for",
           "and", "or", "what", "how", "does", "do", "i", "you", "it",
           "that", "this"},
}


_TOKEN_CACHE: dict = {}


def _section_tokens(lang: str, s: dict) -> list:
    key = (lang, s["id"])
    if key not in _TOKEN_CACHE:
        haystack = _norm(s["title"] + " " + s.get("tagline", "") + " " + s.get("content", ""))
        _TOKEN_CACHE[key] = re.findall(r"\b\w+\b", haystack)
    return _TOKEN_CACHE[key]


def _idf_weights(lang: str) -> tuple:
    """Down-weights words that appear in (almost) every section — like the
    site's own name 'laboratorium'/'maya' — so they don't drown out the
    actually discriminating keyword in a query. Returns (weights, df, n_docs)."""
    cache_key = f"idf::{lang}"
    if cache_key in _TOKEN_CACHE:
        return _TOKEN_CACHE[cache_key]
    docs = [set(_section_tokens(lang, s)) for s in sections(lang)]
    n_docs = len(docs)
    df: dict = {}
    for doc in docs:
        for w in doc:
            df[w] = df.get(w, 0) + 1
    import math
    weights = {w: math.log((n_docs + 1) / (c + 0.5)) + 0.01 for w, c in df.items()}
    result = (weights, df, n_docs)
    _TOKEN_CACHE[cache_key] = result
    return result


_RE_DEFINITION = re.compile(
    r"^\s*apa (itu|artinya)|pengertian (dari |tentang )?|definisi (dari |tentang )?"
    r"|apa (yang dimaksud|maksud)|what is|what does .* mean", re.I)


def search_knowledge(query: str, lang: str = "id", limit: int = 5) -> list:
    """Whole-word, IDF-weighted keyword scoring across sections — avoids
    both substring false-positives (e.g. 'nasi' inside 'Indonesia') and the
    site's own name ('laboratorium', 'maya') dominating every match."""
    q_words = [w for w in _norm(query).split() if len(w) >= 2]
    stop = _STOPWORDS.get(lang, set())
    q_words = [w for w in q_words if w not in stop]
    if not q_words:
        return []

    weights, df, n_docs = _idf_weights(lang)
    # Prefer words that don't already appear in almost every section (the
    # site's own name shows up everywhere and isn't a useful discriminator
    # on its own) — but if that leaves nothing, fall back to the full list.
    q_words = [w for w in q_words if df.get(w, 0) < max(n_docs - 1, 1)]

    results = []
    for s in sections(lang):
        tokens = _section_tokens(lang, s)
        score = 0.0
        for w in q_words:
            count = tokens.count(w)
            if count:
                score += count * weights.get(w, 1.0)
        if score > 0.05:
            results.append({"section": s, "score": score})
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]


def find_relevant_section(query: str, lang: str = "id") -> Optional[dict]:
    results = search_knowledge(query, lang)
    if results:
        return results[0]["section"]
    # No keyword stood out enough (e.g. the query only contains generic
    # words like "laboratorium maya" itself) — a plain "what is X" question
    # defaults to the definition chapter, matching how a human reader would
    # expect the site to behave.
    if _RE_DEFINITION.search(query.strip()):
        return get_section_by_number(lang, 1)
    return None


def loose_topic_overlap(query: str, lang: str = "id") -> bool:
    """At least two distinct 4+ letter query words appear somewhere in the
    knowledge base — used to distinguish 'vaguely on-topic' from 'nothing
    matched at all', same rule as the frontend."""
    words = [w for w in _norm(query).split() if len(w) >= 4]
    if not words:
        return False
    haystack = _norm(" ".join(s["title"] + " " + s.get("content", "") for s in sections(lang)))
    matched = set()
    for w in words:
        if re.search(r"\b" + re.escape(w) + r"\b", haystack):
            matched.add(w)
    return len(matched) >= 2


def extract_example(section: dict) -> str:
    for b in section.get("blocks_raw", []):
        t = b.get("type")
        if t == "list" and b.get("items"):
            return b["items"][0]
        if t == "theoryCards" and b.get("cards"):
            c = b["cards"][0]
            return f"{c.get('title','')} ({c.get('who','')})"
        if t == "flow" and b.get("steps"):
            return b["steps"][0].get("label", "")
        if t == "compare" and b.get("rows"):
            return b["rows"][0].get("label", "")
        if t == "platforms" and b.get("items"):
            return b["items"][0].get("name", "")
        if t == "cflow" and b.get("nodes"):
            return b["nodes"][0]
    return section.get("tagline", "")


def first_paragraph(section: dict) -> str:
    for b in section.get("blocks_raw", []):
        if b.get("type") == "p":
            return b["text"]
    return section.get("tagline", "")


def knowledge_context_for_llm(lang: str, max_chars: int = 6000) -> str:
    """Serialize the whole knowledge base into a compact grounding block for
    the external LLM provider, so it answers strictly from materi.json."""
    parts = []
    for s in sections(lang):
        parts.append(f"## Bab {s['number']}: {s['title']}\n{s['content']}")
    text = "\n\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars] + "…"
    return text
