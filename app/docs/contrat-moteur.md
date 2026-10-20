# Contrat d'entrée / sortie du moteur — version 1.0

Le moteur s'appelle comme un programme ; l'interface ne lit que le dossier de sortie.
La référence exécutable est `src/bph_engine/contract.py`, vérifiée par `tests/test_contract.py`.

## Entrée

`bph-engine analyse VIDEO --out DOSSIER [--config analyse.toml] [--reduced]`

```toml
[analyse]
mode = "complet"        # ou "reduit"
cadence_reduite = 5     # images par seconde analysées en mode réduit

[modeles]
dossier = "models"      # fichiers ONNX
```

## Sortie

| Fichier | Contenu |
|---|---|
| `manifest.json` | version du contrat et du moteur, vidéo, cadence, nombre d'images, cadence analysée |
| `status.json` | phase, progression 0–1, images traitées, erreurs, code de sortie (nul tant que l'analyse tourne) |
| `tracking.parquet` | une ligne par objet et par image : `frame`, `object_id`, `cls`, `team`, `x_px`, `y_px`, `x_cm`, `y_cm`, `confidence` |
| `calibration.parquet` | une ligne par image analysée : `frame`, `homography` (9 valeurs, image → terrain en cm), `valid`, `reprojection_error` |
| `masks/000123.png` | masque d'occlusion de l'image 123 |

`cls` ∈ {`player`, `goalkeeper`, `referee`, `ball`}. `team` vaut 0 ou 1, nul pour l'arbitre et le ballon.
`x_cm`/`y_cm` sont nuls quand l'homographie de l'image est invalide.

`status.json` et `manifest.json` sont réécrits de façon atomique (écriture dans un fichier
temporaire puis renommage) : l'interface ne lit jamais un fichier à moitié écrit.

## Versionnement

`MAJEUR.MINEUR`, inscrit dans `manifest.json`, `status.json` et les métadonnées de chaque
fichier Parquet. Un ajout compatible incrémente MINEUR ; un changement qui casse la lecture
incrémente MAJEUR. L'interface refuse tout MAJEUR inconnu plutôt que d'afficher des données fausses.

## Codes de sortie

`0` succès · `2` arguments ou configuration invalides · `3` vidéo illisible · `4` sortie impossible à écrire.

## État actuel

Les modèles de vision arrivent avec la phase 5. D'ici là, `analyse` produit une sortie
vide mais conforme, ce qui permet de construire la file d'analyse et l'affichage des résultats.
