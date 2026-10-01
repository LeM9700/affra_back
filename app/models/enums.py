"""Valeurs métier de l'attribution et de la facturation.

Stockées en VARCHAR + CHECK constraint (convention du projet : pas d'enum SQL natif,
cf. migration 0003). Les migrations recopient ces valeurs en dur : toute nouvelle valeur
exige une nouvelle migration qui met à jour la CHECK correspondante.
"""
from enum import StrEnum


class MarketingSource(StrEnum):
    GOOGLE_ORGANIC = "GOOGLE_ORGANIC"
    GOOGLE_BUSINESS = "GOOGLE_BUSINESS"
    GOOGLE_ADS = "GOOGLE_ADS"
    BING_ORGANIC = "BING_ORGANIC"
    CHATGPT = "CHATGPT"
    CLAUDE = "CLAUDE"
    PERPLEXITY = "PERPLEXITY"
    GEMINI = "GEMINI"
    REFERRAL = "REFERRAL"
    DIRECT = "DIRECT"
    UNKNOWN = "UNKNOWN"


# Sources considérées comme issues d'un travail d'acquisition digitale identifiable.
DIGITAL_SOURCES: frozenset[MarketingSource] = frozenset(
    s for s in MarketingSource if s not in (MarketingSource.DIRECT, MarketingSource.UNKNOWN)
)


class EventType(StrEnum):
    LANDING = "LANDING"
    QUOTE_STARTED = "QUOTE_STARTED"
    QUOTE_SUBMITTED = "QUOTE_SUBMITTED"
    PHONE_CLICK = "PHONE_CLICK"
    EMAIL_CLICK = "EMAIL_CLICK"
    WHATSAPP_CLICK = "WHATSAPP_CLICK"
    # Réservé au futur call tracking (V2) — jamais accepté depuis l'endpoint public.
    PHONE_CALL = "PHONE_CALL"


# Événements que le navigateur a le droit d'émettre via POST /api/v1/attribution/event.
# LANDING passe par /visit ; QUOTE_SUBMITTED est généré côté serveur par create_devis ;
# PHONE_CALL proviendra d'un fournisseur de call tracking.
CLIENT_EVENT_TYPES: frozenset[EventType] = frozenset(
    {EventType.QUOTE_STARTED, EventType.PHONE_CLICK, EventType.EMAIL_CLICK, EventType.WHATSAPP_CLICK}
)


class FinancialAttribution(StrEnum):
    AFFRA_DIGITAL = "AFFRA_DIGITAL"
    NON_AFFRA = "NON_AFFRA"
    DISPUTED = "DISPUTED"  # à arbitrer / contesté — aucune commission


class AttributionConfidence(StrEnum):
    VERIFIED = "VERIFIED"    # preuve vérifiée manuellement (ou call tracking V2)
    SUPPORTED = "SUPPORTED"  # parcours digital enregistré côté serveur (cookie affra_vid)
    DECLARED = "DECLARED"    # déclaration du prospect (« je vous ai trouvé sur Google »)
    UNKNOWN = "UNKNOWN"


class LeadChannel(StrEnum):
    FORM = "FORM"
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    OTHER = "OTHER"


class LeadStatus(StrEnum):
    NOUVEAU = "nouveau"
    EN_COURS = "en_cours"
    CLIENT = "client"
    PERDU = "perdu"


class CommissionStatus(StrEnum):
    DUE = "DUE"
    PAID = "PAID"
    NOT_DUE = "NOT_DUE"      # facture < 1 000 € HT : 0 tranche, conservée pour l'audit
    CANCELLED = "CANCELLED"  # attribution retirée après facturation (jamais pour une commission PAID)
