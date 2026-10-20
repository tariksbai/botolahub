# FFmpeg : configuration et licence

FFmpeg sert à inspecter les vidéos, à les normaliser à l'import et (plus tard) à exporter les clips.
**Le codeur H.264 embarqué détermine la licence effective du livrable.**

| Codeur | Licence de FFmpeg qui en résulte | Usage |
|---|---|---|
| `libopenh264` (Cisco, BSD) | LGPL v2.1+ | à embarquer dans le livrable |
| `libx264` | GPL | développement et tests uniquement |

`bph_engine.video.ENCODER_PREFERENCE` choisit `libopenh264` s'il est disponible, sinon `libx264`.
Les FFmpeg des gestionnaires de paquets (apt, brew, choco) sont compilés avec `--enable-gpl`
et `libx264` : ils conviennent au développement et à la CI, **pas au livrable**.

## Normalisation à l'import

Une vidéo est normalisée si elle n'est pas en H.264 / yuv420p dans un conteneur MP4, ou si
sa cadence est variable (cas fréquent des téléphones, détecté sur les intervalles réels entre
images). Résultat : H.264, yuv420p, une image clé toutes les 2 secondes, audio AAC,
conteneur MP4. Une source à cadence constante garde exactement ses images ; une source
à cadence variable est rééchantillonnée à cadence constante.

## Décision à prendre (registre des décisions)

- Configuration de compilation FFmpeg livrée : `--disable-gpl --disable-nonfree --enable-libopenh264`
  + décodeurs nécessaires (h264, hevc, mpeg4, prores…). À figer et documenter avant le packaging.
- Qualité de `libopenh264` (débit fixe, 8 Mb/s par défaut) contre le poids des fichiers normalisés :
  arbitrage à faire sur de vrais matchs.
