import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DevisUpdate(BaseModel):
    statut: str | None = Field(None, pattern=r"^(nouveau|devis_envoye|accepte|installation_planifiee|termine|refuse|archive)$")
    notes: str | None = None
    subvention_type: str | None = Field(None, pattern=r"^(advenir|cee|credit_impot|aucune)$")
    subvention_statut: str | None = Field(None, pattern=r"^(en_preparation|soumis|valide|verse)$")


class DevisInternalResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime
    type_client: str | None
    possede_vehicule: str | None
    distance_quotidienne: str | None
    delai: str | None
    distance_tableau: str | None
    prenom: str | None
    email: str | None
    telephone: str | None
    ville: str | None
    statut: str
    notes: str | None
    subvention_type: str | None
    subvention_statut: str | None

    model_config = {"from_attributes": True}


class DevisListItem(BaseModel):
    id: uuid.UUID
    created_at: datetime
    type_client: str | None
    ville: str | None
    prenom: str | None
    email: str | None
    statut: str

    model_config = {"from_attributes": True}


class DevisStats(BaseModel):
    total: int
    nouveau: int
    devis_envoye: int
    accepte: int
    installation_planifiee: int
    termine: int
    refuse: int
    archive: int


class DevisEmailRequest(BaseModel):
    subject: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1, max_length=5000)
