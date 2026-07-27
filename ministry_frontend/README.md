# Ministry of ICT and National Guidance — Offline RAG Chatbot Frontend

FastAPI frontend replacing Streamlit (see project notes: Streamlit couldn't
cleanly host this custom multi-role Tailwind design). Built from the
original Stitch UI/UX export, with these fixes applied:

1. Real Ministry logo (from your uploaded assets) replaces the generic
   placeholder icon used across the original 63-screen export.
2. "FIPS Compliant" badge (a US standard, irrelevant to Uganda) removed;
   replaced with "Data Protection & Privacy Act 2019 Compliant".
3. Accent color unified to a single gold (drawn from the national flag)
   instead of the two conflicting colors (orange vs light blue) found
   across the original design variants.
4. AI-generated fictional staff photos replaced with deterministic
   initials avatars — no photo consent needed, no fabricated people.
5. One canonical version picked per screen (the "_ministry_rag_chatbot"
   line) instead of keeping multiple design-exploration duplicates.

Design touches borrowed from other real Ministry systems:
- The "Can't log in?" progressive-disclosure help pattern and the
  "contact your entity System Administrator" fallback come from
  edocs.go.ug's login flow.
- Footer links to the real eDocs+ (EDRMS) system for cross-system
  consistency with the rest of the Ministry's digital estate.

## Running it

```
pip install -r requirements.txt
python app.py
```
Then open http://localhost:8000

## What's real vs. mocked

- All page routes and templates are real and fully wired.
- `/api/login`, `/api/chat`, `/api/upload` are MOCKS standing in for the
  real RAG Engine (LangChain + ChromaDB + Ollama/Phi-4-mini). Each mock's
  request/response shape already matches the Class Diagram and Sequence
  Diagrams, so wiring in the real pipeline shouldn't require frontend
  changes — just replace the function bodies in app.py.

## Screens included in this pass

landing, login, dashboard, chat workspace, upload documents, knowledge
base, admin roles & permissions, admin audit logs — the core journey
across every actor in the Use Case Diagram. The remaining ~55 screens
from the original Stitch export (settings, notifications, profile, OTP,
etc.) follow the same base.html/style.css system and can be added the
same way.
