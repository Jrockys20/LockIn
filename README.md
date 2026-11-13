# LockIn

<img src="lockin/assets/lockin-mark.svg" width="64" alt="Logo de LockIn">

**Una aplicación de escritorio para acompañar tus sesiones de trabajo y estudio.**

LockIn utiliza tu webcam para observar señales como ojos cerrados durante un
tiempo sostenido, cabeza apartada de una postura de referencia y ausencia de
rostro. Puedes configurar estas señales para que activen un video local elegido
por ti, con audio y en pantalla completa.

## Funciones

- Cámara seleccionable por nombre y vista previa con indicador de rostro.
- Calibración independiente de postura y apertura de ojos.
- Reglas configurables para ojos cerrados, cabeza apartada y rostro ausente.
- Alertas con tu propio video, control de volumen y silencio.
- Cierre del video con **Esc** o al observar una recuperación estable.
- Interfaz en español con tres secciones: **Sesión**, **Calibración** y **Alertas**.

## Descargar para Windows

1. Abre [Releases de LockIn](https://github.com/Jrockys20/LockIn/releases).
2. En la versión disponible, despliega **Assets** y descarga el archivo
   **LockIn-0.1.0-Setup-x64.exe** (o el instalador de una versión posterior).
3. Ejecuta el instalador y sigue el asistente.
4. Abre **LockIn** desde el menú Inicio o el acceso directo opcional del escritorio.

El instalador incluye Python, las bibliotecas y el modelo de rostro. **No necesitas
instalar Python, usar un IDE ni crear un entorno virtual.** Si todavía no hay una
Release con instalador, la descarga de la aplicación aún no está publicada.

La versión inicial está destinada a Windows x64 y no cuenta con firma digital.

## Primer uso

Selecciona tu cámara en **Sesión** y pulsa **Iniciar cámara**. En **Calibración**,
prepara las referencias de postura y ojos abiertos que necesites. Elige un video
local, compruébalo con **Probar video** y activa las reglas desde **Alertas**.

La cámara y las alertas empiezan desactivadas. Cambiar de sección mantiene la
captura; detener la cámara elimina las referencias. Los ajustes se aplican a la
sesión y no se guardan al cerrar.

## Privacidad

El procesamiento de la webcam se realiza en tu equipo. LockIn no guarda ni envía
imágenes de la cámara y no captura audio del micrófono. El video seleccionado se
reproduce desde su ubicación, sin subirlo a un servicio. La aplicación instalada
funciona con archivos locales y no requiere cuentas ni servidor.

## Tecnologías

| Componente | Uso |
| --- | --- |
| Python | Lógica de la aplicación. |
| PySide6 / Qt Widgets | Interfaz de escritorio. |
| OpenCV | Captura de cámara. |
| MediaPipe Tasks Face Landmarker | Puntos faciales y mediciones de rostro. |
| Qt Multimedia | Reproducción de video y audio. |
| PyInstaller e Inno Setup | Ejecutable e instalador de Windows. |

## Alcance

Las señales observadas **no son pruebas definitivas de sueño, distracción ni
falta de atención**. La iluminación, la posición del rostro y el rendimiento del
equipo pueden afectar las mediciones. El cierre automático requiere recuperación
estable de las señales activadas. Una alerta no puede garantizar prioridad sobre
todos los modos exclusivos de pantalla completa.

<details>
<summary>Ejecutar o construir desde el código fuente</summary>

Requiere Windows x64 y Python 3.11 de 64 bits. Desde la carpeta del proyecto:

~~~powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B scripts/download_model.py
.\.venv\Scripts\python.exe -B main.py
~~~

Para construir el ejecutable:

~~~powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_windows.ps1
~~~

Para generar también el instalador, instala Inno Setup 6 y añade la opción
-Installer al último comando. Si el compilador está en otra ubicación, usa
-InnoCompiler "C:\ruta\Inno Setup 6\ISCC.exe".

Los avisos de los componentes de terceros están en packaging/licenses y la
procedencia del modelo se documenta en [models/README.md](models/README.md).

</details>

