import json

from mockpay.handler import lambda_handler


def test_reusing_idempotency_key_does_not_create_another_refund(system):
    _, _, _, refunds, _ = system()
    request = {
        "action": "post",
        "idempotency_key": "refund:wf-test",
        "order_id": "order-123",
        "amount_cents": 1000,
        "failure_mode": "none",
    }
    first = lambda_handler(request, None, refunds)
    second = lambda_handler(request, None, refunds)
    assert first["statusCode"] == second["statusCode"] == 201
    assert json.loads(first["body"])["refund_id"] == json.loads(second["body"])["refund_id"]
    assert len(refunds.items) == 1

