"""
Hatchery Webhook Router — receives agent registration and dispatches events.

This runs on the Hatchery side (or as a sidecar) and:
  1. Accepts agent registrations (POST /register)
  2. Accepts agent heartbeats (POST /agent/{id}/heartbeat)
  3. Dispatches task.assigned / message.received / broadcast events to registered agents

For Hatchery's own deployment (Vercel), this would be an Edge Function or API route.
For local dev, this runs as a standalone Flask server.
"""
from __future__ import annotations

import os
import sys
import json
import time
import uuid
import logging
import sqlite3
import threading
import signal
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict
from flask import Flask, request, jsonify
import urllib.request
import urllib.error

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [hatchery-router] %(levelname)s %(message)s",
)
logger = logging.getLogger("hatchery-router")

# -----------------------------------------------------------------------
# DB Setup (SQLite for agent registry + message queue)
# -----------------------------------------------------------------------

DB_PATH = os.environ.get("HATCHERY_DB_PATH", "/tmp/hatchery-router.db")

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
            agent_id    TEXT PRIMARY KEY,
            agent_type  TEXT NOT NULL,
            name        TEXT,
            webhook_url TEXT NOT NULL,
            api_key     TEXT NOT NULL,
            capabilities TEXT,
            llm_provider TEXT,
            llm_model    TEXT,
            status      TEXT DEFAULT 'offline',
            last_seen   REAL,
            registered_at REAL
        );

        CREATE TABLE IF NOT EXISTS message_queue (
            id          TEXT PRIMARY KEY,
            event_type  TEXT NOT NULL,
            payload     TEXT NOT NULL,
            target      TEXT,  -- agent_id or 'broadcast'
            status      TEXT DEFAULT 'pending',
            created_at  REAL,
            delivered_at REAL,
            attempts    INTEGER DEFAULT 0,
            error       TEXT
        );

        CREATE TABLE IF NOT EXISTS deliveries (
            id          TEXT PRIMARY KEY,
            message_id  TEXT,
            agent_id    TEXT,
            status      TEXT,
            response    TEXT,
            attempted_at REAL,
            FOREIGN KEY (message_id) REFERENCES message_queue(id)
        );
    """)
    conn.commit()
    conn.close()
    logger.info(f"DB initialized at {DB_PATH}")

# -----------------------------------------------------------------------
# Agent Registry
# -----------------------------------------------------------------------

@dataclass
class RegisteredAgent:
    agent_id: str
    agent_type: str
    name: str
    webhook_url: str
    api_key: str
    capabilities: list
    llm_provider: str
    llm_model: str
    status: str
    last_seen: float

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "RegisteredAgent":
        caps = json.loads(row["capabilities"]) if row["capabilities"] else []
        return cls(
            agent_id=row["agent_id"],
            agent_type=row["agent_type"],
            name=row["name"] or "",
            webhook_url=row["webhook_url"],
            api_key=row["api_key"],
            capabilities=caps,
            llm_provider=row["llm_provider"] or "",
            llm_model=row["llm_model"] or "",
            status=row["status"],
            last_seen=row["last_seen"] or 0,
        )

class AgentRegistry:
    """In-memory + SQLite agent registry."""

    def __init__(self):
        self._lock = threading.RLock()
        self._agents: dict[str, RegisteredAgent] = {}
        self._load_from_db()

    def _load_from_db(self):
        conn = get_db()
        cur = conn.execute("SELECT * FROM agents")
        for row in cur.fetchall():
            agent = RegisteredAgent.from_row(row)
            self._agents[agent.agent_id] = agent
        conn.close()
        logger.info(f"Loaded {len(self._agents)} agents from DB")

    def register(self, agent_id: str, agent_type: str, name: str,
                 webhook_url: str, capabilities: list,
                 llm_provider: str, llm_model: str) -> tuple[str, str]:
        """
        Register a new agent. Generates a unique api_key.
        Returns (api_key, agent_id).
        """
        with self._lock:
            api_key = f"agnt_{uuid.uuid4().hex[:24]}"
            now = time.time()
            conn = get_db()
            conn.execute("""
                INSERT OR REPLACE INTO agents
                (agent_id, agent_type, name, webhook_url, api_key, capabilities,
                 llm_provider, llm_model, status, last_seen, registered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'online', ?, ?)
            """, (agent_id, agent_type, name, webhook_url, api_key,
                  json.dumps(capabilities), llm_provider, llm_model, now, now))
            conn.commit()
            conn.close()

            agent = RegisteredAgent(
                agent_id=agent_id, agent_type=agent_type, name=name,
                webhook_url=webhook_url, api_key=api_key,
                capabilities=capabilities, llm_provider=llm_provider,
                llm_model=llm_model, status="online", last_seen=now,
            )
            self._agents[agent_id] = agent
            logger.info(f"Registered agent: {agent_id} ({agent_type}) → {webhook_url}")
            return api_key, agent_id

    def heartbeat(self, agent_id: str) -> bool:
        """Record heartbeat. Returns True if agent is known."""
        with self._lock:
            if agent_id not in self._agents:
                return False
            now = time.time()
            conn = get_db()
            conn.execute("UPDATE agents SET last_seen=?, status='online' WHERE agent_id=?",
                        (now, agent_id))
            conn.commit()
            conn.close()
            self._agents[agent_id].last_seen = now
            self._agents[agent_id].status = "online"
            return True

    def get(self, agent_id: str) -> Optional[RegisteredAgent]:
        return self._agents.get(agent_id)

    def get_online(self) -> list[RegisteredAgent]:
        """Return all agents that have sent a heartbeat within 90 seconds."""
        cutoff = time.time() - 90
        return [a for a in self._agents.values() if a.last_seen > cutoff]

    def get_by_api_key(self, api_key: str) -> Optional[RegisteredAgent]:
        for agent in self._agents.values():
            if agent.api_key == api_key:
                return agent
        return None

    def mark_offline(self, agent_id: str):
        with self._lock:
            if agent_id in self._agents:
                self._agents[agent_id].status = "offline"
                conn = get_db()
                conn.execute("UPDATE agents SET status='offline' WHERE agent_id=?",
                            (agent_id,))
                conn.commit()
                conn.close()


# -----------------------------------------------------------------------
# Webhook Dispatcher
# -----------------------------------------------------------------------

class Dispatcher:
    """
    Delivers events to agent webhook URLs.
    Events are queued in SQLite and processed by a background worker thread.
    """

    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self._queue_thread = threading.Thread(target=self._process_queue, daemon=True)
        self._running = True
        self._queue_thread.start()

    def dispatch(self, event_type: str, payload: dict,
                 target: str = "broadcast",
                 timeout: int = 30):
        """
        Queue an event for delivery.
        target: agent_id for direct message, 'broadcast' for all online agents.
        """
        conn = get_db()
        msg_id = f"msg_{uuid.uuid4().hex[:16]}"
        conn.execute("""
            INSERT INTO message_queue (id, event_type, payload, target, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
        """, (msg_id, event_type, json.dumps(payload), target, time.time()))
        conn.commit()
        conn.close()
        logger.info(f"Queued {event_type} → {target} [{msg_id}]")

    def _deliver(self, agent: RegisteredAgent, payload: dict) -> dict:
        """POST an event to an agent's webhook URL. Returns response."""
        url = agent.webhook_url
        if not url:
            return {"error": "no webhook_url"}
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={
                "Authorization": f"Bearer {agent.api_key}",
                "Content-Type": "application/json",
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return {"status": resp.status, "body": json.loads(resp.read())}
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}", "body": e.read().decode()[:200]}
        except Exception as e:
            return {"error": str(e)}

    def _process_queue(self):
        """Background worker: pick up pending messages and deliver them."""
        while self._running:
            time.sleep(2)  # Poll every 2s
            conn = get_db()
            rows = conn.execute("""
                SELECT * FROM message_queue
                WHERE status = 'pending' AND attempts < 3
                ORDER BY created_at ASC
                LIMIT 10
            """).fetchall()
            conn.close()

            for row in rows:
                msg_id = row["id"]
                target = row["target"]
                payload = json.loads(row["payload"])
                event_type = row["event_type"]

                # Determine recipients
                if target == "broadcast":
                    recipients = self.registry.get_online()
                else:
                    agent = self.registry.get(target)
                    recipients = [agent] if agent else []

                if not recipients:
                    # No recipients — mark pending for later retry
                    continue

                all_ok = True
                for agent in recipients:
                    result = self._deliver(agent, payload)
                    delivery_id = f"dlv_{uuid.uuid4().hex[:12]}"
                    conn2 = get_db()
                    conn2.execute("""
                        INSERT INTO deliveries (id, message_id, agent_id, status, response, attempted_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (delivery_id, msg_id, agent.agent_id,
                          "ok" if "error" not in result else "failed",
                          json.dumps(result), time.time()))
                    if "error" in result:
                        all_ok = False
                    conn2.commit()
                    conn2.close()

                # Update message status
                conn3 = get_db()
                conn3.execute("""
                    UPDATE message_queue
                    SET status=?, attempts=attempts+1,
                        delivered_at=CASE WHEN ?=1 THEN ? ELSE NULL END,
                        error=CASE WHEN ?=0 THEN ? ELSE NULL END
                    WHERE id=?
                """, ("delivered" if all_ok else "pending",
                      1 if all_ok else 0,
                      time.time() if all_ok else None,
                      0 if all_ok else 1,
                      "some deliveries failed" if not all_ok else None,
                      msg_id))
                conn3.commit()
                conn3.close()


# -----------------------------------------------------------------------
# Flask App
# -----------------------------------------------------------------------

app = Flask(__name__)
registry = AgentRegistry()
dispatcher = Dispatcher(registry)


def require_api_key(f):
    """Decorator: validate Bearer token against agent registry."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Missing Authorization header"}), 401
        api_key = auth[7:]
        agent = registry.get_by_api_key(api_key)
        if not agent:
            return jsonify({"error": "Invalid API key"}), 403
        request.agent = agent
        return f(*args, **kwargs)
    return decorated


@app.route("/register", methods=["POST"])
def register():
    """Agent registration endpoint."""
    data = request.get_json() or {}
    required = ["agent_id", "agent_type", "webhook_url"]
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Missing field: {field}"}), 400

    api_key, agent_id = registry.register(
        agent_id=data["agent_id"],
        agent_type=data["agent_type"],
        name=data.get("name", data["agent_id"]),
        webhook_url=data["webhook_url"],
        capabilities=data.get("capabilities", ["git", "coding", "shell"]),
        llm_provider=data.get("llm_provider", ""),
        llm_model=data.get("llm_model", ""),
    )
    return jsonify({
        "agent_api_key": api_key,
        "registered_at": time.time(),
        "workspace_id": os.environ.get("HATCHERY_WS", ""),
    })


@app.route("/agent/<agent_id>/heartbeat", methods=["POST"])
def heartbeat(agent_id: str):
    """Agent heartbeat — also acts as auth check."""
    data = request.get_json() or {}
    if not registry.heartbeat(agent_id):
        return jsonify({"error": "Agent not registered"}), 404
    return jsonify({"status": "alive", "at": time.time()})


@app.route("/dispatch", methods=["POST"])
@require_api_key
def dispatch():
    """
    Internal endpoint: Goop/orchestrator dispatches an event to an agent.
    Called by the Hatchery platform when a task is assigned.
    """
    data = request.get_json() or {}
    event_type = data.get("event", "")
    target = data.get("target", "broadcast")  # agent_id or 'broadcast'
    payload = data.get("payload", {})

    if not event_type:
        return jsonify({"error": "Missing event type"}), 400

    dispatcher.dispatch(event_type, payload, target=target)
    return jsonify({"queued": True})


@app.route("/messages", methods=["POST"])
@require_api_key
def send_message():
    """Agent-to-agent message via dispatcher."""
    data = request.get_json() or {}
    to_agent = data.get("to_agent_id")
    content = data.get("content", "")
    if not to_agent or not content:
        return jsonify({"error": "Missing to_agent_id or content"}), 400

    dispatcher.dispatch("message.received", {
        "event": "message.received",
        "from_agent_id": request.agent.agent_id,
        "from_agent_name": request.agent.name,
        "content": content,
        "channel": data.get("channel", "direct"),
        "message_id": f"msg_{uuid.uuid4().hex[:16]}",
    }, target=to_agent)

    return jsonify({"queued": True})


@app.route("/broadcast", methods=["POST"])
@require_api_key
def broadcast():
    """Broadcast to all online agents."""
    data = request.get_json() or {}
    content = data.get("content", "")
    if not content:
        return jsonify({"error": "Missing content"}), 400

    dispatcher.dispatch("broadcast", {
        "event": "broadcast",
        "from_agent_id": request.agent.agent_id,
        "content": content,
        "received_at": time.time(),
    }, target="broadcast")

    return jsonify({"queued": True})


@app.route("/messages/<msg_id>/response", methods=["POST"])
@require_api_key
def message_response(msg_id: str):
    """
    Agent responds to a message it received.
    The sender (from the original message) receives the response.
    """
    data = request.get_json() or {}
    content = data.get("content", "")
    if not content:
        return jsonify({"error": "Missing content"}), 400

    # Look up the original message to find who sent it
    conn = get_db()
    row = conn.execute("SELECT * FROM message_queue WHERE id=?", (msg_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Original message not found"}), 404

    original = json.loads(row["payload"])
    # The original message had "from_agent_id" - that's who gets the response
    from_agent_id = original.get("from_agent_id")

    # Deliver response back to original sender
    dispatcher.dispatch("message.response", {
        "event": "message.response",
        "in_reply_to": msg_id,
        "from_agent_id": request.agent.agent_id,
        "from_agent_name": request.agent.name,
        "content": content,
    }, target=from_agent_id)

    return jsonify({"queued": True, "in_reply_to": msg_id})


@app.route("/agents", methods=["GET"])
def list_agents():
    """List all registered agents."""
    agents = []
    for a in registry._agents.values():
        agents.append({
            "agent_id": a.agent_id,
            "agent_type": a.agent_type,
            "name": a.name,
            "status": a.status,
            "last_seen": a.last_seen,
            "llm_provider": a.llm_provider,
            "llm_model": a.llm_model,
        })
    return jsonify({"agents": agents})


@app.route("/queue", methods=["GET"])
def queue_status():
    """Check message queue status."""
    conn = get_db()
    pending = conn.execute(
        "SELECT COUNT(*) FROM message_queue WHERE status='pending'"
    ).fetchone()[0]
    delivered = conn.execute(
        "SELECT COUNT(*) FROM message_queue WHERE status='delivered'"
    ).fetchone()[0]
    conn.close()
    return jsonify({"pending": pending, "delivered": delivered})


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("ROUTER_PORT", 8090))
    logger.info(f"Starting Hatchery webhook router on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
