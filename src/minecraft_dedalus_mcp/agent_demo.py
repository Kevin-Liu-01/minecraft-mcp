from __future__ import annotations

import argparse
import asyncio
import json
import os

from dotenv import load_dotenv

from dedalus_labs import AsyncDedalus, DedalusRunner
from dedalus_mcp.client import MCPClient


load_dotenv()


def _is_local_mcp_url(url: str) -> bool:
    return "127.0.0.1" in url or "localhost" in url


def _mcp_tools_to_openai_schemas(list_tools_result) -> list[dict]:
    """Convert MCP ListToolsResult to OpenAI-style tool schemas for the API."""
    schemas = []
    for tool in list_tools_result.tools:
        params = getattr(tool, "inputSchema", None) or {"type": "object", "properties": {}}
        schemas.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": getattr(tool, "description", None) or f"Call {tool.name}",
                "parameters": params,
            },
        })
    return schemas


def _tools_description_for_prompt(tool_schemas: list[dict]) -> str:
    """Build a short list of tool names and descriptions for the user prompt."""
    lines = []
    for s in tool_schemas:
        fn = s.get("function") or {}
        name = fn.get("name", "?")
        desc = (fn.get("description") or "").strip() or "Call this tool"
        lines.append(f"- {name}: {desc}")
    return "You have these tools (call them; your calls will be executed):\n" + "\n".join(lines)


async def _run_agent_local(
    server_url: str,
    model: str,
    goal: str,
    *,
    max_steps: int = 25,
    verbose: bool = True,
) -> None:
    """Run the agent with tool execution against the local MCP server.

    Fetches tool schemas from the MCP server and passes them inline to the API,
    then executes tool_calls locally so the model sees and uses the tools.
    """
    api_key = os.getenv("DEDALUS_API_KEY")
    if not api_key:
        raise SystemExit("DEDALUS_API_KEY is required.")

    # Fetch tool schemas from local MCP
    async with await MCPClient.connect(server_url) as mcp_client:
        list_result = await mcp_client.list_tools()
    tool_schemas = _mcp_tools_to_openai_schemas(list_result)
    tools_in_prompt = _tools_description_for_prompt(tool_schemas)
    if verbose:
        print(f"[local-agent] Loaded {len(tool_schemas)} tools from MCP: {[s['function']['name'] for s in tool_schemas]}")

    # Put tool list in the input so the model always sees what it can call
    user_content = f"{tools_in_prompt}\n\n---\n\n{goal}"
    client = AsyncDedalus(api_key=api_key)
    messages: list[dict] = [{"role": "user", "content": user_content}]
    steps = 0
    final_text = ""

    while steps < max_steps:
        steps += 1
        if verbose:
            print(f"[local-agent] Step {steps}/{max_steps}")

        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tool_schemas,
            instructions=DEFAULT_AGENT_INSTRUCTIONS,
            automatic_tool_execution=False,
        )

        if not getattr(response, "choices", None) or not response.choices:
            break

        choice = response.choices[0]
        msg = choice.message
        msg_dict = vars(msg) if hasattr(msg, "__dict__") else msg
        tool_calls = msg_dict.get("tool_calls") or []
        content = (getattr(msg, "content", None) or msg_dict.get("content") or "").strip()

        if not tool_calls:
            final_text = content or ""
            if verbose and final_text:
                print(f"[local-agent] Done: {final_text[:200]}...")
            break

        # Extract tool call dicts (id, function.name, function.arguments)
        extracted = []
        for tc in tool_calls:
            tc_d = vars(tc) if hasattr(tc, "__dict__") else tc
            fn = tc_d.get("function")
            fn_d = vars(fn) if fn and hasattr(fn, "__dict__") else (fn or {})
            extracted.append({
                "id": tc_d.get("id", ""),
                "type": tc_d.get("type", "function"),
                "function": {
                    "name": fn_d.get("name", ""),
                    "arguments": fn_d.get("arguments", "{}"),
                },
            })

        if verbose:
            print(f"[local-agent] Tool calls: {[t['function']['name'] for t in extracted]}")

        messages.append({"role": "assistant", "content": content or None, "tool_calls": extracted})

        # Execute each tool call via local MCP client
        async with await MCPClient.connect(server_url) as mcp_client:
            for tc in extracted:
                name = tc["function"]["name"]
                raw_args = tc["function"]["arguments"]
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except json.JSONDecodeError:
                    args = {}
                try:
                    result = await mcp_client.call_tool(name, args)
                    text_parts = []
                    for c in result.content:
                        if getattr(c, "type", None) == "text":
                            text_parts.append(getattr(c, "text", str(c)))
                    result_text = "\n".join(text_parts) if text_parts else str(result)
                except Exception as e:
                    result_text = f"Error: {e}"
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result_text})
                if verbose:
                    print(f"  {name}: {result_text[:80]}...")

    print(final_text or "")


DEFAULT_AGENT_INSTRUCTIONS = (
    "You are controlling a Minecraft bot. Use these tools to interact with the world: "
    "go_to_known_location (move to x,y,z), mine_resource (break blocks by name, e.g. oak_log), "
    "dig_block (break one block at x,y,z), place_block (place a block from inventory at x,y,z), "
    "attack_entity (attack by entity name, e.g. zombie). "
    "Always inspect_world or get_bot_status first to get coordinates and entity names. "
    "Work in short loops: inspect → decide → move/break/place/attack. "
    "For survival goals, call recommend_next_goal to plan. "
    "When the goal is a Minecraft chat message (e.g. 'The player said: ...'), treat it as a natural language command: "
    "use read_chat if needed, then interpret what the player asked (move somewhere, mine X, place Y, attack Z, build something, etc.) "
    "and execute the right tool calls to do it. If the message is ambiguous, do the most reasonable interpretation. "
    "Use send_chat sparingly so chat is not spammed. Do NOT send 'On it!' or 'Done!'—the system already does. "
    "Send at most a few progress lines per task: one short phrase per send_chat only, e.g. 'Moving to (10, 70, 0)', 'Mining oak_log', 'Done [mined 4]'. "
    "Never quote, repeat, or include any prior chat message in your send_chat. Never use brackets containing 'On it!' or 'Done!'. "
    "Keep each message under 60 characters."
)


async def run_agent(
    server_url: str,
    model: str,
    goal: str,
    *,
    max_steps: int = 12,
    verbose: bool = True,
) -> None:
    api_key = os.getenv("DEDALUS_API_KEY")
    if not api_key:
        raise SystemExit("DEDALUS_API_KEY is required to run the Dedalus agent demo.")

    if _is_local_mcp_url(server_url):
        await _run_agent_local(
            server_url=server_url,
            model=model,
            goal=goal,
            max_steps=max_steps,
            verbose=verbose,
        )
        return

    client = AsyncDedalus(api_key=api_key)
    runner = DedalusRunner(client, verbose=verbose)
    result = await runner.run(
        input=goal,
        model=model,
        mcp_servers=[server_url],
        instructions=DEFAULT_AGENT_INSTRUCTIONS,
        max_steps=max_steps,
        stream=False,
    )
    print(result.final_output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Dedalus agent against the Minecraft MCP server")
    parser.add_argument("--server-url", default="http://127.0.0.1:8000/mcp")
    parser.add_argument("--model", default="openai/gpt-5.2")
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument(
        "--goal",
        default="Join the world, inspect it, gather some wood, and build a starter pillar.",
    )
    args = parser.parse_args()
    asyncio.run(
        run_agent(
            server_url=args.server_url,
            model=args.model,
            goal=args.goal,
            max_steps=args.max_steps,
        )
    )


if __name__ == "__main__":
    main()
