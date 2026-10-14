
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from app.engine import run_workpilot_stream
from app.database import get_db_connection

router = APIRouter()


class ApprovalRequest(BaseModel):
    invoice_number: str
    vendor_name: str
    amount: float
    due_date: str
    email_date: Optional[str] = None
    file_location: str
    approved: bool


@router.get("/run-stream")
async def run_stream(prompt: str):
    async def event_generator():
        try:
            # Notify frontend that the agent has started.
            yield (
                f"data: {json.dumps({
                    'event_type': 'AGENT_START',
                    'title': 'Task Started'
                })}\n\n"
            )

            # run_workpilot_stream is an asynchronous generator.
            async for event in run_workpilot_stream(prompt):
                yield f"data: {json.dumps(event, default=str)}\n\n"

        except Exception as e:
            err_payload = {
                "event_type": "FINAL_ANSWER",
                "message": f"Server Error: {str(e)}"
            }
            yield f"data: {json.dumps(err_payload)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/transactions")
async def get_transactions():
    conn = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                id,
                invoice_number,
                vendor_name,
                amount,
                due_date,
                status,
                created_at
            FROM invoices
            ORDER BY id DESC
            """
        )

        rows = cursor.fetchall()

        return [
            {
                "id": row[0],
                "invoice_number": row[1],
                "vendor_name": row[2],
                "amount": row[3],
                "due_date": row[4],
                "status": row[5],
                "created_at": row[6],
            }
            for row in rows
        ]

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database query failed: {str(e)}"
        )

    finally:
        if conn is not None:
            conn.close()


@router.get("/transactions/{tx_id}")
async def get_transaction_detail(tx_id: int):
    conn = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                id,
                invoice_number,
                vendor_name,
                amount,
                due_date,
                status,
                file_location,
                created_at
            FROM invoices
            WHERE id = ?
            """,
            (tx_id,)
        )

        row = cursor.fetchone()

        if not row:
            raise HTTPException(
                status_code=404,
                detail="Transaction not found"
            )

        return {
            "id": row[0],
            "invoice_number": row[1],
            "vendor_name": row[2],
            "amount": row[3],
            "due_date": row[4],
            "status": row[5],
            "file_location": row[6],
            "created_at": row[7],
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving transaction #{tx_id}: {str(e)}"
        )

    finally:
        if conn is not None:
            conn.close()


@router.post("/approve")
async def process_approval(payload: ApprovalRequest):
    conn = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if payload.approved:
            cursor.execute(
                """
                INSERT INTO invoices (
                    invoice_number,
                    vendor_name,
                    amount,
                    due_date,
                    file_location,
                    status
                )
                VALUES (?, ?, ?, ?, ?, 'VERIFIED')
                """,
                (
                    payload.invoice_number,
                    payload.vendor_name,
                    payload.amount,
                    payload.due_date,
                    payload.file_location
                )
            )

            recorded_id = cursor.lastrowid
            conn.commit()

            return {
                "status": "approved",
                "recorded_db_id": recorded_id
            }

        return {"status": "rejected"}

    except Exception as e:
        if conn is not None:
            conn.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Approval execution failed: {str(e)}"
        )

    finally:
        if conn is not None:
            conn.close()
