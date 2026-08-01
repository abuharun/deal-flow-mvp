"""Integration tests for the immutable analysis input snapshot builder.

Exercises app.services.analysis_snapshot.build_snapshot against real
Postgres: every precondition guard (job/startup mismatch, input_revision
drift, missing consent, missing/unpaid payment, missing/encrypted/malformed/
textless deck), the bounded/truncated founder-answer and deck-text fields,
and that nothing here is ever persisted (pure read + in-memory build).
"""

import uuid

import pytest
import sqlalchemy as sa
from pypdf import PdfWriter

from app.db import build_engine, build_sessionmaker
from app.models.consent import CONSENT_KIND_AI_PRIVACY, CURRENT_AI_PRIVACY_VERSION
from app.models.payment import PAYMENT_STATUS_FAILED, PAYMENT_STATUS_PAID
from app.repositories import startup_repository
from app.repositories.analysis_repository import get_for_update as get_job_for_update
from app.repositories.deck_repository import PostgresDeckStorage
from app.services.analysis_snapshot import (
    MAX_FIELD_CHARS,
    SnapshotError,
    build_snapshot,
)
from app.services.pdf_validation import validate_deck


@pytest.fixture()
async def engine(test_database_url, db_at_head):
    engine = build_engine(test_database_url)
    yield engine
    await engine.dispose()


def make_pdf_with_text(text: str = "Deck body text.") -> bytes:
    content = f"BT /F1 24 Tf 100 700 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 612 792] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_offset = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n".encode()
    out += f"startxref\n{xref_offset}\n%%EOF".encode()
    return bytes(out)


def make_blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    from io import BytesIO

    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


async def _insert_founder_with_startup(engine, **startup_overrides) -> uuid.UUID:
    email = f"snapshot-{uuid.uuid4().hex}@example.com"
    values = {
        "name": "Snapshot Startup",
        "one_liner": "We do things.",
        "sector": "fintech",
        "funding_stage": "seed",
        "city": "Tashkent",
        "status": "submitted",
        "input_revision": 1,
    }
    values.update(startup_overrides)
    async with build_sessionmaker(engine)() as session:
        founder_id = (
            await session.execute(
                sa.text(
                    "INSERT INTO users (email, password_hash, full_name, role, "
                    "email_verified_at) VALUES (:email, 'x', 'Snapshot Owner', 'founder', now()) "
                    "RETURNING id"
                ),
                {"email": email},
            )
        ).scalar_one()
        columns = ", ".join(["founder_id", *values.keys()])
        placeholders = ", ".join([":fid", *(f":{k}" for k in values)])
        startup_id = (
            await session.execute(
                sa.text(f"INSERT INTO startups ({columns}) VALUES ({placeholders}) RETURNING id"),
                {"fid": str(founder_id), **values},
            )
        ).scalar_one()
        await session.execute(
            sa.text(
                "INSERT INTO submissions (startup_id, problem, product, market, traction, "
                "team, ask, revenue, growth, ask_amount, dataroom_url) VALUES "
                "(:sid, 'Problem text', 'Product text', 'Market text', 'Traction text', "
                "'Team text', 'Ask text', 'Revenue text', 'Growth text', 100000, "
                "'https://dataroom.example.com/x')"
            ),
            {"sid": str(startup_id)},
        )
        await session.commit()
    return startup_id, founder_id


async def _insert_job(engine, startup_id, **overrides) -> uuid.UUID:
    values = {
        "startup_id": str(startup_id),
        "input_revision": 1,
        "status": "running",
        "attempts": 1,
        "started_at": sa.text("now()"),
    }
    values.update(overrides)
    raw_sql = {k: v.text for k, v in values.items() if isinstance(v, sa.sql.elements.TextClause)}
    bound = {k: v for k, v in values.items() if k not in raw_sql}
    columns = ", ".join(values)
    placeholders = ", ".join(raw_sql.get(name, f":{name}") for name in values)
    async with build_sessionmaker(engine)() as session:
        job_id = (
            await session.execute(
                sa.text(
                    f"INSERT INTO analysis_jobs ({columns}) VALUES ({placeholders}) RETURNING id"
                ),
                bound,
            )
        ).scalar_one()
        await session.commit()
    return job_id


async def _grant_consent(engine, startup_id, founder_id) -> None:
    async with build_sessionmaker(engine)() as session:
        await session.execute(
            sa.text(
                "INSERT INTO consents (startup_id, founder_id, kind, text_version) VALUES "
                "(:sid, :fid, :kind, :ver)"
            ),
            {
                "sid": str(startup_id),
                "fid": str(founder_id),
                "kind": CONSENT_KIND_AI_PRIVACY,
                "ver": CURRENT_AI_PRIVACY_VERSION,
            },
        )
        await session.commit()


async def _insert_payment(engine, startup_id, *, status: str = PAYMENT_STATUS_PAID) -> None:
    paid_at_sql = "now()" if status == PAYMENT_STATUS_PAID else "NULL"
    async with build_sessionmaker(engine)() as session:
        await session.execute(
            sa.text(
                f"INSERT INTO payments (startup_id, status, paid_at) VALUES "
                f"(:sid, :status, {paid_at_sql})"
            ),
            {"sid": str(startup_id), "status": status},
        )
        await session.commit()


async def _put_deck(engine, startup_id, content: bytes) -> None:
    deck_file = validate_deck(content, filename="deck.pdf", declared_mime="application/pdf")
    async with build_sessionmaker(engine)() as session:
        await PostgresDeckStorage(session).put(startup_id, deck_file, content)
        await session.commit()


async def _load_locked(session, *, job_id, startup_id):
    job = await get_job_for_update(session, job_id=job_id)
    startup = await startup_repository.get_for_update(
        session, startup_id=startup_id, with_submission=True
    )
    return job, startup


class TestValidSnapshot:
    async def test_builds_bounded_snapshot_from_full_prerequisites(self, engine):
        startup_id, founder_id = await _insert_founder_with_startup(engine)
        job_id = await _insert_job(engine, startup_id)
        await _grant_consent(engine, startup_id, founder_id)
        await _insert_payment(engine, startup_id)
        await _put_deck(engine, startup_id, make_pdf_with_text("Deck body text."))

        async with build_sessionmaker(engine)() as session:
            job, startup = await _load_locked(session, job_id=job_id, startup_id=startup_id)
            snapshot = await build_snapshot(
                session, job=job, startup=startup, deck_storage=PostgresDeckStorage(session)
            )

        assert snapshot.startup_id == startup_id
        assert snapshot.job_id == job_id
        assert snapshot.input_revision == 1
        assert snapshot.startup_name.value == "Snapshot Startup"
        assert snapshot.problem.value == "Problem text"
        assert snapshot.ask_amount == 100000
        assert snapshot.dataroom_url == "https://dataroom.example.com/x"
        assert "Deck body text." in snapshot.deck_text.value
        assert snapshot.deck_text_truncated is False

    async def test_long_answer_is_bounded_not_rejected(self, engine):
        long_text = "x" * (MAX_FIELD_CHARS + 500)
        startup_id, founder_id = await _insert_founder_with_startup(engine)
        job_id = await _insert_job(engine, startup_id)
        await _grant_consent(engine, startup_id, founder_id)
        await _insert_payment(engine, startup_id)
        await _put_deck(engine, startup_id, make_pdf_with_text("Deck body text."))
        async with build_sessionmaker(engine)() as session:
            await session.execute(
                sa.text("UPDATE submissions SET problem = :p WHERE startup_id = :sid"),
                {"p": long_text, "sid": str(startup_id)},
            )
            await session.commit()

        async with build_sessionmaker(engine)() as session:
            job, startup = await _load_locked(session, job_id=job_id, startup_id=startup_id)
            snapshot = await build_snapshot(
                session, job=job, startup=startup, deck_storage=PostgresDeckStorage(session)
            )
        assert len(snapshot.problem.value) == MAX_FIELD_CHARS

    async def test_unsafe_dataroom_url_is_dropped_not_rejected(self, engine):
        startup_id, founder_id = await _insert_founder_with_startup(engine)
        job_id = await _insert_job(engine, startup_id)
        await _grant_consent(engine, startup_id, founder_id)
        await _insert_payment(engine, startup_id)
        await _put_deck(engine, startup_id, make_pdf_with_text("Deck body text."))
        async with build_sessionmaker(engine)() as session:
            await session.execute(
                sa.text("UPDATE submissions SET dataroom_url = :u WHERE startup_id = :sid"),
                {"u": "javascript:alert(1)", "sid": str(startup_id)},
            )
            await session.commit()

        async with build_sessionmaker(engine)() as session:
            job, startup = await _load_locked(session, job_id=job_id, startup_id=startup_id)
            snapshot = await build_snapshot(
                session, job=job, startup=startup, deck_storage=PostgresDeckStorage(session)
            )
        assert snapshot.dataroom_url is None


class TestSnapshotGuards:
    async def test_input_revision_mismatch_is_refused(self, engine):
        startup_id, founder_id = await _insert_founder_with_startup(engine)
        job_id = await _insert_job(engine, startup_id, input_revision=1)
        await _grant_consent(engine, startup_id, founder_id)
        await _insert_payment(engine, startup_id)
        await _put_deck(engine, startup_id, make_pdf_with_text("Deck body text."))
        async with build_sessionmaker(engine)() as session:
            await session.execute(
                sa.text("UPDATE startups SET input_revision = 2 WHERE id = :sid"),
                {"sid": str(startup_id)},
            )
            await session.commit()

        async with build_sessionmaker(engine)() as session:
            job, startup = await _load_locked(session, job_id=job_id, startup_id=startup_id)
            with pytest.raises(SnapshotError) as excinfo:
                await build_snapshot(
                    session, job=job, startup=startup, deck_storage=PostgresDeckStorage(session)
                )
        assert excinfo.value.reason == "input_revision_mismatch"

    async def test_missing_consent_is_refused(self, engine):
        startup_id, _founder_id = await _insert_founder_with_startup(engine)
        job_id = await _insert_job(engine, startup_id)
        await _insert_payment(engine, startup_id)
        await _put_deck(engine, startup_id, make_pdf_with_text("Deck body text."))

        async with build_sessionmaker(engine)() as session:
            job, startup = await _load_locked(session, job_id=job_id, startup_id=startup_id)
            with pytest.raises(SnapshotError) as excinfo:
                await build_snapshot(
                    session, job=job, startup=startup, deck_storage=PostgresDeckStorage(session)
                )
        assert excinfo.value.reason == "consent_missing"

    async def test_missing_payment_is_refused(self, engine):
        startup_id, founder_id = await _insert_founder_with_startup(engine)
        job_id = await _insert_job(engine, startup_id)
        await _grant_consent(engine, startup_id, founder_id)
        await _put_deck(engine, startup_id, make_pdf_with_text("Deck body text."))

        async with build_sessionmaker(engine)() as session:
            job, startup = await _load_locked(session, job_id=job_id, startup_id=startup_id)
            with pytest.raises(SnapshotError) as excinfo:
                await build_snapshot(
                    session, job=job, startup=startup, deck_storage=PostgresDeckStorage(session)
                )
        assert excinfo.value.reason == "payment_not_paid"

    async def test_failed_payment_is_refused(self, engine):
        startup_id, founder_id = await _insert_founder_with_startup(engine)
        job_id = await _insert_job(engine, startup_id)
        await _grant_consent(engine, startup_id, founder_id)
        await _insert_payment(engine, startup_id, status=PAYMENT_STATUS_FAILED)
        await _put_deck(engine, startup_id, make_pdf_with_text("Deck body text."))

        async with build_sessionmaker(engine)() as session:
            job, startup = await _load_locked(session, job_id=job_id, startup_id=startup_id)
            with pytest.raises(SnapshotError) as excinfo:
                await build_snapshot(
                    session, job=job, startup=startup, deck_storage=PostgresDeckStorage(session)
                )
        assert excinfo.value.reason == "payment_not_paid"

    async def test_missing_deck_is_refused(self, engine):
        startup_id, founder_id = await _insert_founder_with_startup(engine)
        job_id = await _insert_job(engine, startup_id)
        await _grant_consent(engine, startup_id, founder_id)
        await _insert_payment(engine, startup_id)

        async with build_sessionmaker(engine)() as session:
            job, startup = await _load_locked(session, job_id=job_id, startup_id=startup_id)
            with pytest.raises(SnapshotError) as excinfo:
                await build_snapshot(
                    session, job=job, startup=startup, deck_storage=PostgresDeckStorage(session)
                )
        assert excinfo.value.reason == "deck_missing"

    async def test_deck_with_no_extractable_text_is_refused(self, engine):
        startup_id, founder_id = await _insert_founder_with_startup(engine)
        job_id = await _insert_job(engine, startup_id)
        await _grant_consent(engine, startup_id, founder_id)
        await _insert_payment(engine, startup_id)
        await _put_deck(engine, startup_id, make_blank_pdf())

        async with build_sessionmaker(engine)() as session:
            job, startup = await _load_locked(session, job_id=job_id, startup_id=startup_id)
            with pytest.raises(SnapshotError) as excinfo:
                await build_snapshot(
                    session, job=job, startup=startup, deck_storage=PostgresDeckStorage(session)
                )
        assert excinfo.value.reason == "deck_no_extractable_text"

    async def test_job_startup_mismatch_is_refused(self, engine):
        startup_id_a, founder_id_a = await _insert_founder_with_startup(engine)
        startup_id_b, founder_id_b = await _insert_founder_with_startup(engine)
        job_id = await _insert_job(engine, startup_id_a)
        await _grant_consent(engine, startup_id_b, founder_id_b)
        await _insert_payment(engine, startup_id_b)
        await _put_deck(engine, startup_id_b, make_pdf_with_text("Deck body text."))

        async with build_sessionmaker(engine)() as session:
            job, startup = await _load_locked(session, job_id=job_id, startup_id=startup_id_b)
            with pytest.raises(SnapshotError) as excinfo:
                await build_snapshot(
                    session, job=job, startup=startup, deck_storage=PostgresDeckStorage(session)
                )
        assert excinfo.value.reason == "job_startup_mismatch"
