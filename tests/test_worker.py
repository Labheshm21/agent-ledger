import json

from worker.handler import lambda_handler, process_workflow


def test_normal_refund_succeeds(system):
    workflow_id, workflows, events, refunds, client = system()
    process_workflow(workflow_id, workflows, events, client, "mockpay")
    workflow = workflows.get_item(Key={"workflow_id": workflow_id})["Item"]
    assert workflow["status"] == "SUCCEEDED"
    assert workflow["attempts"] == 1
    assert workflow["reconciled"] is False
    assert len(refunds.items) == 1


def test_duplicate_sqs_messages_do_not_create_duplicate_refunds(system):
    workflow_id, workflows, events, refunds, client = system()
    process_workflow(workflow_id, workflows, events, client, "mockpay")
    process_workflow(workflow_id, workflows, events, client, "mockpay")
    assert len(refunds.items) == 1
    assert workflows.get_item(Key={"workflow_id": workflow_id})["Item"]["attempts"] == 1


def test_permanently_failing_messages_enter_dead_letter_queue(system):
    workflow_id, workflows, events, refunds, client = system(permanent_failure=True)
    record = {"messageId": "message-1", "body": json.dumps({"workflow_id": workflow_id})}
    dead_letter_queue = []
    for receive_count in range(1, 4):
        record["attributes"] = {"ApproximateReceiveCount": str(receive_count)}
        result = lambda_handler({"Records": [record]}, None, workflows, events, client)
        assert result == {"batchItemFailures": [{"itemIdentifier": "message-1"}]}
        if receive_count == 3:
            dead_letter_queue.append(record)
    assert dead_letter_queue == [record]
    assert len(refunds.items) == 0
    assert workflows.get_item(Key={"workflow_id": workflow_id})["Item"]["status"] == "FAILED"

