# Bottola — instructions pour Claude

Répondre en français. Le propriétaire du projet travaille sous Windows, dans `D:\botola\botolahub`.

## Le dépôt

- Racine : site vitrine statique (HTML) publié sur GitHub Pages. Ne pas y toucher sans demande.
- `app/` : **l'application d'analyse vidéo football**, le vrai produit. C'est là que se fait le travail.
- Le dossier de cadrage (architecture fonctionnelle et technique, planning, plan IA, guide des outils,
  infrastructure) est dans `D:\botola\DOCUMENTS DE TRAVAIL\`, **hors du dépôt**. Le dépôt est public :
  ne jamais y copier ces documents ni leur contenu commercial (tarifs, stratégie de licence, budget).
  Les lire pour décider, citer la tâche du planning (P01…, IA01…, J1…) dans les commits.

## Règles d'architecture (non négociables, issues du dossier)

- Application installée Windows / macOS / Linux, **Python 3.11 + Qt 6 / PySide6**. Jamais d'application
  web, mobile, ni de traitement distant. Aucune vidéo ne quitte le poste.
- `src/bph_engine` (moteur) n'importe **jamais** Qt ; `src/bph_app` (interface) ne contient **aucune**
  logique d'analyse. Le moteur s'appelle en ligne de commande (`bph-engine`) et écrit un contrat de
  fichiers versionné (`docs/contrat-moteur.md`) ; l'interface le lance dans un processus séparé.
- Positions toujours en **numéros d'image**, jamais en secondes.
- Livrable : pas de YOLO/Ultralytics (AGPL), pas de PyTorch (ONNX Runtime chez le client), FFmpeg
  sans GPL (`libopenh264`, voir `docs/ffmpeg.md`). `tools/check_architecture.py` le vérifie.
- Stockage : SQLite (métadonnées, tags, playlists), Parquet (tracking).
- Thème unique clair : couleurs, styles de boutons et icônes dans `src/bph_app/theme.py`
  (propriété `variant` = primary / ghost / danger / icon / play).

## Commandes (depuis `app/`, environnement `.venv` en Python 3.11)

```
py -3.11 -m venv .venv          (une fois)
.venv\Scripts\activate
pip install -e ".[dev]"         (une fois, puis après un changement de dépendances)
python -m bph_app               lancer l'application
python tools/check_architecture.py && ruff check . && mypy && pytest -q -m "not slow"
pytest -q -m slow               critère J1 complet (500 sauts)
```

Avant chaque commit : garde-fou d'architecture, ruff, mypy et pytest doivent passer.
`.github/workflows/app-ci.yml` refait ces contrôles sur les trois systèmes ;
`app-package.yml` construit le paquet Windows (artefact `BottolaAnalyse-windows`).

## État au 20/10/2026

Fait : P01 (squelette, CI, garde-fous), P02 (fenêtre, bibliothèque SQLite, filtre client/saison),
P03 (import, ffprobe, normalisation FFmpeg en processus séparé), P04 (lecteur à l'image près, timeline
zoomable), **J1 validé** (600/600 sur Linux, Windows et macOS en CI), P05 (contrat moteur),
P06 (grille de codes personnalisable, tagging au clavier), design moderne, paquet Windows autonome.

À faire, dans l'ordre du planning (jalon **J2** : un analyste tague un match entier au clavier,
construit une playlist de dix séquences, l'exporte en MP4 et en XML, et la réimporte dans son ancien
outil avec les bons timecodes) :

1. **P07 Playlists** — écran de création, glisser-déposer, réordonnancement, fusion. Le stockage existe
   déjà dans `store.py` (`create_playlist`, `set_playlist_items`, `merge_playlists`), avec ses tests.
2. **P08 Export de clips MP4 avec timecode** — par le moteur (FFmpeg), en file d'attente, nommage des
   fichiers à faire valider par le propriétaire.
3. **P09 Import / export XML Sportscode** — aller-retour sans perte, tests de boucle ; demander au
   propriétaire des fichiers XML réels issus de Hudl ou Nacsport.
4. **P10 Floutage des visages à l'export**.
5. Import de grilles de codes existantes (reste de P06).

Points en suspens : version exacte de FFmpeg à figer avant la version commerciale ; taille du paquet
Windows (~400 Mo, surtout pyarrow) à réduire au packaging P25.
