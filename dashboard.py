#!/usr/bin/env python3
"""Live web dashboard for the Minecraft MCP agent.

Serves a single-page UI at http://localhost:9000 that auto-refreshes to show:
  - Bot status (health, food, position, inventory)
  - Recent chat messages
  - Agent event feed (goals, tool calls, results, errors)

Run alongside the agent (run_live_chat.py).  The dashboard reads from the
shared event_log module and polls the MCP server for bot/chat state.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

load_dotenv()

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)

from dedalus_mcp.client import MCPClient
from minecraft_dedalus_mcp import event_log

MCP_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")

_cached: dict[str, Any] = {
    "status": {},
    "chat": [],
    "events": [],
    "last_poll": 0,
}


async def _poll_mcp() -> None:
    try:
        async with await MCPClient.connect(MCP_URL) as client:
            status_r = await client.call_tool("get_bot_status", {})
            chat_r = await client.call_tool("read_chat", {"limit": 30})

            for c in status_r.content:
                if getattr(c, "type", None) == "text":
                    _cached["status"] = json.loads(c.text)
                    break

            for c in chat_r.content:
                if getattr(c, "type", None) == "text":
                    data = json.loads(c.text)
                    _cached["chat"] = data.get("messages", [])
                    break
    except Exception as e:
        _cached["status"]["_error"] = str(e)

    _cached["events"] = event_log.get_events(limit=150)
    _cached["last_poll"] = time.time()


def _poll_loop() -> None:
    loop = asyncio.new_event_loop()
    while True:
        try:
            loop.run_until_complete(_poll_mcp())
        except Exception:
            pass
        time.sleep(2)


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Minecraft MCP Dashboard</title>
<style>
  :root {
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --text: #c9d1d9; --text2: #8b949e; --accent: #58a6ff;
    --green: #3fb950; --red: #f85149; --yellow: #d29922; --purple: #bc8cff;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font: 13px/1.5 'SF Mono', 'Cascadia Code', 'Consolas', monospace; background: var(--bg); color: var(--text); padding: 12px; }
  h1 { font-size: 16px; color: var(--accent); margin-bottom: 10px; display: flex; align-items: center; gap: 8px; }
  h1 .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--red); }
  h1 .dot.on { background: var(--green); }
  .grid { display: grid; grid-template-columns: 320px 1fr; gap: 10px; height: calc(100vh - 50px); }
  .panel { background: var(--surface); border: 1px solid var(--border); border-radius: 6px; overflow: hidden; display: flex; flex-direction: column; }
  .panel-title { font-size: 11px; text-transform: uppercase; letter-spacing: .8px; color: var(--text2); padding: 8px 12px; border-bottom: 1px solid var(--border); background: var(--bg); }
  .panel-body { flex: 1; overflow-y: auto; padding: 8px 12px; }
  .right { display: flex; flex-direction: column; gap: 10px; }

  .stat { display: flex; justify-content: space-between; padding: 3px 0; border-bottom: 1px solid var(--border); }
  .stat .k { color: var(--text2); }
  .stat .v { color: var(--text); font-weight: 600; }
  .inv-item { display: inline-block; background: var(--bg); border: 1px solid var(--border); border-radius: 3px; padding: 1px 6px; margin: 2px; font-size: 11px; }

  .chat-msg { padding: 3px 0; border-bottom: 1px solid var(--border); }
  .chat-msg .sender { color: var(--accent); font-weight: 600; }
  .chat-msg .sender.system { color: #8b949e; font-style: italic; }
  .chat-msg .sender.self { color: #388bfd66; }
  .chat-msg .msg-type { font-size: 9px; text-transform: uppercase; letter-spacing: .5px; padding: 0 4px; border-radius: 2px; margin-right: 4px; }
  .chat-msg .msg-type.player { background: #238636aa; color: var(--green); }
  .chat-msg .msg-type.system { background: #30363d; color: #8b949e; }
  .chat-msg .msg-type.self { background: #1f6feb22; color: #388bfd66; }
  .chat-msg .time { color: var(--text2); font-size: 11px; margin-left: 6px; }

  .event { padding: 4px 0; border-bottom: 1px solid var(--border); }
  .event .ts { color: var(--text2); font-size: 11px; min-width: 65px; display: inline-block; }
  .badge { display: inline-block; border-radius: 3px; padding: 0 5px; font-size: 11px; font-weight: 600; margin-right: 4px; }
  .badge.agent_start { background: #1f6feb33; color: var(--accent); }
  .badge.agent_step { background: #30363d; color: var(--text2); }
  .badge.agent_done { background: #238636aa; color: var(--green); }
  .badge.chat_command { background: #d2992233; color: var(--yellow); }
  .badge.tool_call { background: #bc8cff22; color: var(--purple); }
  .badge.tool_result { background: #3fb95022; color: var(--green); }
  .badge.tool_result.err { background: #f8514922; color: var(--red); }
  .badge.llm_message { background: #58a6ff22; color: var(--accent); }
  .badge.error { background: #f8514922; color: var(--red); }
  .event-data { color: var(--text2); font-size: 12px; word-break: break-all; }

  .health-bar { height: 6px; border-radius: 3px; background: var(--border); margin-top: 2px; }
  .health-bar .fill { height: 100%; border-radius: 3px; }
  .health-bar .fill.hp { background: var(--red); }
  .health-bar .fill.food { background: var(--yellow); }
</style>
</head>
<body>
<h1><span class="dot" id="dot"></span> Minecraft MCP Dashboard</h1>
<div class="grid">
  <div style="display:flex;flex-direction:column;gap:10px">
    <div class="panel" style="flex:0 0 auto">
      <div class="panel-title">Bot Status</div>
      <div class="panel-body" id="status">Loading...</div>
    </div>
    <div class="panel" style="flex:1">
      <div class="panel-title">Chat</div>
      <div class="panel-body" id="chat">Loading...</div>
    </div>
  </div>
  <div class="panel">
    <div class="panel-title">Agent Events <span id="evcount" style="float:right"></span></div>
    <div class="panel-body" id="events" style="display:flex;flex-direction:column-reverse">Loading...</div>
  </div>
</div>
<script>
function esc(s){let d=document.createElement('div');d.textContent=s;return d.innerHTML}
function ts(t){let d=new Date(t*1000);return d.toLocaleTimeString('en',{hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'})}

function renderStatus(s){
  if(!s||!s.connected)return '<div style="color:var(--red)">Not connected</div>';
  let h='';
  h+=`<div class="stat"><span class="k">User</span><span class="v">${esc(s.username||'?')}</span></div>`;
  let pos=s.position||{};
  h+=`<div class="stat"><span class="k">Position</span><span class="v">${pos.x}, ${pos.y}, ${pos.z}</span></div>`;
  h+=`<div class="stat"><span class="k">Health</span><span class="v">${s.health}/20</span></div>`;
  h+=`<div class="health-bar"><div class="fill hp" style="width:${(s.health/20)*100}%"></div></div>`;
  h+=`<div class="stat"><span class="k">Food</span><span class="v">${s.food}/20</span></div>`;
  h+=`<div class="health-bar"><div class="fill food" style="width:${(s.food/20)*100}%"></div></div>`;
  let inv=s.inventory||[];
  if(inv.length){
    h+=`<div style="margin-top:6px;color:var(--text2);font-size:11px">INVENTORY</div>`;
    inv.forEach(i=>{h+=`<span class="inv-item">${esc(i.item)} x${i.count}</span>`});
  } else {
    h+=`<div style="margin-top:6px;color:var(--text2);font-size:11px">Inventory empty</div>`;
  }
  let ent=(s.entities||[]).filter(e=>e.kind!=='other').slice(0,5);
  if(ent.length){
    h+=`<div style="margin-top:8px;color:var(--text2);font-size:11px">NEARBY</div>`;
    ent.forEach(e=>{h+=`<div style="font-size:12px">${esc(e.name)} (${e.x},${e.y},${e.z})</div>`});
  }
  return h;
}

function renderChat(msgs){
  if(!msgs||!msgs.length)return '<div style="color:var(--text2)">No messages</div>';
  return msgs.slice(-25).map(m=>{
    let t=m.timestamp?new Date(m.timestamp).toLocaleTimeString('en',{hour12:false,hour:'2-digit',minute:'2-digit'}):'';
    let tp=m.type||'system';
    let senderCls=tp==='system'?' system':tp==='self'?' self':'';
    return `<div class="chat-msg"><span class="msg-type ${tp}">${tp}</span><span class="sender${senderCls}">${esc(m.sender||'?')}</span><span class="time">${t}</span><br>${esc(m.message||'')}</div>`;
  }).reverse().join('');
}

function renderEvents(evts){
  if(!evts||!evts.length)return '<div style="color:var(--text2)">No events yet. Say something in Minecraft chat!</div>';
  return evts.slice(-100).reverse().map(ev=>{
    let k=ev.kind, d=ev.data||{};
    let cls=k;
    let detail='';
    if(k==='agent_start') detail=`Goal: ${esc((d.goal||'').substring(0,150))}`;
    else if(k==='agent_step') detail=`Step ${d.step}/${d.max_steps}`;
    else if(k==='agent_done') detail=esc((d.message||'').substring(0,200));
    else if(k==='chat_command') detail=(d.commands||[]).map(c=>esc(c)).join(', ');
    else if(k==='tool_call') detail=`<b>${esc(d.tool||'')}</b>(${esc(JSON.stringify(d.args||{}).substring(0,120))})`;
    else if(k==='tool_result'){cls+=(d.ok?'':' err');detail=`<b>${esc(d.tool||'')}</b> → ${esc((d.result||'').substring(0,150))}`}
    else if(k==='tool_calls') detail=(d.tools||[]).map(t=>'<b>'+esc(t)+'</b>').join(', ');
    else if(k==='llm_message') detail=esc((d.content||'').substring(0,200));
    else detail=esc(JSON.stringify(d).substring(0,200));
    return `<div class="event"><span class="ts">${ts(ev.ts)}</span><span class="badge ${cls}">${esc(k)}</span><span class="event-data">${detail}</span></div>`;
  }).join('');
}

async function refresh(){
  try{
    let r=await fetch('/api/state');
    let d=await r.json();
    document.getElementById('dot').className=d.status?.connected?'dot on':'dot';
    document.getElementById('status').innerHTML=renderStatus(d.status);
    document.getElementById('chat').innerHTML=renderChat(d.chat);
    document.getElementById('events').innerHTML=renderEvents(d.events);
    document.getElementById('evcount').textContent=`${(d.events||[]).length} events`;
  }catch(e){
    document.getElementById('dot').className='dot';
  }
}
refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(_cached, default=str).encode())
        elif parsed.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        pass


def main() -> None:
    port = int(os.environ.get("DASHBOARD_PORT", "9000"))

    poller = threading.Thread(target=_poll_loop, daemon=True)
    poller.start()

    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"[dashboard] http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[dashboard] Stopped.")


if __name__ == "__main__":
    main()
