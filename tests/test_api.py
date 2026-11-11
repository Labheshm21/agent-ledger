import json
from decimal import Decimal

from ledger import response


def test_dynamodb_numbers_are_json_serializable():
    payload = json.loads(response(200, {"amount_cents": Decimal("1000"), "ratio": Decimal("1.25")})["body"])
    assert payload == {"amount_cents": 1000, "ratio": "1.25"}
