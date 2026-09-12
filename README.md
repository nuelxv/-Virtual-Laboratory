# Laboratorium Maya

Website edukasi interaktif "Laboratorium Maya" — ensiklopedia 8 bab tentang laboratorium virtual, lengkap dengan asisten belajar **LaMa AI** dan kuis interaktif **Quizeru**. Frontend adalah satu file `index.html`; seluruh AI, knowledge base, memory, dan logika kuis berjalan di **backend Python (FastAPI)**.

## Struktur Project

```
Laboratorium-Maya/
├── index.html                  # Frontend (HTML+CSS+JS dalam 1 file)
├── backend/
│   ├── app.py                  # FastAPI — semua endpoint REST API
│   ├── ai_provider.py          # Abstraksi AI provider (Anthropic/OpenAI/lokal)
│   ├── lama_engine.py          # Engine LaMa AI (intent detection, grounded answer)
│   ├── knowledge.py            # Loader + search engine knowledge base
│   ├── memory.py               # MemoryService (session, SQLite storage)
│   ├── quiz_engine.py          # Engine Quizeru (generate soal, evaluasi, adaptive learning)
│   ├── requirements.txt
│   ├── .env.example
│   ├── knowledge_base/
│   │   └── materi.json         # 8 bab materi + 24 soal kuis (id & en)
│   └── data/
│       └── memory.sqlite3      # dibuat otomatis saat backend jalan
├── .gitignore
└── README.md
```

## Menjalankan Backend (Local Development)

```bash
cd backend
python3 -m venv venv && source venv/bin/activate   # opsional tapi disarankan
pip install -r requirements.txt
cp .env.example .env       # lalu isi kalau mau pakai AI provider eksternal
uvicorn app:app --reload --port 8000
```

Cek backend hidup: buka `http://127.0.0.1:8000/api/health` — harus muncul `{"status":"ok", ...}`.

Tanpa mengisi `.env` sama sekali, backend tetap jalan penuh — LaMa AI otomatis memakai **knowledge-base engine lokal** (tidak mengarang jawaban, semua bersumber dari `materi.json`).

## Menjalankan Frontend

`index.html` bisa dibuka dengan dua cara:

1. **Langsung sebagai file** (dobel klik / buka di browser). Frontend otomatis mengarah ke `http://127.0.0.1:8000` untuk backend.
2. **Lewat static server** (disarankan, agar tidak kena batasan browser untuk file lokal):
   ```bash
   python3 -m http.server 5500
   # buka http://127.0.0.1:5500/index.html
   ```
   Selama backend jalan di port 8000 di host yang sama, frontend otomatis menemukannya.

Kalau backend ada di alamat lain (mis. sudah di-deploy), atur manual dari console browser:

```js
localStorage.setItem('lm_api_base', 'https://backend-kamu.example.com')
```

## Environment Variables (`backend/.env`)

| Variable          | Keterangan                                                        |
|-------------------|---------------------------------------------------------------------|
| `AI_PROVIDER`     | `none` (default, lokal saja), `anthropic`, atau `openai`            |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | Dipakai kalau `AI_PROVIDER=anthropic`         |
| `OPENAI_API_KEY` / `OPENAI_MODEL`       | Dipakai kalau `AI_PROVIDER=openai`            |
| `CORS_ORIGINS`    | Daftar origin frontend yang diizinkan (production), dipisah koma    |
| `MEMORY_DB_PATH`  | Lokasi file SQLite untuk memory (default `./data/memory.sqlite3`)   |

**API key tidak pernah ditaruh di frontend maupun di repo GitHub.** Selalu lewat `.env` (yang di-`.gitignore`).

## API Endpoints

| Method | Path                | Fungsi                                             |
|--------|---------------------|-----------------------------------------------------|
| GET    | `/api/health`        | Cek status backend + provider AI                   |
| GET    | `/api/material`      | Ambil semua 8 bab materi (`?lang=id\|en`)           |
| GET    | `/api/material/{id}` | Ambil satu bab (by nomor atau slug id)              |
| POST   | `/api/chat`           | Kirim pesan ke LaMa AI                              |
| GET    | `/api/memory`         | Baca memory session (`?session_id=...`)             |
| POST   | `/api/memory`         | Update memory (field terbatas: lang, userName, dll) |
| DELETE | `/api/memory`         | Hapus memory session                                |
| POST   | `/api/quiz/start`     | Mulai sesi Quizeru (`mode: easy\|medium\|hard`)     |
| POST   | `/api/quiz/answer`    | Jawab satu soal (dievaluasi di server)              |
| POST   | `/api/quiz/next`      | Majukan cursor sesi kuis                            |
| POST   | `/api/quiz/finish`    | Selesaikan kuis, dapat skor + rekomendasi belajar   |

## Arsitektur

```
index.html (HTML+CSS+JS)
      │  fetch() / REST API
      ▼
Python Backend (FastAPI)
      │
      ├── LaMa AI (lama_engine.py) ──► AI Provider (opsional: Anthropic/OpenAI)
      ├── Knowledge Base (knowledge.py + materi.json)
      ├── Memory (memory.py, SQLite)
      └── Quizeru (quiz_engine.py)
```

Kalau backend tidak bisa diakses, frontend **tidak blank** — LaMa AI dan Quizeru otomatis jatuh ke engine lokal berbasis knowledge base yang sama, dan badge status di halaman LaMa AI menunjukkan "Mode lokal (backend offline)". Navigasi, materi, dan pencarian tetap berfungsi penuh tanpa backend.

## Deployment

- **Frontend**: bisa di-host di GitHub Pages atau static hosting lain — `index.html` berdiri sendiri.
- **Backend**: perlu hosting yang mendukung Python (Railway, Render, Fly.io, VPS, dll). GitHub Pages **tidak bisa** menjalankan backend Python.
- Setelah backend live, set `CORS_ORIGINS` di `.env` backend ke domain frontend kamu, dan set `lm_api_base` di frontend (lihat bagian "Menjalankan Frontend") ke URL backend tersebut.

## Teknologi

**Frontend:** HTML5, CSS3, JavaScript ES6+, SVG, Google Fonts, Web Audio API, Vibration API, Fetch API, localStorage API.

**Backend:** Python, FastAPI, REST API, JSON, SQLite, environment variables (`python-dotenv`), abstraksi AI provider (Anthropic/OpenAI opsional).

---

Dikembangkan oleh **nuelxv** (GitHub: **NuelDev**), dengan bantuan Gemini AI (sumber informasi), ChatGPT (prompt engineer), Claude & Codex (vibecoding), Figma (UI/UX), dan Visual Studio Code.
