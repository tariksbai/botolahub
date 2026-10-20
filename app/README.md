# Bottola Analyse — application d'analyse vidéo football

Application installée (Windows, macOS, Linux), écrite en Python 3.11 avec Qt 6 / PySide6.
Tout le traitement se fait sur la machine de l'utilisateur : aucune vidéo ne quitte le poste.

## État d'avancement

| Tâche | Contenu | État |
|---|---|---|
| P01 | Squelette, deux zones (livrable `src/` / entraînement `training/`), CI, garde-fous | fait |
| P02 | Fenêtre principale, bibliothèque de matchs, schéma SQLite avec migrations | fait |
| P03 | Import, inspection et normalisation FFmpeg, fiche de match | fait, à valider sur vos vrais fichiers |
| P04 | Lecteur à l'image près, pas à pas, scrubbing, zoom de timeline, vitesse | fait |
| J1 | 500 sauts aléatoires + 100 pas, numéro affiché = numéro incrusté | réussi sous Linux ; Windows et macOS via la CI |
| P05 | Contrat moteur : ligne de commande, état JSON, Parquet, versionnement | fait |
| P06 | Grille de codes personnalisable, tagging au clavier | fait (import de grilles existantes : à faire) |
| P07 | Playlists | stockage prêt, écran à faire |
| P08–P10 | Export MP4, XML Sportscode, floutage | à faire |

## Lancer l'application (poste de développement)

```bash
cd app
python3.11 -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -e ".[dev]"
python -m bph_app
```

FFmpeg doit être installé et accessible dans le `PATH` (`ffmpeg -version`).

## Vérifier le jalon J1 sur votre machine

Dans l'application : **Outils › Test de précision du lecteur (J1)…** puis **Lancer le test**.
L'application fabrique une vidéo de 5 minutes dont chaque image porte son numéro, effectue
500 sauts aléatoires et 100 pas image par image, et vérifie à chaque fois que le numéro
affiché est exactement celui de l'image. Le résultat s'affiche en fin de test.

En ligne de commande :

```bash
python tools/counter_video.py compteur.mp4 --minutes 5
python tools/j1_seek_test.py compteur.mp4 --jumps 500
```

## Raccourcis clavier (espace de travail)

| Touche | Action |
|---|---|
| Espace | lecture / pause |
| ← / → | image précédente / suivante |
| Maj + ← / → | ± 1 seconde |
| Ctrl + ← / → | ± 10 secondes |
| J / K / L | recul 5 s / pause / lecture puis accélération |
| Début / Fin | début / fin du match |
| 1 … 0 (grille par défaut) | créer un tag à l'image courante |
| I / O | début / fin du tag sélectionné à la position courante |
| Suppr | supprimer le tag sélectionné |
| Ctrl + molette sur la timeline | zoom, jusqu'à l'image près |

## Organisation du code

```
app/
├── src/
│   ├── bph_engine/   moteur d'analyse — n'importe JAMAIS Qt ; s'appelle en ligne de commande
│   └── bph_app/      interface Qt — n'effectue aucun calcul d'analyse
├── training/         zone d'entraînement : jamais livrée, jamais importée par src/
├── tools/            garde-fou d'architecture, vidéo à compteur, test J1
├── tests/
└── docs/
```

Règles vérifiées automatiquement (`python tools/check_architecture.py`, en CI et en pre-commit) :

1. aucun import de Qt dans `bph_engine` ;
2. aucune bibliothèque interdite dans le livrable (`ultralytics` sous AGPL, `torch`) ;
3. aucun import de `training` depuis `src/`.

Contrôles avant chaque commit : `ruff check . && mypy && pytest -q` (ou `pre-commit install`).

## Moteur en ligne de commande

```bash
bph-engine probe match.mp4                      # inspection (JSON)
bph-engine normalize match.mov match_norm.mp4   # normalisation
bph-engine analyse match.mp4 --out resultat/ [--reduced]
```

Format de sortie : voir [docs/contrat-moteur.md](docs/contrat-moteur.md).
Choix de licence FFmpeg : voir [docs/ffmpeg.md](docs/ffmpeg.md).
