"""
Ministry of ICT and National Guidance â€” Offline RAG Chatbot
FastAPI frontend server.

This replaces Streamlit as the UI layer (per project decision â€” Streamlit
can't cleanly host a custom multi-role design like this one). FastAPI was
chosen because it's pure Python, integrates directly with the rest of the
finalized stack (LangChain, ChromaDB, Ollama) with no extra glue, and
supports async request handling, which matters when calls to the local
LLM (Ollama) or the embedding model take a moment to return.

Every /api/* endpoint below is a MOCK standing in for the real RAG Engine,
ChromaDB retriever, and document loader described in the Class/Sequence
diagrams. Swap the mock logic for real calls; the request/response shapes
already match what the frontend expects, so no template/JS changes should
be needed when the real pipeline is wired in.
"""

import asyncio
import random
import time
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Ministry Offline RAG Chatbot")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# ---------------------------------------------------------------------------
# Mock "session" â€” replace with real auth (see User/Role classes) later.
# ---------------------------------------------------------------------------
CURRENT_USER = {"name": "Stephen Okello", "role": "ICT Admin"}

NAV_BY_ROLE = [
    {"label": "Dashboard", "href": "/dashboard"},
    {"label": "Chat", "href": "/chat"},
    {"label": "Knowledge Base", "href": "/knowledge-base"},
    {"label": "Upload", "href": "/upload"},
    {"label": "Admin", "href": "/admin/roles"},
]


def nav_for(active_href: str):
    items = []
    for item in NAV_BY_ROLE:
        items.append({**item, "active": item["href"] == active_href})
    return items


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------
@app.get("/")
def landing(request: Request):
    return templates.TemplateResponse(request, "landing.html", {"nav_items": []})


@app.get("/login")
def login(request: Request):
    return templates.TemplateResponse(request, "login.html", {"nav_items": []})


@app.get("/dashboard")
def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", {"nav_items": nav_for("/dashboard"),
            "user_name": CURRENT_USER["name"],
            "user_role": CURRENT_USER["role"],
            "can_upload": CURRENT_USER["role"] in ("ICT Admin", "Knowledge Management Officer"),
            "doc_count": 128,
            "recent_chats": [
                {"title": "Data Protection Act consent requirements", "when": "2h ago"},
                {"title": "Procurement threshold for ICT equipment", "when": "Yesterday"},
                {"title": "Cybersecurity framework alignment", "when": "3 days ago"},
            ],
            "pinned_docs": ["National ICT Policy 2024", "Data Protection and Privacy Act 2019", "Electronic Transactions Act"],
        },
    )


@app.get("/chat")
def chat_page(request: Request):
    return templates.TemplateResponse(request, "chat.html", {"nav_items": nav_for("/chat"),
            "user_name": CURRENT_USER["name"],
            "recent_chats": [
                {"title": "Data Protection Act consent requirements"},
                {"title": "Procurement threshold for ICT equipment"},
                {"title": "Cybersecurity framework alignment"},
            ],
        },
    )


@app.get("/upload")
def upload_page(request: Request):
    return templates.TemplateResponse(request, "upload.html", {"nav_items": nav_for("/upload"),
            "categories": ["Legal & Regulatory", "ICT Standards", "Procurement Guidelines", "National Policies"],
        },
    )


@app.get("/knowledge-base")
def knowledge_base(request: Request):
    categories = ["Legal & Regulatory", "ICT Standards", "Procurement Guidelines", "National Policies"]
    documents = [
        {"title": "National ICT Policy 2024", "category": "National Policies", "uploaded": "12 Jun 2026", "chunks": 84},
        {"title": "Data Protection and Privacy Act 2019", "category": "Legal & Regulatory", "uploaded": "03 May 2026", "chunks": 61},
        {"title": "Computer Misuse Act", "category": "Legal & Regulatory", "uploaded": "03 May 2026", "chunks": 45},
        {"title": "National Information Security Framework", "category": "ICT Standards", "uploaded": "21 Apr 2026", "chunks": 72},
        {"title": "Public ICT Procurement Guidelines", "category": "Procurement Guidelines", "uploaded": "14 Mar 2026", "chunks": 38},
    ]
    return templates.TemplateResponse(request, "knowledge_base.html", {"nav_items": nav_for("/knowledge-base"),
            "categories": categories,
            "category_counts": {c: sum(1 for d in documents if d["category"] == c) for c in categories},
            "documents": documents,
            "doc_count": len(documents),
        },
    )


@app.get("/admin/roles")
def admin_roles(request: Request):
    roles = [
        {"name": "System Administrator", "ask": True, "docs": True, "users": True, "maintenance": True},
        {"name": "Knowledge Management Officer", "ask": True, "docs": True, "users": False, "maintenance": False},
        {"name": "Ministry Staff", "ask": True, "docs": False, "users": False, "maintenance": False},
        {"name": "ICT Consultant", "ask": True, "docs": False, "users": False, "maintenance": False},
        {"name": "Ministry Intern", "ask": True, "docs": False, "users": False, "maintenance": False},
        {"name": "Citizen", "ask": True, "docs": False, "users": False, "maintenance": False},
    ]
    users = [
        {"name": "Stephen Okello", "role": "System Administrator"},
        {"name": "Grace Nabirye", "role": "Knowledge Management Officer"},
        {"name": "Daniel Ochieng", "role": "Ministry Staff"},
    ]
    return templates.TemplateResponse(request, "admin_roles.html", {"nav_items": nav_for("/admin/roles"), "roles": roles, "users": users},
    )


@app.get("/admin/audit-logs")
def audit_logs(request: Request):
    users = [{"name": "Stephen Okello"}, {"name": "Grace Nabirye"}, {"name": "Daniel Ochieng"}]
    logs = [
        {"icon": "login", "user": "Stephen Okello", "action": "logged in", "when": "10:42 AM"},
        {"icon": "upload_file", "user": "Grace Nabirye", "action": "uploaded 'National ICT Policy 2024'", "when": "09:15 AM"},
        {"icon": "admin_panel_settings", "user": "Stephen Okello", "action": "updated role permissions for Ministry Intern", "when": "Yesterday, 4:02 PM"},
        {"icon": "delete", "user": "Grace Nabirye", "action": "removed an outdated procurement circular", "when": "Yesterday, 11:30 AM"},
    ]
    return templates.TemplateResponse(request, "audit_logs.html", {"nav_items": nav_for("/admin/audit-logs"), "users": users, "logs": logs},
    )


# ---------------------------------------------------------------------------
# Mock API â€” replace internals with the real pipeline, shapes stay the same.
# ---------------------------------------------------------------------------
@app.post("/api/login")
async def api_login(payload: dict):
    email = payload.get("email", "")
    password = payload.get("password", "")
    if not email or not password:
        return JSONResponse(status_code=400, content={"detail": "Email and password are required."})
    # TODO: replace with real User/Role lookup (see Class Diagram)
    return {"redirect": "/dashboard", "role": "ICT Admin"}


@app.post("/api/chat")
async def api_chat(payload: dict):
    """Mock RAG Engine. Real version: embed(question) -> ChromaDB.search()
    (role-filtered) -> Ollama/Phi-4-mini generate() -> return answer + Source
    Reference list. See Sequence Diagram 1."""
    question = payload.get("question", "")
    await asyncio.sleep(1.1)  # simulate retrieval + generation latency
    return {
        "answer": (
            f"Based on the Data Protection and Privacy Act 2019, personal data may only be processed "
            f"with the data subject's consent, unless another lawful basis applies (e.g. a legal obligation). "
            f"(This is a placeholder answer for: \"{question}\" â€” replace with the real RAG Engine output.)"
        ),
        "sources": [
            {"document": "Data Protection and Privacy Act 2019", "page": 7},
            {"document": "National ICT Policy 2024", "page": 22},
        ],
    }


@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...), category: str = Form(...)):
    """Mock ingestion pipeline: loader -> chunk -> embed -> store.
    See Sequence Diagram 2 (steps 2-6)."""
    contents = await file.read()
    await asyncio.sleep(1.2)  # simulate extract + embed + store
    chunks = max(1, len(contents) // 2000)
    return {"status": "indexed", "category": category, "chunks": chunks}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
