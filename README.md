# WorkPilot: Autonomous Enterprise Financial Task Worker

**Live Demo:** [https://workpilot-ledger.onrender.com/](https://workpilot-ledger.onrender.com/)

WorkPilot is an autonomous financial task worker built to automate the extraction, multi-tier verification, approval routing, and ledger recording of vendor PDF invoices.

Built with **FastAPI, React (Vite), Groq, PyMuPDF, and SQLite**, WorkPilot uses a ReAct (Reasoning + Acting) agent loop paired with real-time Server-Sent Events (SSE) streaming and a human-in-the-loop (HITL) approval gate for high-value transactions ($\ge \$10,000$).

---

## Key Features

- **ReAct Agent Loop:** Multi-step tool execution powered by Groq LLM with structured iteration limits and cross-platform path sanitization.
- **Real-Time SSE Streaming:** Streams live agent reasoning steps (`AGENT_START`, `TOOL_CALL`, `OBSERVATION`, `APPROVAL_REQUIRED`, `FINAL_ANSWER`) directly to the React UI.
- **PDF Invoice Extraction:** Parses unstructured vendor PDFs from the inbox using PyMuPDF.
- **Multi-Tier Validation & Duplicate Guard:** Enforces schema validation and checks existing ledger entries before committing writes.
- **Human-in-the-Loop Safety Gate:** Automatically pauses execution and prompts for manual approval whenever an invoice equals or exceeds **$10,000**.
- **Ledger Management:** Interactive transaction history sidebar supporting single-record inspection and deletion.

---

## System Architecture

WorkPilot runs as a unified full-stack service where FastAPI serves both the REST/SSE API and the compiled React production bundle (`frontend/dist`).

```text
┌─────────────────────────────────────────────────────────────┐
│                  React Frontend Workbench                   │
│  - ReadableStream SSE Event Listener                        │
│  - Collapsible Agent Thought Chain Accordion                │
│  - Interactive HITL Approval & Decision Action Buttons      │
│  - Real-Time Transaction History Sidebar & Detail View      │
└──────────────────────────────┬──────────────────────────────┘
                               │
                     HTTP / SSE (/api/v1)
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                 FastAPI Application Gateway                  │
│  - GET    /api/v1/run-stream                                │
│  - GET    /api/v1/transactions                              │
│  - GET    /api/v1/transactions/{tx_id}                      │
│  - DELETE /api/v1/transactions/{tx_id}                      │
│  - POST   /api/v1/approve                                   │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                  ReAct Agent Execution Engine                │
│  - Groq LLM Integration                                     │
│  - Multi-Step Tool Dispatcher                               │
│  - Path Sanitization & Iteration Safeguards                 │
└──────────────┬────────────────┬────────────────┬────────────┘
               │                │                │
               ▼                ▼                ▼
       ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐
       │ Inbox Scanner│ │ PyMuPDF      │ │ SQLite Database    │
       │              │ │ Invoice Parser│ │ Ledger             │
       └──────────────┘ └──────────────┘ └────────────────────┘
```

---

## Execution & Verification Pipeline

When a user submits an instruction (e.g., *"Scan inbox for ABC Corp and process the invoice"*), WorkPilot runs the following workflow:

```text
User Prompt
     │
     ▼
1. scan_inbox(vendor_name)
     │
     ▼
2. read_pdf_invoice(file_path)
     │
     ├── Amount >= $10,000? ── YES ──► Emit APPROVAL_REQUIRED (Halt for Human Approval)
     │
     NO
     │
     ▼
3. verify_invoice_data(...)
     │
     ├── Missing/invalid fields? ── YES ──► Return Verification Warning
     │
     NO
     │
     ▼
4. check_duplicate_invoice(...)
     │
     ├── Invoice already exists? ── YES ──► Return Duplicate Warning + View Transaction Redirect
     │
     NO
     │
     ▼
5. Record in SQLite Ledger & Verify Persistence
```

### Validation Standards

| Field | Expected Format | Verification Rule |
|---|---|---|
| `invoice_number` | String (e.g., `INV-2026-001`) | Non-empty, not `UNKNOWN`, unique in ledger |
| `vendor_name` | String (e.g., `ABC Corp`) | Must be present and match extracted vendor |
| `amount` | Positive float | Must be $> 0$; amounts $\ge \$10,000$ trigger HITL gate |
| `due_date` | ISO Date (`YYYY-MM-DD`) | Must be a valid calendar date |
| `file_location` | System file path | Must resolve to a valid invoice PDF |

---

## Repository Structure

```text
workpilot/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── api.py              # FastAPI REST & SSE streaming endpoints
│   │   ├── config.py           # Pydantic settings & environment config
│   │   ├── database.py         # SQLite connection & table initialization
│   │   ├── engine.py           # ReAct agent loop & tool dispatcher
│   │   ├── main.py             # ASGI entrypoint & static SPA serving
│   │   └── tools.py            # Inbox scanner, PyMuPDF parser & ledger tools
│   └── requirements.txt        # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── WorkPilotChat.jsx   # Main chat, SSE stream & ledger UI
│   │   ├── index.css           # Application styling
│   │   ├── main.jsx            # React DOM entrypoint
│   │   └── App.jsx             # Root component
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── data/
│   ├── mock_inbox/             # Sample vendor PDF invoices
│   ├── seed_data.py            # Database seeding script
│   └── workpilot.db            # SQLite ledger database
├── render.yaml                 # Render Blueprint deployment config
└── README.md
```

---

## Database Schema

Transactions are stored in `data/workpilot.db` under the `invoices` table:

```sql
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number VARCHAR(100) NOT NULL UNIQUE,
    vendor_name VARCHAR(255) NOT NULL,
    amount REAL NOT NULL,
    due_date VARCHAR(50),
    file_location TEXT,
    status VARCHAR(50) DEFAULT 'VERIFIED',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/run-stream?prompt={query}` | Streams real-time agent execution events (`text/event-stream`) |
| `GET` | `/api/v1/transactions` | Lists all recorded ledger transactions (newest first) |
| `GET` | `/api/v1/transactions/{tx_id}` | Fetches full metadata for a single transaction |
| `DELETE` | `/api/v1/transactions/{tx_id}` | Deletes an individual transaction record from the ledger |
| `DELETE` | `/api/v1/transactions` | Clears all transaction records from the ledger |
| `POST` | `/api/v1/approve` | Submits human approval/rejection for high-value invoices |

---

## Local Development Setup

### Prerequisites
- Python 3.12+
- Node.js 18+
- A Groq API key from [console.groq.com](https://console.groq.com/)

### 1. Clone & Configure Environment
```bash
git clone [https://github.com/sk3026/workpilot_ai.git](https://github.com/sk3026/workpilot_ai.git)
cd workpilot_ai
```

Create `backend/.env`:
```env
GROQ_API_KEY=your_groq_api_key_here
```

### 2. Start the Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate        # On Windows (use `source venv/bin/activate` on macOS/Linux)
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
API docs are available at `http://localhost:8000/docs`.

### 3. Start the Frontend
Open a second terminal from the repository root:
```bash
cd frontend
npm install
npm run dev
```
Open the app at `http://localhost:5173`.

---

## Production Deployment (Render)

WorkPilot deploys as a unified web service via `render.yaml`:

- **Build Command:** `cd frontend && npm install && npm run build && cd ../backend && pip install -r requirements.txt`
- **Start Command:** `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Environment Variable:** `GROQ_API_KEY` configured in the Render dashboard.