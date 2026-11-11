import io
import json
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).parents[1] / "src"))


class ConditionalFailure(Exception):
    response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class MemoryTable:
    def __init__(self, *keys):
        self.keys = keys
        self.items = {}

    def _key(self, item):
        return tuple(item[key] for key in self.keys)

    def put_item(self, Item, ConditionExpression=None):
        key = self._key(Item)
        if ConditionExpression and key in self.items:
            raise ConditionalFailure()
        self.items[key] = dict(Item)
        return {}

    def get_item(self, Key, **kwargs):
        item = self.items.get(tuple(Key[key] for key in self.keys))
        return {"Item": dict(item)} if item else {}

    def update_item(self, Key, UpdateExpression, ExpressionAttributeValues, ExpressionAttributeNames=None, ReturnValues=None):
        key = tuple(Key[name] for name in self.keys)
        item = self.items[key]
        item["status"] = ExpressionAttributeValues[":status"]
        item["updated_at"] = ExpressionAttributeValues[":now"]
        if ":one" in ExpressionAttributeValues:
            item["attempts"] += ExpressionAttributeValues[":one"]
        if ":reconciled" in ExpressionAttributeValues:
            item["reconciled"] = ExpressionAttributeValues[":reconciled"]
        return {"Attributes": dict(item)} if ReturnValues else {}

    def query(self, ExpressionAttributeValues, **kwargs):
        workflow_id = ExpressionAttributeValues[":workflow_id"]
        items = [dict(item) for key, item in sorted(self.items.items()) if key[0] == workflow_id]
        return {"Items": items}


class FakeLambda:
    def __init__(self, refunds, permanent_failure=False):
        self.refunds = refunds
        self.permanent_failure = permanent_failure

    def invoke(self, Payload, **kwargs):
        from mockpay.handler import lambda_handler

        event = json.loads(Payload)
        reply = {"statusCode": 503, "body": json.dumps({"error": "permanent failure"})} if self.permanent_failure else lambda_handler(event, None, self.refunds)
        return {"Payload": io.BytesIO(json.dumps(reply).encode())}


@pytest.fixture
def system():
    def build(failure_mode="none", permanent_failure=False):
        workflows = MemoryTable("workflow_id")
        events = MemoryTable("workflow_id", "event_id")
        refunds = MemoryTable("idempotency_key")
        workflow_id = "wf-test"
        workflows.put_item(
            Item={
                "workflow_id": workflow_id,
                "order_id": "order-123",
                "amount_cents": 1000,
                "status": "PENDING",
                "idempotency_key": f"refund:{workflow_id}",
                "attempts": 0,
                "reconciled": False,
                "failure_mode": failure_mode,
                "created_at": "now",
                "updated_at": "now",
            }
        )
        return workflow_id, workflows, events, refunds, FakeLambda(refunds, permanent_failure)

    return build

