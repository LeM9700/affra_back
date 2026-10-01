"""Classification des sources marketing — implémentation UNIQUE du projet.

Le navigateur ne transmet que des signaux bruts (UTM, click IDs, referrer, landing page) ;
la source est toujours calculée ici, côté serveur. Le frontend ne classe rien.

Priorité :
  1. paramètres UTM explicites (utm_source / utm_medium) ;
  2. click IDs Google Ads (gclid, gbraid, wbraid) ;
  3. referrer externe (hôte) ;
  4. sinon DIRECT.

Le referrer interne (navigation sur le site lui-même) est ignoré.
"""
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit

from app.models.enums import MarketingSource as S

# Valeurs utm_source reconnues (comparaison en minuscules, sans "www.").
_GOOGLE_BUSINESS_UTM_SOURCES = {"google_business", "google_business_profile", "gbp", "gmb", "google_my_business", "google_maps"}
_GOOGLE_BUSINESS_UTM_MEDIUMS = {"organic_local", "local", "gmb", "gbp", "maps", "business_profile"}
_PAID_MEDIUMS = {"cpc", "ppc", "paid", "paidsearch", "paid_search", "sem", "ads"}

_UTM_SOURCE_MAP: dict[str, S] = {
    "bing": S.BING_ORGANIC,
    "bing.com": S.BING_ORGANIC,
    "chatgpt": S.CHATGPT,
    "chatgpt.com": S.CHATGPT,  # ajouté automatiquement par ChatGPT sur ses liens
    "chat.openai.com": S.CHATGPT,
    "openai": S.CHATGPT,
    "claude": S.CLAUDE,
    "claude.ai": S.CLAUDE,
    "anthropic": S.CLAUDE,
    "perplexity": S.PERPLEXITY,
    "perplexity.ai": S.PERPLEXITY,
    "gemini": S.GEMINI,
    "gemini.google.com": S.GEMINI,
    "bard": S.GEMINI,
}

# Referrers : l'ordre compte (gemini.google.com avant google.*).
_REFERRER_EXACT_HOSTS: dict[str, S] = {
    "gemini.google.com": S.GEMINI,
    "bard.google.com": S.GEMINI,
    "chatgpt.com": S.CHATGPT,
    "chat.openai.com": S.CHATGPT,
    "claude.ai": S.CLAUDE,
    "perplexity.ai": S.PERPLEXITY,
    "maps.google.com": S.GOOGLE_BUSINESS,
    "business.google.com": S.GOOGLE_BUSINESS,
}

_DEFAULT_MEDIUM: dict[S, str] = {
    S.GOOGLE_ORGANIC: "organic",
    S.BING_ORGANIC: "organic",
    S.GOOGLE_BUSINESS: "organic_local",
    S.GOOGLE_ADS: "cpc",
    S.CHATGPT: "ai_assistant",
    S.CLAUDE: "ai_assistant",
    S.PERPLEXITY: "ai_assistant",
    S.GEMINI: "ai_assistant",
    S.REFERRAL: "referral",
    S.DIRECT: "(none)",
    S.UNKNOWN: "(unknown)",
}

# Paramètres de requête conservés dans landing_page (tout le reste est supprimé :
# un paramètre arbitraire peut contenir des données personnelles).
KEPT_QUERY_PARAMS = ("utm_source", "utm_medium", "utm_campaign", "gclid", "gbraid", "wbraid")


@dataclass(frozen=True)
class TouchSignals:
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    referrer: str | None = None
    landing_page: str | None = None
    gclid: str | None = None
    gbraid: str | None = None
    wbraid: str | None = None


@dataclass(frozen=True)
class Classification:
    source: S
    medium: str
    campaign: str | None

    @property
    def is_direct_or_unknown(self) -> bool:
        return self.source in (S.DIRECT, S.UNKNOWN)


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _host(url: str | None) -> str | None:
    if not url:
        return None
    raw = url.strip()
    if raw.startswith("android-app://"):
        # ex. android-app://com.google.android.googlequicksearchbox/
        return raw[len("android-app://"):].split("/")[0].lower() or None
    try:
        host = urlsplit(raw).hostname
    except ValueError:
        return None
    if not host:
        return None
    host = host.lower()
    return host[4:] if host.startswith("www.") else host


def _is_google_host(host: str) -> bool:
    # google.fr, google.com, google.co.uk, news.google.com… et l'app Google Android.
    labels = host.split(".")
    return "google" in labels or host == "com.google.android.googlequicksearchbox"


def _is_internal(host: str, site_hosts: frozenset[str]) -> bool:
    return host in site_hosts


def _classify_utm(source: str, medium: str) -> S:
    if source in _GOOGLE_BUSINESS_UTM_SOURCES:
        return S.GOOGLE_BUSINESS
    if source in ("google", "google.com", "google.fr"):
        if medium in _GOOGLE_BUSINESS_UTM_MEDIUMS:
            return S.GOOGLE_BUSINESS
        if medium in _PAID_MEDIUMS:
            return S.GOOGLE_ADS
        return S.GOOGLE_ORGANIC
    # Bing Ads n'est pas distingué en V1 (aucune campagne Microsoft Ads active).
    return _UTM_SOURCE_MAP.get(source, S.REFERRAL)


def _classify_referrer_host(host: str) -> S:
    if host in _REFERRER_EXACT_HOSTS:
        return _REFERRER_EXACT_HOSTS[host]
    if host.endswith(".perplexity.ai"):
        return S.PERPLEXITY
    if host.startswith("maps.google."):
        return S.GOOGLE_BUSINESS
    if _is_google_host(host):
        return S.GOOGLE_ORGANIC
    if host == "bing.com" or host.endswith(".bing.com"):
        return S.BING_ORGANIC
    return S.REFERRAL


def classify(signals: TouchSignals, site_hosts: frozenset[str]) -> Classification:
    campaign = (signals.utm_campaign or "").strip() or None

    # 1. UTM explicites
    utm_source = _norm(signals.utm_source)
    if utm_source.startswith("www."):
        utm_source = utm_source[4:]
    if utm_source:
        source = _classify_utm(utm_source, _norm(signals.utm_medium))
        medium = _norm(signals.utm_medium) or _DEFAULT_MEDIUM[source]
        return Classification(source, medium[:100], campaign)

    # 2. Click IDs Google Ads
    if signals.gclid or signals.gbraid or signals.wbraid:
        return Classification(S.GOOGLE_ADS, _DEFAULT_MEDIUM[S.GOOGLE_ADS], campaign)

    # 3. Referrer externe
    host = _host(signals.referrer)
    if host and not _is_internal(host, site_hosts):
        source = _classify_referrer_host(host)
        return Classification(source, _DEFAULT_MEDIUM[source], campaign)

    # 4. Direct
    return Classification(S.DIRECT, _DEFAULT_MEDIUM[S.DIRECT], campaign)


def sanitize_referrer(referrer: str | None, max_length: int = 500) -> str | None:
    """Ne garde que schéma + hôte + chemin (pas de query string : peut contenir des données personnelles)."""
    if not referrer:
        return None
    raw = referrer.strip()
    if raw.startswith("android-app://"):
        return raw[:max_length]
    try:
        parts = urlsplit(raw)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    return f"{parts.scheme}://{parts.hostname.lower()}{parts.path or '/'}"[:max_length]


def sanitize_page_path(path: str | None, max_length: int = 500, keep_query: bool = True) -> str | None:
    """Chemin relatif au site (« /devis?utm_source=… »), en ne gardant que les paramètres d'attribution."""
    if not path:
        return None
    raw = path.strip()
    try:
        parts = urlsplit(raw)
    except ValueError:
        return None
    clean_path = parts.path or "/"
    if not clean_path.startswith("/") or clean_path.startswith("//"):
        return None
    query = ""
    if keep_query and parts.query:
        kept = [(k, v[:150]) for k, v in parse_qsl(parts.query) if k in KEPT_QUERY_PARAMS]
        query = urlencode(kept)
    return (clean_path + (f"?{query}" if query else ""))[:max_length]


def referrer_is_internal(referrer: str | None, site_hosts: frozenset[str]) -> bool:
    host = _host(referrer)
    return bool(host) and _is_internal(host, site_hosts)
