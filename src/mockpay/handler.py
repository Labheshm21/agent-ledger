import json
import os
import uuid

from ledger import FAILURE_MODES, now, request_body, response


def _table():
    import boto3

    return boto3.resource("dynamodb").Table(os.environ["REFUNDS_TABLE"])


def _conditional_failure(exc):
    return getattr(exc, "response", {}).get("Error", {}).get("Code") == "ConditionalCheckFailedException"


def _request(event):
    if event.get("action"):
        return event["action"].lower(), event
    method = ((event.get("requestContext") or {}).get("http") or {}).get("method", "").lower()
    if method == "get":
        return "get", {"idempotency_key": (event.get("pathParameters") or {}).get("idempotency_key")}
    if method == "post":
        return "post", request_body(event)
    return method, {}


def lambda_handler(event, context, refunds=None):
    refunds = refunds or _table()
    try:
        action, payload = _request(event)
    except (ValueError, TypeError, json.JSONDecodeError):
        return response(400, {"error": "body must be valid JSON"})

    idempotency_key = payload.get("idempotency_key")
    if not isinstance(idempotency_key, str) or not idempotency_key:
        return response(400, {"error": "idempotency_key is required"})

    if action == "get":
        item = refunds.get_item(Key={"idempotency_key": idempotency_key}, ConsistentRead=True).get("Item")
        return response(200, item) if item else response(404, {"error": "refund not found"})
    if action != "post":
        return response(405, {"error": "method not allowed"})

    order_id = payload.get("order_id")
    amount_cents = payload.get("amount_cents")
    failure_mode = payload.get("failure_mode", "none")
    if not isinstance(order_id, str) or not order_id:
        return response(400, {"error": "order_id is required"})
    if isinstance(amount_cents, bool) or not isinstance(amount_cents, int) or amount_cents <= 0:
        return response(400, {"error": "amount_cents must be a positive integer"})
    if failure_mode not in FAILURE_MODES:
        return response(400, {"error": "unsupported failure_mode"})
    if failure_mode == "timeout_before_success":
        return response(504, {"error": "simulated timeout before refund"})

    item = {
        "idempotency_key": idempotency_key,
        "refund_id": f"ref-{uuid.uuid4().hex}",
        "order_id": order_id,
        "amount_cents": amount_cents,
        "status": "SUCCEEDED",
        "created_at": now(),
    }
    try:
        refunds.put_item(Item=item, ConditionExpression="attribute_not_exists(idempotency_key)")
    except Exception as exc:
        if not _conditional_failure(exc):
            raise
        item = refunds.get_item(Key={"idempotency_key": idempotency_key}, ConsistentRead=True)["Item"]

    if failure_mode == "timeout_after_success":
        return response(504, {"error": "simulated timeout after refund"})
    return response(201, item)

