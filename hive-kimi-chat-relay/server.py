#!/usr/bin/env python3
import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8787"))
LAB_TOKEN = "HIVE-KIMI-CHAT-LAB-20260827-V0"
TASK_ID = "HIVE-KIMI-CHAT-0001"
RESULT_LOG = os.path.join(os.path.dirname(__file__), "result.log")


def now():
    return datetime.now(timezone.utc).isoformat()


class Handler(BaseHTTPRequestHandler):
    server_version = "HIVERelay/0.1"

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"[{now()}] {self.address_string()} {fmt % args}", flush=True)

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/health":
            return self._json({"ok": True, "service": "hive-kimi-chat-relay", "version": "0.1-lab"})

        if parsed.path == "/task":
            host = self.headers.get("Host")
            proto = self.headers.get("X-Forwarded-Proto", "https")
            callback_query = urlencode({
                "token": LAB_TOKEN,
                "task_id": TASK_ID,
                "message": "KIMI_CHAT_CONNECTED",
            })
            callback = f"{proto}://{host}/submit?{callback_query}"
            return self._json({
                "hive": "HIVE Kimi Chat Relay",
                "version": "0.1-lab",
                "task_id": TASK_ID,
                "agent": "KIMI_CHAT_FREE",
                "purpose": "Certify bidirectional HIVE communication using only Kimi Chat web_open_url.",
                "instructions": [
                    "Use only web_open_url for this connectivity test.",
                    "Do not use GitHub, Kimi Code, MCP, API keys, localhost, or paid tools.",
                    "Open callback_url exactly once.",
                    "If callback returns ok=true and accepted=true, report HIVE CHAT RELAY READY to the user."
                ],
                "callback_url": callback,
                "expected_callback": {"ok": True, "accepted": True, "task_id": TASK_ID},
                "security": {"lab_only": True, "production_data": False, "secrets_required": False}
            })

        if parsed.path == "/submit":
            token = qs.get("token", [""])[0]
            task_id = qs.get("task_id", [""])[0]
            message = qs.get("message", [""])[0]
            if token != LAB_TOKEN:
                return self._json({"ok": False, "accepted": False, "error": "invalid lab token"}, 403)
            if task_id != TASK_ID or message != "KIMI_CHAT_CONNECTED":
                return self._json({"ok": False, "accepted": False, "error": "invalid lab payload"}, 400)

            record = {
                "at": now(),
                "task_id": task_id,
                "message": message,
                "user_agent": self.headers.get("User-Agent"),
                "forwarded_for": self.headers.get("X-Forwarded-For"),
            }
            with open(RESULT_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            print("HIVE_KIMI_CHAT_CALLBACK_ACCEPTED " + json.dumps(record, ensure_ascii=False), flush=True)
            return self._json({
                "ok": True,
                "accepted": True,
                "task_id": task_id,
                "message": message,
                "next": "Report HIVE CHAT RELAY READY to the user."
            })

        if parsed.path == "/result":
            records = []
            if os.path.exists(RESULT_LOG):
                with open(RESULT_LOG, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                records.append(json.loads(line))
                            except json.JSONDecodeError:
                                pass
            return self._json({"ok": True, "task_id": TASK_ID, "callbacks": records[-20:]})

        return self._json({"ok": False, "error": "not found"}, 404)


if __name__ == "__main__":
    print(f"HIVE Kimi Chat Relay listening on http://{HOST}:{PORT}", flush=True)
    print("Endpoints: /health /task /submit /result", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
