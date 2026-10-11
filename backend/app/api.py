import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.engine import run_workpilot_stream
from app.database import SessionLocal, InvoiceRecord

router = APIRouter(prefix="/api/v1")

class ApprovalDecision(BaseModel):
    invoice_number: str
    vendor_name: str
    amount: float
    due_date: str
    email_date: str
    file_location: str
    approved: bool

@router.get("/run-stream")
async def run_stream(prompt: str):
    async def event_generator():
        async for event in run_workpilot_stream(prompt):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("/approve")
async def approve_invoice(decision: ApprovalDecision):
    if not decision.approved:
        return {"status": "REJECTED", "message": f"Invoice {decision.invoice_number} rejected by user."}

    session = SessionLocal()
    try:
        record = InvoiceRecord(
            invoice_number=decision.invoice_number,
            vendor_name=decision.vendor_name,
            amount=decision.amount,
            due_date=decision.due_date,
            email_date=decision.email_date,
            file_location=decision.file_location,
            status="APPROVED_AND_RECORDED"
        )
        session.add(record)
        session.commit()
        rec_id = record.id
        session.close()
        return {"status": "SUCCESS", "recorded_db_id": rec_id, "invoice_number": decision.invoice_number}
    except Exception as e:
        session.rollback()
        session.close()
        return {"status": "ERROR", "message": str(e)}

@router.get("/ledger")
async def get_ledger():
    session = SessionLocal()
    records = session.query(InvoiceRecord).all()
    session.close()
    return [
        {
            "id": r.id,
            "invoice_number": r.invoice_number,
            "vendor_name": r.vendor_name,
            "amount": r.amount,
            "due_date": r.due_date,
            "status": r.status,
            "created_at": str(r.created_at)
        }
        for r in records
    ]