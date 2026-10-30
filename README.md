# Vigil V2

Détection de phishing en temps réel à partir du flux de Certificate Transparency (CertStream).
MVP modulaire en Python asynchrone, selon une architecture producteur-consommateur pilotée par les événements.

Les heuristiques sont codées en dur en Python et séparées de l'ingestion réseau. Les fonctions d'heuristiques sont livrées **vides** (`return 0, ""`) : elles sont à implémenter (voir [ADDING_HEURISTICS.md](ADDING_HEURISTICS.md)).

## Architecture

```
CertStream (WebSocket)
        │
        ▼
┌───────────────────┐   CertEvent   ┌──────────────┐
│ ingestion         │──────────────▶│ core         │
│ certstream_ws.py  │   publish()   │ QueueManager │
└───────────────────┘               └──────┬───────┘
                                           │ get()
                                           ▼
                          ┌─────────────────────────────────┐
                          │ engine                          │
                          │ domain_parser → rules_* → scorer│
                          └────────────────┬────────────────┘
                                           │ ScoreResult (score ≥ seuil)
                                           ▼
                          ┌─────────────────────────────────┐
                          │ output                          │
                          │ formatter (JSON) → dispatcher   │
                          └─────────────────────────────────┘
```

```
vigil_v2/
├── main.py
└── src/
    ├── core/queue_manager.py        CertEvent + file asyncio bornée
    ├── ingestion/certstream_ws.py   WebSocket, nettoyage JSON, publication
    ├── engine/
    │   ├── domain_parser.py         FQDN → racine / sous-domaines / TLD (tldextract)
    │   ├── rules_brand.py           Heuristiques de marque (allowlist, typosquatting)
    │   ├── rules_context.py         Heuristiques contextuelles (mots-clés, TLD, CA)
    │   └── scorer.py                Orchestrateur, cumul des points
    └── output/
        ├── formatter.py             Alerte → JSON
        └── dispatcher.py            Terminal et/ou fichier JSON Lines
```

| Module | Rôle |
|---|---|
| `QueueManager` | Enveloppe une `asyncio.Queue` bornée. `publish()` ne bloque jamais : si la file est pleine, l'événement est abandonné et compté dans `dropped`. |
| `CertstreamClient` | Se connecte au WebSocket, reconnexion automatique, ignore les certificats CA, retire les `*.`, dédoublonne, publie un `CertEvent` par domaine. |
| `DomainParser` | Retourne un `ParsedDomain` (`fqdn`, `subdomain`, `root`, `suffix`). Utilise la liste de suffixes embarquée de `tldextract`, sans accès réseau. |
| Données | `src/data/brands_legits_domain.yaml` (marques et domaines officiels) est chargé une fois par `rules_brand.py` (heuristique `check_brand_in_subdomain`). `src/data/brands_typosquats.yaml`, généré par `scripts/generate_typosquats.py`, alimente `check_typosquatting`. |
| `Scorer` | Applique chaque règle du registre, additionne les points, collecte les raisons. Une règle qui lève une exception est ignorée et journalisée. |
| `AlertFormatter` / `AlertDispatcher` | Sérialisation JSON, puis écriture sur stdout et/ou dans un fichier (JSON Lines). |

## Modèle d'exécution

Une seule boucle `asyncio`, lancée par `main.py`, héberge des tâches concurrentes :

1. **ingestion** (producteur) : lit le WebSocket et publie dans la file.
2. **engine-N** (consommateurs, `--workers`) : retirent un événement, le scorent et, si `score >= seuil`, formatent puis dispatchent l'alerte.
3. **stats** : journalise périodiquement la taille de la file et le nombre d'événements abandonnés.

La file bornée assure la contre-pression : le flux CertStream peut dépasser la capacité d'analyse, et la lecture du socket n'est jamais bloquée. Les règles sont synchrones et se veulent rapides (CPU léger, pas d'I/O). Une règle qui a besoin d'I/O devrait être traitée à part. L'écriture de fichier est déléguée à un thread.

## Prérequis

- Python 3.10 ou supérieur
- Un serveur CertStream compatible (format « lite » : `message_type`, `data.leaf_cert.all_domains`, etc.), par exemple une instance locale de [certstream-server-go](https://github.com/d-Rickyy-b/certstream-server-go)
- Dépendances : `websockets`, `tldextract`, `PyYAML`

## Installation et lancement

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python main.py --url ws://localhost:8080/ --threshold 50 --output-file alerts.jsonl
```

| Option | Défaut | Description |
|---|---|---|
| `--url` | `$CERTSTREAM_URL` ou `ws://localhost:8080/` | Serveur CertStream |
| `--threshold` | `50` | Score minimal pour émettre une alerte |
| `--output-file` | aucun | Fichier JSON Lines en plus du terminal |
| `--queue-size` | `10000` | Capacité de la file |
| `--workers` | `1` | Nombre de consommateurs du moteur |
| `--stats-interval` | `60` | Période des logs de statistiques (s) |
| `--verbose` | désactivé | Logs DEBUG |

Tant que les heuristiques sont vides, tous les scores valent 0 et aucune alerte n'est émise (sauf avec `--threshold 0`, pratique pour tester le pipeline de bout en bout).

## Format d'une alerte

```json
{"timestamp": "2026-10-30T11:00:00+00:00", "domain": "login.paypa1-secure.xyz", "root": "paypa1-secure", "subdomain": "login", "tld": "xyz", "score": 80, "reasons": ["typosquatting: paypal"], "issuer": "Let's Encrypt", "serial": "04AB...", "cert_type": "X509"}
```

## Conventions de code

- Aucun commentaire `#` dans le corps du code ; documentation par docstrings uniquement.
- Une heuristique retourne toujours un tuple `(score, raison)`.
