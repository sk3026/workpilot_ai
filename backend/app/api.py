import json
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.engine import run_workpilot_stream
from app.database import get_db_connection

router = APIRouter(prefix="/api/v1")

class ApprovalRequest(BaseModel):
    invoice_number: str
    vendor_name: str
    amount: float
    due_date: str
    email_date: str = "2026-10-10"
    file_location: str
    approved: bool

@router.get("/run-stream")
async def run_stream(prompt: str = Query(..., description="User instruction for WorkPilot")):
    async def event_generator():
        async for event in run_workpilot_stream(prompt):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("/approve")
async def approve_invoice(payload: ApprovalRequest):
    if not payload.approved:
        return {"status": "REJECTED", "message": f"Invoice {payload.invoice_number} rejected by user."}

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO invoices (invoice_number, vendor_name, amount, due_date, file_location, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            payload.invoice_number,
            payload.vendor_name,
            payload.amount,
            payload.due_date,
            payload.file_location,
            "APPROVED_AND_RECORDED"
        )
    )
    conn.commit()
    record_id = cursor.lastrowid
    conn.close()

    return {
        "status": "APPROVED_AND_RECORDED",
        "recorded_db_id": record_id,
        "invoice_number": payload.invoice_number
    }

@router.get("/transactions")
async def get_transactions():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, invoice_number, vendor_name, amount, due_date, file_location, status, created_at FROM invoices ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@router.get("/transactions/{transaction_id}")
async def get_transaction_by_id(transaction_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, invoice_number, vendor_name, amount, due_date, file_location, status, created_at FROM invoices WHERE id = ?", (transaction_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Transaction record not found")
    return dict(row)