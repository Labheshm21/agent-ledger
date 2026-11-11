import pytest

from worker.handler import process_workflow


def test_timeout_after_success_is_reconciled(system):
    workflow_id, workflows, events, refunds, client = system("timeout_after_success")
    process_workflow(workflow_id, workflows, events, client, "mockpay")
    workflow = workflows.get_item(Key={"workflow_id": workflow_id})["Item"]
    event_types = [item["event_type"] for item in events.items.values()]
    assert workflow["status"] == "SUCCEEDED"
    assert workflow["reconciled"] is True
    assert len(refunds.items) == 1
    assert "OUTCOME_UNKNOWN" in event_types
    assert "RECONCILIATION_STARTED" in event_types


@pytest.mark.parametrize("failure_mode", ["timeout_before_success", "worker_crash_after_response"])
def test_retryable_failures_recover_without_duplicates(system, failure_mode):
    workflow_id, workflows, events, refunds, client = system(failure_mode)
    with pytest.raises(RuntimeError):
        process_workflow(workflow_id, workflows, events, client, "mockpay")
    process_workflow(workflow_id, workflows, events, client, "mockpay")
    workflow = workflows.get_item(Key={"workflow_id": workflow_id})["Item"]
    assert workflow["status"] == "SUCCEEDED"
    assert workflow["attempts"] == 2
    assert len(refunds.items) == 1

