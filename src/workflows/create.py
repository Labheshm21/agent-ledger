import os
import uuid

from ledger import FAILURE_MODES, now, record_event, request_body, response


def _tables():
    import boto3

    dynamodb = boto3.resource("dynamodb")
    return (
        dynamodb.Table(os.environ["WORKFLOWS_TABLE"]),
        dynamodb.Table(os.environ["EVENTS_TABLE"]),
    )


def lambda_handler(event, context, workflows=None, events=None):
    if workflows is None or events is None:
        workflows, events = _tables()

    try:
        body = request_body(event)
    except (ValueError, TypeError):
        return response(400, {"error": "body must be valid JSON"})

    order_id = body.get("order_id")
    amount_cents = body.get("amount_cents")
    failure_mode = body.get("failure_mode", "none")
    if not isinstance(order_id, str) or not order_id.strip():
        return response(400, {"error": "order_id must be a non-empty string"})
    if isinstance(amount_cents, bool) or not isinstance(amount_cents, int) or amount_cents <= 0:
        return response(400, {"error": "amount_cents must be a positive integer"})
    if failure_mode not in FAILURE_MODES:
        return response(400, {"error": "unsupported failure_mode"})

    workflow_id = f"wf-{uuid.uuid4().hex}"
    created_at = now()
    item = {
        "workflow_id": workflow_id,
        "order_id": order_id.strip(),
        "amount_cents": amount_cents,
        "status": "PENDING",
        "idempotency_key": f"refund:{workflow_id}",
        "attempts": 0,
        "reconciled": False,
        "failure_mode": failure_mode,
        "created_at": created_at,
        "updated_at": created_at,
    }
    workflows.put_item(Item=item, ConditionExpression="attribute_not_exists(workflow_id)")
    record_event(events, workflow_id, "WORKFLOW_CREATED", "Refund workflow created")
    return response(202, item)

