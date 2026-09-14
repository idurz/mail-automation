from app.web import _condition_from_fields


def test_condition_preserves_deliberate_filter_spaces():
    condition = _condition_from_fields({
        "subject": "  payment details  ",
        "text": "   ",
    })

    assert condition == "contains(subject, '  payment details  ')"