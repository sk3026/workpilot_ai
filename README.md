# WorkPilot: Autonomous Enterprise Financial Task Worker

WorkPilot is an enterprise-grade, autonomous financial task worker designed to automate the extraction, multi-tier verification, approval routing, and ledger recording of vendor PDF invoices.

Built with **FastAPI**, **React (Vite)**, **Groq Llama-3.1 Models**, **PyMuPDF**, and **SQLite**, WorkPilot implements a ReAct (Reasoning + Acting) agent loop with human-in-the-loop (HITL) safety thresholds for high-value transactions ($\ge \$10,000$).

---

## 🏗️ System Architecture

WorkPilot operates as a single-port or decoupled full-stack workspace. The system architecture consists of four distinct layers:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       React Frontend Workbench                              │
│  - Live EventSource SSE Listener                                            │
│  - Interactive Thought-Chain Accordions                                     │
│  - Pre-Commit Decision Tree Action Pills                                    │
│  - Real-Time Transaction Sidebar & Redirect Feed                            │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                          HTTP / SSE Stream (Port 8000)
                                    │
┌───────────────────────────────────▼─────────────────────────────────────────┐
│                        FastAPI Application Gateway                          │
│  - GET  /api/v1/run-stream?prompt=...  (EventSource SSE Stream)             │
│  - GET  /api/v1/transactions           (Sidebar Ledger Queries)            │
│  - GET  /api/v1/transactions/{id}      (Transaction Redirection View)       │
│  - POST /api/v1/approve                (Human Safety Gate Decision Endpoint)│
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼─────────────────────────────────────────┐
│                      ReAct Agent Execution Engine                           │
│  - Groq LLM (llama-3.1-8b-instant / llama-3.3-70b-versatile)               │
│  - Multi-Step Tool Dispatcher & Backslash Path Sanitizers                   │
│  - Agentic State Loop (Max 8 Iteration Guard)                               │
└──────────────┬────────────────────┬───────────────────┬─────────────────────┘
               │                    │                   │
               ▼                    ▼                   ▼
┌──────────────────────┐  ┌──────────────────┐  ┌─────────────────────────────┐
│    Inbox Scanner     │  │  PyMuPDF Parser  │  │ SQLite Database Ledger      │
│ (Vendor Query Filter)│  │ (Regex Extraction│  │ (data/workpilot.db)         │
│                      │  │  & Validation)   │  │                             │
└──────────────────────┘  └──────────────────┘  └─────────────────────────────┘
```

---

## 🧠 Multi-Tier Verification & Execution Flow

When a user submits a prompt (e.g., *"Scan inbox for ABC Corp and process the invoice"*), WorkPilot executes the following multi-tier verification pipeline:

```
[User Request]
       │
       ▼
1. scan_inbox(vendor_name) ──► Extracts clean vendor attachment (.pdf)
       │
       ▼
2. read_pdf_invoice(file_path) ──► Parses Invoice No, Amount, Due Date, Vendor
       │
       ├──► [Amount >= $10,000?] ──► YES ──► Emit APPROVAL_REQUIRED Event
       │                                     (Halt for Human Approval Gate)
       ▼ NO
3. verify_invoice_data(...)
       │
       ├──► [Missing/Invalid Fields?] ──► YES ──► Output Verification Warning
       │                                           (Provide Missing Details / Skip)
       ▼ NO (All Fields Valid)
4. check_duplicate_invoice(...)
       │
       ├──► [Found in DB?] ──► YES ──► Output Duplicate Record Warning
       │                               (Provide View Transaction #ID Pill)
       ▼ NO (New Transaction)
5. Emit Pre-Commit State ──► Displays Parsed Record & Source File Paths
       │                      Provide ["Store & Record in Ledger", "Skip Invoice"]
       ▼
6. update_invoice_ledger(...) ──► Persists Row to SQLite DB (status: 'VERIFIED')
       │
       ▼
7. verify_ledger_entry(...) ──► Confirms Row Creation & Returns Transaction ID
```

---

## 📋 Required Fields & Validation Standards

Every processed invoice must satisfy strict data completeness standards before being committed to the ledger:

| Field Name | Expected Format / Type | Verification Rule |
| :--- | :--- | :--- |
| **Invoice Number** | `String` (e.g., `INV-2026-001`) | Must be non-empty, non-`UNKNOWN`, and strictly match regex anchors. |
| **Vendor Name** | `String` (e.g., `ABC Corp`) | Must be non-empty and match vendor entity metadata. |
| **Amount** | `Float` (e.g., `1250.00`) | Must be a positive numerical value. If $\ge \$10,000$, halts for human safety approval. |
| **Due Date** | `ISO Date String` (`YYYY-MM-DD`) | Must be a valid date string. |
| **Source File Location** | `Absolute System Path` | Path backslashes (`\`) are auto-sanitized to avoid JSON escaping crashes. |
| **Target Database** | `File System Path` | `data/workpilot.db` (SQLite engine). |

---

## 📁 Repository Directory Structure

```text
workpilot/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── api.py           # FastAPI REST & SSE Route Definitions
│   │   ├── config.py        # Environment variables & Groq API configuration
│   │   ├── database.py      # SQLite connection helpers & schema initializers
│   │   ├── engine.py        # ReAct Agent loop, Groq LLM streaming, & tool dispatching
│   │   ├── main.py          # ASGI application entrypoint & static mount
│   │   └── tools.py         # PyMuPDF parser, regex extractor, and ledger handlers
│   └── requirements.txt     # Lightweight, Render-optimized Python dependencies
├── frontend/
│   ├── src/
│   │   ├── WorkPilotChat.jsx # Enterprise Workbench UI component
│   │   ├── index.css        # Enterprise dark-theme styles & animation keyframes
│   │   ├── main.jsx         # React application mounting point
│   │   └── App.jsx          # Top-level React wrapper
│   ├── index.html           # HTML template
│   ├── package.json         # Node dependencies (React, Vite)
│   └── vite.config.js       # Vite development configuration
├── data/
│   ├── invoices/            # Directory containing sample PDF invoices
│   └── workpilot.db         # SQLite persistent transaction storage
├── setup_workpilot_and_tests.py # Master setup script for README & PDF test creation
├── render.yaml              # Unified single-service Render deployment blueprint
└── README.md                # Project documentation
```

---

## 🗄️ Database Schema (`data/workpilot.db`)

WorkPilot stores transaction data in an SQLite table named `invoices`:

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

## 🔌 API Endpoints Specification

### 1. Execute Task Stream (SSE)
* **Endpoint:** `GET /api/v1/run-stream?prompt={query}`
* **Response Type:** `text/event-stream`
* **Event Types:**
  * `AGENT_START`: Agent initialization event.
  * `TOOL_CALL`: Executing a specific tool with parsed JSON arguments.
  * `OBSERVATION`: Output result returned by a tool execution.
  * `APPROVAL_REQUIRED`: Triggered when an invoice amount is $\ge \$10,000$.
  * `FINAL_ANSWER`: Workflow completion message containing text and `---ACTION_BUTTONS---`.

### 2. Fetch Ledger Transactions
* **Endpoint:** `GET /api/v1/transactions`
* **Response:** Array of recorded invoice objects sorted by newest first (`ORDER BY id DESC`).

### 3. Fetch Single Transaction Detail
* **Endpoint:** `GET /api/v1/transactions/{tx_id}`
* **Response:** Detailed JSON payload for direct redirect view.

### 4. Human Safety Gate Decision
* **Endpoint:** `POST /api/v1/approve`
* **Request Body:**
  ```json
  {
    "invoice_number": "INV-10992",
    "vendor_name": "Acme Supplies",
    "amount": 12500.00,
    "due_date": "2026-11-15",
    "file_location": "data/invoices/acme_10992.pdf",
    "approved": true
  }
  ```
* **Response:** `{"status": "approved", "recorded_db_id": 42}`

---

## 🧪 Test Case PDF Generation

To run and verify all agent scenarios (Standard Processing, Missing Fields, and Safety Gate), generate test PDF files locally using `pymupdf`:

### Generated Test Files Overview

| File Path | Vendor Name | Invoice Number | Amount | Test Scenario |
| :--- | :--- | :--- | :--- | :--- |
| `data/invoices/abc_corp_invoice.pdf` | ABC Corp | `INV-2026-001` | `$1,250.00` | **Standard Flow**: Clean extraction, pre-commit prompt, ledger persistence. |
| `data/invoices/tech_global_invoice.pdf` | Tech Global | `INV-2026-002` | `$3,400.00` | **Missing Field Flow**: Missing due date triggers verification warning. |
| `data/invoices/acme_supplies_invoice.pdf` | Acme Supplies | `INV-2026-003` | `$12,500.00` | **Safety Threshold Flow**: Exceeds $10,000, triggering Human Safety Gate. |

---

## 🚀 Local Development Setup

### Prerequisites
* **Python**: `3.10+`
* **Node.js**: `v18+`
* **Groq API Key**: Obtainable from [console.groq.com](https://console.groq.com)

### 1. Environment Configuration
Create a `.env` file inside `backend/`:

```env
GROQ_API_KEY=your_groq_api_key_here
```

### 2. Run Test Suite & Generate Test PDFs
Run the master setup script to synthesize sample invoice PDF test files:
```bash
python setup_workpilot_and_tests.py
```

### 3. Start Backend Server
```bash
cd backend
python -m venv venv
# On Windows: venv\Scripts\activate | On macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
*Verify backend API docs at `http://localhost:8000/docs`.*

### 4. Start Frontend Dev Server
In a separate terminal window:
```bash
cd frontend
npm install
npm run dev
```
*Open `http://localhost:5173` in your browser.*

---

## ☁️ Production Deployment (Render Free Tier)

WorkPilot is pre-configured with a unified single-service `render.yaml` blueprint. Under this configuration, FastAPI serves the pre-built React static assets directly from `frontend/dist`, ensuring zero CORS overhead and minimizing free-tier resource consumption.

### Deploying via Render Blueprints

1. Commit and push code to GitHub.
2. Log into **[Render Dashboard](https://dashboard.render.com)**.
3. Click **New +** $\rightarrow$ **Blueprint**.
4. Connect your GitHub repository.
5. Set `GROQ_API_KEY` under environment variables.
6. Click **Apply**.