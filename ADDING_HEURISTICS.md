# Ajouter une heuristique

Ce guide explique comment ajouter une règle de détection à Vigil V2 et la brancher dans le pipeline.

## 1. Choisir le bon module

| Module | À utiliser pour | Exemples |
|---|---|---|
| `src/engine/rules_brand.py` | Règles qui dépendent d'une **marque** surveillée | allowlist, typosquatting, homoglyphes |
| `src/engine/rules_context.py` | Règles **génériques**, sans lien avec une marque précise | mots-clés, TLD à risque, autorité de certification, profondeur de sous-domaines |

## 2. Signature et format de retour

Toute heuristique respecte la signature `Rule` définie dans `scorer.py` :

```python
Rule = Callable[[ParsedDomain, CertEvent], tuple[int, str]]
```

**Entrées**

- `parsed: ParsedDomain` (`src/engine/domain_parser.py`) :
  - `fqdn` : nom complet (`login.paypa1-secure.co.uk`)
  - `subdomain` : `login`
  - `root` : `paypa1-secure`
  - `suffix` : `co.uk`
  - `registered_domain` : `paypa1-secure.co.uk`
  - `subdomain_labels` : `("login",)`
- `event: CertEvent` (`src/core/queue_manager.py`) : `domain`, `issuer`, `serial`, `is_precert`, `seen_at`.

**Sortie : un tuple `(score, raison)`**

| Cas | Retour |
|---|---|
| La règle ne se déclenche pas | `(0, "")` |
| La règle se déclenche | `(points, "explication courte")` |
| Atténuation (ex: domaine légitime) | `(-points, "explication")` |

Contraintes :

- `score` est un `int`. Il est **additionné** au score total ; il peut être négatif.
- `raison` est une `str` lisible, qui apparaît dans le champ `reasons` de l'alerte. Une raison vide est ignorée.
- La fonction doit être **pure, synchrone et rapide** : pas d'I/O ni d'appel réseau, car elle est exécutée pour chaque domaine du flux.
- Une exception levée est capturée par le `Scorer` et la règle est ignorée pour ce domaine. Ce n'est pas un moyen de contrôle : retournez `(0, "")`.

## 3. Écrire la fonction

Ajoutez la fonction dans `rules_brand.py` ou `rules_context.py`, avec une docstring (pas de commentaires `#` dans le projet).

```python
def check_subdomain_depth(parsed: ParsedDomain, event: CertEvent) -> tuple[int, str]:
    """Pénalise les FQDN avec un nombre anormal de sous-domaines.

    Args:
        parsed: Domaine décomposé en racine, sous-domaines et TLD.
        event: Événement d'origine (émetteur, numéro de série, type).

    Returns:
        Un tuple ``(score, raison)``. ``(0, "")`` si la profondeur est normale.
    """
    depth = len(parsed.subdomain_labels)
    if depth >= 4:
        return 20, f"{depth} niveaux de sous-domaines"
    return 0, ""
```

Même si votre règle n'utilise pas `event`, gardez les deux paramètres : l'orchestrateur appelle toutes les règles de la même façon.

## 4. L'intégrer dans `scorer.py`

Les règles sont enregistrées dans trois tuples au début de `src/engine/scorer.py`. Le `Scorer` les parcourt **dans l'ordre**.

1. Importez le module si ce n'est pas déjà fait (`rules_brand` et `rules_context` le sont déjà).
2. Ajoutez la fonction au tuple correspondant :

```python
CONTEXT_RULES: tuple[Rule, ...] = (
    rules_context.check_keywords,
    rules_context.check_tld,
    rules_context.check_certificate_authority,
    rules_context.check_subdomain_depth,
)
```

`DEFAULT_RULES = BRAND_RULES + CONTEXT_RULES` est recalculé automatiquement ; il n'y a rien d'autre à modifier. Ni `main.py` ni les autres modules ne sont concernés.

Pour tester un jeu de règles réduit, `Scorer` accepte un paramètre `rules` :

```python
scorer = Scorer(threshold=20, rules=[rules_context.check_subdomain_depth])
```

## 5. Calibrer et tester

Le score total est la somme des points de toutes les règles. Un domaine déclenche une alerte lorsque `score >= threshold` (`--threshold`, 50 par défaut). Choisissez donc vos points en fonction de ce seuil : une règle faible (10-20) doit se combiner à d'autres, une règle très fiable peut atteindre le seuil seule.

Test rapide sans réseau :

```python
from src.core.queue_manager import CertEvent
from src.engine.scorer import Scorer

scorer = Scorer(threshold=0)
event = CertEvent(domain="a.b.c.d.paypa1.xyz", issuer="Let's Encrypt", serial="01", is_precert=False)
result = scorer.evaluate(event)
print(result.score, result.reasons)
```

Pour valider de bout en bout avec un serveur CertStream, lancez `python main.py --threshold 0 --verbose` pour voir passer tous les domaines.

## Checklist

- [ ] Signature `(parsed: ParsedDomain, event: CertEvent) -> tuple[int, str]`
- [ ] Retourne `(0, "")` quand la règle ne s'applique pas
- [ ] Docstring complète, aucun commentaire `#`
- [ ] Pas d'I/O ni d'appel bloquant
- [ ] Fonction ajoutée à `BRAND_RULES` ou `CONTEXT_RULES` dans `scorer.py`
- [ ] Points calibrés par rapport au seuil
