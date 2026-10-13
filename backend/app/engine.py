import json
import uuid
import asyncio
from groq import Groq
from app.config import settings
from app.tools import dispatch_tool, TOOLS_SCHEMA

client = Groq(api_key=settings.GROQ_API_KEY)
MODEL_NAME = "openai/gpt-oss-120b"

SYSTEM_PROMPT = """You are WorkPilot, an autonomous enterprise financial task worker.

TRANSACTION HISTORY & REDIRECT RULES:
1. Always run pipeline: `scan_inbox` -> `read_pdf_invoice` -> `verify_invoice_data` -> `check_duplicate_invoice`.
2. IF `check_duplicate_invoice` returns `FOUND_IN_DATABASE`:
   - Clearly state that the invoice is ALREADY PROCESSED and exists in the transaction history ledger.
   - Extract the `transaction_id` (or `id`) from the check_duplicate_invoice observation payload.
   - YOU MUST TERMINATE WITH AN ACTION BUTTON THAT REDIRECTS TO THAT SPECIFIC TRANSACTION:

---ACTION_BUTTONS---
[
  {"label": "View Transaction #<TRANSACTION_ID>", "command": "View transaction history details for ID <TRANSACTION_ID>"},
  {"label": "Scan Next Inbox Invoice", "command": "Scan inbox for next invoice"}
]

3. IF Invoice is NEW (NOT_FOUND_IN_DATABASE):
   - Prompt user to store it in ledger with:
---ACTION_BUTTONS---
[
  {"label": "Store & Record in Ledger", "command": "Record invoice <INVOICE_NO> from <VENDOR> into database ledger"},
  {"label": "Skip Invoice", "command": "Skip processing this invoice"}
]

4. IF Invoice was JUST RECORDED into ledger in the current turn:
   - Provide direct transaction reference button:
---ACTION_BUTTONS---
[
  {"label": "View Transaction #<TRANSACTION_ID>", "command": "View transaction history details for ID <TRANSACTION_ID>"},
  {"label": "Scan Next Inbox Invoice", "command": "Scan inbox for next invoice"}
]
"""

async def run_workpilot_stream(goal: str):
    run_id = str(uuid.uuid4())[:8]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": goal}
    ]

    for step in range(10):
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