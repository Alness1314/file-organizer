"""Main PySide6 window and background worker."""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from organizer import AnalysisResult, OrganizationResult, analyze_folder, organize_folder


class OrganizerWorker(QObject):
    log = Signal(str)
    progress = Signal(int)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, folder: Path, dry_run: bool) -> None:
        super().__init__()
        self.folder = folder
        self.dry_run = dry_run

    @Slot()
    def run(self) -> None:
        try:
            result = organize_folder(
                self.folder,
                self.dry_run,
                log_callback=self.log.emit,
                progress_callback=self._report_progress,
            )
            self.finished.emit(result)
        except Exception as error:  # Keep unexpected filesystem errors inside the UI.
            self.failed.emit(str(error))

    def _report_progress(self, current: int, total: int) -> None:
        self.progress.emit(round(current * 100 / total) if total else 100)


class SummaryCard(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("summaryCard")
        layout = QVBoxLayout(self)
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        self.value_label = QLabel("0")
        self.value_label.setObjectName("cardValue")
        layout.addWidget(title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value: int) -> None:
        self.value_label.setText(str(value))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.selected_folder: Path | None = None
        self.thread: QThread | None = None
        self.worker: OrganizerWorker | None = None
        self.latest_report_path: Path | None = None
        self.theme_mode = "system"
        self.cards: dict[str, SummaryCard] = {}
        self.setWindowTitle("Organizador de archivos")
        self.setMinimumSize(900, 650)
        self.resize(1000, 720)
        self._build_ui()
        self._apply_styles()
        QApplication.styleHints().colorSchemeChanged.connect(self._system_theme_changed)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        title = QLabel("Organizador de archivos")
        title.setObjectName("title")
        subtitle = QLabel("Clasifica tus archivos y subcarpetas de forma rápida y segura.")
        subtitle.setObjectName("subtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        folder_row = QHBoxLayout()
        self.path_label = QLabel("Ninguna carpeta seleccionada")
        self.path_label.setObjectName("pathLabel")
        self.path_label.setTextInteractionFlags(self.path_label.textInteractionFlags())
        select_button = QPushButton("Seleccionar carpeta")
        select_button.clicked.connect(self.select_folder)
        folder_row.addWidget(self.path_label, 1)
        folder_row.addWidget(select_button)
        root.addLayout(folder_row)

        cards_layout = QGridLayout()
        cards_layout.setSpacing(10)
        card_data = [
            ("TOTAL", "Total"), ("PDF", "PDFs"), ("IMG", "Imágenes"),
            ("DOCS", "Documentos"), ("EXE", "Ejecutables"), ("ZIP", "Comprimidos"),
            ("PROGRAMACION", "Programación"), ("PROYECTOS", "Proyectos"),
            ("OTROS", "Otros"),
        ]
        for index, (key, label) in enumerate(card_data):
            card = SummaryCard(label)
            self.cards[key] = card
            cards_layout.addWidget(card, index // 3, index % 3)
        root.addLayout(cards_layout)

        controls = QHBoxLayout()
        self.analyze_button = QPushButton("Analizar carpeta")
        self.analyze_button.setEnabled(False)
        self.analyze_button.clicked.connect(self.analyze)
        self.organize_button = QPushButton("Organizar archivos")
        self.organize_button.setObjectName("primaryButton")
        self.organize_button.setEnabled(False)
        self.organize_button.clicked.connect(self.confirm_organization)
        self.dry_run_checkbox = QCheckBox("Simular organización sin mover archivos")
        self.download_report_button = QPushButton("Guardar reporte PDF")
        self.download_report_button.setEnabled(False)
        self.download_report_button.clicked.connect(self.save_report)
        self.theme_button = QPushButton("Tema: Sistema")
        self.theme_button.clicked.connect(self.cycle_theme)
        controls.addWidget(self.analyze_button)
        controls.addWidget(self.organize_button)
        controls.addWidget(self.download_report_button)
        controls.addStretch()
        controls.addWidget(self.dry_run_checkbox)
        controls.addWidget(self.theme_button)
        root.addLayout(controls)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        root.addWidget(self.progress_bar)

        log_title = QLabel("Registro de actividad")
        log_title.setObjectName("sectionTitle")
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setPlaceholderText("Aquí aparecerán los archivos procesados...")
        root.addWidget(log_title)
        root.addWidget(self.log_area, 1)

    @Slot()
    def select_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de origen")
        if not folder:
            return
        self.selected_folder = Path(folder)
        self.path_label.setText(str(self.selected_folder))
        self.path_label.setToolTip(str(self.selected_folder))
        self.analyze_button.setEnabled(True)
        self.organize_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_area.clear()
        self.latest_report_path = None
        self.download_report_button.setEnabled(False)
        self._reset_summary()

    @Slot()
    def analyze(self) -> None:
        if not self.selected_folder:
            return
        try:
            result = analyze_folder(self.selected_folder)
            self._show_analysis(result)
            if result.root_is_project:
                self.log_area.append(
                    "Proyecto detectado en la carpeta seleccionada. Selecciona su carpeta "
                    "contenedora para moverlo completo."
                )
            else:
                self.log_area.append(
                    f"Análisis completado: {result.total} elemento(s) encontrado(s)."
                )
            self.organize_button.setEnabled(result.total > 0 and not result.root_is_project)
        except (OSError, ValueError) as error:
            self.log_area.append(f"ERROR: {error}")
            QMessageBox.critical(self, "Error al analizar", str(error))

    @Slot()
    def confirm_organization(self) -> None:
        if not self.selected_folder:
            return
        dry_run = self.dry_run_checkbox.isChecked()
        action = "simular la organización" if dry_run else "mover los archivos"
        answer = QMessageBox.question(
            self,
            "Confirmar operación",
            f"¿Deseas {action} en esta carpeta y sus subcarpetas?\n\n"
            f"{self.selected_folder}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._start_worker(dry_run)

    def _start_worker(self, dry_run: bool) -> None:
        assert self.selected_folder is not None
        self.progress_bar.setValue(0)
        self.log_area.append("\nIniciando simulación..." if dry_run else "\nIniciando organización...")
        self._set_controls_enabled(False)

        self.thread = QThread(self)
        self.worker = OrganizerWorker(self.selected_folder, dry_run)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.log_area.append)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self._operation_finished)
        self.worker.failed.connect(self._operation_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._thread_finished)
        self.thread.start()

    @Slot(object)
    def _operation_finished(self, result: OrganizationResult) -> None:
        self.progress_bar.setValue(100)
        action_count = result.simulated if result.simulated else result.moved
        action_label = "simulados" if result.simulated else "movidos"
        message = (
            f"Proceso finalizado.\n\nElementos {action_label}: {action_count}\n"
            f"Errores: {result.errors}\nTotal procesado: {result.processed}"
        )
        if result.report_path:
            self.latest_report_path = result.report_path
            self.download_report_button.setEnabled(True)
            message += f"\n\nReporte PDF:\n{result.report_path}"
        elif result.report_error:
            message += f"\n\nNo se pudo crear el reporte: {result.report_error}"
        self.log_area.append(message.replace("\n", " | "))
        QMessageBox.information(self, "Proceso completado", message)

    @Slot(str)
    def _operation_failed(self, message: str) -> None:
        self.log_area.append(f"ERROR: {message}")
        QMessageBox.critical(self, "Error durante el proceso", message)

    @Slot()
    def _thread_finished(self) -> None:
        self.thread = None
        self.worker = None
        self._set_controls_enabled(True)
        self.analyze()

    def _show_analysis(self, result: AnalysisResult) -> None:
        self.cards["TOTAL"].set_value(result.total)
        for category, count in result.counts.items():
            self.cards[category].set_value(count)

    def _reset_summary(self) -> None:
        for card in self.cards.values():
            card.set_value(0)

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.analyze_button.setEnabled(enabled)
        self.organize_button.setEnabled(enabled)
        self.dry_run_checkbox.setEnabled(enabled)
        self.download_report_button.setEnabled(enabled and bool(self.latest_report_path))

    @Slot()
    def save_report(self) -> None:
        if not self.latest_report_path or not self.latest_report_path.exists():
            QMessageBox.warning(self, "Reporte no disponible", "Primero genera un reporte PDF.")
            return
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar reporte PDF",
            self.latest_report_path.name,
            "Archivos PDF (*.pdf)",
        )
        if not destination:
            return
        destination_path = Path(destination)
        if destination_path.suffix.lower() != ".pdf":
            destination_path = destination_path.with_suffix(".pdf")
        try:
            if destination_path.resolve() != self.latest_report_path.resolve():
                shutil.copy2(self.latest_report_path, destination_path)
            QMessageBox.information(self, "Reporte guardado", f"Reporte guardado en:\n{destination_path}")
        except OSError as error:
            QMessageBox.critical(self, "Error al guardar", str(error))

    @Slot()
    def cycle_theme(self) -> None:
        modes = ("system", "light", "dark")
        self.theme_mode = modes[(modes.index(self.theme_mode) + 1) % len(modes)]
        labels = {"system": "Sistema", "light": "Claro", "dark": "Oscuro"}
        self.theme_button.setText(f"Tema: {labels[self.theme_mode]}")
        self._apply_styles()

    @Slot(object)
    def _system_theme_changed(self, _scheme: object = None) -> None:
        if self.theme_mode == "system":
            self._apply_styles()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.thread and self.thread.isRunning():
            QMessageBox.information(
                self, "Operación en curso", "Espera a que termine la operación antes de cerrar."
            )
            event.ignore()
            return
        event.accept()

    def _apply_styles(self) -> None:
        system_dark = QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
        dark = self.theme_mode == "dark" or (self.theme_mode == "system" and system_dark)
        if dark:
            self.setStyleSheet("""
            QMainWindow, QWidget { background: #111827; color: #f3f4f6; font-family: "Segoe UI"; font-size: 14px; }
            QLabel#title { font-size: 28px; font-weight: 700; color: #f9fafb; }
            QLabel#subtitle, QLabel#cardTitle { color: #9ca3af; }
            QLabel#pathLabel, QFrame#summaryCard { background: #1f2937; border: 1px solid #374151; border-radius: 8px; color: #e5e7eb; padding: 8px; }
            QLabel#sectionTitle { font-size: 16px; font-weight: 600; }
            QLabel#cardValue { color: #60a5fa; font-size: 24px; font-weight: 700; }
            QPushButton { background: #374151; color: #f9fafb; border: 1px solid #4b5563; border-radius: 7px; padding: 9px 14px; font-weight: 600; }
            QPushButton:hover { background: #4b5563; }
            QPushButton:disabled { color: #6b7280; background: #1f2937; }
            QPushButton#primaryButton { background: #2563eb; color: white; border-color: #2563eb; }
            QProgressBar { background: #1f2937; color: white; border: 1px solid #4b5563; border-radius: 6px; height: 17px; text-align: center; }
            QProgressBar::chunk { background: #3b82f6; border-radius: 5px; }
            QTextEdit { background: #030712; color: #d1fae5; border: 1px solid #374151; border-radius: 8px; padding: 9px; font-family: Consolas; font-size: 12px; }
        """)
            return
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #f4f7fb; color: #172033; font-family: "Segoe UI"; font-size: 14px; }
            QLabel#title { font-size: 28px; font-weight: 700; color: #14213d; }
            QLabel#subtitle { color: #667085; margin-bottom: 8px; }
            QLabel#pathLabel { background: white; border: 1px solid #d8dee9; border-radius: 7px; padding: 10px; color: #475467; }
            QLabel#sectionTitle { font-size: 16px; font-weight: 600; margin-top: 4px; }
            QFrame#summaryCard { background: white; border: 1px solid #e4e7ec; border-radius: 9px; }
            QLabel#cardTitle { color: #667085; font-size: 12px; }
            QLabel#cardValue { color: #1d4ed8; font-size: 24px; font-weight: 700; }
            QPushButton { background: white; border: 1px solid #cfd6e4; border-radius: 7px; padding: 9px 14px; font-weight: 600; }
            QPushButton:hover { background: #eef3ff; border-color: #8aa7e8; }
            QPushButton:disabled { color: #98a2b3; background: #eaecf0; }
            QPushButton#primaryButton { background: #2563eb; color: white; border-color: #2563eb; }
            QPushButton#primaryButton:hover { background: #1d4ed8; }
            QProgressBar { background: white; border: 1px solid #d8dee9; border-radius: 6px; height: 17px; text-align: center; }
            QProgressBar::chunk { background: #2563eb; border-radius: 5px; }
            QTextEdit { background: #111827; color: #d1e7d9; border: 0; border-radius: 8px; padding: 9px; font-family: Consolas; font-size: 12px; }
            QCheckBox { spacing: 7px; }
        """)
