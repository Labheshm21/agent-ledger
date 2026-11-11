import json
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal


FAILURE_MODES = {
    "none",
    "timeout_before_success",
    "timeout_after_success",
    "worker_crash_after_response",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def response(status_code, payload):
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(payload, default=_json_default),
    }


def _json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else str(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def request_body(event):
    body = event.get("body", {})
    if isinstance(body, str):
        body = json.loads(body or "{}")
    if not isinstance(body, dict):
        raise ValueError("request body must be a JSON object")
    return body


def record_event(table, workflow_id, event_type, message):
    created_at = now()
    table.put_item(
        Item={
            "workflow_id": workflow_id,
            "event_id": f"{time.time_ns():020d}#{uuid.uuid4().hex}",
            "event_type": event_type,
            "message": message,
            "created_at": created_at,
        }
    )

