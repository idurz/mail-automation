from __future__ import annotations

from threading import Thread
from typing import Any

from flask import Flask, jsonify, render_template, request

from .config import Rule
from .state import ProcessingState

VALID_ACTIONS = {"none", "move", "copy", "delete", "flag"}


def create_app(state: ProcessingState) -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/api/actions")
    def actions() -> Any:
        return jsonify(state.recent_actions())

    @app.get("/api/rules")
    def rules() -> Any:
        return jsonify(state.list_rules())

    @app.post("/api/rules")
    def add_rule() -> Any:
        payload = request.get_json(silent=True) or {}
        try:
            rule = Rule(
                name=str(payload["name"]).strip(),
                condition=str(payload["condition"]).strip(),
                action=str(payload["action"]).strip(),
                target=_optional_string(payload.get("target")),
                flag=_optional_string(payload.get("flag")),
            )
        except KeyError as error:
            return jsonify(error=f"missing field: {error.args[0]}"), 400
        if not rule.name or not rule.condition or rule.action not in VALID_ACTIONS:
            return jsonify(error="name, condition, and a valid action are required"), 400
        if rule.action in {"move", "copy"} and not rule.target:
            return jsonify(error=f"{rule.action} requires a target folder"), 400
        return jsonify(id=state.add_rule(rule)), 201

    @app.delete("/api/rules/<int:rule_id>")
    def delete_rule(rule_id: int) -> Any:
        return ("", 204) if state.delete_rule(rule_id) else ("", 404)

    return app


def start_server(state: ProcessingState, port: int) -> Thread:
    app = create_app(state)
    thread = Thread(
        target=app.run,
        kwargs={"host": "0.0.0.0", "port": port, "debug": False, "use_reloader": False},
        daemon=True,
    )
    thread.start()
    return thread


def _optional_string(value: object) -> str | None:
    return str(value).strip() or None if value is not None else None
