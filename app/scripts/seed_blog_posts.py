"""
Seed script - create or update two long-form published blog posts.
Run: python -m app.scripts.seed_blog_posts
"""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.blog import BlogPost

POSTS = [
    {
        "slug": "cout-installation-borne-recharge-domicile",
        "titre": "Combien coute l'installation d'une borne de recharge a domicile ?",
        "meta_description": "Budget reel d'une borne de recharge a domicile: materiel, pose, electricite, aides et delais. Guide complet pour preparer votre projet IRVE.",
        "contenu_markdown": """# Combien coute l'installation d'une borne de recharge a domicile ?

Installer une borne de recharge a domicile est un investissement utile, mais le prix final varie selon plusieurs facteurs techniques. Beaucoup de proprietaires entendent des montants tres differents et ne savent pas comment construire un budget realiste. Ce guide vous donne une lecture claire, poste par poste, pour eviter les mauvaises surprises et prendre une decision solide.

## 1) Ce qui compose vraiment le cout d'un projet

Le budget d'un projet IRVE ne se limite pas au prix de la borne. Il faut additionner:

- le materiel principal (borne, protections, accessoires),
- la main-d'oeuvre de pose et de raccordement,
- l'eventuelle adaptation du tableau electrique,
- la distance entre tableau et point de pose,
- les obligations de mise en conformite,
- la mise en service et les verifications finales.

En pratique, le prix global depend surtout du niveau de complexite electrique, plus que du simple modele de borne.

## 2) Fourchettes de prix observees sur le terrain

Pour une maison individuelle, les fourchettes les plus frequentes sont:

- **Projet simple**: de 900 a 1 400 EUR.
- **Projet intermediaire**: de 1 400 a 2 000 EUR.
- **Projet complexe**: de 2 000 a 3 200 EUR et plus.

Un projet simple correspond souvent a un tableau recent, une distance reduite, et peu de travaux annexes. Un projet complexe apparait quand il faut renforcer la protection, tirer une ligne plus longue, traverser plusieurs zones, ou corriger des points de conformite.

## 3) Le cout de la borne elle-meme

Le prix de la borne varie selon la puissance, la marque et les fonctions:

- entree de gamme: pilotage de base,
- milieu de gamme: programmation, suivi conso, app mobile,
- haut de gamme: pilotage dynamique, integration domotique, fonctions avancees.

Le bon choix n'est pas toujours le modele le plus cher. Il faut d'abord verifier votre usage quotidien:

- nombre de kilometres par semaine,
- horaires de recharge,
- type de vehicule,
- abonnement electrique,
- besoin de gestion d'energie.

Une borne bien dimensionnee coute moins cher a exploiter qu'une borne surdimensionnee mal reglee.

## 4) Main-d'oeuvre et conditions de pose

La pose inclut l'etude du cheminement, le tirage de cable, les protections, la fixation, les essais et les controles. Le temps de chantier peut aller d'une demi-journee a plus d'une journee selon:

- l'accessibilite des zones techniques,
- la distance tableau-garage,
- le type de murs ou de percements,
- les contraintes esthetiques,
- la coordination avec vos disponibilites.

Sur un devis serieux, ces elements doivent etre explicites. Un tarif "trop simple" masque souvent des options qui sortiront apres signature.

## 5) Tableau electrique et mise en conformite

Un point cle est la capacite de votre installation existante. Selon l'etat du tableau, il peut etre necessaire de:

- ajouter ou remplacer des protections,
- reorganiser certaines lignes,
- verifier la terre,
- traiter des anomalies anciennes.

Ces ajustements sont essentiels pour la securite et la durabilite. Ce sont aussi eux qui expliquent des ecarts de prix entre deux logements de surface similaire.

## 6) Distance et cheminement: le facteur souvent sous-estime

Plus la borne est loin du tableau, plus le cout augmente. Pourquoi:

- plus de cable,
- plus de temps de pose,
- plus de passages techniques,
- parfois des contraintes exterieures supplementaires.

Un bon reperage en amont permet de choisir l'implantation la plus efficace. Un metre de moins peut parfois faire gagner plusieurs centaines d'euros sur un chantier contraint.

## 7) Aides et optimisation du budget

Selon votre situation, des dispositifs peuvent reduire le reste a charge. Le cadre evolue regulierement, il faut donc verifier les conditions au moment du projet.

Conseil pratique:

1. valider l'eligibilite des aides avant signature,
2. verifier les pieces justificatives requises,
3. planifier l'ordre des demarches,
4. conserver un dossier complet (devis, factures, attestations).

Le gain peut etre significatif, a condition d'anticiper.

## 8) Delais realistes

Un projet standard se deroule souvent en 3 etapes:

- **etude et devis**,
- **validation technique et administrative**,
- **installation et mise en service**.

Le delai depend de la disponibilite des references materiel, de la complexite chantier et de l'agenda d'installation. Un calendrier clair evite les attentes inutiles.

## 9) Comment comparer deux devis correctement

Comparer seulement le total n'est pas suffisant. Utilisez cette grille:

- marque et reference de borne,
- puissance et mode de pilotage,
- details des protections,
- longueur et type de cable,
- contenu exact de la prestation,
- conditions de garantie,
- delai d'execution,
- modalites de SAV.

Un devis detaille protege votre projet. Un devis flou peut paraitre moins cher au depart mais couter plus cher ensuite.

## 10) Erreurs frequentes a eviter

- Choisir uniquement sur le prix le plus bas.
- Sous-estimer l'etat du tableau electrique.
- Oublier la verification des aides.
- Valider un materiel mal adapte a l'usage reel.
- Ne pas cadrer le SAV et le suivi apres pose.

Ces erreurs sont evitables avec une etude serieuse et une installation encadree.

## 11) Quelle enveloppe budgetaire prevoir

Pour avancer sereinement, prevoyez une enveloppe en trois scenarios:

- scenario cible (cas le plus probable),
- scenario prudent (si adaptations techniques),
- scenario maximal (si contraintes lourdes).

Cette approche vous permet de decider sans improvisation, et d'eviter de repousser un projet utile pour des raisons de visibilite budgetaire.

## 12) Conclusion

Le cout d'installation d'une borne de recharge a domicile depend d'abord de la realite technique de votre logement. Le bon reflexe consiste a demander une evaluation claire, avec un devis detaille et un niveau d'information suffisant pour arbitrer intelligemment.

Un projet IRVE bien prepare, c'est un budget maitrise, une recharge fiable au quotidien, et une installation conforme sur la duree.
""",
    },
    {
        "slug": "prise-renforcee-ou-borne-recharge-quelle-solution",
        "titre": "Prise renforcee ou borne de recharge: quelle solution choisir ?",
        "meta_description": "Prise renforcee ou borne IRVE: comparez securite, vitesse, confort, budget et usages pour choisir la meilleure solution pour votre vehicule electrique.",
        "contenu_markdown": """# Prise renforcee ou borne de recharge: quelle solution choisir ?

Lorsqu'on passe a la mobilite electrique, la meme question revient presque toujours: faut-il installer une prise renforcee ou une borne de recharge ? Les deux options existent, mais elles ne repondent pas aux memes besoins. Pour faire un choix fiable, il faut raisonner sur l'usage quotidien, la securite et la projection a moyen terme.

## 1) Comprendre la difference fondamentale

Une **prise renforcee** est une solution amelioree par rapport a une prise standard. Elle permet une recharge plus encadree, avec un niveau de protection adapte, mais reste limitee en puissance.

Une **borne de recharge** est un equipement dedie a la recharge de vehicules electriques. Elle est pensee pour des cycles reguliers, une gestion de puissance plus stable, et un meilleur confort d'utilisation.

Autrement dit, la prise renforcee peut convenir dans certains cas. La borne est generalement plus performante et plus durable pour un usage frequent.

## 2) Temps de recharge: un critere decisif

Le temps de recharge est souvent l'argument qui fait basculer le choix.

- Avec une prise renforcee, la recharge est plus lente.
- Avec une borne, la recharge est plus rapide et plus previsible.

Si vous roulez peu et rechargez la nuit sans contrainte horaire, la prise renforcee peut suffire. Si vous avez des trajets frequents, des horaires serres, ou plusieurs vehicules, la borne devient rapidement plus pertinente.

## 3) Securite electrique et continuite de service

Les deux solutions doivent etre installees correctement. Cependant, la borne apporte souvent:

- un niveau de pilotage mieux adapte,
- une meilleure stabilite en usage intensif,
- des protections dediees a la recharge.

La prise renforcee, bien qu'utile, reste plus proche d'une logique "acces simplifie". Pour un usage quotidien intensif, la borne apporte un cadre plus robuste.

## 4) Confort d'utilisation au quotidien

Le confort est sous-estime au moment de la decision. Pourtant, il influence l'experience sur plusieurs annees.

La borne offre souvent:

- programmation des plages horaires,
- suivi de consommation,
- pilotage intelligent,
- usage plus simple au quotidien.

La prise renforcee peut convenir en mode minimaliste, mais elle offre moins de souplesse pour optimiser cout et organisation.

## 5) Impact sur le budget initial

En general:

- la prise renforcee coute moins cher a l'installation,
- la borne coute plus cher au depart.

Mais le bon calcul se fait sur la duree. Une borne bien choisie peut eviter des adaptations futures si vos besoins augmentent (nouveau vehicule, plus de kilometres, changement d'usage familial).

## 6) Quel profil pour une prise renforcee

La prise renforcee peut etre adaptee si:

- vous roulez peu chaque semaine,
- vous avez du temps de recharge disponible,
- vous cherchez une solution de depart,
- vous n'avez pas de contrainte de rotation vehicule.

C'est une option de transition raisonnable dans certains contextes.

## 7) Quel profil pour une borne IRVE

La borne est recommandee si:

- vous roulez regulierement,
- vous voulez une recharge plus rapide,
- vous souhaitez mieux piloter votre consommation,
- vous anticipez des besoins futurs,
- vous voulez un equipement durable et confortable.

Pour beaucoup de foyers, c'est la solution la plus coherente des que l'usage devient quotidien.

## 8) Cas particuliers a ne pas negliger

### Maison individuelle

Le choix depend surtout de l'installation existante, de la distance au tableau et de l'usage vehicule. Une etude rapide permet de trancher objectivement.

### Copropriete

Le contexte technique et administratif peut orienter vers une borne dediee selon les contraintes de reseau, de comptage et de gouvernance.

### Petite flotte professionnelle

Des besoins de rotation et de disponibilite rendent souvent la borne indispensable.

## 9) Evolutivite: penser a 3 ans, pas a 3 mois

Un projet bien decide aujourd'hui doit rester pertinent demain. Posez-vous ces questions:

- Mon kilometrage peut-il augmenter ?
- Un second vehicule electrique est-il probable ?
- Ai-je besoin d'une recharge plus rapide a moyen terme ?
- Souhaite-je suivre et optimiser mes couts ?

Si plusieurs reponses sont "oui", la borne est souvent le meilleur choix strategique.

## 10) Cout d'usage et optimisation energie

Au-dela du cout d'installation, la capacite a piloter la recharge impacte vos depenses. Les fonctions de programmation peuvent aider a:

- privilegier les heures avantageuses,
- eviter des pointes de puissance,
- lisser la consommation du logement.

La borne apporte en general davantage d'outils pour cette optimisation.

## 11) Erreurs de decision frequentes

- Choisir uniquement sur le cout initial.
- Sous-estimer le volume de recharge futur.
- Ne pas anticiper l'evolution du foyer ou de la flotte.
- Negliger les contraintes de confort quotidien.
- Reporter une solution durable puis payer deux fois.

Un mauvais arbitrage peut couter plus cher en adaptations successives.

## 12) Methode simple pour choisir

Appliquez cette methode en 4 points:

1. **Usage reel**: kilometres, rythmes, contraintes horaires.
2. **Contexte technique**: tableau, puissance disponible, distance de pose.
3. **Projection**: besoins dans 12 a 36 mois.
4. **Pilotage**: besoin de suivi et d'optimisation energie.

Cette grille permet de choisir sur des faits, pas sur des impressions.

## 13) Conclusion

La prise renforcee est une option pertinente pour certains usages limites ou de transition. La borne de recharge est generalement la meilleure solution des que l'usage devient regulier, exigeant, ou evolutif.

Le bon choix est celui qui aligne securite, confort, budget et trajectoire de votre mobilite electrique. Une etude technique claire permet de prendre cette decision avec confiance.
""",
    },
]


async def seed() -> None:
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        for payload in POSTS:
            result = await session.execute(select(BlogPost).where(BlogPost.slug == payload["slug"]))
            existing = result.scalar_one_or_none()

            if existing:
                existing.titre = payload["titre"]
                existing.meta_description = payload["meta_description"]
                existing.contenu_markdown = payload["contenu_markdown"]
                existing.og_image_url = existing.og_image_url or "/images/og/og-default.png"
                existing.published = True
                existing.published_at = existing.published_at or now
                print(f"Updated post: {existing.slug}")
            else:
                post = BlogPost(
                    slug=payload["slug"],
                    titre=payload["titre"],
                    meta_description=payload["meta_description"],
                    contenu_markdown=payload["contenu_markdown"],
                    og_image_url="/images/og/og-default.png",
                    published=True,
                    published_at=now,
                )
                session.add(post)
                print(f"Created post: {post.slug}")

        await session.commit()

    print("Blog seed done.")


if __name__ == "__main__":
    asyncio.run(seed())
