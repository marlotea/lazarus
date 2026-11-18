"""CEBRA and preprocessing parameter models (no database)."""

import pytest
from pydantic import ValidationError

from app.schemas.cebra import (
    PARAMS_BY_MODE,
    BehaviourParams,
    HybridParams,
    TimeParams,
)
from app.schemas.preprocess import PreprocessParams

SHARED = {
    "model_architecture": "offset10-model",
    "output_dimension": 8,
    "batch_size": 512,
    "learning_rate": 3e-4,
    "temperature": 1.0,
    "max_iterations": 5000,
    "distance": "cosine",
    "time_offsets": 10,
    "seed": 0,
}


@pytest.mark.parametrize("mode", ["time", "behaviour", "hybrid"])
def test_each_mode_accepts_defaults(mode):
    params = PARAMS_BY_MODE[mode]()
    assert PARAMS_BY_MODE[mode].model_validate({}) == params
    dumped = params.model_dump()
    assert {k: dumped[k] for k in SHARED} == SHARED
    if mode == "time":
        assert set(dumped) == set(SHARED)
    else:
        assert dumped["continuous_labels"] == ["wheel_velocity"]
        assert dumped["discrete_label"] is None


@pytest.mark.parametrize("model", [BehaviourParams, HybridParams])
def test_labelled_modes_reject_no_labels(model):
    with pytest.raises(ValidationError) as info:
        model(continuous_labels=[], discrete_label=None)
    (err,) = info.value.errors()
    assert err["type"] == "labels_required"
    assert err["ctx"] == {"field": "continuous_labels"}
    if model is BehaviourParams:
        # One discrete label alone is enough.
        assert model(continuous_labels=[], discrete_label="choice").discrete_label == "choice"


def test_hybrid_rejects_discrete_label():
    # cebra 0.6.1 cannot train hybrid with a discrete label.
    for continuous in ([], ["wheel_velocity"]):
        with pytest.raises(ValidationError) as info:
            HybridParams(continuous_labels=continuous, discrete_label="choice")
        (err,) = info.value.errors()
        assert err["type"] == "hybrid_discrete_unsupported"
        assert err["ctx"] == {"field": "discrete_label"}


def test_hidden_mode_fields():
    assert TimeParams().cebra_kwargs()["conditional"] == "time"
    assert "hybrid" not in TimeParams().cebra_kwargs()
    assert BehaviourParams().cebra_kwargs()["conditional"] == "time_delta"
    hybrid = HybridParams().cebra_kwargs()
    assert (hybrid["conditional"], hybrid["hybrid"]) == ("time_delta", True)
    # Not CEBRA arguments, and never in the form schema or a request body.
    for kwargs in (TimeParams().cebra_kwargs(), hybrid):
        assert not {"seed", "continuous_labels", "discrete_label"} & set(kwargs)
    for model in PARAMS_BY_MODE.values():
        props = model.model_json_schema()["properties"]
        assert "conditional" not in props and "hybrid" not in props
    with pytest.raises(ValidationError):
        TimeParams.model_validate({"conditional": "time_delta"})
    with pytest.raises(ValidationError):
        TimeParams.model_validate({"continuous_labels": ["wheel_velocity"]})


@pytest.mark.parametrize(
    "field, value",
    [
        ("output_dimension", 1),
        ("output_dimension", 65),
        ("output_dimension", 8.5),
        ("batch_size", 63),
        ("learning_rate", 0.2),
        ("temperature", 0.001),
        ("max_iterations", 99),
        ("time_offsets", 0),
        ("seed", -1),
        ("distance", "manhattan"),
        ("model_architecture", "offset1-model"),
    ],
)
def test_bounds(field, value):
    with pytest.raises(ValidationError) as info:
        TimeParams.model_validate({field: value})
    assert info.value.errors()[0]["loc"] == (field,)


def test_labels():
    p = BehaviourParams(continuous_labels=["signed_contrast", "wheel_velocity", "signed_contrast"])
    assert p.continuous_labels == ["signed_contrast", "wheel_velocity"]
    with pytest.raises(ValidationError):
        BehaviourParams(continuous_labels=["pupil"])
    with pytest.raises(ValidationError):
        BehaviourParams(discrete_label=["choice", "feedback"])


def test_preprocess_defaults_and_lock():
    p = PreprocessParams()
    assert p.model_dump() == {
        "bin_size_ms": 20,
        "align_event": "stimOn_times",
        "window_pre_s": 0.5,
        "window_post_s": 1.0,
        "good_units_only": True,
    }
    with pytest.raises(ValidationError):
        PreprocessParams(good_units_only=False)
    with pytest.raises(ValidationError):
        PreprocessParams(align_event="goCue_times")
    with pytest.raises(ValidationError) as info:
        PreprocessParams(bin_size_ms=100, window_pre_s=0, window_post_s=0.05)
    assert info.value.errors()[0]["ctx"] == {"field": "window_post_s"}
