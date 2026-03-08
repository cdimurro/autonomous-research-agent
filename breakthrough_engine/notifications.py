"""Notification hooks for the Breakthrough Engine.

Pluggable notifier adapters for run events:
- LoggingNotifier: writes to Python logging (default)
- FileNotifier: appends to a notification log file
- WebhookNotifier: POSTs JSON to a webhook URL (interface only, no live calls in tests)
"""

from __future__ import annotations

import abc
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class NotificationEvent:
    """Structured notification payload."""

    def __init__(
        self,
        event_type: str,
        run_id: str = "",
        program_name: str = "",
        message: str = "",
        details: dict | None = None,
    ):
        self.event_type = event_type
        self.run_id = run_id
        self.program_name = program_name
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "run_id": self.run_id,
            "program_name": self.program_name,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
        }


class Notifier(abc.ABC):
    """Abstract notifier interface."""

    @abc.abstractmethod
    def send(self, event: NotificationEvent) -> bool:
        """Send a notification. Returns True on success."""


class LoggingNotifier(Notifier):
    """Logs notifications via Python logging."""

    def send(self, event: NotificationEvent) -> bool:
        logger.info(
            "[NOTIFICATION] %s | run=%s | %s",
            event.event_type, event.run_id, event.message,
        )
        return True


class FileNotifier(Notifier):
    """Appends notifications to a log file."""

    def __init__(self, path: str | Path | None = None):
        if path is None:
            root = os.environ.get("SCIRES_RUNTIME_ROOT", "runtime")
            path = Path(root) / "logs" / "notifications.jsonl"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def send(self, event: NotificationEvent) -> bool:
        try:
            with open(self.path, "a") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
            return True
        except Exception as e:
            logger.warning("FileNotifier failed: %s", e)
            return False


class WebhookNotifier(Notifier):
    """POSTs notifications to a webhook URL."""

    def __init__(self, url: str, timeout: int = 10):
        self.url = url
        self.timeout = timeout

    def send(self, event: NotificationEvent) -> bool:
        try:
            import requests
            resp = requests.post(
                self.url,
                json=event.to_dict(),
                timeout=self.timeout,
                headers={"Content-Type": "application/json"},
            )
            return resp.status_code < 400
        except Exception as e:
            logger.warning("WebhookNotifier failed: %s", e)
            return False


class NotificationDispatcher:
    """Dispatches events to multiple notifiers."""

    def __init__(self, notifiers: list[Notifier] | None = None):
        self.notifiers = notifiers or [LoggingNotifier()]

    def notify(self, event: NotificationEvent) -> None:
        for notifier in self.notifiers:
            try:
                notifier.send(event)
            except Exception as e:
                logger.warning("Notifier %s failed: %s", type(notifier).__name__, e)

    def run_completed(self, run_id: str, program_name: str, status: str, **kwargs) -> None:
        self.notify(NotificationEvent(
            event_type="run_completed",
            run_id=run_id,
            program_name=program_name,
            message=f"Run {run_id[:8]} completed with status: {status}",
            details={"status": status, **kwargs},
        ))

    def draft_awaiting_review(self, run_id: str, program_name: str, draft_id: str, title: str) -> None:
        self.notify(NotificationEvent(
            event_type="draft_awaiting_review",
            run_id=run_id,
            program_name=program_name,
            message=f"Draft '{title}' awaiting operator review",
            details={"draft_id": draft_id, "candidate_title": title},
        ))

    def run_failed(self, run_id: str, program_name: str, error: str) -> None:
        self.notify(NotificationEvent(
            event_type="run_failed",
            run_id=run_id,
            program_name=program_name,
            message=f"Run {run_id[:8]} failed: {error}",
            details={"error": error},
        ))
