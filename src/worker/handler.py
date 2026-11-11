import json
import os

from ledger import now, record_event


TERMINAL_STATES = {"SUCCEEDED", "FAILED"}


def _dependencies():
    import boto3

    dynamodb = boto3.resource("dynamodb")
    return (
        dynamodb.Table(os.environ["WORKFLOWS_TABLE"]),
        dynamodb.Table(os.environ["EVENTS_TABLE"]),
        boto3.client("lambda"),
    )


def _mockpay(client, function_name, payload):
    result = client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode(),
    )
    if result.get("FunctionError"):
        raise RuntimeError("MockPay Lambda failed")
    raw = result["Payload"].read()
    reply = json.loads(raw)
    body = reply.get("body", {})
    if isinstance(body, str):
        body = json.loads(body or "{}")
    return reply.get("statusCode", 500), body


def _set_status(workflows, workflow_id, status, reconciled=None):
    values = {":status": status, ":now": now()}
    expression = "SET #status = :status, updated_at = :now"
    if reconciled is not None:
        expression += ", reconciled = :reconciled"
        values[":reconciled"] = reconciled
    workflows.update_item(
        Key={"workflow_id": workflow_id},
        UpdateExpression=expression,
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues=values,
    )


def _metric(name, value=1):
    print(
        json.dumps(
            {
                "_aws": {
                    "Timestamp": int(__import__("time").time() * 1000),
                    "CloudWatchMetrics": [
                        {
                            "Namespace": "AgentLedger",
                            "Dimensions": [[]],
                            "Metrics": [{"Name": name, "Unit": "Count"}],
                        }
                    ],
                },
                name: value,
            }
        )
    )


def _complete(workflows, events, workflow_id, reconciled):
    _set_status(workflows, workflow_id, "SUCCEEDED", reconciled)
    record_event(events, workflow_id, "WORKFLOW_SUCCEEDED", "Refund found during reconciliation" if reconciled else "Refund completed")
    _metric("WorkflowSucceeded")
    if reconciled:
        _metric("WorkflowReconciled")


def process_workflow(workflow_id, workflows, events, lambda_client, mockpay_function):
    workflow = workflows.get_item(Key={"workflow_id": workflow_id}, ConsistentRead=True).get("Item")
    if not workflow:
        raise ValueError(f"workflow {workflow_id} not found")
    if workflow["status"] in TERMINAL_STATES:
        return

    updated = workflows.update_item(
        Key={"workflow_id": workflow_id},
        UpdateExpression="SET #status = :status, updated_at = :now ADD attempts :one",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={":status": "PROCESSING", ":now": now(), ":one": 1},
        ReturnValues="ALL_NEW",
    )["Attributes"]
    attempts = int(updated["attempts"])
    record_event(events, workflow_id, "ATTEMPT_STARTED", f"Worker attempt {attempts} started")

    lookup = {"action": "get", "idempotency_key": workflow["idempotency_key"]}
    status, refund = _mockpay(lambda_client, mockpay_function, lookup)
    if status == 200:
        _complete(workflows, events, workflow_id, True)
        return
    if status != 404:
        raise RuntimeError(f"MockPay lookup failed with status {status}")

    # Failure injection is one-shot; later attempts only run after absence is confirmed.
    failure_mode = workflow.get("failure_mode", "none") if attempts == 1 else "none"
    status, result = _mockpay(
        lambda_client,
        mockpay_function,
        {
            "action": "post",
            "idempotency_key": workflow["idempotency_key"],
            "order_id": workflow["order_id"],
            "amount_cents": int(workflow["amount_cents"]),
            "failure_mode": failure_mode,
        },
    )
    if 200 <= status < 300:
        record_event(events, workflow_id, "MOCKPAY_RESPONDED", "MockPay confirmed the refund")
        if failure_mode == "worker_crash_after_response":
            raise RuntimeError("simulated worker crash after MockPay response")
        _complete(workflows, events, workflow_id, False)
        return
    if status != 504:
        record_event(events, workflow_id, "MOCKPAY_FAILED", f"MockPay returned status {status}")
        raise RuntimeError(f"MockPay request failed with status {status}: {result}")

    _set_status(workflows, workflow_id, "UNKNOWN_OUTCOME")
    record_event(events, workflow_id, "OUTCOME_UNKNOWN", "MockPay timed out; blind retry blocked")
    _metric("UnknownOutcome")
    _set_status(workflows, workflow_id, "RECONCILING")
    record_event(events, workflow_id, "RECONCILIATION_STARTED", "Checking MockPay by idempotency key")
    lookup_status, _ = _mockpay(lambda_client, mockpay_function, lookup)
    if lookup_status == 200:
        _complete(workflows, events, workflow_id, True)
        return
    if lookup_status == 404:
        record_event(events, workflow_id, "REFUND_CONFIRMED_ABSENT", "A later retry is safe")
        raise RuntimeError("refund confirmed absent; retry requested")
    raise RuntimeError(f"MockPay reconciliation failed with status {lookup_status}")


def lambda_handler(event, context, workflows=None, events=None, lambda_client=None):
    if workflows is None or events is None or lambda_client is None:
        workflows, events, lambda_client = _dependencies()
    failures = []
    function_name = os.environ.get("MOCKPAY_FUNCTION", "mockpay")
    for record in event.get("Records", []):
        workflow_id = None
        try:
            workflow_id = json.loads(record["body"])["workflow_id"]
            process_workflow(workflow_id, workflows, events, lambda_client, function_name)
        except Exception as exc:
            print(json.dumps({"level": "error", "message": str(exc), "message_id": record.get("messageId")}))
            receive_count = int((record.get("attributes") or {}).get("ApproximateReceiveCount", "1"))
            if workflow_id and receive_count >= int(os.environ.get("MAX_RECEIVE_COUNT", "3")):
                _set_status(workflows, workflow_id, "FAILED")
                record_event(events, workflow_id, "WORKFLOW_FAILED", "Message exhausted SQS retries and is entering the dead-letter queue")
                _metric("WorkflowFailed")
            failures.append({"itemIdentifier": record.get("messageId", "unknown")})
    return {"batchItemFailures": failures}

