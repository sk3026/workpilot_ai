import os
import re
import json
import sqlite3
import fitz  # PyMuPDF
from app.config import settings


def scan_inbox(query: str):
    manifest_path = os.path.join(settings.INBOX_DIR, "inbox_metadata.json")
    if not os.path.exists(manifest_path):
        return {"status": "ERROR", "message": f"Inbox manifest missing at {manifest_path}"}
    
    with open(manifest_path, "r") as f:
        emails = json.load(f)
    
    # Strip conversational stop words to isolate clean vendor search terms
    stop_words = {"invoice", "invoices", "scan", "inbox", "for", "process", "the", "and", "check", "email", "emails"}
    tokens = [w for w in re.findall(r"\w+", query.lower()) if w not in stop_words]
    clean_query = " ".join(tokens) if tokens else query.lower().strip()
    
    matched = []
    for e in emails:
        searchable_text = f"{e.get('sender', '')} {e.get('subject', '')} {e.get('body', '')}".lower()
        if clean_query and clean_query in searchable_text:
            matched.append(e)
        elif tokens and any(t in searchable_text for t in tokens):
            matched.append(e)

    if not matched:
        return {"status": "NOT_FOUND", "message": f"No emails matched query '{query}'"}
    
    email = matched[0]
    
    attachment_name = (
        email.get("attachment_file") or 
        email.get("attachment") or 
        email.get("file_name") or 
        email.get("filename") or 
        email.get("file") or 
        email.get("pdf_file") or 
        ""
    )

    if not attachment_name:
        for val in email.values():
            if isinstance(val, str) and val.lower().endswith(".pdf"):
                attachment_name = val
                break

    if not attachment_name and os.path.exists(settings.INBOX_DIR):
        clean_q = tokens[0] if tokens else query.lower().split()[0]
        for fname in os.listdir(settings.INBOX_DIR):
            if fname.lower().endswith(".pdf") and clean_q in fname.lower():
                attachment_name = fname
                break

    pdf_path = os.path.abspath(os.path.join(settings.INBOX_DIR, attachment_name)) if attachment_name else ""
    db_path = os.path.abspath(settings.DATABASE_URL.replace("sqlite:///", ""))
    
    return {
        "status": "SUCCESS",
        "email_id": email.get("id", ""),
        "subject": email.get("subject", ""),
        "sender": email.get("sender", ""),
        "attachment": attachment_name,
        "attachment_file": attachment_name,
        "file_path": pdf_path,
        "source_file_location": pdf_path,
        "target_database_location": db_path
    }


def read_pdf_invoice(file_path: str):
    if not os.path.exists(file_path):
        file_path = os.path.join(settings.INBOX_DIR, os.path.basename(file_path))

    if not os.path.exists(file_path):
        return {"status": "ERROR", "message": f"PDF file not found at {file_path}"}

    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        text += page.get_text()

    inv_match = re.search(
        r"(?:\bInvoice\s*Number\b|\bInvoice\s*#|\bINV\b|\bInvoice\b)[\s:]*([A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*)", 
        text, 
        re.IGNORECASE
    )
    vendor_match = re.search(r"(?:\bVendor\b|\bCompany\b|\bFrom\b)[\s:]*([^\n]+)", text, re.IGNORECASE)
    amount_match = re.search(
        r"(?:Total\s*Amount|Grand\s*Total|\bTotal\b|\bAmount\b)[\s:]*\$?\s*([0-9,]+(?:\.[0-9]{2})?)", 
        text, 
        re.IGNORECASE
    )
    due_match = re.search(r"(?:\bDue\s*Date\b|\bDue\b)[\s:]*([0-9]{4}-[0-9]{2}-[0-9]{2}|[^\n]+)", text, re.IGNORECASE)

    raw_inv = inv_match.group(1).strip() if inv_match else "UNKNOWN"

    invalid_keywords = {"OICE", "VOICE", "INVOICE", "NUMBER", "NO", "NUM", "UNKNOWN"}
    if raw_inv.upper() in invalid_keywords or re.match(r"^[-_]+$", raw_inv) or len(raw_inv) < 3:
        invoice_number = "UNKNOWN"
    else:
        invoice_number = raw_inv

    vendor_name = vendor_match.group(1).strip() if vendor_match else "UNKNOWN"
    due_date = due_match.group(1).strip() if due_match else "UNKNOWN"

    amount = 0.0
    if amount_match:
        try:
            amount = float(amount_match.group(1).replace(",", ""))
        except ValueError:
            amount = 0.0

    if amount == 0.0:
        dollar_matches = re.findall(r"\$\s*([0-9,]+(?:\.[0-9]{2})?)", text)
        if dollar_matches:
            for dm in reversed(dollar_matches):
                try:
                    parsed_val = float(dm.replace(",", ""))
                    if parsed_val > 0.0:
                        amount = parsed_val
                        break
                except ValueError:
                    continue

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    for line in lines:
        line_lower = line.lower()
        if invoice_number == "UNKNOWN" and "invoice" in line_lower and ":" in line:
            candidate = line.split(":")[-1].strip()
            if candidate and candidate.upper() not in invalid_keywords and not re.match(r"^[-_]+$", candidate):
                invoice_number = candidate
        if vendor_name in ["Unknown Vendor", "UNKNOWN"] and "vendor" in line_lower and ":" in line:
            vendor_name = line.split(":")[-1].strip()

    source_path = os.path.abspath(file_path)
    db_path = os.path.abspath(settings.DATABASE_URL.replace("sqlite:///", ""))

    # Threshold Check (>= $10,000 safety gate requiring human approval)
    if amount >= settings.APPROVAL_THRESHOLD_AMOUNT:
        return {
            "status": "AWAITING_HUMAN_APPROVAL",
            "warning": f"Invoice amount (${amount:,.2f}) meets or exceeds safety threshold (${settings.APPROVAL_THRESHOLD_AMOUNT:,.2f}).",
            "pending_payload": {
                "invoice_number": invoice_number,
                "vendor_name": vendor_name,
                "amount": amount,
                "due_date": due_date,
                "file_location": source_path,
                "target_db_location": db_path
            }
        }

    return {
        "status": "SUCCESS",
        "data": {
            "invoice_number": invoice_number,
            "vendor_name": vendor_name,
            "amount": amount,
            "due_date": due_date,
            "source_file_location": source_path,
            "target_database_location": db_path
        }
    }


def verify_invoice_data(invoice_number: str, vendor_name: str, amount: float, due_date: str, sender_email: str = ""):
    checks = []
    missing_fields = []
    is_valid = True

    if not invoice_number or invoice_number.upper() in ["UNKNOWN", "OICE", "VOICE"] or len(invoice_number) < 3:
        checks.append({"check": "invoice_number_format", "passed": False, "detail": f"Invalid or missing invoice number '{invoice_number}'"})
        missing_fields.append("invoice_number")
        is_valid = False
    else:
        checks.append({"check": "invoice_number_format", "passed": True, "detail": f"Valid format '{invoice_number}'"})

    if amount <= 0.0:
        checks.append({"check": "amount_validity", "passed": False, "detail": f"Amount is zero or negative (${amount})"})
        missing_fields.append("amount")
        is_valid = False
    else:
        checks.append({"check": "amount_validity", "passed": True, "detail": f"Valid amount (${amount:,.2f})"})

    if not vendor_name or vendor_name.upper() in ["UNKNOWN", "UNKNOWN VENDOR"]:
        checks.append({"check": "vendor_identity", "passed": False, "detail": "Vendor identity missing"})
        missing_fields.append("vendor_name")
        is_valid = False
    else:
        checks.append({"check": "vendor_identity", "passed": True, "detail": f"Vendor identified as '{vendor_name}'"})

    if not due_date or due_date.upper() == "UNKNOWN":
        checks.append({"check": "due_date_validity", "passed": False, "detail": "Due date missing"})
        missing_fields.append("due_date")
        is_valid = False
    else:
        checks.append({"check": "due_date_validity", "passed": True, "detail": f"Due date identified as '{due_date}'"})

    return {
        "status": "VERIFICATION_PASSED" if is_valid else "VERIFICATION_FAILED",
        "verification_passed": is_valid,
        "missing_fields": missing_fields,
        "verification_checks": checks,
        "confidence_score": 1.0 if is_valid else max(0.0, 1.0 - (len(missing_fields) * 0.25))
    }


def check_duplicate_invoice(invoice_number: str):
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, invoice_number, vendor_name, amount, due_date, file_location, status, created_at FROM invoices WHERE invoice_number = ?", (invoice_number,))
    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            "status": "FOUND_IN_DATABASE",
            "transaction_id": row[0],
            "existing_record": {
                "transaction_id": row[0],
                "invoice_number": row[1],
                "vendor_name": row[2],
                "amount": row[3],
                "due_date": row[4],
                "file_location": row[5],
                "status": row[6],
                "created_at": row[7]
            },
            "database_path": os.path.abspath(db_path)
        }
    
    return {
        "status": "NOT_FOUND_IN_DATABASE",
        "invoice_number": invoice_number,
        "database_path": os.path.abspath(db_path)
    }


def update_invoice_ledger(invoice_number: str, vendor_name: str, amount: float, due_date: str, file_location: str):
    invalid_inv = not invoice_number or invoice_number.upper() in ["UNKNOWN", "OICE", "VOICE"] or re.match(r"^[-_]+$", invoice_number)
    invalid_vendor = not vendor_name or vendor_name.upper() in ["UNKNOWN", "UNKNOWN VENDOR"]
    
    if invalid_inv or invalid_vendor or amount <= 0.0:
        return {
            "status": "ERROR",
            "message": "Cannot record invoice: Invalid or missing critical fields.",
            "details": {
                "invalid_invoice_number": invalid_inv,
                "invalid_vendor": invalid_vendor,
                "invalid_amount": amount <= 0.0
            }
        }

    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO invoices (invoice_number, vendor_name, amount, due_date, file_location, status) VALUES (?, ?, ?, ?, ?, ?)",
        (invoice_number, vendor_name, amount, due_date, file_location, "RECORDED")
    )
    conn.commit()
    record_id = cursor.lastrowid
    conn.close()

    return {
        "status": "SUCCESS",
        "transaction_id": record_id,
        "record_id": record_id,
        "invoice_number": invoice_number,
        "target_database_location": os.path.abspath(db_path)
    }


def verify_ledger_entry(record_id: int, expected_invoice_number: str):
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, invoice_number, vendor_name, amount, status FROM invoices WHERE id = ?", (record_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {
            "status": "POST_COMMIT_VERIFICATION_FAILED",
            "message": f"Transaction #{record_id} not found in database."
        }

    matches = (row[1] == expected_invoice_number)
    return {
        "status": "POST_COMMIT_VERIFIED" if matches else "RECORD_MISMATCH",
        "transaction_id": row[0],
        "verified_db_id": row[0],
        "invoice_number": row[1],
        "vendor_name": row[2],
        "amount": row[3],
        "status_flag": row[4],
        "audit_pass": matches
    }


TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "scan_inbox",
            "description": "Scan inbox for email matching query to locate PDF attachment.",
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
            "description": "Extract text fields from target PDF invoice file.",
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
            "name": "verify_invoice_data",
            "description": "Agentic pre-commit verification checking field integrity and rules.",
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice_number": {"type": "string"},
                    "vendor_name": {"type": "string"},
                    "amount": {"type": "number"},
                    "due_date": {"type": "string"},
                    "sender_email": {"type": "string"}
                },
                "required": ["invoice_number", "vendor_name", "amount", "due_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_duplicate_invoice",
            "description": "Check if an invoice number already exists in SQLite database.",
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
            "description": "Insert validated invoice record into database ledger.",
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice_number": {"type": "string"},
                    "vendor_name": {"type": "string"},
                    "amount": {"type": "number"},
                    "due_date": {"type": "string"},
                    "file_location": {"type": "string"}
                },
                "required": ["invoice_number", "vendor_name", "amount", "due_date", "file_location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "verify_ledger_entry",
            "description": "Agentic post-commit verification confirming row persistence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "record_id": {"type": "integer"},
                    "expected_invoice_number": {"type": "string"}
                },
                "required": ["record_id", "expected_invoice_number"]
            }
        }
    }
]


def dispatch_tool(name: str, args: dict):
    if name == "scan_inbox":
        return scan_inbox(**args)
    elif name == "read_pdf_invoice":
        return read_pdf_invoice(**args)
    elif name == "verify_invoice_data":
        return verify_invoice_data(**args)
    elif name == "check_duplicate_invoice":
        return check_duplicate_invoice(**args)
    elif name == "update_invoice_ledger":
        return update_invoice_ledger(**args)
    elif name == "verify_ledger_entry":
        return verify_ledger_entry(**args)
    else:
        return {"status": "ERROR", "message": f"Unknown tool: {name}"}