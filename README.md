# Organizador de archivos

Aplicación de escritorio para Windows creada con Python 3 y PySide6. Analiza recursivamente una carpeta y organiza sus archivos en `PDF`, `IMG`, `DOCS`, `EXE`, `ZIP`, `PROGRAMACION`, `PROYECTOS` y `OTROS`.

## Características

- Interfaz clara con resumen por categoría, progreso y registro de actividad.
- Procesamiento en segundo plano para mantener la interfaz disponible.
- Confirmación antes de cada operación.
- Modo de simulación que no modifica ningún archivo.
- Renombrado automático de duplicados: `archivo (1).pdf`, `archivo (2).pdf`, etc.
- Análisis recursivo de subcarpetas.
- Las carpetas de categoría y `REPORTES` no se procesan nuevamente.
- Detecta proyectos de programación, comprime cada carpeta completa como ZIP y guarda el resultado en `PROYECTOS`.
- Mueve archivos de código sueltos, como `.sql`, `.json`, `.java` y `.ps1`, a `PROGRAMACION`.
- Tema automático según Windows, con selector manual claro/oscuro.
- Botón para guardar una copia del último reporte PDF.
- Reporte PDF tabular con nombre, extensión, categoría, tamaño, fecha, rutas y estado.
- Los errores se registran sin cerrar la aplicación.

## Requisitos

- Windows 10 u 11.
- Python 3.10 o posterior.

## Instalación

Abre PowerShell en la carpeta del proyecto y ejecuta:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Ejecución

```powershell
python main.py
```

Selecciona una carpeta, pulsa **Analizar carpeta** y revisa el resumen. Después puedes activar la simulación o pulsar **Organizar archivos** para mover los archivos tras confirmar la operación.

Al finalizar se crea un PDF dentro de la subcarpeta `REPORTES`. La simulación también genera un reporte, pero no mueve los archivos analizados.

La detección de proyectos reconoce marcadores habituales como `pyproject.toml`, `package.json`, `pom.xml`, `build.gradle`, `Cargo.toml`, `go.mod`, archivos `.sln` y otros. También reconoce carpetas con varios archivos fuente. El ZIP conserva la carpeta raíz y todo su contenido. Si seleccionas directamente la raíz de un proyecto, la aplicación la protege; selecciona su carpeta contenedora para comprimirlo completo.

## Crear un ejecutable

Con las dependencias instaladas, ejecuta:

```powershell
pyinstaller --onefile --windowed main.py
```

El ejecutable se generará en la carpeta `dist`.

> Antes de distribuirlo, Windows puede requerir firma de código para evitar advertencias de SmartScreen.
