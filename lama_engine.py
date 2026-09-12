"""
LaMa AI — source-grounded, memory-aware learning assistant engine.

Deep-reasoning pipeline (never exposed to the user, per spec §14):
  1. Dekonstruksi masalah   -> _detect_name / _detect_instruction / intent regexes
  2. Identifikasi intent    -> creator / tech-stack / quiz-history / greeting / material
  3. Analisis context       -> pronoun resolution against memory.activeTopic
  4. Retrieval knowledge    -> knowledge.search_knowledge / find_relevant_section
  5. Validasi               -> isAllowedTopic gate, anti-hallucination
  6. Sintesis                -> local grounded response OR external LLM (grounded prompt)
  7. Response               -> final text only
"""
import re
from typing import Optional

import ai_provider
import knowledge
import memory as memory_mod

SITE = {
    "name": "Laboratorium Maya",
    "author": "nuelxv",
    "github": "NuelDev",
    "mainFile": "index.html",
    "team": [
        {"id": "Gemini AI", "en": "Gemini AI", "noteId": "sumber informasi", "noteEn": "information source"},
        {"id": "ChatGPT", "en": "ChatGPT", "noteId": "prompt engineer", "noteEn": "prompt engineer"},
        {"id": "Claude dan Codex", "en": "Claude and Codex", "noteId": "membuat hasil vibecoding", "noteEn": "vibecoding implementation"},
        {"id": "Figma", "en": "Figma", "noteId": "membuat UI/UX", "noteEn": "UI/UX design"},
        {"id": "Visual Studio Code", "en": "Visual Studio Code", "noteId": "software utama untuk mengolah teks HTML", "noteEn": "main editor used to write the HTML"},
    ],
    "tech": {
        "html": "HTML5", "css": "CSS3", "js": "JavaScript ES6+", "backend": "Python (FastAPI)",
        "apis": ["Web Audio API", "Vibration API", "Fetch API", "localStorage API"],
    },
}

_RE_NAME = [
    re.compile(r"panggil (saya|aku) ([a-zA-Z]{2,20})", re.I),
    re.compile(r"nama saya ([a-zA-Z]{2,20})", re.I),
    re.compile(r"call me ([a-zA-Z]{2,20})", re.I),
    re.compile(r"my name is ([a-zA-Z]{2,20})", re.I),
]
_RE_SIMPLE = re.compile(r"bahasa (yang )?sederhana|sederhanakan|simple language|explain (it )?simply", re.I)
_RE_SHORT = re.compile(r"jawab (yang )?singkat|singkat saja|ringkas saja|short answer|be brief|keep it short", re.I)
_RE_EXAMPLES = re.compile(r"pakai contoh|gunakan contoh|beri(kan)? contoh|use examples|give (me )?an example|with examples", re.I)
_RE_GREETING = re.compile(r"^\s*(hai+|halo+|hello|hi|hey|selamat (pagi|siang|sore|malam))\b", re.I)
_RE_CREATOR = re.compile(
    r"siapa (yang )?(membuat|pembuat|bikin|mengembangkan).*(website|web|aplikasi|app)"
    r"|pembuat (website|web|aplikasi) ini|dibuat oleh siapa|bagaimana (website|web) ini dibuat"
    r"|who (made|built|created|developed) this (website|site|app)", re.I)
_RE_TECHSTACK = re.compile(
    r"dibuat (pakai|menggunakan)( bahasa)? apa|bahasa pemrograman apa|teknologi apa (yang )?digunakan"
    r"|stack (website|web)? ?apa|coding.?nya pakai apa|dibuat menggunakan bahasa apa"
    r"|what (language|tech|stack|technology).*(built|made|use)|built (with|using) what|what technology", re.I)
_RE_QUIZ_HISTORY = re.compile(
    r"salah (apa|dimana|pada)|apa (yang )?(tadi )?saya salah|skor (saya|quiz)|hasil quiz"
    r"|what did i get wrong|my score|quiz result", re.I)
_RE_PRONOUN = re.compile(r"\b(itu|ini|tadi|that|this|it)\b", re.I)
_RE_STRIP_NAME = re.compile(
    r"panggil (saya|aku) [a-zA-Z]+|nama saya [a-zA-Z]+|call me [a-zA-Z]+|my name is [a-zA-Z]+", re.I)


def _detect_name(q: str) -> Optional[str]:
    for pat in _RE_NAME:
        m = pat.search(q)
        if m:
            return m.group(m.lastindex)
    return None


def _detect_instruction(q: str) -> dict:
    flags = {}
    if _RE_SIMPLE.search(q):
        flags["simple"] = True
    if _RE_SHORT.search(q):
        flags["short"] = True
    if _RE_EXAMPLES.search(q):
        flags["useExamples"] = True
    return flags


def is_greeting(q: str) -> bool:
    return bool(_RE_GREETING.search(q))


def is_creator_question(q: str) -> bool:
    return bool(_RE_CREATOR.search(q))


def is_techstack_question(q: str) -> bool:
    return bool(_RE_TECHSTACK.search(q))


def is_quiz_history_question(q: str) -> bool:
    return bool(_RE_QUIZ_HISTORY.search(q))


def _is_pronoun_ambiguous(q: str) -> bool:
    words = q.strip().split()
    return len(words) <= 9 and bool(_RE_PRONOUN.search(q))


def creator_answer_text(lang: str) -> str:
    is_id = lang == "id"
    lines = [f"{m['id']} — {m['noteId']}" if is_id else f"{m['en']} — {m['noteEn']}" for m in SITE["team"]]
    intro = (f"{SITE['name']} dikembangkan oleh {SITE['author']} (GitHub: {SITE['github']}), dengan bantuan beberapa tools dan AI:"
             if is_id else
             f"{SITE['name']} was developed by {SITE['author']} (GitHub: {SITE['github']}), with help from a few tools and AI systems:")
    return intro + "\n" + "\n".join("• " + l for l in lines)


def tech_answer_text(lang: str) -> str:
    is_id = lang == "id"
    t = SITE["tech"]
    if is_id:
        return (f"{SITE['name']} menggunakan {t['html']}, {t['css']}, dan {t['js']} pada frontend ({SITE['mainFile']}), "
                f"dan {t['backend']} pada backend untuk LaMa AI, knowledge base, memory, serta Quizeru. "
                f"Website ini juga memanfaatkan {t['apis'][0]} untuk efek suara, {t['apis'][1]} untuk getaran saat jawaban benar, "
                f"{t['apis'][2]} untuk komunikasi frontend-backend, dan {t['apis'][3]} untuk menyimpan tema serta preferensi bahasa.")
    return (f"{SITE['name']} uses {t['html']}, {t['css']}, and {t['js']} on the frontend ({SITE['mainFile']}), "
            f"and {t['backend']} on the backend for LaMa AI, the knowledge base, memory, and Quizeru. "
            f"It also uses the {t['apis'][0]} for sound effects, the {t['apis'][1]} for haptic feedback on correct answers, "
            f"the {t['apis'][2]} for frontend-backend communication, and {t['apis'][3]} for theme and language preferences.")


def creator_and_tech_answer_text(lang: str) -> str:
    return creator_answer_text(lang) + "\n\n" + tech_answer_text(lang)


def is_allowed_topic(query: str, lang: str) -> bool:
    return bool(
        knowledge.find_relevant_section(query, lang)
        or knowledge.loose_topic_overlap(query, lang)
        or is_creator_question(query)
        or is_techstack_question(query)
        or is_greeting(query)
    )


def _generate_fallback_response(section: dict, memory: dict, lang: str) -> str:
    instr = memory.get("instructionStyle", {})
    if instr.get("short"):
        base = section.get("tagline", "")
    else:
        base = knowledge.first_paragraph(section)
        if len(base) > 320:
            base = base[:300].rsplit(" ", 1)[0] + "…"
    suffix = (f" (Dari materi Bab {section['number']}: {section['title']})" if lang == "id"
              else f" (From Chapter {section['number']}: {section['title']} in the material)")
    text = base + suffix
    if instr.get("useExamples"):
        example = knowledge.extract_example(section)
        text += (" Contoh: " if lang == "id" else " Example: ") + example + "."
    return text


def _welcome_text(lang: str) -> str:
    if lang == "id":
        return ("Halo! Aku LaMa AI. Tanyakan apa saja seputar Laboratorium Maya — definisi, teori, arsitektur, "
                "perbandingan, sampai platform yang dibahas di website ini.")
    return ("Hi! I'm LaMa AI. Ask me anything about Laboratorium Maya — definitions, theories, architecture, "
            "comparisons, or the platforms covered on this site.")


def _out_of_scope_text(lang: str) -> str:
    if lang == "id":
        return ("Itu di luar materi Laboratorium Maya, jadi saya tidak bisa menjawabnya berdasarkan dokumen di "
                "website ini. Untuk pertanyaan umum semacam itu sebaiknya dicek lewat sumber lain.")
    return ("That's outside the Laboratorium Maya material, so I can't answer it from this website's document. "
            "For general questions like that, it's best to check another source.")


def _not_found_text(lang: str) -> str:
    if lang == "id":
        return "Topik itu berkaitan dengan Laboratorium Maya, tapi saya belum menemukan bagian materi yang cocok."
    return "That's related to Laboratorium Maya, but I couldn't find a matching section in the material."


def _quiz_history_text(memory: dict, lang: str) -> str:
    qh = memory.get("quizHistory")
    if not qh:
        return ("Kamu belum menyelesaikan sesi Quizeru mana pun, jadi belum ada riwayat yang bisa saya rangkum."
                if lang == "id" else
                "You haven't completed a Quizeru session yet, so there's no history for me to summarize.")
    wrong_list = ", ".join(qh.get("wrongTopics", [])) or ("tidak ada" if lang == "id" else "none")
    if lang == "id":
        return (f"Pada sesi Quizeru mode {qh['mode']} terakhir, skor kamu {qh['score']}% "
                f"({qh['correct']} benar, {qh['wrong']} salah). Kamu sempat salah pada topik: {wrong_list}.")
    return (f"In your last Quizeru session ({qh['mode']} mode), your score was {qh['score']}% "
            f"({qh['correct']} correct, {qh['wrong']} wrong). You missed questions related to: {wrong_list}.")


def _llm_grounded_answer(query: str, section: Optional[dict], memory: dict, lang: str) -> Optional[str]:
    """Ask the configured external provider, but keep it strictly grounded in
    materi.json. Returns None if no provider is configured or on failure —
    caller falls back to the local engine."""
    if not ai_provider.provider_available():
        return None
    context = knowledge.knowledge_context_for_llm(lang)
    convo_tail = memory.get("messages", [])[-6:]
    convo_text = "\n".join(f"{m['role']}: {m['content']}" for m in convo_tail)
    lang_name = "Bahasa Indonesia" if lang == "id" else "English"
    system_prompt = (
        f"Kamu adalah LaMa AI, asisten belajar untuk website edukasi 'Laboratorium Maya'. "
        f"Jawab HANYA berdasarkan materi berikut, jangan mengarang fakta, angka, atau sumber di luar materi ini. "
        f"Jika informasi tidak ada di materi, katakan terus terang bahwa informasi tersebut tidak tersedia di materi. "
        f"Jawab singkat, jelas, natural, tanpa basa-basi pembuka seperti 'Tentu saja' atau 'Sebagai AI'. "
        f"Jawab dalam {lang_name}.\n\n=== MATERI LABORATORIUM MAYA ===\n{context}"
    )
    user_message = f"Riwayat percakapan singkat:\n{convo_text}\n\nPertanyaan pengguna: {query}"
    try:
        return ai_provider.generate(system_prompt, user_message, max_tokens=500)
    except Exception:
        return None


def answer_question(raw_query: str, memory: dict, lang: str) -> dict:
    """Runs the full pipeline and returns {text, section?, sectionNumber?}.
    Mutates `memory` in place (name, instruction style, active topic) —
    caller is responsible for persisting it."""
    query = (raw_query or "").strip()
    if not query:
        return {"text": _welcome_text(lang)}

    name = _detect_name(query)
    if name:
        memory["userName"] = name[:1].upper() + name[1:]
        return {"text": f"Baik, {memory['userName']}." if lang == "id" else f"Got it, {memory['userName']}."}

    flags = _detect_instruction(query)
    if flags:
        memory["instructionStyle"] = {**memory.get("instructionStyle", {}), **flags}

    if is_creator_question(query) and is_techstack_question(query):
        return {"text": creator_and_tech_answer_text(lang)}
    if is_creator_question(query):
        return {"text": creator_answer_text(lang)}
    if is_techstack_question(query):
        return {"text": tech_answer_text(lang)}

    if is_quiz_history_question(query):
        return {"text": _quiz_history_text(memory, lang)}

    if is_greeting(query) and len(query.split()) <= 5:
        name_part = memory.get("userName")
        hi = (f"Halo, {name_part}!" if name_part else "Halo!") if lang == "id" else (f"Hi, {name_part}!" if name_part else "Hi!")
        return {"text": hi + " " + _welcome_text(lang)}

    stripped = _RE_STRIP_NAME.sub("", query).strip()
    if flags and len(stripped) < 8:
        return {"text": "Baik, saya akan menyesuaikan gaya jawaban saya mulai sekarang." if lang == "id"
                else "Got it — I'll adjust my answers accordingly from now on."}

    effective_query = query
    if _is_pronoun_ambiguous(query) and memory.get("activeTopic"):
        effective_query = memory["activeTopic"]

    section = knowledge.find_relevant_section(effective_query, lang)
    if not section and effective_query != query:
        section = knowledge.find_relevant_section(query, lang)

    if section:
        memory["activeTopic"] = section["title"]
        memory["activeSection"] = section["number"]

        llm_text = _llm_grounded_answer(query, section, memory, lang)
        text = llm_text if llm_text else _generate_fallback_response(section, memory, lang)
        return {"text": text, "sectionNumber": section["number"], "sectionTitle": section["title"]}

    if knowledge.loose_topic_overlap(query, lang):
        llm_text = _llm_grounded_answer(query, None, memory, lang)
        return {"text": llm_text if llm_text else _not_found_text(lang)}

    return {"text": _out_of_scope_text(lang)}
