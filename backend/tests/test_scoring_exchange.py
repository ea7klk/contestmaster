from backend.app.adjudication.scoring import _exchange_values
from backend.app.rulesets.schema import ExchangeRule


def test_rst_is_mapped_from_its_own_qso_field_without_consuming_exchange_tokens():
    exchange_rule = ExchangeRule.model_validate(
        {
            "kind": "exchange",
            "fields": [
                {
                    "key": "rst",
                    "label": "Signal report",
                    "value_type": "text",
                    "direction": "both",
                    "required": True,
                },
                {
                    "key": "exchange",
                    "label": "Contest exchange",
                    "value_type": "text",
                    "direction": "both",
                    "required": True,
                },
            ],
        }
    )

    sent = _exchange_values(
        {"raw": "001 CA", "rst": "59"}, exchange_rule, direction="sent"
    )
    received = _exchange_values(
        {"raw": "042 NY", "rst": "59"}, exchange_rule, direction="received"
    )

    assert sent == {"exchange": "001 CA", "rst": "59"}
    assert received == {"exchange": "042 NY", "rst": "59"}
