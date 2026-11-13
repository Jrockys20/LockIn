# Modelo local de Face Landmarker

Modelo oficial de Google, paquete Face Landmarker float16, versión 1.

Fuente: https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task

Documentación: https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker

SHA-256 verificado el 2 de noviembre de 2026:
`64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`

Tamaño verificado: 3 758 596 bytes. El archivo es un modelo; no contiene imágenes
de la cámara del usuario. Se conserva localmente como face_landmarker.task.

Para descargarlo o comprobar que existe, desde la raíz de LockIn:

```powershell
.\.venv\Scripts\python.exe scripts/download_model.py
```

El script comprueba el SHA-256. Si ya existe un archivo diferente no lo sobrescribe.
Para restaurar un archivo corrupto, detén la aplicación, mueve ese archivo fuera
de esta carpeta y ejecuta nuevamente el comando.

La aplicación nunca descarga el modelo automáticamente y puede funcionar sin red.
No se envían fotogramas. La versión binaria se excluye de Git; el script permite
reproducir la instalación. Consulta la fuente oficial para los términos del modelo.