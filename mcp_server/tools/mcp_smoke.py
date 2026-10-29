"""最小 MCP SSE 客户端：不依赖任何第三方库，只用标准库。

用途：在 Nexent 之外独立验证 MCP server 的协议是否正确。
如果这个脚本能跑通 initialize / tools/list / tools/call，
那么 Nexent 作为客户端也基本不会有问题（协议一致）。

用法：
    python mcp_smoke.py [http://127.0.0.1:8931]
"""
import json
import queue
import sys
import threading
import time
import urllib.parse
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8931").rstrip("/")
LOG = []
_q = queue.Queue()
_ep = {}


def log(*a):
    line = " ".join(str(x) for x in a)
    LOG.append(line)
    print(line, flush=True)


def _sse_reader():
    req = urllib.request.Request(BASE + "/sse", headers={"Accept": "text/event-stream"})
    with urllib.request.urlopen(req, timeout=60) as r:
        event = None
        for raw in r:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1].strip()
                if event == "endpoint":
                    _ep["url"] = data
                elif event == "message":
                    _q.put(json.loads(data))
                event = None


def _post(payload):
    req = urllib.request.Request(
        _ep["full"],
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def _rpc(msg_id, method, params=None, notify=False):
    payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if not notify:
        payload["id"] = msg_id
    status = _post(payload)
    if notify:
        return {"status": status}
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            msg = _q.get(timeout=max(0.1, deadline - time.time()))
        except queue.Empty:
            break
        if msg.get("id") == msg_id:
            return msg
    raise RuntimeError(f"timeout waiting for response to {method}")


def main():
    t = threading.Thread(target=_sse_reader, daemon=True)
    t.start()
    for _ in range(200):
        if "url" in _ep:
            break
        time.sleep(0.05)
    if "url" not in _ep:
        log("FAIL: 未收到 SSE endpoint 事件，服务未启动或 /sse 路径不对")
        return 1

    _ep["full"] = urllib.parse.urljoin(BASE + "/", _ep["url"].lstrip("/"))
    log("[1] SSE endpoint =", _ep["url"])

    init = _rpc(
        1,
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "dsh-smoke", "version": "1.0.0"},
        },
    )
    res = init.get("result", {})
    log("[2] initialize OK ->", res.get("serverInfo"), "protocol", res.get("protocolVersion"))

    _rpc(None, "notifications/initialized", notify=True)
    log("[3] notifications/initialized sent")

    tools = _rpc(2, "tools/list").get("result", {}).get("tools", [])
    log("[4] tools/list ->", len(tools), "tools")
    for tl in tools:
        log("     -", tl["name"], "|", (tl.get("description") or "").splitlines()[0][:60])

    from urllib.parse import quote

    assert "ping" in [t["name"] for t in tools], "tool 'ping' missing"
    for name, args in [
        ("ping", {}),
        ("list_equipment", {}),
        ("get_equipment", {"keyword": "CNC-01"}),
        ("get_fault_code", {"code_or_name": "E-101"}),
        ("get_spare_part", {"keyword": "SP-1001"}),
        ("get_threshold", {"keyword": "振动"}),
    ]:
        r = _rpc(100 + len(LOG), "tools/call", {"name": name, "arguments": args})
        content = r.get("result", {}).get("content", [])
        text = content[0]["text"] if content else json.dumps(r, ensure_ascii=False)
        log(f"[5] tools/call {name} -> OK, {len(text)} chars")
        log("     " + text[:300].replace("\n", " "))

    log("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
