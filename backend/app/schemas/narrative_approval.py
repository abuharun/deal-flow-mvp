"""Request/response contracts for founder approval of the pitch narrative.

Approving is an explicit, deliberate act, so the request names the exact
version the founder is looking at rather than "whatever is current now": a
second tab that saved an edit in between must make the approval fail loudly,
never silently freeze text the founder never read. The version number is the
only field a client may send -- who approved it and when are server-assigned.

The response is a full projection of what was frozen, including the approved
text itself: the founder must be able to see exactly what an investor will
eventually read, without a second request. It also reports the startup's
resulting locked state (`status`/`vc_visible_at`).

Deliberately absent: any recipient, audience, or delivery field. Approval
freezes the narrative and makes the startup VC-visible; who sees it and when
it is sent is future work.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import StartupStatus
from app.schemas.narrative import NarrativeSource

# The version column is a 32-bit integer; bounding the request here turns an
# absurd number into the canonical 422 instead of a database-level error.
MAX_VERSION_NUMBER = 2**31 - 1


class NarrativeApprovalRequest(BaseModel):
    """The exact narrative version the founder means to approve.

    `extra="forbid"`: approval timestamps, the approving founder, and the
    resulting startup state are server-assigned, and a client that tries to
    supply them gets the canonical 422 rather than a silently ignored field.
    """

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1, le=MAX_VERSION_NUMBER)


class NarrativeApprovalResponse(BaseModel):
    """The frozen narrative: which version, its exact text, and the lock.

    `version`/`content`/`source`/`report_id`/`input_revision` describe the
    immutable version that was approved -- it stays retrievable and unchanged
    no matter how much history precedes it. `status`/`vc_visible_at` report
    the startup state the approval produced.
    """

    model_config = ConfigDict(from_attributes=True)

    startup_id: uuid.UUID
    narrative_version_id: uuid.UUID
    version: int
    content: str
    source: NarrativeSource
    report_id: uuid.UUID
    input_revision: int
    approved_by: uuid.UUID
    approved_at: datetime
    status: StartupStatus
    vc_visible_at: datetime
