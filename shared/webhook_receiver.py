"""Flask-based webhook receiver for Hatchery agents."""
import os
import logging
import threading
from typing import Callable, Optional
from flask import Flask, request, jsonify, Response

logger = logging.getLogger(__name__)

class WebhookReceiver:
    """
    Lightweight Flask server that receives Hatchery webhook events.

    Usage:
        receiver = WebhookReceiver(port=8201, agent_api_key="agnt_xxx")
        receiver.register_handler('task.assigned', my_agent.on_task_assigned)
        receiver.register_handler('message.received', my_agent.on_message)
        receiver.start()
    """

    def __init__(self, port: int, agent_api_key: str,
                 event_handlers: Optional[dict] = None):
        self.port = port
        self.agent_api_key = agent_api_key
        self._handlers: dict[str, Callable] = event_handlers or {}
        self._app = Flask(__name__)
        self._server_thread: Optional[threading.Thread] = None
        self._running = False
        self._setup_routes()

    def register_handler(self, event_type: str, handler: Callable):
        """Register a handler for a specific event type."""
        self._handlers[event_type] = handler

    def _setup_routes(self):
        @self._app.route("/webhook", methods=["POST"])
        def webhook():
            # Validate Bearer token
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                logger.warning("Webhook received without Bearer token")
                return jsonify({"error": "Unauthorized"}), 401

            token = auth[7:]
            if token != self.agent_api_key:
                logger.warning(f"Webhook token mismatch: got {token[:10]}...")
                return jsonify({"error": "Forbidden"}), 403

            # Parse event
            try:
                event = request.get_json()
                if not event:
                    return jsonify({"error": "Empty body"}), 400
            except Exception:
                return jsonify({"error": "Invalid JSON"}), 400

            event_type = event.get("event", "")
            handler = self._handlers.get(event_type)

            logger.info(f"Webhook [{event_type}] received")
            response_data = {"acknowledged": True}

            if handler:
                try:
                    result = handler(event)
                    if isinstance(result, dict):
                        response_data.update(result)
                except Exception as e:
                    logger.error(f"Handler error for {event_type}: {e}")
                    response_data["error"] = str(e)
            else:
                logger.info(f"No handler for event type: {event_type}")

            return jsonify(response_data), 200

        @self._app.route("/health", methods=["GET"])
        def health():
            return jsonify({"status": "ok", "agent": os.environ.get("AGENT_ID", "?")})

    def start(self, background: bool = True):
        """Start the Flask server."""
        if background:
            self._server_thread = threading.Thread(
                target=self._run_server, daemon=True
            )
            self._server_thread.start()
            self._running = True
            logger.info(f"Webhook receiver started on port {self.port}")
        else:
            self._run_server()

    def _run_server(self):
        self._app.run(host="0.0.0.0", port=self.port, debug=False, threaded=True)

    def stop(self):
        """Stop the server (Flask doesn't have clean shutdown; rely on daemon)."""
        self._running = False
