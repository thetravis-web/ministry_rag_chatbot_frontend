"""
Ministry of ICT and National Guidance - Offline RAG Chatbot.

Local FastAPI backend with SQLite persistence, real password authentication,
document storage, a lightweight local retriever, and optional Ollama generation.
"""

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import shutil
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "ministry.db"
COOKIE_NAME = "ministry_session"
COOKIE_MAX_AGE = 60 * 60 * 8
SECRET_KEY = os.getenv("MINISTRY_SECRET_KEY", "change-this-local-dev-secret")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
CHATBOT_NAME = "MINDY"

app = FastAPI(title="Ministry Offline RAG Chatbot")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

NAV_BY_ROLE = [
    {"label": "Dashboard", "href": "/dashboard", "permission": "ask"},
    {"label": "Chat", "href": "/chat", "permission": "ask"},
    {"label": "Knowledge Base", "href": "/knowledge-base", "permission": "ask"},
    {"label": "Upload", "href": "/upload", "permission": "docs"},
    {"label": "Admin", "href": "/admin/roles", "permission": "users"},
]

DEFAULT_ROLES = [
    ("System Administrator", 1, 1, 1, 1),
    ("Knowledge Management Officer", 1, 1, 0, 0),
    ("Ministry Staff", 1, 0, 0, 0),
    ("ICT Consultant", 1, 0, 0, 0),
    ("Ministry Intern", 1, 0, 0, 0),
    ("Citizen", 1, 0, 0, 0),
]

DEFAULT_USERS = [
    ("Stephen Okello", "stephen.okello@ict.go.ug", "Admin@12345", "System Administrator"),
    ("Grace Nabirye", "grace.nabirye@ict.go.ug", "Knowledge@12345", "Knowledge Management Officer"),
    ("Daniel Ochieng", "daniel.ochieng@ict.go.ug", "Staff@12345", "Ministry Staff"),
]

SEED_DOCUMENTS = [
    (
        "National ICT Policy 2024",
        "National Policies",
        "The National ICT Policy guides digital transformation, e-government services, interoperability, cybersecurity readiness, and responsible data use across public institutions.",
    ),
    (
        "Data Protection and Privacy Act 2019",
        "Legal & Regulatory",
        "The Data Protection and Privacy Act 2019 requires lawful, fair, and transparent processing of personal data, including consent or another valid legal basis.",
    ),
    (
        "Computer Misuse Act",
        "Legal & Regulatory",
        "The Computer Misuse Act addresses unauthorized access, cyber harassment, misuse of protected systems, and offences involving computer systems.",
    ),
    (
        "National Information Security Framework",
        "ICT Standards",
        "The National Information Security Framework sets expectations for risk management, access controls, incident response, and security governance.",
    ),
    (
        "Public ICT Procurement Guidelines",
        "Procurement Guidelines",
        "Public ICT procurement should follow approved thresholds, transparent evaluation, lifecycle planning, and value-for-money principles.",
    ),
]


@contextmanager
def db_connection():
    DATA_DIR.mkdir(exist_ok=True)
    UPLOAD_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def display_date(value: str | None) -> str:
    if not value:
        return "Unknown"
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.strftime("%d %b %Y")


def display_time(value: str | None) -> str:
    if not value:
        return "Unknown"
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.strftime("%d %b %Y, %H:%M")


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260000)
    return f"{salt}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(password, salt), f"{salt}${digest}")


def sign_payload(payload: dict[str, Any]) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    signature = hmac.new(SECRET_KEY.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def unsign_payload(token: str | None) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    encoded, signature = token.rsplit(".", 1)
    expected = hmac.new(SECRET_KEY.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded.encode()).decode())
    except (ValueError, json.JSONDecodeError):
        return None
    if payload.get("expires", 0) < time.time():
        return None
    return payload


def query_all(sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    with db_connection() as conn:
        return conn.execute(sql, params).fetchall()


def query_one(sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    with db_connection() as conn:
        return conn.execute(sql, params).fetchone()


def execute(sql: str, params: tuple[Any, ...] = ()) -> int:
    with db_connection() as conn:
        cursor = conn.execute(sql, params)
        return int(cursor.lastrowid)


def initialize_database() -> None:
    with db_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                ask INTEGER NOT NULL DEFAULT 1,
                docs INTEGER NOT NULL DEFAULT 0,
                users INTEGER NOT NULL DEFAULT 0,
                maintenance INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role_id INTEGER NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY(role_id) REFERENCES roles(id)
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                original_filename TEXT,
                stored_path TEXT,
                content_type TEXT,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                chunks INTEGER NOT NULL DEFAULT 0,
                uploaded_by INTEGER,
                uploaded_at TEXT NOT NULL,
                FOREIGN KEY(uploaded_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS document_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(id)
            );

            CREATE TABLE IF NOT EXISTS chat_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                sender TEXT NOT NULL,
                message TEXT NOT NULL,
                sources_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES chat_sessions(id)
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                user_id INTEGER,
                user_name TEXT NOT NULL,
                action TEXT NOT NULL,
                icon TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            """
        )

        for role in DEFAULT_ROLES:
            conn.execute(
                """
                INSERT OR IGNORE INTO roles (name, ask, docs, users, maintenance)
                VALUES (?, ?, ?, ?, ?)
                """,
                role,
            )

        for name, email, password, role_name in DEFAULT_USERS:
            role_id = conn.execute("SELECT id FROM roles WHERE name = ?", (role_name,)).fetchone()["id"]
            conn.execute(
                """
                INSERT OR IGNORE INTO users (name, email, password_hash, role_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, email, hash_password(password), role_id, utc_now()),
            )

        existing_docs = conn.execute("SELECT COUNT(*) AS total FROM documents").fetchone()["total"]
        if existing_docs == 0:
            admin_id = conn.execute("SELECT id FROM users WHERE email = ?", (DEFAULT_USERS[0][1],)).fetchone()["id"]
            for title, category, content in SEED_DOCUMENTS:
                document_id = conn.execute(
                    """
                    INSERT INTO documents (title, category, original_filename, size_bytes, chunks, uploaded_by, uploaded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (title, category, None, len(content), 1, admin_id, utc_now()),
                ).lastrowid
                conn.execute(
                    "INSERT INTO document_chunks (document_id, chunk_index, content) VALUES (?, ?, ?)",
                    (document_id, 0, content),
                )


def audit(action_type: str, user: sqlite3.Row | dict[str, Any] | None, action: str, icon: str) -> None:
    user_id = user["id"] if user else None
    user_name = user["name"] if user else "System"
    execute(
        """
        INSERT INTO audit_logs (action_type, user_id, user_name, action, icon, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (action_type, user_id, user_name, action, icon, utc_now()),
    )


def user_with_role(user_id: int) -> sqlite3.Row | None:
    return query_one(
        """
        SELECT u.id, u.name, u.email, u.is_active, r.name AS role,
               r.ask, r.docs, r.users, r.maintenance
        FROM users u
        JOIN roles r ON r.id = u.role_id
        WHERE u.id = ? AND u.is_active = 1
        """,
        (user_id,),
    )


def current_user(request: Request) -> sqlite3.Row | None:
    payload = unsign_payload(request.cookies.get(COOKIE_NAME))
    if not payload:
        return None
    return user_with_role(int(payload.get("user_id", 0)))


def require_user(request: Request) -> sqlite3.Row:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user


def require_permission(request: Request, permission: str) -> sqlite3.Row:
    user = require_user(request)
    if not bool(user[permission]):
        raise HTTPException(status_code=403, detail="You do not have permission to perform this action.")
    return user


def page_user(request: Request, permission: str | None = None) -> sqlite3.Row | RedirectResponse:
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if permission and not bool(user[permission]):
        return RedirectResponse("/dashboard", status_code=303)
    return user


def nav_for(active_href: str, user: sqlite3.Row | None):
    items = []
    for item in NAV_BY_ROLE:
        if user and bool(user[item["permission"]]):
            items.append({**item, "active": item["href"] == active_href})
    return items


def categories() -> list[str]:
    rows = query_all("SELECT DISTINCT category FROM documents ORDER BY category")
    existing = [row["category"] for row in rows]
    defaults = ["Legal & Regulatory", "ICT Standards", "Procurement Guidelines", "National Policies"]
    return sorted(set(existing + defaults))


def documents_for(category: str | None = None) -> list[dict[str, Any]]:
    params: tuple[Any, ...] = ()
    where = ""
    if category and category != "All":
        where = "WHERE d.category = ?"
        params = (category,)
    rows = query_all(
        f"""
        SELECT d.*, u.name AS uploader
        FROM documents d
        LEFT JOIN users u ON u.id = d.uploaded_by
        {where}
        ORDER BY d.uploaded_at DESC, d.id DESC
        """,
        params,
    )
    return [
        {
            "id": row["id"],
            "title": row["title"],
            "category": row["category"],
            "uploaded": display_date(row["uploaded_at"]),
            "chunks": row["chunks"],
            "uploader": row["uploader"] or "System",
            "downloadable": bool(row["stored_path"]),
        }
        for row in rows
    ]


def recent_chat_titles(user_id: int, limit: int = 5) -> list[dict[str, str]]:
    rows = query_all(
        "SELECT title, updated_at FROM chat_sessions WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
        (user_id, limit),
    )
    return [{"title": row["title"], "when": display_time(row["updated_at"])} for row in rows]


def pinned_documents(limit: int = 3) -> list[str]:
    rows = query_all("SELECT title FROM documents ORDER BY uploaded_at DESC, id DESC LIMIT ?", (limit,))
    return [row["title"] for row in rows]


def extract_text_from_upload(path: Path, content_type: str | None) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".docx":
        try:
            import zipfile
            import xml.etree.ElementTree as ET

            with zipfile.ZipFile(path) as archive:
                xml_content = archive.read("word/document.xml")
            root = ET.fromstring(xml_content)
            text_nodes = [node.text for node in root.iter() if node.text]
            return " ".join(text_nodes)
        except Exception:
            return ""
    if suffix == ".pdf" or content_type == "application/pdf":
        return path.read_bytes().decode("latin-1", errors="ignore")
    return path.read_text(encoding="utf-8", errors="ignore")


def chunk_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    chunks = []
    start = 0
    while start < len(cleaned):
        chunks.append(cleaned[start : start + size])
        start += size - overlap
    return chunks


def save_document(file: UploadFile, category: str, user: sqlite3.Row) -> dict[str, Any]:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file.filename or "document").name)
    unique_name = f"{int(time.time())}_{secrets.token_hex(4)}_{safe_name}"
    stored_path = UPLOAD_DIR / unique_name
    with stored_path.open("wb") as target:
        shutil.copyfileobj(file.file, target)

    extracted = extract_text_from_upload(stored_path, file.content_type)
    chunks = chunk_text(extracted)
    if not chunks:
        chunks = [f"{safe_name} was uploaded, but readable text could not be extracted locally yet."]

    document_id = execute(
        """
        INSERT INTO documents (title, category, original_filename, stored_path, content_type, size_bytes, chunks, uploaded_by, uploaded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            Path(safe_name).stem.replace("_", " "),
            category,
            safe_name,
            str(stored_path.relative_to(BASE_DIR)),
            file.content_type,
            stored_path.stat().st_size,
            len(chunks),
            user["id"],
            utc_now(),
        ),
    )
    with db_connection() as conn:
        conn.executemany(
            "INSERT INTO document_chunks (document_id, chunk_index, content) VALUES (?, ?, ?)",
            [(document_id, index, chunk) for index, chunk in enumerate(chunks)],
        )

    audit("Document upload", user, f"uploaded '{safe_name}'", "upload_file")
    return {"status": "indexed", "category": category, "chunks": len(chunks), "document_id": document_id}


def tokenize(text: str) -> set[str]:
    return {word.lower() for word in re.findall(r"[A-Za-z0-9]{3,}", text)}


def retrieve_context(question: str, limit: int = 4) -> list[dict[str, Any]]:
    question_terms = tokenize(question)
    rows = query_all(
        """
        SELECT c.content, c.chunk_index, d.id AS document_id, d.title, d.category
        FROM document_chunks c
        JOIN documents d ON d.id = c.document_id
        """
    )
    scored = []
    for row in rows:
        content_terms = tokenize(row["content"])
        score = len(question_terms & content_terms)
        if score:
            scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "document_id": row["document_id"],
            "document": row["title"],
            "page": row["chunk_index"] + 1,
            "content": row["content"],
        }
        for _, row in scored[:limit]
    ]


async def generate_answer(question: str, contexts: list[dict[str, Any]]) -> tuple[str, bool]:
    if not contexts:
        return (
            f"{CHATBOT_NAME} could not find a strong match in the local knowledge base yet. "
            "Upload the relevant policy document, then ask again.",
            False,
        )

    context_text = "\n\n".join(
        f"Source: {item['document']} chunk {item['page']}\n{item['content']}" for item in contexts
    )
    prompt = (
        f"You are {CHATBOT_NAME}, the Ministry of ICT and National Guidance offline knowledge assistant. "
        "Answer only from the provided local document context. If the answer is not supported, say so clearly. "
        "Keep the answer concise and mention the relevant source names.\n\n"
        f"Context:\n{context_text}\n\nQuestion: {question}\nAnswer:"
    )
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(
                OLLAMA_URL,
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            )
            response.raise_for_status()
            data = response.json()
            answer = data.get("response", "").strip()
            if answer:
                return answer, True
    except (httpx.HTTPError, ValueError):
        pass

    top = contexts[0]
    return (
        f"{CHATBOT_NAME} found the closest local match in {top['document']}: {top['content'][:650]}",
        False,
    )


def context_for_page(active_href: str, user: sqlite3.Row) -> dict[str, Any]:
    return {
        "nav_items": nav_for(active_href, user),
        "user_name": user["name"],
        "user_role": user["role"],
        "chatbot_name": CHATBOT_NAME,
    }


@app.on_event("startup")
def startup() -> None:
    initialize_database()


@app.get("/")
def landing(request: Request):
    return templates.TemplateResponse(request, "landing.html", {"nav_items": []})


@app.get("/login")
def login(request: Request):
    if current_user(request):
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"nav_items": []})


@app.get("/logout")
def logout(request: Request):
    user = current_user(request)
    if user:
        audit("Logout", user, "logged out", "logout")
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/dashboard")
def dashboard(request: Request):
    user = page_user(request)
    if isinstance(user, RedirectResponse):
        return user
    doc_count = query_one("SELECT COUNT(*) AS total FROM documents")["total"]
    recent = recent_chat_titles(user["id"], 3)
    if not recent:
        recent = [{"title": "No conversations yet", "when": "Start in Chat"}]
    context = context_for_page("/dashboard", user)
    context.update(
        {
            "can_upload": bool(user["docs"]),
            "doc_count": doc_count,
            "recent_chats": recent,
            "pinned_docs": pinned_documents(),
        }
    )
    return templates.TemplateResponse(request, "dashboard.html", context)


@app.get("/chat")
def chat_page(request: Request):
    user = page_user(request, "ask")
    if isinstance(user, RedirectResponse):
        return user
    context = context_for_page("/chat", user)
    context["recent_chats"] = recent_chat_titles(user["id"]) or [{"title": "No conversations yet"}]
    return templates.TemplateResponse(request, "chat.html", context)


@app.get("/upload")
def upload_page(request: Request):
    user = page_user(request, "docs")
    if isinstance(user, RedirectResponse):
        return user
    context = context_for_page("/upload", user)
    context["categories"] = categories()
    return templates.TemplateResponse(request, "upload.html", context)


@app.get("/knowledge-base")
def knowledge_base(request: Request, category: str | None = None):
    user = page_user(request, "ask")
    if isinstance(user, RedirectResponse):
        return user
    all_categories = categories()
    documents = documents_for(category)
    counts = {cat: query_one("SELECT COUNT(*) AS total FROM documents WHERE category = ?", (cat,))["total"] for cat in all_categories}
    context = context_for_page("/knowledge-base", user)
    context.update(
        {
            "categories": all_categories,
            "selected_category": category or "All",
            "category_counts": counts,
            "documents": documents,
            "doc_count": query_one("SELECT COUNT(*) AS total FROM documents")["total"],
        }
    )
    return templates.TemplateResponse(request, "knowledge_base.html", context)


@app.get("/documents/{document_id}")
def document_download(document_id: int, request: Request):
    require_permission(request, "ask")
    row = query_one("SELECT * FROM documents WHERE id = ?", (document_id,))
    if not row or not row["stored_path"]:
        raise HTTPException(status_code=404, detail="Document file is not available.")
    path = BASE_DIR / row["stored_path"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored file is missing.")
    media_type = row["content_type"] or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=row["original_filename"] or path.name)


@app.get("/admin/roles")
def admin_roles(request: Request):
    user = page_user(request, "users")
    if isinstance(user, RedirectResponse):
        return user
    roles = [dict(row) for row in query_all("SELECT * FROM roles ORDER BY id")]
    users = [
        dict(row)
        for row in query_all(
            """
            SELECT u.id, u.name, u.email, u.is_active, r.name AS role
            FROM users u
            JOIN roles r ON r.id = u.role_id
            ORDER BY u.name
            """
        )
    ]
    context = context_for_page("/admin/roles", user)
    context.update({"roles": roles, "users": users})
    return templates.TemplateResponse(request, "admin_roles.html", context)


@app.get("/admin/audit-logs")
def audit_logs(request: Request, action: str | None = None, user_name: str | None = None, date: str | None = None):
    user = page_user(request, "users")
    if isinstance(user, RedirectResponse):
        return user
    clauses = []
    params: list[Any] = []
    if action and action != "All actions":
        clauses.append("action_type = ?")
        params.append(action)
    if user_name and user_name != "All users":
        clauses.append("user_name = ?")
        params.append(user_name)
    if date:
        clauses.append("date(created_at) = date(?)")
        params.append(date)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    logs = [
        {
            "icon": row["icon"],
            "user": row["user_name"],
            "action": row["action"],
            "when": display_time(row["created_at"]),
            "action_type": row["action_type"],
        }
        for row in query_all(f"SELECT * FROM audit_logs {where} ORDER BY created_at DESC, id DESC LIMIT 100", tuple(params))
    ]
    users = [dict(row) for row in query_all("SELECT name FROM users ORDER BY name")]
    actions = ["Login", "Logout", "Document upload", "Role change", "User change", "Chat"]
    context = context_for_page("/admin/audit-logs", user)
    context.update({"users": users, "logs": logs, "actions": actions, "selected_action": action or "All actions", "selected_user": user_name or "All users", "selected_date": date or ""})
    return templates.TemplateResponse(request, "audit_logs.html", context)


@app.post("/api/login")
async def api_login(payload: dict):
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "")
    if not email or not password:
        return JSONResponse(status_code=400, content={"detail": "Email and password are required."})

    row = query_one(
        """
        SELECT u.*, r.name AS role
        FROM users u
        JOIN roles r ON r.id = u.role_id
        WHERE lower(u.email) = ? AND u.is_active = 1
        """,
        (email,),
    )
    if not row or not verify_password(password, row["password_hash"]):
        audit("Login", None, f"failed login attempt for {email}", "warning")
        return JSONResponse(status_code=401, content={"detail": "Invalid email or password."})

    payload = {"user_id": row["id"], "expires": int(time.time()) + COOKIE_MAX_AGE}
    response = JSONResponse(content={"redirect": "/dashboard", "role": row["role"], "name": row["name"]})
    response.set_cookie(COOKIE_NAME, sign_payload(payload), max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax")
    audit("Login", row, "logged in", "login")
    return response


@app.post("/api/chat")
async def api_chat(payload: dict, request: Request):
    user = require_permission(request, "ask")
    question = payload.get("question", "").strip()
    session_id = payload.get("session_id")
    if not question:
        return JSONResponse(status_code=400, content={"detail": "Question is required."})

    if session_id:
        session = query_one("SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?", (session_id, user["id"]))
        if not session:
            return JSONResponse(status_code=404, content={"detail": "Chat session not found."})
    else:
        title = question[:70] + ("..." if len(question) > 70 else "")
        session_id = execute(
            "INSERT INTO chat_sessions (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (user["id"], title, utc_now(), utc_now()),
        )

    contexts = retrieve_context(question)
    answer, used_ollama = await generate_answer(question, contexts)
    sources = [{"document": item["document"], "page": item["page"], "document_id": item["document_id"]} for item in contexts]
    with db_connection() as conn:
        conn.execute(
            "INSERT INTO chat_messages (session_id, sender, message, created_at) VALUES (?, ?, ?, ?)",
            (session_id, "user", question, utc_now()),
        )
        conn.execute(
            "INSERT INTO chat_messages (session_id, sender, message, sources_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, "bot", answer, json.dumps(sources), utc_now()),
        )
        conn.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (utc_now(), session_id))
    audit("Chat", user, f"asked {CHATBOT_NAME}: {question[:90]}", "chat")
    return {"answer": answer, "sources": sources, "session_id": session_id, "assistant": CHATBOT_NAME, "used_ollama": used_ollama}


@app.post("/api/upload")
async def api_upload(request: Request, file: UploadFile = File(...), category: str = Form(...)):
    user = require_permission(request, "docs")
    if not file.filename:
        return JSONResponse(status_code=400, content={"detail": "A file is required."})
    if Path(file.filename).suffix.lower() not in {".pdf", ".docx", ".txt"}:
        return JSONResponse(status_code=400, content={"detail": "Only PDF, DOCX, and TXT files are supported locally."})
    return save_document(file, category, user)


@app.post("/api/roles/{role_id}")
async def api_update_role(role_id: int, payload: dict, request: Request):
    user = require_permission(request, "users")
    allowed = {"ask", "docs", "users", "maintenance"}
    updates = {key: int(bool(payload[key])) for key in allowed if key in payload}
    if not updates:
        return JSONResponse(status_code=400, content={"detail": "No role permissions supplied."})
    assignments = ", ".join(f"{key} = ?" for key in updates)
    params = tuple(updates.values()) + (role_id,)
    execute(f"UPDATE roles SET {assignments} WHERE id = ?", params)
    role = query_one("SELECT name FROM roles WHERE id = ?", (role_id,))
    audit("Role change", user, f"updated role permissions for {role['name'] if role else role_id}", "admin_panel_settings")
    return {"status": "updated", "role_id": role_id}


@app.post("/api/users/{user_id}/role")
async def api_update_user_role(user_id: int, payload: dict, request: Request):
    user = require_permission(request, "users")
    role_name = payload.get("role")
    role = query_one("SELECT id, name FROM roles WHERE name = ?", (role_name,))
    target = query_one("SELECT name FROM users WHERE id = ?", (user_id,))
    if not role or not target:
        return JSONResponse(status_code=404, content={"detail": "User or role not found."})
    execute("UPDATE users SET role_id = ? WHERE id = ?", (role["id"], user_id))
    audit("User change", user, f"changed {target['name']}'s role to {role['name']}", "manage_accounts")
    return {"status": "updated", "user_id": user_id, "role": role["name"]}


if __name__ == "__main__":
    import uvicorn

    initialize_database()
    uvicorn.run(app, host="0.0.0.0", port=8000)
