import os

from ledger import response


def lambda_handler(event, context, events=None):
    if events is None:
        import boto3

        events = boto3.resource("dynamodb").Table(os.environ["EVENTS_TABLE"])

    workflow_id = (event.get("pathParameters") or {}).get("workflow_id")
    if not workflow_id:
        return response(400, {"error": "workflow_id is required"})
    result = events.query(
        KeyConditionExpression="workflow_id = :workflow_id",
        ExpressionAttributeValues={":workflow_id": workflow_id},
        ScanIndexForward=True,
    )
    return response(200, {"workflow_id": workflow_id, "events": result.get("Items", [])})

