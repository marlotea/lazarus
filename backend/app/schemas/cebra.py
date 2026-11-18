"""CEBRA parameter models, one per mode.

`CebraParams` holds the fields every mode shares. Each mode subclasses it and pins the CEBRA
arguments that define the mode (`conditional`, `hybrid`) as class constants, so they are not
model fields: they never appear in the JSON Schema the form is built from, are never stored
in `runs.params`, and a client cannot send them (`extra="forbid"`). `cebra_kwargs()` adds
them back when the worker builds `cebra.CEBRA(...)`.

Field `title`, `description`, defaults and bounds are what the New run form shows. Fields
with `"x-group": "labels"` in their schema go in the form's Behaviour labels section; all
others go in Model and training.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

Mode = Literal["time", "behaviour", "hybrid"]
ModelArchitecture = Literal["offset10-model", "offset5-model", "offset36-model"]
Distance = Literal["cosine", "euclidean"]
ContinuousLabel = Literal["wheel_velocity", "signed_contrast"]
DiscreteLabel = Literal["choice", "feedback"]

LABELS_GROUP = {"x-group": "labels"}

# Params fields that are not `cebra.CEBRA(...)` arguments.
_NOT_CEBRA_KWARGS = {"seed", "continuous_labels", "discrete_label"}


class CebraParams(BaseModel):
    """Fields shared by every mode."""

    model_config = ConfigDict(extra="forbid")

    conditional: ClassVar[str]
    hybrid: ClassVar[bool] = False

    model_architecture: ModelArchitecture = Field(
        "offset10-model",
        title="Model architecture",
        description="CEBRA encoder. The number is its receptive field in time bins.",
    )
    output_dimension: int = Field(
        8, ge=2, le=64, title="Output dimension", description="Size of the embedding."
    )
    batch_size: int = Field(
        512,
        ge=64,
        le=4096,
        title="Batch size",
        description="Samples per training step. Each group needs at least this many bins.",
    )
    learning_rate: float = Field(
        3e-4, ge=1e-6, le=1e-1, title="Learning rate", description="Adam optimiser step size."
    )
    temperature: float = Field(
        1.0,
        ge=0.01,
        le=10,
        title="Temperature",
        description="Scales the InfoNCE similarities. Lower gives sharper contrasts.",
    )
    max_iterations: int = Field(
        5000, ge=100, le=100_000, title="Max iterations", description="Training steps."
    )
    distance: Distance = Field(
        "cosine", title="Distance", description="Similarity measure in the embedding space."
    )
    time_offsets: int = Field(
        10,
        ge=1,
        le=100,
        title="Time offsets",
        description="How many bins apart the positive sample is drawn in time.",
    )
    # Upper bound: np.random.seed only takes 32-bit seeds.
    seed: int = Field(
        0,
        ge=0,
        le=2**32 - 1,
        title="Seed",
        description="Random seed for model initialisation and sampling.",
    )

    def cebra_kwargs(self) -> dict[str, Any]:
        """Keyword arguments for `cebra.CEBRA`, including the mode's hidden fields.
        Device and verbosity are left to the caller."""
        kwargs = self.model_dump(exclude=_NOT_CEBRA_KWARGS)
        kwargs["conditional"] = self.conditional
        if self.hybrid:
            kwargs["hybrid"] = True
        return kwargs


class TimeParams(CebraParams):
    """Self-supervised: uses time only, no behaviour labels."""

    conditional: ClassVar[str] = "time"


class LabelledParams(CebraParams):
    """Shared by the modes that learn from behaviour labels."""

    conditional: ClassVar[str] = "time_delta"

    continuous_labels: list[ContinuousLabel] = Field(
        ["wheel_velocity"],
        title="Continuous labels",
        description="Behaviour variables used as continuous labels.",
        json_schema_extra=LABELS_GROUP,
    )
    # CEBRA accepts at most one discrete label, so this is a single value.
    discrete_label: DiscreteLabel | None = Field(
        None,
        title="Discrete label",
        description="At most one; CEBRA takes a single discrete label.",
        json_schema_extra=LABELS_GROUP,
    )

    @field_validator("continuous_labels")
    @classmethod
    def _dedupe(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(v))

    @model_validator(mode="after")
    def _needs_a_label(self) -> LabelledParams:
        if not self.continuous_labels and self.discrete_label is None:
            # `ctx.field` tells the API which form field to attach this model-level error to.
            raise PydanticCustomError(
                "labels_required",
                "Pick at least one behaviour label",
                {"field": "continuous_labels"},
            )
        return self


class BehaviourParams(LabelledParams):
    """Supervised by the behaviour labels."""


class HybridParams(LabelledParams):
    """Learns from both time and behaviour labels."""

    hybrid: ClassVar[bool] = True

    @model_validator(mode="after")
    def _no_discrete_label(self) -> HybridParams:
        # cebra 0.6.1's sklearn API raises NotImplementedError for hybrid training with any
        # discrete label ("Invalid index combination"), so reject it here instead of failing
        # the run after preprocessing.
        if self.discrete_label is not None:
            raise PydanticCustomError(
                "hybrid_discrete_unsupported",
                "Hybrid mode cannot use a discrete label (CEBRA does not support it)",
                {"field": "discrete_label"},
            )
        return self


PARAMS_BY_MODE: dict[str, type[CebraParams]] = {
    "time": TimeParams,
    "behaviour": BehaviourParams,
    "hybrid": HybridParams,
}

JsonSchema = dict[str, Any]


class CebraModeSchemas(BaseModel):
    time: JsonSchema
    behaviour: JsonSchema
    hybrid: JsonSchema


class CebraSchema(BaseModel):
    """JSON Schema of each mode's params and of the preprocessing params. Property order is
    the order the form and the runs table use."""

    modes: CebraModeSchemas
    preprocess: JsonSchema
