import pytest

from pimlint.schema import ChannelSchema, Severity


def _schema():
    return ChannelSchema.from_dict({
        "channel": "test",
        "attributes": {
            "sku": {"type": "string", "required": True, "max_length": 10},
            "title": {"type": "string", "required": True, "min_length": 3},
            "price": {"type": "float", "required": True},
            "qty": {"type": "int", "required": True},
            "active": {"type": "bool", "required": False},
            "currency": {"type": "enum", "required": True,
                         "values": ["BRL", "USD"]},
            "launch": {"type": "date", "required": False},
            "url": {"type": "string", "required": False,
                    "pattern": "^https?://"},
        },
    })


def test_enum_without_values_is_rejected():
    with pytest.raises(ValueError, match="values"):
        ChannelSchema.from_dict({
            "channel": "x",
            "attributes": {"c": {"type": "enum", "required": True}},
        })


def test_invalid_pattern_is_rejected():
    with pytest.raises(ValueError, match="pattern"):
        ChannelSchema.from_dict({
            "channel": "x",
            "attributes": {"u": {"type": "string", "pattern": "([unclosed"}},
        })


def test_required_attributes_property():
    assert set(_schema().required_attributes) == {"sku", "title", "price", "qty", "currency"}


def test_shorthand_required_syntax():
    schema = ChannelSchema.from_dict({
        "channel": "x",
        "attributes": {"sku": "required", "note": "optional"},
    })
    assert schema.get("sku").required is True
    assert schema.get("note").required is False


def test_get_returns_none_for_unknown():
    assert _schema().get("nao_existe") is None
