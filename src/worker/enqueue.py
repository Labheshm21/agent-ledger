import json
import os


def lambda_handler(event, context, sqs=None):
    if sqs is None:
        import boto3

        sqs = boto3.client("sqs")
    failures = []
    for record in event.get("Records", []):
        sequence_number = record.get("dynamodb", {}).get("SequenceNumber", "")
        try:
            image = record.get("dynamodb", {}).get("NewImage", {})
            if record.get("eventName") != "INSERT" or image.get("status", {}).get("S") != "PENDING":
                continue
            workflow_id = image["workflow_id"]["S"]
            sqs.send_message(QueueUrl=os.environ["QUEUE_URL"], MessageBody=json.dumps({"workflow_id": workflow_id}))
        except Exception as exc:
            print(json.dumps({"level": "error", "message": str(exc), "event_id": record.get("eventID")}))
            failures.append({"itemIdentifier": sequence_number})
    return {"batchItemFailures": failures}

