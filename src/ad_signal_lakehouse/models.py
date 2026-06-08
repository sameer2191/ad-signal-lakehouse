"""Shared constants and typed structures for the lakehouse simulator."""

from __future__ import annotations

from dataclasses import dataclass


EVENT_TYPES = ("impression", "click", "conversion", "spend")
REQUIRED_FIELDS = (
    "event_id",
    "event_ts",
    "ingest_ts",
    "event_type",
    "channel",
    "campaign_id",
    "campaign_name",
    "user_id",
    "cost_usd",
    "revenue_usd",
)


@dataclass(frozen=True)
class Campaign:
    campaign_id: str
    campaign_name: str
    channel: str
    base_ctr: float
    base_cvr: float
    avg_order_value: float
    spend_weight: float


CAMPAIGNS = (
    Campaign("SEA_BRAND_US", "US Brand Search", "paid_search", 0.061, 0.072, 118.0, 1.35),
    Campaign("SEA_NONBRAND_US", "US Nonbrand Search", "paid_search", 0.038, 0.044, 96.0, 1.60),
    Campaign("SOC_RETARGET", "Paid Social Retargeting", "paid_social", 0.024, 0.058, 84.0, 1.10),
    Campaign("SOC_PROSPECT", "Paid Social Prospecting", "paid_social", 0.015, 0.021, 76.0, 1.45),
    Campaign("DSP_AWARENESS", "Programmatic Awareness", "display", 0.006, 0.008, 68.0, 0.95),
    Campaign("YT_VIDEO_TEST", "YouTube Video Test", "video", 0.011, 0.014, 73.0, 0.80),
    Campaign("AFF_DEALS", "Affiliate Deal Sites", "affiliate", 0.031, 0.067, 91.0, 0.70),
    Campaign("EMAIL_WINBACK", "Lifecycle Winback", "email", 0.047, 0.086, 102.0, 0.35),
)

CHANNELS = tuple(sorted({campaign.channel for campaign in CAMPAIGNS}))
