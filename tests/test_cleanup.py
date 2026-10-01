from sqlalchemy import func, select, text

from app.jobs.cleanup import purge_expired_data
from app.models.lead import Lead
from tests.helpers import invoice_payload, lead_id_for_email, new_vid, submit_devis, visit


async def test_rgpd_purge_keeps_customers_and_recent_data(client, admin_client, session):
    await submit_devis(client, email="old-prospect@example.com")
    await submit_devis(client, email="old-customer@example.com")
    vid = new_vid()
    await visit(client, vid, referrer="https://www.google.fr/")
    await submit_devis(client, vid, email="recent@example.com")
    customer_lead = await lead_id_for_email(admin_client, "old-customer@example.com")
    assert (await admin_client.post(f"/internal/leads/{customer_lead}/invoices", json=invoice_payload(120_000))).status_code == 201

    await session.execute(
        text(
            "UPDATE leads SET created_at = now() - interval '400 days', updated_at = now() - interval '400 days' "
            "WHERE email IN ('old-prospect@example.com', 'old-customer@example.com')"
        )
    )
    await session.execute(
        text("UPDATE devis SET created_at = now() - interval '400 days' WHERE email LIKE 'old-%'")
    )
    await session.commit()

    counts = await purge_expired_data(session)
    await session.commit()

    assert counts["devis"] == 2
    assert counts["leads"] == 1  # le lead devenu client est conservé
    emails = set((await session.execute(select(Lead.email))).scalars())
    assert emails == {"old-customer@example.com", "recent@example.com"}
    assert (await session.execute(select(func.count()).select_from(Lead))).scalar_one() == 2
