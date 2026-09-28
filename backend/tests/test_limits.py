from app.limits import DEFAULT_RULES, effective_limit


def rules():
    import json

    return json.loads(json.dumps(DEFAULT_RULES))


def test_type_defaults_follow_deck_rules():
    r = rules()
    assert effective_limit("unit", "Common", r) == 3
    assert effective_limit("spell", "Rare", r) == 3
    assert effective_limit("gear", "Uncommon", r) == 3
    assert effective_limit("legend", "Legend", r) == 1
    assert effective_limit("battlefield", "Epic", r) == 1
    assert effective_limit("rune", "Common", r) == 12


def test_unknown_type_uses_fallback():
    assert effective_limit("token", "Common", rules()) == 3


def test_override_beats_everything():
    r = rules()
    r["rarity_caps_enabled"] = True
    assert effective_limit("unit", "Epic", r, override=7) == 7


def test_rarity_cap_applies_only_when_enabled():
    r = rules()
    assert effective_limit("unit", "Epic", r) == 3
    r["rarity_caps_enabled"] = True
    assert effective_limit("unit", "Epic", r) == 1
    # Cap lowers the limit but never raises it above the type default.
    r["rarity_caps"]["common"] = 99
    assert effective_limit("unit", "Common", r) == 3
