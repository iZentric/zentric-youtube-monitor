from __future__ import annotations

import reactii


def test_tag_is_removed_from_the_text_before_tts():
    text, tags = reactii.parse_tags("Ce naiba ai zis?! [anger] Ești nebun?")
    assert text == "Ce naiba ai zis?! Ești nebun?"
    assert tags == ["anger"]


def test_unknown_tags_are_ignored_and_do_not_break_the_text():
    text, tags = reactii.parse_tags("Salut [ploaie] lume")
    assert text == "Salut lume"
    assert tags == []


def test_aliases_and_repeated_tags():
    _text, tags = reactii.parse_tags("[angry] a [rage] b [shock]")
    assert tags == ["anger", "shock"]


def test_every_state_from_the_specification_exists():
    for tag in ("neutral", "smirk", "anger", "shock", "hype"):
        assert tag in reactii.REACTII


def test_head_angles_stay_inside_the_model_ranges():
    limit = {"ParamAngleX": 30, "ParamAngleY": 30, "ParamAngleZ": 30,
             "ParamBodyAngleX": 10, "ParamBodyAngleY": 10, "ParamBodyAngleZ": 10,
             "ParamEyeBallX": 1, "ParamEyeBallY": 1}
    for reactie in reactii.REACTII.values():
        for pid, value in reactie.angle.items():
            assert abs(value) <= limit[pid], f"{reactie.tag}: {pid}={value} iese din interval"


def test_requests_use_the_official_message_types():
    kinds = [message for message, _data in reactii.requests_for("shock")]
    assert kinds == ["ExpressionActivationRequest", "InjectParameterDataRequest"]


def test_expression_request_points_at_a_file_from_the_package():
    message, data = reactii.expression_request("shocked")
    assert message == "ExpressionActivationRequest"
    assert data["expressionFile"] == "izentric.shocked.exp3.json"
    assert 0.0 <= data["fadeTime"] <= 2.0


def test_head_request_sets_parameters_directly():
    message, data = reactii.head_request({"ParamAngleX": 14})
    assert message == "InjectParameterDataRequest"
    assert data["mode"] == "set" and data["faceFound"] is False
    assert data["parameterValues"] == [{"id": "ParamAngleX", "value": 14.0, "weight": 1.0}]
