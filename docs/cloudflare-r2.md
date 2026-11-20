# Stockage des factures importées — Cloudflare R2

Les factures PDF importées depuis le dashboard (bouton « Importer une facture ») sont conservées
telles quelles dans un bucket Cloudflare R2 **privé**, hébergé dans l'**Union européenne**.
Chaque fichier est identifié par son empreinte SHA-256 : preuve d'origine en cas de désaccord sur
une commission, et refus automatique d'un même fichier importé deux fois.

Personne n'accède au bucket depuis Internet : seule l'API (Railway) lit et écrit, avec un jeton
limité à ce seul bucket. Le dashboard affiche un fichier via un lien temporaire (5 minutes).

## 1. Créer le compte et activer R2 (5 min)

1. Créer un compte sur <https://dash.cloudflare.com/sign-up> (ou se connecter).
2. Menu de gauche : **R2 Object Storage** → **Activer / Purchase R2**.
   - Une carte bancaire est demandée, mais l'offre gratuite suffit largement :
     10 Go de stockage, aucun frais de sortie. Une facture PDF fait ~1 Mo.

## 2. Créer le bucket (2 min)

1. **R2 Object Storage** → **Create bucket**.
2. **Bucket name** : `affra-factures`
3. **Location** : choisir **Specify jurisdiction** → **European Union (EU)**.
   - ⚠️ Ce choix est **définitif** : il garantit que les factures (données personnelles des clients)
     restent stockées dans l'UE (RGPD).
4. **Default storage class** : Standard.
5. **Create bucket**.
6. Dans le bucket → **Settings** → **Public access** : laisser **désactivé** (aucun domaine public,
   aucun accès `r2.dev`).

## 3. Créer le jeton d'accès limité au bucket (3 min)

1. Page **R2 Object Storage** (vue d'ensemble) → **Manage R2 API Tokens** (ou « API Tokens » → Manage).
2. **Create API token** (jeton de compte ou d'utilisateur, au choix).
3. **Token name** : `affra-api-railway`
4. **Permissions** : lecture **et** écriture des objets (libellé du type *Object Read & Write*).
   Ne pas donner les droits d'administration.
5. **Specify bucket(s)** : uniquement **`affra-factures`**.
6. **TTL** : Forever (ou une date, à renouveler alors avant expiration).
7. **Create API Token**, puis **copier immédiatement** :
   - **Access Key ID**
   - **Secret Access Key** (⚠️ affichée **une seule fois**)
   - l'**Account ID** (affiché sur la page R2, colonne de droite « Account details »).

🔒 Ne jamais coller ces valeurs dans un chat, un ticket ou le code : uniquement dans Railway.

## 4. Renseigner Railway (2 min)

Projet Railway → service **API** → **Variables** → **New Variable**, une par ligne :

| Variable | Valeur |
|---|---|
| `R2_ACCOUNT_ID` | l'Account ID |
| `R2_ACCESS_KEY_ID` | l'Access Key ID du jeton |
| `R2_SECRET_ACCESS_KEY` | la Secret Access Key du jeton |
| `R2_BUCKET` | `affra-factures` |
| `R2_JURISDICTION` | `eu` |

Railway redéploie l'API automatiquement. L'adresse utilisée est
`https://<R2_ACCOUNT_ID>.eu.r2.cloudflarestorage.com` (endpoint de la juridiction UE).

Tant que ces variables sont absentes, l'import de facture répond « Stockage des factures non
configuré » (503) ; le reste de l'API fonctionne normalement.

## 5. Lecture automatique des factures scannées (optionnel)

Les PDF produits par le logiciel de facturation (modèle `FAC…`) sont lus directement, sans service
externe. Pour les **scans / photos** ou un autre modèle de facture, l'API peut utiliser l'API Claude
(Anthropic) en secours :

| Variable | Valeur |
|---|---|
| `ANTHROPIC_API_KEY` | clé créée sur <https://console.anthropic.com> → API Keys |

Sans cette clé, un scan est accepté mais le formulaire n'est pas pré-rempli : la saisie est manuelle.
Coût indicatif : quelques centimes par facture lue. La facture est alors transmise à Anthropic
(sous-traitant) : à mentionner dans le registre des traitements.

## 6. Vérifier

Dans le dashboard : fiche d'un lead → **Importer une facture** → choisir un PDF. Le fichier doit
apparaître dans le bucket R2 sous `invoices/<id du lead>/<empreinte>.pdf`.

## Conservation

Les factures sont des pièces comptables : conservation **10 ans** (article L123-22 du Code de
commerce). Aucune règle de suppression automatique n'est configurée sur le bucket.
