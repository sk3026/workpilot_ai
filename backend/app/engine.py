import json
import uuid
import asyncio
from groq import Groq
from app.config import settings
from app.tools import dispatch_tool, TOOLS_SCHEMA

client = Groq(api_key=settings.GROQ_API_KEY)
MODEL_NAME = "openai/gpt-oss-120b"

SYSTEM_PROMPT = """You are WorkPilot, an autonomous enterprise financial task worker with multi-tier agentic verification.

EXECUTION & WORKFLOW RULES:

1. MISSING FIELDS & INTEGRITY WARNING RULE:
   When processing a fresh prompt ("Scan inbox for X and process..."):
   - Execute: `scan_inbox` -> `read_pdf_invoice` -> `verify_invoice_data` -> `check_duplicate_invoice`.
   - IF `verify_invoice_data` returns `VERIFICATION_FAILED` OR any required field (Invoice Number, Vendor Name, Amount, Due Date) is missing, "UNKNOWN", "UNSTATED", or invalid:
     - DO NOT show the "Store & Record in Ledger" button.
     - State clearly: **Verification Warning: Missing or Unparsed Fields Detected**.
     - Display the extracted values and explicitly highlight the missing/invalid field(s).
     - Render the explicit absolute paths:
       - **Source File Location:** `<source_file_location>`
       - **Target Database Location:** `<target_database_location>`
     - Provide the missing field action buttons:
       ---ACTION_BUTTONS---
       [
         {"label": "Provide Missing Details", "command": "Update invoice details for missing fields"},
         {"label": "Skip Invoice", "command": "Skip processing this invoice"}
       ]

2. DUPLICATE DETECTION RULE:
   - IF `check_duplicate_invoice` returns `FOUND_IN_DATABASE`:
     State that the invoice is ALREADY PRESENT in the database ledger, display transaction details, and terminate with:
     ---ACTION_BUTTONS---
     [
       {"label": "View Transaction #<TRANSACTION_ID>", "command": "View transaction history details for ID <TRANSACTION_ID>"},
       {"label": "Scan Next Inbox Invoice", "command": "Scan inbox for next invoice"}
     ]

3. NEW TRANSACTION (PRE-COMMIT) RULE:
   - IF ALL FIELDS ARE VALID and `check_duplicate_invoice` returns `NOT_FOUND_IN_DATABASE`:
     State clearly that this is a **New Transaction Detected**. 
     Display the parsed fields (Invoice Number, Vendor Name, Amount, Due Date), along with explicit absolute paths:
     - **Source File Location:** `<source_file_location>`
     - **Target Database Location:** `<target_database_location>`
     Then provide the pre-commit action buttons:
     ---ACTION_BUTTONS---
     [
       {"label": "Store & Record in Ledger", "command": "Record invoice <INVOICE_NO> from <VENDOR> with amount <AMOUNT> due <DUE_DATE> file <FILE_PATH> into database ledger"},
       {"label": "Skip Invoice", "command": "Skip processing this invoice"}
     ]

4. DIRECT STORAGE EXECUTION RULE:
   - When the user sends a command to record an invoice (e.g., clicking "Store & Record in Ledger" or passing explicit recording parameters):
     - DO NOT re-scan the inbox.
     - IMMEDIATELY call `update_invoice_ledger` using the invoice number, vendor name, amount, due date, and file location.
     - Immediately follow with `verify_ledger_entry` to confirm row persistence.
     - After recording, present the success state with the transaction ID and terminate with action buttons:
       ---ACTION_BUTTONS---
       [
         {"label": "View Transaction #<TRANSACTION_ID>", "command": "View transaction history details for ID <TRANSACTION_ID>"},
         {"label": "Scan Next Inbox Invoice", "command": "Scan inbox for next invoice"}
       ]

5. EXCEPTION (Safety Gate): If invoice amount >= $10,000, halt at `read_pdf_invoice` and trigger human safety approval.

QUERY CLEANING RULE:
When calling `scan_inbox`, pass ONLY the clean vendor or company name as the `query` argument (e.g., "ABC Corp", "Acme Supplies"). Never include noise words.
"""

def parse_tool_args(raw_args: str) -> dict:
    try:
        return json.loads(raw_args)
    except json.JSONDecodeError:
        # Sanitize Windows backslashes in JSON strings (e.g., C:\path -> C:\\path)
        fixed_args = raw_args.replace("\\", "\\\\")
        try:
            return json.loads(fixed_args)
        except Exception:
            return {}

async def run_workpilot_stream(goal: str):
    run_id = str(uuid.uuid4())[:8]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": goal}
    ]

    for step in range(8):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto"
            )
        except Exception as err:
            yield {
                "event_type": "FINAL_ANSWER",
                "run_id": run_id,
                "step": step + 1,
                "message": f"API Request Error: {str(err)}"
            }
            break

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
            fn_args = parse_tool_args(tool_call.function.arguments)

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