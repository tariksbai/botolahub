# Zone d'entraînement

Code d'annotation, d'entraînement et d'évaluation des modèles (PyTorch, et YOLO pour
comparaison). **Rien ici n'est livré au client** et `src/` ne doit jamais importer ce dossier :
`tools/check_architecture.py` le vérifie. Les modèles quittent cette zone uniquement sous forme
de fichiers ONNX.
