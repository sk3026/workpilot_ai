import os
import json
import fitz  # PyMuPDF
from app.config import settings
from app.database import SessionLocal, InvoiceRecord

def scan_inbox(query: str) -> dict:
    manifest_path = os.path.abspath(os.path.join(os.path.dirname(__file__), settings.INBOX_DIR, "inbox_metadata.json"))
    if not os.path.exists(manifest_path):
        return {"status": "error", "message": f"Inbox manifest not found at {manifest_path}"}

    with open(manifest_path, "r") as f:
        emails = json.load(f)

    query_lower = query.lower()
    matches = [
        e for e in emails
        if query_lower in e.get("sender", "").lower()
        or query_lower in e.get("subject", "").lower()
    ]
    return {"status": "success", "found_count": len(matches), "emails": matches}

def read_pdf_invoice(file_path: str) -> dict:
    try:
        doc = fitz.open(file_path)
        raw_text = "".join([page.get_text("text") for page in doc])
        doc.close()
        return {"status": "success", "file_path": file_path, "raw_text": raw_text}
    except Exception as e:
        return {"status": "error", "message": f"Failed to parse PDF: {str(e)}"}

def check_duplicate_invoice(invoice_number: str) -> dict:
    session = SessionLocal()
    existing = session.query(InvoiceRecord).filter_by(invoice_number=invoice_number).first()
    session.close()

    if existing:
        return {
            "status": "EXISTS",
            "invoice_number": existing.invoice_number,
            "recorded_db_id": existing.id,
            "vendor_name": existing.vendor_name,
            "recorded_amount": existing.amount,
            "recorded_due_date": existing.due_date,
            "recorded_at": str(existing.created_at)
        }
    return {"status": "NOT_FOUND", "invoice_number": invoice_number}

def update_invoice_ledger(invoice_number: str, vendor_name: str, amount: float, due_date: str, email_date: str, file_location: str) -> dict:
    if amount > settings.APPROVAL_THRESHOLD_AMOUNT:
        return {
            "status": "AWAITING_HUMAN_APPROVAL",
            "reason": f"Invoice amount (${amount:,.2f}) exceeds safety limit (${settings.APPROVAL_THRESHOLD_AMOUNT:,.2f}).",
            "pending_payload": {
                "invoice_number": invoice_number,
                "vendor_name": vendor_name,
                "amount": amount,
                "due_date": due_date,
                "email_date": email_date,
                "file_location": file_location
            }
        }

    session = SessionLocal()
    try:
        record = InvoiceRecord(
            invoice_number=invoice_number,
            vendor_name=vendor_name,
            amount=amount,
            due_date=due_date,
            email_date=email_date,
            file_location=file_location,
            status="RECORDED"
        )
        session.add(record)
        session.commit()
        rec_id = record.id
        session.close()
        return {"status": "SUCCESS", "recorded_db_id": rec_id, "invoice_number": invoice_number}
    except Exception as e:
        session.rollback()
        session.close()
        return {"status": "ERROR", "message": str(e)}

def verify_invoice_record(invoice_number: str) -> dict:
    session = SessionLocal()
    record = session.query(InvoiceRecord).filter_by(invoice_number=invoice_number).first()
    session.close()

    if record:
        return {
            "verified": True,
            "db_id": record.id,
            "invoice_number": record.invoice_number,
            "vendor_name": record.vendor_name,
            "amount": record.amount,
            "status": record.status
        }
    return {"verified": False, "reason": "Record entry not found in database"}

def dispatch_tool(tool_name: str, args: dict) -> dict:
    tool_map = {
        "scan_inbox": scan_inbox,
        "read_pdf_invoice": read_pdf_invoice,
        "check_duplicate_invoice": check_duplicate_invoice,
        "update_invoice_ledger": update_invoice_ledger,
        "verify_invoice_record": verify_invoice_record,
    }
    fn = tool_map.get(tool_name)
    if fn:
        return fn(**args)
    return {"status": "error", "message": f"Unknown tool: {tool_name}"}

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "scan_inbox",
            "description": "Searches inbox for emails matching vendor name or query.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_pdf_invoice",
            "description": "Reads raw text content from local PDF invoice.",
            "parameters": {
                "type": "object",
                "properties": {"file_path": {"type": "string"}},
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_duplicate_invoice",
            "description": "Queries database to check if invoice number exists.",
            "parameters": {
                "type": "object",
                "properties": {"invoice_number": {"type": "string"}},
                "required": ["invoice_number"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_invoice_ledger",
            "description": "Records a new invoice entry in internal finance database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice_number": {"type": "string"},
                    "vendor_name": {"type": "string"},
                    "amount": {"type": "number"},
                    "due_date": {"type": "string"},
                    "email_date": {"type": "string"},
                    "file_location": {"type": "string"}
                },
                "required": ["invoice_number", "vendor_name", "amount", "due_date", "email_date", "file_location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "verify_invoice_record",
            "description": "Verifies invoice record was accurately saved into database.",
            "parameters": {
                "type": "object",
                "properties": {"invoice_number": {"type": "string"}},
                "required": ["invoice_number"]
            }
        }
    }
]