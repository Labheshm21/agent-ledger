import os

from ledger import response


def lambda_handler(event, context, workflows=None):
    if workflows is None:
        import boto3

        workflows = boto3.resource("dynamodb").Table(os.environ["WORKFLOWS_TABLE"])

    workflow_id = (event.get("pathParameters") or {}).get("workflow_id")
    if not workflow_id:
        return response(400, {"error": "workflow_id is required"})
    item = workflows.get_item(Key={"workflow_id": workflow_id}, ConsistentRead=True).get("Item")
    return response(200, item) if item else response(404, {"error": "workflow not found"})

