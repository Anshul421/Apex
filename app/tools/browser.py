from __future__ import annotations

from datetime import datetime, timezone

from app.domain import WebFact
from app.storage.repository import AthleteRepository


ALLOWED_WEB_FACT_FIELDS = {'facility_open', 'slot_available', 'venue_notice', 'fixture_time'}


class UntrustedWebPolicyError(ValueError):
    pass


class SandboxWebReader:
    """Converts untrusted environment content into a narrow fact schema.

    Raw page text is never promoted to executable instructions. This makes the
    security boundary visible even before a real Playwright adapter is connected.
    """

    def __init__(self, repo: AthleteRepository):
        self.repo = repo

    def facility_slot_fact(self, athlete_id: str, facility: str, start_time: datetime, plan_id: str | None = None) -> WebFact:
        slot = self.repo.facility_slot(facility, start_time)
        value = bool(slot and slot.available)
        fact = WebFact(
            field='slot_available',
            value={'facility': facility, 'start_time': start_time.isoformat(), 'available': value},
            source_url=f'sandbox://facilities/{facility}',
            retrieved_at=datetime.now(timezone.utc),
            provenance={'extractor': 'sandbox_structured_reader', 'trust': 'untrusted_evidence'},
        )
        self.repo.add_web_evidence(
            athlete_id=athlete_id,
            plan_id=plan_id,
            url=fact.source_url,
            retrieved_at=fact.retrieved_at,
            field=fact.field,
            value=fact.value,
            provenance=fact.provenance,
        )
        return fact

    @staticmethod
    def normalize_external_fact(field: str, value, source_url: str) -> WebFact:
        if field not in ALLOWED_WEB_FACT_FIELDS:
            raise UntrustedWebPolicyError(f'Web field {field!r} is not allow-listed')
        return WebFact(
            field=field,
            value=value,
            source_url=source_url,
            retrieved_at=datetime.now(timezone.utc),
            provenance={'trust': 'untrusted_evidence'},
        )


class PlaywrightWebReader:
    """Optional real-browser adapter.

    The dependency is intentionally optional for the first backend slice. When enabled,
    extraction must still return WebFact objects; raw page instructions never become policy.
    """

    async def extract_fact(self, *, url: str, field: str) -> WebFact:
        if field not in ALLOWED_WEB_FACT_FIELDS:
            raise UntrustedWebPolicyError(f'Web field {field!r} is not allow-listed')
        try:
            from playwright.async_api import async_playwright  # type: ignore
        except ImportError as exc:
            raise RuntimeError('Install playwright and its browser runtime to use the real browser adapter') from exc

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until='domcontentloaded')
            # Intentionally return a bounded structural observation. A domain-specific
            # extractor should replace this generic text check for real facilities.
            text = (await page.locator('body').inner_text())[:4000]
            await browser.close()
        return WebFact(
            field=field,
            value={'observed_text': text},
            source_url=url,
            retrieved_at=datetime.now(timezone.utc),
            provenance={'extractor': 'playwright', 'trust': 'untrusted_evidence'},
        )
