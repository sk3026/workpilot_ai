import json
import uuid
import asyncio
from groq import Groq
from app.config import settings
from app.tools import dispatch_tool, TOOLS_SCHEMA

client = Groq(api_key=settings.GROQ_API_KEY)
MODEL_NAME = "openai/gpt-oss-120b"

async def run_workpilot_stream(goal: str):
    run_id = str(uuid.uuid4())[:8]
    messages = [
        {
            "role": "system",
            "content": "You are WorkPilot, an autonomous enterprise task worker. Execute tool calls: scan email -> read PDF -> check duplicates -> update ledger -> verify entry. If duplicate exists, stop and report location. If human approval required, pause execution."
        },
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

            yield {
                "event_type": "OBSERVATION",
                "run_id": run_id,
                "step": step + 1,
                "title": f"Result from {fn_name}",
                "payload": observation
            }
            await asyncio.sleep(0.1)

            if observation.get("status") == "AWAITING_HUMAN_APPROVAL":
                yield {
                    "event_type": "APPROVAL_REQUIRED",
                    "run_id": run_id,
                    "step": step + 1,
                    "title": "Human Approval Required",
                    "payload": observation.get("pending_payload")
                }
                return

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(observation)
            })