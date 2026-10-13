import os
import json
import fitz  # PyMuPDF

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INBOX_DIR = os.path.join(BASE_DIR, "mock_inbox")
os.makedirs(INBOX_DIR, exist_ok=True)

invoice_scenarios = [
    {
        "id": "msg_001",
        "sender": "billing@abccorp.com",
        "subject": "Invoice INV-2026-001 from ABC Corp",
        "date": "2026-10-09T10:00:00Z",
        "filename": "invoice_abc_corp_001.pdf",
        "vendor": "ABC Corp",
        "inv_num": "INV-2026-001",
        "amount": 1450.00,
        "due_date": "2026-11-01",
        "note": "Standard processing"
    },
    {
        "id": "msg_002",
        "sender": "billing@abccorp.com",
        "subject": "FW: Invoice INV-2026-001 from ABC Corp (Resent)",
        "date": "2026-10-09T14:30:00Z",
        "filename": "invoice_abc_corp_001.pdf",
        "vendor": "ABC Corp",
        "inv_num": "INV-2026-001",
        "amount": 1450.00,
        "due_date": "2026-11-01",
        "note": "Exact duplicate entry test"
    },
    {
        "id": "msg_003",
        "sender": "accounts@acmesupplies.com",
        "subject": "Invoice INV-2026-002 from Acme Supplies",
        "date": "2026-10-10T08:15:00Z",
        "filename": "invoice_acme_002.pdf",
        "vendor": "Acme Supplies",
        "inv_num": "INV-2026-002",
        "amount": 12500.00,
        "due_date": "2026-11-15",
        "note": "High-value invoice (> $10,000 safety limit)"
    },
    {
        "id": "msg_004",
        "sender": "invoices@apexcloud.io",
        "subject": "Cloud Infrastructure Billing - Apex Cloud",
        "date": "2026-10-10T09:00:00Z",
        "filename": "invoice_apex_cloud_003.pdf",
        "vendor": "Apex Cloud Services",
        "inv_num": "INV-2026-003",
        "amount": 3200.00,
        "due_date": "2026-10-30",
        "note": "Standard cloud utility invoice"
    },
    {
        "id": "msg_005",
        "sender": "finance@globaltech.com",
        "subject": "Global Tech Services Invoice INV-2026-004",
        "date": "2026-10-10T11:45:00Z",
        "filename": "invoice_globaltech_004.pdf",
        "vendor": "Global Tech Solutions",
        "inv_num": "INV-2026-004",
        "amount": 850.00,
        "due_date": "UNSTATED",
        "note": "Missing explicit due date edge case"
    },
    {
        "id": "msg_006",
        "sender": "billing@starlightlogistics.com",
        "subject": "Freight Payment Invoice INV-2026-005",
        "date": "2026-10-10T13:20:00Z",
        "filename": "invoice_starlight_005.pdf",
        "vendor": "Starlight Logistics",
        "inv_num": "INV-2026-005",
        "amount": 24000.00,
        "due_date": "2026-10-25",
        "note": "High-value logistics invoice requiring approval"
    },
    {
        "id": "msg_007",
        "sender": "ar@nexusdynamics.net",
        "subject": "Nexus Dynamics Invoice INV-2026-006",
        "date": "2026-10-10T14:10:00Z",
        "filename": "invoice_nexus_006.pdf",
        "vendor": "Nexus Dynamics",
        "inv_num": "INV-2026-006",
        "amount": 4100.00,
        "due_date": "2026-11-10",
        "note": "Standard software milestone invoice"
    },
    {
        "id": "msg_008",
        "sender": "support@quantumanalytics.ai",
        "subject": "Quantum Analytics Subscription INV-2026-007",
        "date": "2026-10-10T15:00:00Z",
        "filename": "invoice_quantum_007.pdf",
        "vendor": "Quantum Analytics",
        "inv_num": "INV-2026-007",
        "amount": 9500.00,
        "due_date": "2026-11-05",
        "note": "Subscription invoice near approval limit"
    },
    {
        "id": "msg_009",
        "sender": "billing@cybershield.io",
        "subject": "CyberShield Security Audit Invoice INV-2026-008",
        "date": "2026-10-10T16:30:00Z",
        "filename": "invoice_cybershield_008.pdf",
        "vendor": "CyberShield Inc",
        "inv_num": "INV-2026-008",
        "amount": 1200.00,
        "due_date": "2026-11-01",
        "note": "Standard security audit invoice"
    },
    {
        "id": "msg_010",
        "sender": "accounts@vortexmedia.com",
        "subject": "Vortex Media Ad Campaign Invoice INV-2026-009",
        "date": "2026-10-10T17:00:00Z",
        "filename": "invoice_vortex_009.pdf",
        "vendor": "Vortex Media",
        "inv_num": "INV-2026-009",
        "amount": 650.00,
        "due_date": "2026-10-28",
        "note": "Standard media campaign invoice"
    }
]

metadata_list = []

for item in invoice_scenarios:
    pdf_path = os.path.join(INBOX_DIR, item["filename"])

    if not os.path.exists(pdf_path):
        doc = fitz.open()
        page = doc.new_page()
        pdf_text = f"""INVOICE
--------------------------------------------------
Vendor: {item['vendor']}
Invoice Number: {item['inv_num']}
Invoice Date: {item['date'][:10]}
Due Date: {item['due_date']}

Bill To: Enterprise Client Inc.

Line Items:
- Service Description / Professional Work
- Total Charges: ${item['amount']:,.2f}

Total Amount Due: ${item['amount']:,.2f}
--------------------------------------------------
Terms & Policy: Net 30 Days
Note: {item['note']}
"""
        page.insert_text((50, 50), pdf_text, fontsize=11)
        doc.save(pdf_path)
        doc.close()

    metadata_list.append({
        "message_id": item["id"],
        "sender": item["sender"],
        "subject": item["subject"],
        "received_date": item["date"],
        "attachment_name": item["filename"],
        "file_path": pdf_path,
        "scenario_note": item["note"]
    })

manifest_path = os.path.join(INBOX_DIR, "inbox_metadata.json")
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(metadata_list, f, indent=2)

print(f"✓ 10 test PDFs and inbox_metadata.json generated at {INBOX_DIR}")