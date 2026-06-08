"""Deterministic synthetic ad event generation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import random
from typing import Any

from .models import CAMPAIGNS


DEFAULT_BASE_TIME = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _weighted_campaign(rng: random.Random):
    total = sum(campaign.spend_weight for campaign in CAMPAIGNS)
    target = rng.random() * total
    running = 0.0
    for campaign in CAMPAIGNS:
        running += campaign.spend_weight
        if running >= target:
            return campaign
    return CAMPAIGNS[-1]


def _choose_event_type(rng: random.Random, campaign) -> str:
    click_probability = min(max(campaign.base_ctr * 4.0, 0.04), 0.22)
    conversion_probability = min(max(campaign.base_cvr * 0.85, 0.006), 0.075)
    spend_probability = 0.085
    draw = rng.random()
    if draw < spend_probability:
        return "spend"
    if draw < spend_probability + conversion_probability:
        return "conversion"
    if draw < spend_probability + conversion_probability + click_probability:
        return "click"
    return "impression"


def _cost_for_event(rng: random.Random, event_type: str, campaign) -> float:
    if event_type != "spend":
        return 0.0
    channel_floor = {
        "paid_search": 4.4,
        "paid_social": 2.9,
        "display": 1.2,
        "video": 1.6,
        "affiliate": 0.9,
        "email": 0.25,
    }[campaign.channel]
    return round(channel_floor * campaign.spend_weight * rng.uniform(0.45, 2.65), 2)


def _revenue_for_event(rng: random.Random, event_type: str, campaign) -> float:
    if event_type != "conversion":
        return 0.0
    return round(campaign.avg_order_value * rng.uniform(0.55, 1.95), 2)


def generate_events(
    count: int,
    seed: int = 42,
    base_time: datetime = DEFAULT_BASE_TIME,
    inject_failures: bool = True,
) -> list[dict[str, Any]]:
    """Return deterministic synthetic ad events.

    The generated stream intentionally includes operational edge cases when
    ``inject_failures`` is true: a duplicate event id, one negative spend row, a
    late event, and one schema violation for reasonably sized datasets.
    """

    if count < 0:
        raise ValueError("count must be non-negative")

    rng = random.Random(seed)
    events: list[dict[str, Any]] = []
    devices = ("desktop", "mobile", "tablet")
    geos = ("US-CA", "US-NY", "US-TX", "US-FL", "US-WA", "US-IL", "US-GA")
    placements = ("search_top", "feed", "story", "pre_roll", "partner_site", "newsletter")

    for index in range(count):
        campaign = _weighted_campaign(rng)
        event_type = _choose_event_type(rng, campaign)
        event_ts = base_time - timedelta(
            minutes=rng.randint(0, 7 * 24 * 60),
            seconds=rng.randint(0, 59),
        )
        ingest_ts = event_ts + timedelta(minutes=rng.randint(1, 90), seconds=rng.randint(0, 59))
        cost_usd = _cost_for_event(rng, event_type, campaign)
        revenue_usd = _revenue_for_event(rng, event_type, campaign)

        events.append(
            {
                "event_id": f"evt_{seed}_{index:08d}",
                "event_ts": _iso(event_ts),
                "ingest_ts": _iso(ingest_ts),
                "event_type": event_type,
                "channel": campaign.channel,
                "campaign_id": campaign.campaign_id,
                "campaign_name": campaign.campaign_name,
                "user_id": f"user_{rng.randint(10000, 99999)}",
                "device": rng.choice(devices),
                "geo": rng.choice(geos),
                "placement": rng.choice(placements),
                "cost_usd": cost_usd,
                "revenue_usd": revenue_usd,
                "source": "synthetic_ad_platform",
            }
        )

    if inject_failures:
        _inject_known_failure_modes(events)

    return events


def _inject_known_failure_modes(events: list[dict[str, Any]]) -> None:
    if len(events) >= 8:
        events[7]["event_id"] = events[2]["event_id"]

    if len(events) >= 16:
        events[15]["event_type"] = "spend"
        events[15]["cost_usd"] = -7.25
        events[15]["revenue_usd"] = 0.0

    if len(events) >= 24:
        event_ts = _parse_utc(events[23]["event_ts"])
        events[23]["ingest_ts"] = _iso(event_ts + timedelta(hours=72, minutes=4))

    if len(events) >= 32:
        events[31].pop("campaign_id", None)


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
