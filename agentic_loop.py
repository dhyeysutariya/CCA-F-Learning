"""
Order Tracking Agent — CCA-F Agentic Loop Example
==================================================
Demonstrates the canonical agentic loop pattern:
  1. Send user message to Claude with tools defined
  2. Inspect stop_reason
     - "tool_use"  → execute the tool, append tool_result, loop again
     - "end_turn"  → done, return Claude's final response
"""

import anthropic
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── Mock database ────────────────────────────────────────────────────────────

ORDERS = {
    "ORD-1042": {
        "id": "ORD-1042",
        "status": "shipped",
        "customer": "Dhyey Shah",
        "email": "dhyey@example.com",
        "items": [{"name": "Minimalist Niacinamide Serum", "qty": 2, "price": 349}],
        "total": 698,
        "address": "Surat, Gujarat",
        "tracking_number": "DTDC-4421",
        "estimated_delivery": "May 11, 2026",
    },
    "ORD-2891": {
        "id": "ORD-2891",
        "status": "delivered",
        "customer": "Dhyey Shah",
        "email": "dhyey@example.com",
        "items": [{"name": "Whey Protein 1kg", "qty": 1, "price": 1299}],
        "total": 1299,
        "address": "Surat, Gujarat",
        "tracking_number": "BLUEDART-8812",
        "delivered_on": "May 1, 2026",
    },
    "ORD-9001": {
        "id": "ORD-9001",
        "status": "cancelled",
        "customer": "Dhyey Shah",
        "email": "dhyey@example.com",
        "items": [{"name": "Standing Desk Pro", "qty": 1, "price": 12000}],
        "total": 12000,
        "address": "Surat, Gujarat",
        "cancelled_on": "May 2, 2026",
        "refund_status": "Refund initiated",
    },
}

TRACKING_EVENTS = {
    "DTDC-4421": [
        {"timestamp": "May 9, 2026 10:30", "location": "Mumbai Hub",    "event": "Shipment picked up"},
        {"timestamp": "May 9, 2026 23:00", "location": "Ahmedabad Hub", "event": "In transit"},
        {"timestamp": "May 10, 2026 08:00", "location": "Surat",        "event": "Out for delivery"},
    ],
    "BLUEDART-8812": [
        {"timestamp": "Apr 29, 2026 09:00", "location": "Delhi Hub",    "event": "Shipment picked up"},
        {"timestamp": "Apr 30, 2026 14:00", "location": "Mumbai Hub",   "event": "In transit"},
        {"timestamp": "May 1, 2026 10:30",  "location": "Surat",        "event": "Delivered"},
    ],
}


# ── Tool implementations ──────────────────────────────────────────────────────

def get_order_details(order_id: str) -> dict:
    """Fetch order details from the database."""
    order = ORDERS.get(order_id.upper())
    if not order:
        return {"error": f"Order {order_id} not found"}
    return order


def get_tracking_events(tracking_number: str) -> dict:
    """Fetch shipment tracking timeline."""
    events = TRACKING_EVENTS.get(tracking_number)
    if not events:
        return {"error": f"No tracking events found for {tracking_number}"}
    return {"tracking_number": tracking_number, "events": events}


def check_refund_status(order_id: str) -> dict:
    """Check refund status for a cancelled order."""
    order = ORDERS.get(order_id.upper())
    if not order:
        return {"error": f"Order {order_id} not found"}
    if order["status"] != "cancelled":
        return {"message": f"Order {order_id} is not cancelled. No refund applicable."}
    return {
        "order_id": order_id,
        "refund_status": order.get("refund_status", "Not initiated"),
        "amount": order["total"],
        "note": "Refunds are processed within 5–7 business days.",
    }


# ── Tool dispatcher ───────────────────────────────────────────────────────────

TOOL_HANDLERS = {
    "get_order_details":  get_order_details,
    "get_tracking_events": get_tracking_events,
    "check_refund_status": check_refund_status,
}

def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Route a tool_use block to the correct function and return JSON string."""
    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    result = handler(**tool_input)
    return json.dumps(result)


# ── Tool definitions (passed to Claude) ──────────────────────────────────────

TOOLS = [
    {
        "name": "get_order_details",
        "description": (
            "Fetch full order details including status, items, price, "
            "address, and tracking number for a given order ID."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The order ID, e.g. ORD-1042",
                }
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "get_tracking_events",
        "description": (
            "Fetch shipment tracking timeline for a given tracking number. "
            "Use after get_order_details to get the tracking_number."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tracking_number": {
                    "type": "string",
                    "description": "Carrier tracking number, e.g. DTDC-4421",
                }
            },
            "required": ["tracking_number"],
        },
    },
    {
        "name": "check_refund_status",
        "description": "Check refund status for a cancelled order.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The order ID to check refund for",
                }
            },
            "required": ["order_id"],
        },
    },
]


# ── The agentic loop ──────────────────────────────────────────────────────────

def run_order_agent(user_query: str) -> str:
    """
    Core agentic loop.

    Iteration flow:
      send request → inspect stop_reason
        "tool_use" → execute tool(s) → append tool_result → repeat
        "end_turn"  → return final text response
    """
    client = anthropic.Anthropic()

    messages = [{"role": "user", "content": user_query}]

    system_prompt = (
        "You are a helpful order tracking assistant. "
        "When a user asks about an order, always call get_order_details first. "
        "If the order is shipped, also call get_tracking_events to get the latest location. "
        "If the order is cancelled, also call check_refund_status. "
        "Be concise and friendly in your final response."
    )

    iteration = 0

    print(f"\n{'='*60}")
    print(f"  User: {user_query}")
    print(f"{'='*60}")

    # ── Agentic loop ──────────────────────────────────────────────
    while True:
        iteration += 1
        print(f"\n[Iteration {iteration}] Sending {len(messages)} message(s) to Claude...")

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )

        print(f"[Iteration {iteration}] stop_reason = '{response.stop_reason}'")

        # ── TERMINATION CONDITION: only stop_reason drives the loop ──
        if response.stop_reason == "end_turn":
            # Extract the final text response
            final_text = next(
                (block.text for block in response.content if hasattr(block, "text")),
                "No response generated.",
            )
            print(f"\n{'='*60}")
            print(f"  Agent: {final_text}")
            print(f"{'='*60}\n")
            return final_text

        # ── TOOL EXECUTION: stop_reason == "tool_use" ─────────────
        if response.stop_reason == "tool_use":
            # Append Claude's response (containing tool_use blocks) to history
            messages.append({"role": "assistant", "content": response.content})

            # Collect all tool_use blocks and execute them
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  → Tool call : {block.name}({json.dumps(block.input)})")
                    result_str = execute_tool(block.name, block.input)
                    print(f"  ← Tool result: {result_str[:120]}{'...' if len(result_str) > 120 else ''}")

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,   # must match the block.id from Claude
                        "content": result_str,
                    })

            # Append all tool results as a single user message, then loop
            messages.append({"role": "user", "content": tool_results})
            # → loop continues, Claude now sees the tool results and decides next action

        # Guard against unexpected stop_reason values
        else:
            print(f"[Warning] Unhandled stop_reason: {response.stop_reason}")
            break

    return "Agent loop exited unexpectedly."


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    queries = [
        "Where is my order ORD-1042?",
        "Has my order ORD-2891 been delivered?",
        "I cancelled ORD-9001 — what's the refund status?",
        "Can you tell me about order ORD-9999?",  # Non-existent order
    ]

    for query in queries:
        run_order_agent(query)
        print()