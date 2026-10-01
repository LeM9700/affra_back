# Attribution digitale, factures et commissions — V1

Objectif : relier chaque client facturé à l'acquisition digitale qui l'a amené, avec un journal
auditable, et calculer automatiquement la commission. PostgreSQL est la seule source de vérité
(Google Sheets n'est qu'une copie, GA4 n'intervient pas).

```
Visitor (cookie affra_vid) → AttributionEvent → Lead → Devis éventuel
                                                  → 1re facture → Customer → Commission
```

## 1. Identifiant navigateur `affra_vid`

- UUID v4 aléatoire (`crypto.randomUUID`) créé à la première visite par
  `site_vitrine/src/lib/attribution/visitor.ts`, seul module qui lit ou écrit ce cookie.
- Cookie first-party, `SameSite=Lax`, `Secure` en HTTPS, durée 13 mois, non prolongé.
  Il ne contient aucune donnée personnelle. Aucun fingerprinting.
- Il est lu côté serveur par la route `/api/attribution/[kind]` et par l'action `submitDevis`.
  Le navigateur n'appelle jamais FastAPI directement : la clé API reste sur le serveur Next.js.

## 2. Visites, first touch et last touch

`POST /api/v1/attribution/visit` est envoyé au premier chargement de la session, et à chaque nouvelle
arrivée qui porte un signal d'acquisition (UTM, click ID, referrer externe).

| Champ | Règle |
|---|---|
| `first_*` | Écrit à la première visite reçue, puis jamais modifié. |
| `last_*` | Mis à jour à chaque visite **non directe**. Un retour direct n'efface donc pas une source connue. |

Exemple : jour 1 ChatGPT, jour 3 Google, puis retour direct → `first_source = CHATGPT`,
`last_source = GOOGLE_ORGANIC`.

## 3. Classification des sources

Une seule implémentation, côté serveur : `app/services/attribution_classifier.py`. Le navigateur
n'envoie que des signaux bruts. L'ordre de priorité est le suivant :

1. UTM (`utm_source` / `utm_medium`)
2. click IDs Google Ads (`gclid`, `gbraid`, `wbraid`) → `GOOGLE_ADS`
3. hôte du referrer externe (le referrer interne est ignoré)
4. `DIRECT`

Valeurs possibles : `GOOGLE_ORGANIC`, `GOOGLE_BUSINESS`, `GOOGLE_ADS`, `BING_ORGANIC`, `CHATGPT`, `CLAUDE`,
`PERPLEXITY`, `GEMINI`, `REFERRAL`, `DIRECT`, `UNKNOWN`.

Données minimisées :
- le referrer est réduit à schéma, hôte et chemin (la query string est supprimée) ;
- la landing page ne garde que les paramètres `utm_*` et les click IDs.

## 4. Événements

| Type | Émis par |
|---|---|
| `LANDING` | `/visit` |
| `QUOTE_STARTED` | navigateur, clic « Commencer » du formulaire de devis |
| `QUOTE_SUBMITTED` | serveur, dans `create_devis` : non falsifiable par le navigateur |
| `PHONE_CLICK` / `EMAIL_CLICK` | navigateur (`TrackedPhoneLink`, `TrackedEmailLink`), en `sendBeacon` : l'ouverture du téléphone n'est jamais retardée |
| `WHATSAPP_CLICK` | prévu dans le modèle ; aucun lien WhatsApp sur le site aujourd'hui |
| `PHONE_CALL` | réservé au call tracking V2 ; refusé par l'endpoint public |

Un événement est attribué au last touch du visiteur au moment où il se produit.

Protections de l'endpoint public `/api/v1/attribution/*` :
- `X-API-Key` obligatoire ;
- schéma strict (`extra=forbid`) ;
- corps limité à 4 Ko ;
- metadata limitée : 10 clés au plus, valeurs plates de 200 caractères au plus, 1 Ko au total, clés sensibles refusées ;
- idempotence via `client_event_id` ;
- rate limit de 60 requêtes par minute et par IP visiteur (`X-Client-IP`, posé par le serveur Next.js).

## 5. Lead et attribution financière

Le `Lead` est indépendant du devis : il peut venir du formulaire, du téléphone ou d'un autre canal.
Un devis est rattaché au lead de même email (`devis.lead_id`).

Pourquoi un modèle `Lead` distinct de `Devis` :
- les devis sont purgés à 12 mois, alors que les leads devenus clients doivent rester ;
- un appel téléphonique n'a pas de devis.

Les coordonnées sont donc copiées une fois, à la création du lead.

On distingue la source marketing (`marketing_source`, instantané à la création) de la décision
financière :

- `financial_attribution` : `AFFRA_DIGITAL` | `NON_AFFRA` | `DISPUTED` (« à arbitrer ») ;
- `attribution_confidence` : `VERIFIED` | `SUPPORTED` | `DECLARED` | `UNKNOWN`.

Décision initiale automatique, prise par le système :

| Situation | Décision | Confiance |
|---|---|---|
| first touch ou last touch digital (toute source sauf `DIRECT` et `UNKNOWN`) | `AFFRA_DIGITAL` | `SUPPORTED` |
| sinon : direct, inconnu ou pas de cookie | `DISPUTED` | `UNKNOWN` |

Dans ce second cas, un arbitrage manuel est requis.

**Journal** : chaque changement passe par `POST /internal/leads/{id}/attribution` avec un motif
obligatoire. Il ajoute une ligne à `attribution_decisions` avec la décision précédente, l'auteur et
la date. Un trigger SQL interdit tout `UPDATE` de ce journal. `PATCH /internal/leads/{id}` refuse les
champs d'attribution.

**Appel téléphonique** (Google → site → appel) : le dashboard liste les `PHONE_CLICK` récents non
rattachés. L'opérateur crée le lead depuis le clic qui correspond à l'heure de l'appel : le lead hérite
du visiteur et de son parcours. Un appel direct depuis Google Business, sans visite du site, est saisi
avec une source déclarée (`DECLARED`).

## 6. Factures → Customer → Commission

`POST /internal/leads/{id}/invoices` exécute une seule transaction :
1. verrou sur la ligne du lead ;
2. création du Customer à la première facture, réutilisation ensuite (`customers.lead_id UNIQUE`) ;
3. création de la facture et de ses lignes ;
4. création de la commission si l'attribution en vigueur est `AFFRA_DIGITAL` ;
5. passage du lead au statut `client`.

En cas d'erreur, rien n'est conservé. Un devis accepté ne crée jamais de Customer.

Règles sur les factures :
- montants en centimes (`BIGINT`), aucun float ;
- la TVA est calculée par taux ;
- numérotation automatique continue `FA-AAAA-NNNN`, ou numéro saisi, unique globalement ;
- les identités vendeur et client sont figées dans la facture (instantanés).

Une facture est **immuable** : un trigger interdit `UPDATE` et `DELETE`. Les avoirs sont hors V1.

### Règle de commission

```
commission = floor(montant HT de la facture / 1 000 €) × 100 €
```

Le calcul est **indépendant pour chaque facture** : les reliquats ne sont jamais cumulés.
Exemple : 1 800 € + 1 500 € donnent 100 € + 100 € = 200 €, et non 300 €.

- Base de calcul : le **montant HT** de la facture (la TVA est reversée à l'État). À valider avec AFFRA.
- Implémentation : `app/services/commission.py`, contrôlée par une CHECK SQL
  (`number_of_brackets = invoice_amount_cents / 100000`, `commission = brackets × 10000`).
- Facture de moins de 1 000 € HT : une commission à 0 € est créée avec le statut `NOT_DUE`. Elle est conservée pour l'audit.
- Statuts : `DUE` → `PAID` (date et auteur enregistrés). `CANCELLED` signifie que l'attribution a été retirée après facturation.
- Si l'attribution change après facturation :
  - les commissions non payées sont annulées, ou réactivées ou créées si le lead redevient `AFFRA_DIGITAL` ;
  - une commission `PAID` n'est jamais modifiée (trigger SQL).

## 7. Google Business Profile

Lien de site recommandé dans la fiche Google Business Profile, à modifier manuellement dans GBP :

```
https://affra-reseaux.fr/?utm_source=google_business&utm_medium=organic_local
```

Ce lien est classé `GOOGLE_BUSINESS`. Sans ces UTM, un clic depuis la fiche arrive avec un referrer
`google.com` et est classé `GOOGLE_ORGANIC`.

## 8. Endpoints

| Méthode | Chemin | Accès |
|---|---|---|
| POST | `/api/v1/attribution/visit` | API key (proxy Next.js) |
| POST | `/api/v1/attribution/event` | API key (proxy Next.js) |
| GET/POST | `/internal/leads` | API key + JWT |
| GET/PATCH | `/internal/leads/{id}` | API key + JWT |
| POST | `/internal/leads/{id}/attribution` | API key + JWT |
| POST | `/internal/leads/{id}/invoices` | API key + JWT |
| GET | `/internal/invoices`, `/internal/invoices/{id}` | API key + JWT |
| GET | `/internal/commissions` · POST `/internal/commissions/{id}/pay` | API key + JWT |
| GET | `/internal/attribution/stats` (KPI SQL), `/internal/attribution/phone-clicks` | API key + JWT |

## 9. RGPD

La purge quotidienne (`app/jobs/cleanup.py`) supprime :
- les devis de plus de 12 mois (comportement existant) ;
- les leads non clients inactifs depuis plus de 12 mois ;
- les visiteurs inactifs depuis plus de 13 mois et sans lead.

Les leads devenus clients sont conservés, car leurs factures relèvent d'une obligation comptable.
La metadata n'accepte ni secrets, ni tokens, ni cookies.

## 10. Points d'extension V2 (non implémentés)

- **Call tracking réel** : un fournisseur (numéro dynamique) créera des événements `PHONE_CALL` via un
  webhook dédié. Le type existe déjà en base et est refusé par l'endpoint public.
- **API de logiciel de facturation / webhook** :
  - `customer_invoices.source_system` accepte déjà `MANUAL`, `IMPORT`, `WEBHOOK` et `API` ;
  - `external_reference` est unique par système, pour un import idempotent ;
  - `billing_service.create_invoice_for_lead` est le point d'entrée unique à réutiliser.
- **Import de factures (CSV)** : même point d'entrée, avec `source_system = 'IMPORT'`.

## 11. Tests

```bash
pip install -r requirements-dev.txt
# PostgreSQL local dédié (jamais la base Railway : conftest refuse tout hôte non local)
export TEST_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:55432/affra_test
python -m pytest
```

`tests/test_migrations.py` utilise en plus la base `affra_migr_test`, sur le même serveur.
