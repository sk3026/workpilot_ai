import json
import uuid
import asyncio
from groq import Groq
from app.config import settings
from app.tools import dispatch_tool, TOOLS_SCHEMA

client = Groq(api_key=settings.GROQ_API_KEY)
MODEL_NAME = "openai/gpt-oss-120b"

SYSTEM_PROMPT = """You are WorkPilot, an autonomous enterprise financial task worker.

EXECUTION INSTRUCTIONS:
1. When the user asks to process an invoice (e.g., "Scan inbox for ABC Corp and process the invoice"):
   - Execute the pipeline: `scan_inbox` -> `read_pdf_invoice` -> `verify_invoice_data` -> `check_duplicate_invoice`.
2. IF `check_duplicate_invoice` returns `FOUND_IN_DATABASE`:
   - State that the invoice is already present in the database ledger.
   - Terminate with action buttons:
     ---ACTION_BUTTONS---
     [
       {"label": "View Transaction #<TRANSACTION_ID>", "command": "View transaction history details for ID <TRANSACTION_ID>"},
       {"label": "Scan Next Inbox Invoice", "command": "Scan inbox for next invoice"}
     ]
3. IF `check_duplicate_invoice` returns `NOT_FOUND_IN_DATABASE`:
   - State clearly that this is a **New Transaction Detected**.
   - Display the extracted values (Invoice Number, Vendor Name, Amount, Due Date) and both absolute paths:
     - **Source File Location:** `<source_file_location>`
     - **Target Database Location:** `<target_database_location>`
   - Terminate with pre-commit action buttons:
     ---ACTION_BUTTONS---
     [
       {"label": "Store & Record in Ledger", "command": "Record invoice <INVOICE_NO> from <VENDOR> with amount <AMOUNT> due <DUE_DATE> file <FILE_PATH> into database ledger"},
       {"label": "Skip Invoice", "command": "Skip processing this invoice"}
     ]
4. WHEN the user sends a command to record or store an invoice ("Record invoice..."):
   - Call `update_invoice_ledger` followed immediately by `verify_ledger_entry`.
   - Output the success summary and action buttons.

QUERY CLEANING RULE:
When calling `scan_inbox`, pass ONLY the clean vendor name as the `query` argument (e.g., "ABC Corp"). Never include noise words.
"""

async def run_workpilot_stream(goal: str):
    run_id = str(uuid.uuid4())[:8]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": goal}
    ]

    for step in range(8):
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            tools=TOOLS_SCHEMA,
            tool_choice="auto"
        )

        msg = response.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            yield {
                "event_type": "FINAL_ANSWER",
                "run_id": run_id,
                "step": step + 1,
                "message": msg.content
            }
            break

        for tool_call in msg.tool_calls:
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)

            yield {
                "event_type": "TOOL_CALL",
                "run_id": run_id,
                "step": step + 1,
                "title": f"Invoking tool: {fn_name}",
                "payload": fn_args
            }
            await asyncio.sleep(0.1)

            observation = dispatch_tool(fn_name, fn_args)

            if isinstance(observation, dict) and observation.get("status") == "AWAITING_HUMAN_APPROVAL":
                yield {
                    "event_type": "APPROVAL_REQUIRED",
                    "run_id": run_id,
                    "step": step + 1,
                    "title": "Human Safety Approval Required",
                    "payload": observation.get("pending_payload")
                }
                return

            yield {
                "event_type": "OBSERVATION",
                "run_id": run_id,
                "step": step + 1,
                "title": f"Result from {fn_name}",
                "payload": observation
            }
            await asyncio.sleep(0.1)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(observation)
            })