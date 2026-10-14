# WorkPilot: Autonomous Enterprise Financial Task Worker

WorkPilot is an enterprise-grade autonomous financial task worker designed to automate the extraction, multi-tier verification, approval routing, and ledger recording of vendor PDF invoices.

Built with **FastAPI, React (Vite), Groq, PyMuPDF, and SQLite**, WorkPilot implements a ReAct (Reasoning + Acting) agent loop with human-in-the-loop (HITL) safety thresholds for high-value transactions (≥ $10,000).

---

## 🏗️ System Architecture

WorkPilot operates as a single-service or decoupled full-stack workspace. The system architecture consists of four distinct layers:

```text
┌─────────────────────────────────────────────────────────────┐
│                  React Frontend Workbench                   │
│  - Live EventSource SSE Listener                             │
│  - Interactive Agent Event Display                          │
│  - Pre-Commit Decision Tree Action Buttons                  │
│  - Real-Time Transaction Sidebar and Redirect Feed          │
└──────────────────────────────┬──────────────────────────────┘
                               │
                      HTTP / SSE (Port 8000)
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                 FastAPI Application Gateway                  │
│  - GET  /api/v1/run-stream                                   │
│  - GET  /api/v1/transactions                                  │
│  - GET  /api/v1/transactions/{id}                             │
│  - POST /api/v1/approve                                      │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                  ReAct Agent Execution Engine                │
│  - Groq LLM Integration                                      │
│  - Multi-Step Tool Dispatcher                                │
│  - Windows Path Sanitization                                 │
│  - Agent Execution Loop with Iteration Limit                 │
└──────────────┬────────────────┬────────────────┬────────────┘
               │                │                │
               ▼                ▼                ▼
       ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐
       │ Inbox Scanner│ │ PyMuPDF      │ │ SQLite Database    │
       │              │ │ Invoice Parser│ │ Ledger             │
       └──────────────┘ └──────────────┘ └────────────────────┘
```

---

## 🧠 Multi-Tier Verification & Execution Flow

When a user submits a prompt, such as "Scan inbox for ABC Corp and process the invoice", WorkPilot executes the following pipeline:

```text
User Request
     |
     v
1. scan_inbox(vendor_name)
     |
     v
2. read_pdf_invoice(file_path)
     |
     +---- Amount >= $10,000? ---- YES ----> Human Approval Required
     |                                         Halt for approval
     |
     NO
     |
     v
3. verify_invoice_data(...)
     |
     +---- Missing or invalid fields? ---- YES ----> Verification Warning
     |                                                Provide Missing Details / Skip
     |
     NO
     |
     v
4. check_duplicate_invoice(...)
     |
     +---- Invoice exists? ---- YES ----> Duplicate Record Warning
     |                                     View Transaction / Scan Next
     |
     NO
     |
     v
5. Emit Pre-Commit State
     |
     v
6. User chooses Store & Record in Ledger
     |
     v
7. update_invoice_ledger(...)
     |
     v
8. verify_ledger_entry(...)
     |
     v
Confirm successful ledger persistence
```

### Safety and Verification Rules

- Required invoice fields must be present and valid before recording.
- Duplicate invoices must be detected before creating a new ledger entry.
- Invoices of $10,000 or more require human approval.
- A new transaction is presented for confirmation before ledger recording.
- Ledger persistence is verified after recording.

---

## 📋 Required Fields & Validation Standards

| Field | Expected Format | Verification Rule |
|---|---|---|
| Invoice Number | String, e.g. `INV-2026-001` | Must be non-empty and not `UNKNOWN`. |
| Vendor Name | String, e.g. `ABC Corp` | Must be present and match the vendor information. |
| Amount | Positive numeric value | Must be valid; amounts ≥ $10,000 require human approval. |
| Due Date | ISO date, `YYYY-MM-DD` | Must be a valid date. |
| Source File Location | Absolute system path | Must identify the invoice source file. |
| Target Database | File path | SQLite database location, configured by the application. |

---

## 📁 Repository Directory Structure

```text
workpilot/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── api.py              # FastAPI REST and SSE routes
│   │   ├── config.py           # Environment variables and Groq configuration
│   │   ├── database.py         # SQLite connection and schema initialization
│   │   ├── engine.py           # ReAct agent loop and tool dispatching
│   │   ├── main.py             # ASGI application entry point
│   │   └── tools.py            # PDF parsing, validation and ledger handlers
│   └── requirements.txt        # Backend dependencies
├── frontend/
│   ├── src/
│   │   ├── WorkPilotChat.jsx   # Main WorkPilot interface
│   │   ├── index.css           # Application styles
│   │   ├── main.jsx            # React entry point
│   │   └── App.jsx             # Root React component
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── data/
│   ├── invoices/               # Invoice PDF storage
│   └── workpilot.db            # SQLite ledger database
├── render.yaml                 # Render deployment configuration
└── README.md
```

---

## 🗄️ Database Schema

WorkPilot stores invoice transactions in an SQLite table named `invoices`.

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

The invoice number is unique, helping prevent duplicate ledger entries.

---

## 🔌 API Endpoints

### 1. Execute Task Stream

**Endpoint:** `GET /api/v1/run-stream?prompt={query}`

**Response type:** `text/event-stream`

This endpoint streams agent execution events to the frontend.

Supported event types:

- `AGENT_START` — Agent initialization.
- `TOOL_CALL` — A tool is being invoked.
- `OBSERVATION` — The result returned by a tool.
- `APPROVAL_REQUIRED` — Human approval is required.
- `FINAL_ANSWER` — Workflow completion or final response.

### 2. Fetch Ledger Transactions

**Endpoint:** `GET /api/v1/transactions`

Returns invoice transactions sorted by newest first.

### 3. Fetch Transaction Details

**Endpoint:** `GET /api/v1/transactions/{tx_id}`

Returns the details of a specific invoice transaction.

### 4. Human Approval Endpoint

**Endpoint:** `POST /api/v1/approve`

Example request body:

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

Example response:

```json
{
  "status": "approved",
  "recorded_db_id": 42
}
```

The actual transaction ID will depend on the database.

---

## 🚀 Local Development Setup

### Prerequisites

- Python 3.10 or newer
- Node.js 18 or newer
- A Groq API key

### 1. Clone the Repository

```bash
git clone <your-github-repository-url>
cd workpilot
```

Replace the placeholder with your actual GitHub repository URL.

### 2. Configure Environment Variables

Create a `.env` file inside the `backend/` directory.

```env
GROQ_API_KEY=your_groq_api_key_here
```

Obtain an API key from [Groq Console](https://console.groq.com/).

Do not commit your `.env` file or expose your API key in the repository.

### 3. Install Backend Dependencies

From the project root:

```powershell
cd backend
python -m venv venv
```

Activate the virtual environment on Windows:

```powershell
venv\Scripts\activate
```

Install the dependencies:

```powershell
pip install -r requirements.txt
```

### 4. Start the Backend Server

```powershell
uvicorn app.main:app --reload --port 8000
```

Open the API documentation:

[http://localhost:8000/docs](http://localhost:8000/docs)

### 5. Start the Frontend

Open a separate terminal at the project root:

```powershell
cd frontend
npm install
npm run dev
```

Open the frontend at:

[http://localhost:5173](http://localhost:5173)

---

## ☁️ Production Deployment on Render

WorkPilot is intended to use a unified Render web service in which FastAPI serves the built React frontend from `frontend/dist`.

### Deployment Steps

1. Commit and push the project to GitHub.
2. Sign in to the [Render Dashboard](https://dashboard.render.com/).
3. Select **New + → Blueprint**.
4. Connect the GitHub repository containing `render.yaml`.
5. Configure `GROQ_API_KEY` in the service's environment settings.
6. Review the build and start commands in `render.yaml`.
7. Click **Apply** to deploy.
8. Open the generated Render URL and verify the frontend and API endpoints.

### Deployment Considerations

- Ensure the frontend is built before FastAPI attempts to serve `frontend/dist`.
- Ensure the backend start command uses the correct application module.
- Configure environment variables through Render rather than committing secrets.
- Verify the invoice directory and SQLite database paths.
- Render's default filesystem may be ephemeral. Use persistent storage or an appropriate external database if ledger data must survive restarts and redeployments.
- Test invoice extraction, duplicate detection, approval handling and ledger persistence before processing real financial records.



## 🔒 Security Considerations

- Keep API keys in environment variables.
- Require human approval for high-value invoices.
- Validate invoice fields before recording.
- Check for duplicate invoices before inserting transactions.
- Verify ledger persistence after a write.
- Protect approval and ledger endpoints from unauthorized access before exposing the application publicly.

---

## 📌 Project Summary

WorkPilot combines an LLM-powered agent loop, PDF invoice extraction, multi-tier validation, duplicate detection, human approval, and a SQLite ledger in a full-stack financial workflow application.

The goal is to reduce repetitive invoice-processing work while retaining verification and human oversight for sensitive financial operations.
