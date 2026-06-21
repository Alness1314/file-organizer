"""Core file analysis and organization logic."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


CATEGORY_EXTENSIONS = {
    "PDF": {".pdf"},
    "IMG": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico"},
    "DOCS": {
        ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".txt", ".csv", ".rtf", ".odt",
    },
    "EXE": {".exe", ".msi", ".bat", ".cmd"},
    "ZIP": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
    "PROGRAMACION": {
        ".sql", ".json", ".jsonl", ".geojson", ".ps1", ".sh", ".bash",
        ".py", ".pyw", ".java", ".kt", ".kts", ".js", ".jsx", ".ts", ".tsx",
        ".c", ".h", ".cpp", ".hpp", ".cs", ".go", ".rs", ".rb", ".php",
        ".swift", ".dart", ".scala", ".lua", ".r", ".m", ".mm", ".fs", ".fsx",
        ".vb", ".ex", ".exs", ".clj", ".cljs", ".hs", ".erl", ".hrl", ".sol",
        ".vue", ".svelte", ".html", ".htm", ".css", ".scss", ".sass", ".less",
        ".xml", ".yaml", ".yml", ".toml",
    },
}
CATEGORIES = ("PDF", "IMG", "DOCS", "EXE", "ZIP", "PROGRAMACION", "PROYECTOS", "OTROS")
EXCLUDED_DIRECTORIES = frozenset((*CATEGORIES, "REPORTES"))
PROJECT_MARKERS = frozenset({
    ".git", ".idea", ".vscode", "pyproject.toml", "requirements.txt", "setup.py",
    "pipfile", "poetry.lock", "package.json", "tsconfig.json", "pom.xml", "build.gradle",
    "settings.gradle", "gradlew", "cargo.toml", "go.mod", "composer.json", "gemfile",
    "pubspec.yaml", "mix.exs", "cmakelists.txt", "makefile", "dockerfile",
})
PROJECT_FILE_EXTENSIONS = frozenset({
    ".py", ".pyw", ".java", ".kt", ".kts", ".js", ".jsx", ".ts", ".tsx",
    ".c", ".h", ".cpp", ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift",
    ".dart", ".scala", ".lua", ".r", ".m", ".mm", ".fs", ".fsx", ".vb", ".ex",
    ".exs", ".clj", ".cljs", ".hs", ".erl", ".hrl", ".sol", ".vue", ".svelte",
})


@dataclass
class AnalysisResult:
    """Counts and files found while analyzing a source folder."""

    files: list[Path] = field(default_factory=list)
    projects: list[Path] = field(default_factory=list)
    root_is_project: bool = False
    counts: dict[str, int] = field(
        default_factory=lambda: {category: 0 for category in CATEGORIES}
    )

    @property
    def total(self) -> int:
        return len(self.files) + len(self.projects) + int(self.root_is_project)


@dataclass
class OrganizationResult:
    """Summary of an organization operation."""

    total: int
    processed: int = 0
    moved: int = 0
    simulated: int = 0
    errors: int = 0
    report_path: Path | None = None
    report_error: str | None = None
    counts: dict[str, int] = field(
        default_factory=lambda: {category: 0 for category in CATEGORIES}
    )


def category_for(file_path: Path) -> str:
    """Return the destination category for a file extension."""
    extension = file_path.suffix.lower()
    for category, extensions in CATEGORY_EXTENSIONS.items():
        if extension in extensions:
            return category
    return "OTROS"


@dataclass
class FileRecord:
    """Filesystem metadata captured for one organization attempt."""

    name: str
    extension: str
    category: str
    size: int
    modified_at: datetime
    source: Path
    destination: Path
    status: str


def is_project_folder(folder: Path) -> bool:
    """Detect common project markers or a collection of source-code files."""
    try:
        entries = list(folder.iterdir())
    except OSError:
        return False
    names = {entry.name.lower() for entry in entries}
    if names & PROJECT_MARKERS or any(name.endswith((".sln", ".csproj", ".xcodeproj")) for name in names):
        return True
    source_count = sum(
        1
        for entry in entries
        if entry.is_file() and entry.suffix.lower() in PROJECT_FILE_EXTENSIONS
    )
    return source_count >= 2


def _scan_source(source: Path) -> tuple[list[Path], list[Path]]:
    """Return recursive files and project roots while pruning output folders."""
    files: list[Path] = []
    projects: list[Path] = []
    try:
        for entry in source.iterdir():
            try:
                if entry.is_file():
                    files.append(entry)
                elif (
                    entry.is_dir()
                    and not entry.is_symlink()
                    and entry.name.upper() not in EXCLUDED_DIRECTORIES
                ):
                    if is_project_folder(entry):
                        projects.append(entry)
                    else:
                        child_files, child_projects = _scan_source(entry)
                        files.extend(child_files)
                        projects.extend(child_projects)
            except OSError:
                continue
    except OSError as error:
        raise OSError(f"No se pudo leer la carpeta {source}: {error}") from error
    return files, projects


def analyze_folder(folder: Path | str) -> AnalysisResult:
    """Analyze files recursively, excluding organization output folders."""
    source = Path(folder)
    if not source.exists():
        raise FileNotFoundError(f"La carpeta no existe: {source}")
    if not source.is_dir():
        raise NotADirectoryError(f"La ruta no es una carpeta: {source}")

    result = AnalysisResult()
    if is_project_folder(source):
        result.root_is_project = True
        result.counts["PROYECTOS"] = 1
        return result
    entries, projects = _scan_source(source)
    entries.sort(key=lambda item: str(item).lower())
    projects.sort(key=lambda item: str(item).lower())
    for entry in entries:
        result.files.append(entry)
        result.counts[category_for(entry)] += 1
    result.projects.extend(projects)
    result.counts["PROYECTOS"] = len(projects)
    return result


def _folder_size(folder: Path) -> int:
    total = 0
    try:
        for item in folder.rglob("*"):
            try:
                if item.is_file():
                    total += item.stat().st_size
            except OSError:
                continue
    except OSError:
        pass
    return total


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"


def create_pdf_report(folder: Path, records: list[FileRecord], dry_run: bool) -> Path:
    """Create a paginated PDF report and return its path."""
    reports_dir = folder / "REPORTES"
    reports_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = unique_destination(reports_dir / f"Reporte_organizacion_{timestamp}.pdf")

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle", parent=styles["Title"], alignment=TA_CENTER,
        fontName="Helvetica-Bold", fontSize=18, textColor=colors.HexColor("#374151"),
    )
    cell_style = ParagraphStyle(
        "ReportCell", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=6.5, leading=8, spaceAfter=0,
    )
    header_style = ParagraphStyle(
        "ReportHeader", parent=cell_style, fontName="Helvetica-Bold",
        textColor=colors.white, alignment=TA_CENTER,
    )

    document = SimpleDocTemplate(
        str(report_path), pagesize=landscape(A4), leftMargin=10 * mm,
        rightMargin=10 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
        title="Reporte de organización de archivos",
    )
    mode = "SIMULACIÓN" if dry_run else "ORGANIZACIÓN REAL"
    story = [
        Paragraph("Reporte de organización de archivos", title_style),
        Paragraph(
            f"Modo: {mode} | Fecha: {datetime.now():%d/%m/%Y %H:%M:%S} | "
            f"Elementos: {len(records)}",
            ParagraphStyle("Summary", parent=styles["Normal"], alignment=TA_CENTER, fontSize=9),
        ),
        Spacer(1, 5 * mm),
    ]
    headers = ("Nombre", "Ext.", "Categoría", "Tamaño", "Fecha", "Ruta original", "Destino", "Estado")
    data = [[Paragraph(escape(value), header_style) for value in headers]]
    for record in records:
        values = (
            record.name,
            record.extension or "(sin extensión)",
            record.category,
            _format_size(record.size),
            record.modified_at.strftime("%d/%m/%Y %H:%M:%S"),
            str(record.source),
            str(record.destination),
            record.status,
        )
        data.append([Paragraph(escape(str(value)), cell_style) for value in values])

    table = Table(
        data, repeatRows=1,
        colWidths=[35 * mm, 14 * mm, 19 * mm, 18 * mm, 27 * mm, 57 * mm, 57 * mm, 25 * mm],
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#374151")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    story.append(table)
    document.build(story)
    return report_path


def unique_destination(destination: Path, reserved: set[Path] | None = None) -> Path:
    """Find a non-existing destination without overwriting another file."""
    reserved = reserved if reserved is not None else set()
    if not destination.exists() and destination not in reserved:
        return destination

    counter = 1
    while True:
        candidate = destination.with_name(
            f"{destination.stem} ({counter}){destination.suffix}"
        )
        if not candidate.exists() and candidate not in reserved:
            return candidate
        counter += 1


def organize_folder(
    folder: Path | str,
    dry_run: bool = False,
    log_callback: Callable[[str], None] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> OrganizationResult:
    """Organize files recursively and generate a PDF activity report."""
    source = Path(folder)
    analysis = analyze_folder(source)
    if analysis.root_is_project:
        raise ValueError(
            "La carpeta seleccionada es un proyecto. Selecciona su carpeta contenedora "
            "para moverlo completo sin separar sus archivos."
        )
    result = OrganizationResult(total=analysis.total, counts=analysis.counts.copy())
    reserved: set[Path] = set()
    records: list[FileRecord] = []

    def log(message: str) -> None:
        if log_callback:
            log_callback(message)

    work_items = [(path, True) for path in analysis.projects]
    work_items.extend((path, False) for path in analysis.files)

    for index, (item_path, is_project) in enumerate(work_items, start=1):
        file_path = item_path
        category = "PROYECTOS" if is_project else category_for(file_path)
        destination_dir = source / category
        destination_name = f"{file_path.name}.zip" if is_project else file_path.name
        destination = unique_destination(destination_dir / destination_name, reserved)
        reserved.add(destination)

        try:
            metadata = file_path.stat()
            item_size = _folder_size(file_path) if is_project else metadata.st_size
            if dry_run:
                status = "Simulado"
                log(f"[SIMULACIÓN] {file_path} -> {destination}")
                result.simulated += 1
            else:
                destination_dir.mkdir(exist_ok=True)
                if is_project:
                    archive_base = destination.with_suffix("")
                    created_archive = Path(shutil.make_archive(
                        str(archive_base),
                        "zip",
                        root_dir=str(file_path.parent),
                        base_dir=file_path.name,
                    ))
                    if created_archive != destination:
                        created_archive.replace(destination)
                    shutil.rmtree(file_path)
                    status = "Comprimido"
                else:
                    shutil.move(str(file_path), str(destination))
                    status = "Movido"
                item_label = "Proyecto comprimido" if is_project else "Movido"
                log(f"{item_label}: {file_path} -> {destination}")
                result.moved += 1
            records.append(FileRecord(
                name=file_path.name,
                extension=".zip" if is_project else file_path.suffix.lower(),
                category=category,
                size=item_size,
                modified_at=datetime.fromtimestamp(metadata.st_mtime),
                source=file_path,
                destination=destination,
                status=status,
            ))
        except (OSError, shutil.Error) as error:
            result.errors += 1
            log(f"ERROR con {file_path.name}: {error}")
        finally:
            result.processed += 1
            if progress_callback:
                progress_callback(index, analysis.total)

    try:
        result.report_path = create_pdf_report(source, records, dry_run)
        log(f"Reporte PDF creado: {result.report_path}")
    except Exception as error:
        result.report_error = str(error)
        log(f"ERROR al crear el reporte PDF: {error}")
    return result
