"""Request/response contracts for the founder demo payment endpoint.

Every response explicitly carries mode='demo': nothing here may ever be
read as confirmation that a real charge occurred. There is deliberately no
amount/currency/provider field — this is an honest stub, not a gateway.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class PaymentSimulateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulate_outcome: Literal["paid", "failed"]


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mode: str
    status: str
    label: str
    paid_at: datetime | None
    created_at: datetime
    updated_at: datetime
