"""Preprocessing parameters, shown in the New run form and stored in `runs.preprocess`."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

AlignEvent = Literal["stimOn_times", "firstMovement_times", "feedback_times"]


class PreprocessParams(BaseModel):
    """Binning of good units' spike times around one trial event."""

    model_config = ConfigDict(extra="forbid")

    bin_size_ms: int = Field(
        20, ge=1, le=1000, title="Bin size (ms)", description="Width of one time bin."
    )
    align_event: AlignEvent = Field(
        "stimOn_times",
        title="Align event",
        description="Trial event the window is centred on.",
    )
    window_pre_s: float = Field(
        0.5, ge=0, le=10, title="Window before (s)", description="Seconds before the event."
    )
    window_post_s: float = Field(
        1.0, ge=0, le=10, title="Window after (s)", description="Seconds after the event."
    )
    # Locked in v0: `Literal[True]` makes the schema `const: true`, so the form shows it
    # checked and disabled, and the API rejects `false`.
    good_units_only: Literal[True] = Field(
        True,
        title="Good units only",
        description="IBL cluster label == 1. Locked in v0.",
        json_schema_extra={"readOnly": True},
    )

    @model_validator(mode="after")
    def _window_holds_a_bin(self) -> PreprocessParams:
        if (self.window_pre_s + self.window_post_s) * 1000 < self.bin_size_ms:
            raise PydanticCustomError(
                "window_too_short",
                "The window must be at least one bin long",
                {"field": "window_post_s"},
            )
        return self
