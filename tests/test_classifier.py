import pytest

from app.models.enums import MarketingSource as S
from app.services.attribution_classifier import (
    TouchSignals,
    classify,
    sanitize_page_path,
    sanitize_referrer,
)

SITE = frozenset({"affra-reseaux.fr", "localhost"})


def _source(**kwargs) -> S:
    return classify(TouchSignals(**kwargs), SITE).source


@pytest.mark.parametrize(
    ("referrer", "expected"),
    [
        ("https://www.google.fr/", S.GOOGLE_ORGANIC),
        ("https://www.google.com/search?q=borne+recharge", S.GOOGLE_ORGANIC),
        ("android-app://com.google.android.googlequicksearchbox/", S.GOOGLE_ORGANIC),
        ("https://maps.google.fr/", S.GOOGLE_BUSINESS),
        ("https://www.bing.com/", S.BING_ORGANIC),
        ("https://chatgpt.com/", S.CHATGPT),
        ("https://chat.openai.com/c/abc", S.CHATGPT),
        ("https://claude.ai/chat/123", S.CLAUDE),
        ("https://www.perplexity.ai/search/xyz", S.PERPLEXITY),
        ("https://gemini.google.com/app", S.GEMINI),
        ("https://www.leboncoin.fr/annonce", S.REFERRAL),
    ],
)
def test_referrer_classification(referrer, expected):
    assert _source(referrer=referrer) == expected


@pytest.mark.parametrize(
    ("utm_source", "utm_medium", "expected"),
    [
        ("google_business", "organic_local", S.GOOGLE_BUSINESS),
        ("google", "organic_local", S.GOOGLE_BUSINESS),
        ("google", "cpc", S.GOOGLE_ADS),
        ("google", "organic", S.GOOGLE_ORGANIC),
        ("chatgpt.com", None, S.CHATGPT),
        ("perplexity", "referral", S.PERPLEXITY),
        ("bing", "organic", S.BING_ORGANIC),
        ("claude.ai", None, S.CLAUDE),
        ("gemini", None, S.GEMINI),
        ("newsletter", "email", S.REFERRAL),
    ],
)
def test_utm_classification(utm_source, utm_medium, expected):
    assert _source(utm_source=utm_source, utm_medium=utm_medium) == expected


def test_google_business_recommended_url_medium():
    result = classify(TouchSignals(utm_source="google_business", utm_medium="organic_local"), SITE)
    assert result.source == S.GOOGLE_BUSINESS
    assert result.medium == "organic_local"


def test_utm_takes_priority_over_referrer():
    assert _source(utm_source="google_business", utm_medium="organic_local", referrer="https://chatgpt.com/") == S.GOOGLE_BUSINESS


def test_click_id_takes_priority_over_referrer():
    assert _source(gclid="Cj0KCQ-abc", referrer="https://www.google.fr/") == S.GOOGLE_ADS
    assert _source(gbraid="0AAAA-x") == S.GOOGLE_ADS


def test_direct_without_signals():
    result = classify(TouchSignals(landing_page="/"), SITE)
    assert result.source == S.DIRECT
    assert result.is_direct_or_unknown


def test_internal_referrer_is_direct():
    assert _source(referrer="https://www.affra-reseaux.fr/offres") == S.DIRECT


def test_campaign_is_kept():
    assert classify(TouchSignals(utm_source="google", utm_medium="cpc", utm_campaign="irve-34"), SITE).campaign == "irve-34"


def test_sanitize_referrer_drops_query_string():
    assert sanitize_referrer("https://www.google.com/search?q=jean+dupont") == "https://www.google.com/search"
    assert sanitize_referrer("javascript:alert(1)") is None


def test_sanitize_page_path_keeps_only_attribution_params():
    assert (
        sanitize_page_path("/devis?utm_source=google_business&email=x@y.fr&utm_medium=organic_local")
        == "/devis?utm_source=google_business&utm_medium=organic_local"
    )
    assert sanitize_page_path("https://evil.example/x") == "/x"  # l'hôte n'est jamais conservé
    assert sanitize_page_path("//evil.example/path") == "/path"
    assert sanitize_page_path("javascript:alert(1)") is None
    assert sanitize_page_path("/offres", keep_query=False) == "/offres"
