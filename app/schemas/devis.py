import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class DevisCreate(BaseModel):
    # Questionnaire IRVE (écrans 2-6)
    type_client: str = Field(..., pattern=r"^(maison|copropriete|entreprise)$")
    possede_vehicule: str = Field(..., pattern=r"^(oui|pas_encore|livraison_prochaine)$")
    distance_quotidienne: str = Field(..., pattern=r"^(0_50|50_150|plus_150)$")
    delai: str = Field(..., pattern=r"^(rapidement|un_deux_mois|pas_urgent)$")
    distance_tableau: str = Field(..., pattern=r"^(0_5m|5_15m|plus_15m|ne_sait_pas)$")

    # Coordonnées (écran 7)
    prenom: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    telephone: str = Field(..., pattern=r"^(\+33|0)[1-9](\d{8})$")
    ville: str = Field(..., min_length=1, max_length=100)

    # Anti-spam honeypot (doit rester vide)
    website: str | None = Field(None, max_length=0)

    # Attribution : valeur du cookie first-party affra_vid, lue côté serveur par Next.js (optionnelle)
    anonymous_id: uuid.UUID | None = None

    @field_validator("website")
    @classmethod
    def honeypot_must_be_empty(cls, v: str | None) -> str | None:
        if v:
            raise ValueError("Spam detected")
        return v


class DevisResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime
    statut: str

    model_config = {"from_attributes": True}
