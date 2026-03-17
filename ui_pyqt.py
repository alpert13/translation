import os
import sys
import json
from collections import deque
from typing import Deque, Dict, List, Optional

from PyQt6.QtCore import QThread, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QColor, QFont, QFontDatabase, QTextBlockFormat, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import data
from config import (
    batch_config,
    coi_config,
    coi_deepseek_config,
    deepseek_config,
    sequential_config,
)
from main import get_provider
from translator import TranslatorCore


CONFIG_OPTIONS: Dict[str, dict] = {
    "LOTM - Gemini Sequential": sequential_config,
    "LOTM - Gemini Batch Config (run single chapter in UI)": batch_config,
    "LOTM - DeepSeek": deepseek_config,
    "COI - Gemini": coi_config,
    "COI - DeepSeek": coi_deepseek_config,
}


def build_translator(config_name: str) -> TranslatorCore:
    cfg = dict(CONFIG_OPTIONS[config_name])
    provider = get_provider(cfg)
    return TranslatorCore(cfg, provider)


def get_output_path(translator: TranslatorCore, chapter_id: int) -> str:
    return os.path.join(translator.output_dir, f"Chapter_{chapter_id}.txt")


class TranslationWorker(QThread):
    started_chapter = pyqtSignal(int)
    stream_chunk = pyqtSignal(int, str)
    finished_chapter = pyqtSignal(int, str, str)
    failed_chapter = pyqtSignal(int, str)

    def __init__(self, translator: TranslatorCore, chapter: dict):
        super().__init__()
        self.translator = translator
        self.chapter = chapter

    def run(self) -> None:
        chapter_id = int(self.chapter["chapter_id"])
        self.started_chapter.emit(chapter_id)
        raw_chunks: List[str] =[]

        try:
            for chunk in self.translator.translate_chapter_stream(self.chapter):
                raw_chunks.append(chunk)
                self.stream_chunk.emit(chapter_id, chunk)

            translation_raw = "".join(raw_chunks)
            saved_path = self.translator.process_and_save_translation(chapter_id, translation_raw)
            self.finished_chapter.emit(chapter_id, saved_path, translation_raw)
        except Exception as exc:
            self.failed_chapter.emit(chapter_id, str(exc))


class TranslatorWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Novel Translator (PyQt Stream)")
        self.resize(1300, 850)

        self.settings_path = os.path.join(os.path.dirname(__file__), "ui_settings.json")
        self.config_name: str = "COI - DeepSeek"

        self.auto_translate_enabled = True
        self.auto_translate_ahead = 3
        self.read_mode = "vi"
        self.last_chapter_id: Optional[int] = None
        self.last_scroll_value = 0

        self.font_family = "Consolas"
        self.font_size = 13
        self.text_margin = 14
        self.row_height_percent = 140
        self.bg_color = "#111111"
        self.text_color = "#EAEAEA"
        self.font_family_options = sorted(QFontDatabase.families())
        if not self.font_family_options:
            self.font_family_options =[
                "Consolas",
                "Cascadia Code",
                "JetBrains Mono",
                "Segoe UI",
                "Times New Roman",
                "Arial",
            ]
        if self.font_family not in self.font_family_options:
            self.font_family = self.font_family_options[0]
        self.font_size_options =[10, 11, 12, 13, 14, 15, 16, 18, 20, 24, 28, 32]
        self.row_height_options =[100, 110, 120, 130, 140, 150, 160, 180, 200, 220]

        self._load_settings()
        self._normalize_loaded_settings()
        
        self.translator: Optional[TranslatorCore] = None

        self.chapters: List[dict] =[]
        self.chapter_map: Dict[int, dict] = {}
        self.chapter_ids: List[int] = []

        self.selected_chapter_id: Optional[int] = None
        self.current_worker: Optional[TranslationWorker] = None
        self.current_job_id: Optional[int] = None
        self.stream_buffers: Dict[int, str] = {}
        
        self.job_queue: Deque[int] = deque()
        self.job_total_chapters = 0
        self.job_completed_chapters = 0
        self.auto_queue: Deque[int] = deque()
        
        self._pending_restore_position = True

        self.chapter_label = QLabel("Chapter: -")
        self.meta_label = QLabel("Source length: -")
        self.mode_toggle_button = QPushButton("VI")

        self.reader_box = QTextEdit()
        self.reader_box.setReadOnly(True)
        self.reader_box.setPlaceholderText("Chapter text appears here")

        self._build_layout()
        self._build_menus()
        self._update_mode_button()
        self._apply_text_style()
        self._render_empty()
        
        self._show_status("Initializing... Please wait.")

        # DEFER loading so the main window can render and show up immediately
        QTimer.singleShot(0, self._post_init)

    def _post_init(self) -> None:
        try:
            self.translator = build_translator(self.config_name)
        except Exception as exc:
            QMessageBox.critical(self, "Initialization Error", f"Cannot build translator:\n{exc}")
            self._show_status("Initialization Failed")
            return
            
        self._reload_chapters(reset_selection=True)
        self._show_status("Ready")

    def _build_layout(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)
        root.addWidget(self.chapter_label)
        root.addWidget(self.meta_label)
        root.addWidget(self.reader_box, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #333333;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 3px;
            }
        """)
        root.addWidget(self.progress_bar)

        self.setCentralWidget(central)

    def _load_settings(self) -> None:
        if not os.path.exists(self.settings_path):
            return

        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except Exception:
            return

        if not isinstance(settings, dict):
            return

        try:
            self.config_name = str(settings.get("config_name", self.config_name))
            self.auto_translate_enabled = bool(
                settings.get("auto_translate_enabled", self.auto_translate_enabled)
            )
            self.auto_translate_ahead = int(
                settings.get("auto_translate_ahead", self.auto_translate_ahead)
            )
            self.read_mode = str(settings.get("read_mode", self.read_mode))
            self.font_family = str(settings.get("font_family", self.font_family))
            self.font_size = int(settings.get("font_size", self.font_size))
            self.text_margin = int(settings.get("text_margin", self.text_margin))
            self.row_height_percent = int(
                settings.get("row_height_percent", self.row_height_percent)
            )
            self.bg_color = str(settings.get("bg_color", self.bg_color))
            self.text_color = str(settings.get("text_color", self.text_color))
            chapter_value = settings.get("last_chapter_id", self.last_chapter_id)
            self.last_chapter_id = int(chapter_value) if chapter_value is not None else None
            self.last_scroll_value = int(
                settings.get("last_scroll_value", self.last_scroll_value)
            )
        except (TypeError, ValueError):
            return

    def _save_settings(self) -> None:
        settings = {
            "config_name": self.config_name,
            "auto_translate_enabled": self.auto_translate_enabled,
            "auto_translate_ahead": self.auto_translate_ahead,
            "read_mode": self.read_mode,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "text_margin": self.text_margin,
            "row_height_percent": self.row_height_percent,
            "bg_color": self.bg_color,
            "text_color": self.text_color,
            "last_chapter_id": self.selected_chapter_id,
            "last_scroll_value": self._get_reader_scroll_value(),
        }

        try:
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            self._show_status(f"Cannot save settings: {exc}")

    def _normalize_loaded_settings(self) -> None:
        if self.config_name not in CONFIG_OPTIONS:
            self.config_name = "COI - DeepSeek"

        self.read_mode = "en" if self.read_mode == "en" else "vi"
        self.auto_translate_ahead = max(1, min(50, int(self.auto_translate_ahead)))
        self.font_size = max(8, min(72, int(self.font_size)))
        self.text_margin = max(0, min(120, int(self.text_margin)))
        self.last_scroll_value = max(0, int(self.last_scroll_value))

        if self.row_height_percent not in self.row_height_options:
            self.row_height_percent = 140

    def _build_menus(self) -> None:
        menu = self.menuBar()
        if menu is None:
            return

        config_menu = menu.addMenu("Config")
        if config_menu is None:
            return
        self.config_menu = config_menu
        self.config_group = QActionGroup(self)
        self.config_group.setExclusive(True)

        for name in CONFIG_OPTIONS:
            action = QAction(name, self)
            action.setCheckable(True)
            action.setChecked(name == self.config_name)
            action.triggered.connect(lambda checked, n=name: self._change_config(n))
            self.config_group.addAction(action)
            config_menu.addAction(action)

        chapter_menu = menu.addMenu("Chapter")
        if chapter_menu is None:
            return

        select_action = QAction("Select Chapter...", self)
        select_action.triggered.connect(self._select_chapter_dialog)
        chapter_menu.addAction(select_action)

        next_action = QAction("Next Chapter", self)
        next_action.setShortcut("Ctrl+Right")
        next_action.triggered.connect(self._go_next_chapter)
        chapter_menu.addAction(next_action)

        prev_action = QAction("Previous Chapter", self)
        prev_action.setShortcut("Ctrl+Left")
        prev_action.triggered.connect(self._go_prev_chapter)
        chapter_menu.addAction(prev_action)

        first_untranslated_action = QAction("Jump To First Untranslated", self)
        first_untranslated_action.triggered.connect(self._jump_first_untranslated)
        chapter_menu.addAction(first_untranslated_action)

        translate_menu = menu.addMenu("Translate")
        if translate_menu is None:
            return

        translate_current_action = QAction("Translate Selected (Stream)", self)
        translate_current_action.setShortcut("Ctrl+T")
        translate_current_action.triggered.connect(self._translate_selected)
        translate_menu.addAction(translate_current_action)

        translate_range_action = QAction("Translate Range...", self)
        translate_range_action.triggered.connect(self._translate_range_dialog)
        translate_menu.addAction(translate_range_action)

        stop_action = QAction("Stop Current Job", self)
        stop_action.triggered.connect(self._stop_current_job)
        translate_menu.addAction(stop_action)

        self.auto_toggle_action = QAction("Enable Auto Translate Ahead", self)
        self.auto_toggle_action.setCheckable(True)
        self.auto_toggle_action.setChecked(self.auto_translate_enabled)
        self.auto_toggle_action.triggered.connect(self._toggle_auto_translate)
        translate_menu.addAction(self.auto_toggle_action)

        ahead_action = QAction("Set Auto Ahead Count...", self)
        ahead_action.triggered.connect(self._set_auto_ahead_count)
        translate_menu.addAction(ahead_action)

        view_menu = menu.addMenu("View")
        if view_menu is None:
            return

        reload_action = QAction("Reload Chapters", self)
        reload_action.triggered.connect(lambda: self._reload_chapters(reset_selection=False))
        view_menu.addAction(reload_action)

        open_output_action = QAction("Open Output Folder", self)
        open_output_action.triggered.connect(self._open_output_folder)
        view_menu.addAction(open_output_action)

        text_menu = menu.addMenu("Text")
        if text_menu is None:
            return

        font_action = QAction("Set Font Family...", self)
        font_action.triggered.connect(self._set_font_family)
        text_menu.addAction(font_action)

        font_size_action = QAction("Set Font Size...", self)
        font_size_action.triggered.connect(self._set_font_size)
        text_menu.addAction(font_size_action)

        margin_action = QAction("Set Text Margin...", self)
        margin_action.triggered.connect(self._set_text_margin)
        text_menu.addAction(margin_action)

        row_height_action = QAction("Set Row Height...", self)
        row_height_action.triggered.connect(self._set_row_height)
        text_menu.addAction(row_height_action)

        bg_color_action = QAction("Set Background Color...", self)
        bg_color_action.triggered.connect(self._set_bg_color)
        text_menu.addAction(bg_color_action)

        text_color_action = QAction("Set Text Color...", self)
        text_color_action.triggered.connect(self._set_text_color)
        text_menu.addAction(text_color_action)

        self.mode_toggle_button.setToolTip("Toggle reading mode: VI/EN")
        self.mode_toggle_button.setFixedWidth(60)
        self.mode_toggle_button.clicked.connect(self._toggle_read_mode)
        menu.setCornerWidget(self.mode_toggle_button, Qt.Corner.TopRightCorner)

    def _change_config(self, config_name: str) -> None:
        if config_name == self.config_name:
            return

        if self.current_worker is not None and self.current_worker.isRunning():
            QMessageBox.warning(
                self,
                "Busy",
                "Stop the current translation before changing config.",
            )
            return

        self.config_name = config_name
        self.translator = build_translator(self.config_name)
        self.auto_queue.clear()
        self.job_queue.clear()
        self.progress_bar.setVisible(False)
        self.job_total_chapters = 0
        self.job_completed_chapters = 0
        self._save_settings()
        self._reload_chapters(reset_selection=True)
        self._show_status(f"Loaded config: {self.config_name}")

    def _reload_chapters(self, reset_selection: bool) -> None:
        if not self.translator: return
            
        try:
            self.chapters = data.load_chapters(self.translator.pickle_file)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Cannot load chapters: {exc}")
            self.chapters =[]
            self.chapter_map = {}
            self.chapter_ids =[]
            self.selected_chapter_id = None
            self._render_empty()
            return

        if not self.chapters:
            QMessageBox.information(self, "No data", "No chapters found.")
            self.chapter_map = {}
            self.chapter_ids =[]
            self.selected_chapter_id = None
            self._render_empty()
            return

        self.chapter_map = {int(ch["chapter_id"]): ch for ch in self.chapters}
        self.chapter_ids = sorted(self.chapter_map.keys())

        if reset_selection or self.selected_chapter_id not in self.chapter_map:
            if self.last_chapter_id in self.chapter_map:
                self.selected_chapter_id = self.last_chapter_id
            else:
                self.selected_chapter_id = self.chapter_ids[0]

        self._render_selected_chapter()
        self._refresh_auto_queue()
        self._start_next_queued_translation()

    def _render_empty(self) -> None:
        self.chapter_label.setText("Chapter: -")
        self.meta_label.setText("Source length: -")
        self._set_reader_text("")

    def _load_saved_translation(self, chapter_id: int) -> str:
        if not self.translator: return ""
        output_path = get_output_path(self.translator, chapter_id)
        if not os.path.exists(output_path):
            return ""
        with open(output_path, "r", encoding="utf-8") as f:
            return f.read()

    def _render_reader_content(self) -> None:
        if self.selected_chapter_id is None:
            self._set_reader_text("")
            return

        chapter = self.chapter_map[self.selected_chapter_id]
        source_text = str(chapter.get("text", ""))

        if self.read_mode == "en":
            self._set_reader_text(source_text)
            self._show_status("Showing English source")
            return

        stream_preview = self.stream_buffers.get(self.selected_chapter_id, "")
        if stream_preview and self.current_job_id == self.selected_chapter_id and self.current_worker is not None:
            self._set_reader_text(stream_preview)
            self._show_status("Showing Vietnamese translation (streaming)")
            return

        translated = self._load_saved_translation(self.selected_chapter_id)
        if translated:
            self._set_reader_text(translated)
            self._show_status("Showing Vietnamese translation")
        else:
            self._set_reader_text(stream_preview)
            self._show_status("No Vietnamese translation yet")

    def _update_mode_button(self) -> None:
        self.mode_toggle_button.setText("VI" if self.read_mode == "vi" else "EN")

    def _toggle_read_mode(self) -> None:
        self.read_mode = "en" if self.read_mode == "vi" else "vi"
        self._update_mode_button()
        self._save_settings()
        self._render_reader_content()

    def _render_selected_chapter(self) -> None:
        if self.selected_chapter_id is None:
            self._render_empty()
            return

        chapter = self.chapter_map[self.selected_chapter_id]
        title = str(chapter.get("title", ""))
        source_text = str(chapter.get("text", ""))

        self.chapter_label.setText(
            f"Chapter {self.selected_chapter_id}: {title}"
        )
        self.meta_label.setText(f"Source length: {len(source_text):,} chars")
        self._render_reader_content()

        if self._pending_restore_position and self.selected_chapter_id == self.last_chapter_id:
            QTimer.singleShot(0, self._restore_last_reader_position)
            return

        if self._pending_restore_position:
            self._pending_restore_position = False

        self._save_settings()

    def _get_reader_scroll_value(self) -> int:
        scroll_bar = self.reader_box.verticalScrollBar()
        if scroll_bar is None:
            return 0
        return int(scroll_bar.value())

    def _restore_last_reader_position(self) -> None:
        self._pending_restore_position = False
        scroll_bar = self.reader_box.verticalScrollBar()
        if scroll_bar is None:
            return

        target = max(scroll_bar.minimum(), min(self.last_scroll_value, scroll_bar.maximum()))
        scroll_bar.setValue(target)
        self._save_settings()

    def _show_status(self, message: str) -> None:
        status_bar = self.statusBar()
        if status_bar is not None:
            status_bar.showMessage(message)

    def _select_chapter_dialog(self) -> None:
        if not self.chapter_ids:
            return

        current = self.selected_chapter_id or self.chapter_ids[0]
        value, ok = QInputDialog.getInt(
            self,
            "Select Chapter",
            "Chapter ID:",
            current,
            min(self.chapter_ids),
            max(self.chapter_ids),
            1,
        )
        if not ok:
            return

        if value not in self.chapter_map:
            QMessageBox.warning(self, "Not found", f"Chapter {value} not available.")
            return

        self.selected_chapter_id = value
        self._render_selected_chapter()
        self._refresh_auto_queue()
        self._start_next_queued_translation()

    def _go_next_chapter(self) -> None:
        if self.selected_chapter_id is None:
            return

        idx = self.chapter_ids.index(self.selected_chapter_id)
        if idx < len(self.chapter_ids) - 1:
            self.selected_chapter_id = self.chapter_ids[idx + 1]
            self._render_selected_chapter()
            self._refresh_auto_queue()
            self._start_next_queued_translation()

    def _go_prev_chapter(self) -> None:
        if self.selected_chapter_id is None:
            return

        idx = self.chapter_ids.index(self.selected_chapter_id)
        if idx > 0:
            self.selected_chapter_id = self.chapter_ids[idx - 1]
            self._render_selected_chapter()
            self._refresh_auto_queue()
            self._start_next_queued_translation()

    def _jump_first_untranslated(self) -> None:
        if not self.translator: return
            
        for chapter_id in self.chapter_ids:
            if not os.path.exists(get_output_path(self.translator, chapter_id)):
                self.selected_chapter_id = chapter_id
                self._render_selected_chapter()
                self._refresh_auto_queue()
                self._start_next_queued_translation()
                return

        QMessageBox.information(self, "Info", "All chapters already translated.")

    def _is_translated(self, chapter_id: int) -> bool:
        if not self.translator: return False
        return os.path.exists(get_output_path(self.translator, chapter_id))

    def _translate_selected(self) -> None:
        if self.selected_chapter_id is None:
            return

        if self._is_translated(self.selected_chapter_id):
            self._render_selected_chapter()
            QMessageBox.information(self, "Info", "Selected chapter is already translated.")
            return

        if self.current_worker is None:
            self._start_translation(self.selected_chapter_id)
            return

        if self.current_job_id == self.selected_chapter_id:
            self._show_status("Selected chapter is currently translating")
            return

        if self.selected_chapter_id in self.job_queue:
            self.job_queue.remove(self.selected_chapter_id)
        self.job_queue.appendleft(self.selected_chapter_id)
        
        if self.job_total_chapters > 0:
            self.job_total_chapters += 1
            self.progress_bar.setMaximum(self.job_total_chapters)
        else:
            self.job_total_chapters = 1
            self.job_completed_chapters = 0
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)

        self._show_status(
            f"Queued selected chapter {self.selected_chapter_id} as next job"
        )

    def _translate_range_dialog(self) -> None:
        if not self.chapter_ids:
            QMessageBox.warning(self, "No chapters", "No chapters available.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Translate Range")
        layout = QFormLayout(dialog)

        start_spin = QSpinBox(dialog)
        start_spin.setRange(min(self.chapter_ids), max(self.chapter_ids))
        start_spin.setValue(self.selected_chapter_id or min(self.chapter_ids))

        end_spin = QSpinBox(dialog)
        end_spin.setRange(min(self.chapter_ids), max(self.chapter_ids))
        end_spin.setValue(max(self.chapter_ids))

        layout.addRow("Start Chapter:", start_spin)
        layout.addRow("End Chapter:", end_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec():
            start = start_spin.value()
            end = end_spin.value()
            if start > end:
                start, end = end, start

            chapters_to_translate =[
                cid for cid in self.chapter_ids 
                if start <= cid <= end and not self._is_translated(cid)
            ]
            
            if not chapters_to_translate:
                QMessageBox.information(self, "Info", "All chapters in this range are already translated.")
                return

            self.job_queue = deque(chapters_to_translate)
            self.job_total_chapters = len(chapters_to_translate)
            self.job_completed_chapters = 0

            self.progress_bar.setRange(0, self.job_total_chapters)
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)

            self._show_status(f"Queued {self.job_total_chapters} chapters for translation.")

            if self.current_worker is None:
                self._start_next_queued_translation()

    def _start_translation(self, chapter_id: int) -> None:
        if self.current_worker is not None or not self.translator:
            return

        if self._is_translated(chapter_id):
            return

        chapter = self.chapter_map.get(chapter_id)
        if chapter is None:
            return

        self.current_job_id = chapter_id
        self.current_worker = TranslationWorker(self.translator, chapter)
        self.current_worker.started_chapter.connect(self._on_worker_started)
        self.current_worker.stream_chunk.connect(self._on_worker_stream_chunk)
        self.current_worker.finished_chapter.connect(self._on_worker_finished)
        self.current_worker.failed_chapter.connect(self._on_worker_failed)
        self.current_worker.finished.connect(self._cleanup_worker)
        self.stream_buffers[chapter_id] = ""

        if self.selected_chapter_id == chapter_id and self.read_mode == "vi":
            self._set_reader_text("")

        self.current_worker.start()

    def _on_worker_started(self, chapter_id: int) -> None:
        msg = f"Streaming Chapter {chapter_id}..."
        if self.job_total_chapters > 0:
            msg += f" (Job Progress: {self.job_completed_chapters}/{self.job_total_chapters})"
        self._show_status(msg)

    def _on_worker_stream_chunk(self, chapter_id: int, chunk: str) -> None:
        self.stream_buffers[chapter_id] = self.stream_buffers.get(chapter_id, "") + chunk

        if chapter_id != self.selected_chapter_id or self.read_mode != "vi":
            return
            
        self.reader_box.moveCursor(QTextCursor.MoveOperation.End)
        self.reader_box.insertPlainText(chunk)

    def _on_worker_finished(self, chapter_id: int, saved_path: str, _raw: str) -> None:
        self.stream_buffers.pop(chapter_id, None)

        if chapter_id == self.selected_chapter_id and self.read_mode == "vi":
            with open(saved_path, "r", encoding="utf-8") as f:
                self._set_reader_text(f.read())

        self._show_status(f"Done Chapter {chapter_id}. Saved to {saved_path}")

        if self.job_total_chapters > 0:
            self._increment_job_progress()

        self._refresh_auto_queue()

    def _increment_job_progress(self) -> None:
        self.job_completed_chapters += 1
        self.progress_bar.setValue(self.job_completed_chapters)
        if self.job_completed_chapters >= self.job_total_chapters:
            self.progress_bar.setVisible(False)
            self.job_total_chapters = 0
            self.job_completed_chapters = 0
            self._show_status("Range translation job completed.")

    def _on_worker_failed(self, chapter_id: int, error_msg: str) -> None:
        self._show_status(f"Translation failed on Chapter {chapter_id}")
        self.job_queue.clear()
        self.progress_bar.setVisible(False)
        self.job_total_chapters = 0
        self.job_completed_chapters = 0
        QMessageBox.critical(
            self,
            "Translation failed",
            f"Chapter {chapter_id} failed:\n{error_msg}\n\nQueue stopped.",
        )

    def _cleanup_worker(self) -> None:
        self.current_worker = None
        self.current_job_id = None
        self._start_next_queued_translation()

    def _stop_current_job(self) -> None:
        worker = self.current_worker
        if worker is None:
            QMessageBox.information(self, "Info", "No running job.")
            return

        chapter_id = self.current_job_id

        self.current_worker = None
        self.current_job_id = None

        try:
            worker.finished.disconnect(self._cleanup_worker)
        except (TypeError, RuntimeError):
            pass

        worker.requestInterruption()
        if worker.isRunning():
            worker.terminate()
            worker.wait(3000)

        self.job_queue.clear()
        self.progress_bar.setVisible(False)
        self.job_total_chapters = 0
        self.job_completed_chapters = 0

        if chapter_id is not None:
            self._show_status(f"Stopped Chapter {chapter_id}")

        self._start_next_queued_translation()

    def _toggle_auto_translate(self, enabled: bool) -> None:
        self.auto_translate_enabled = enabled
        self._save_settings()
        if not enabled:
            self.auto_queue.clear()
            self._show_status("Auto translate ahead disabled")
            return

        self._show_status(
            f"Auto translate ahead enabled (next {self.auto_translate_ahead} chapters)"
        )
        self._refresh_auto_queue()
        self._start_next_queued_translation()

    def _set_auto_ahead_count(self) -> None:
        value, ok = QInputDialog.getInt(
            self,
            "Auto Translate Ahead",
            "Translate ahead chapters:",
            self.auto_translate_ahead,
            1,
            50,
            1,
        )
        if not ok:
            return

        self.auto_translate_ahead = value
        self._save_settings()
        self._show_status(
            f"Auto translate ahead set to {self.auto_translate_ahead}"
        )
        self._refresh_auto_queue()
        self._start_next_queued_translation()

    def _refresh_auto_queue(self) -> None:
        if not self.auto_translate_enabled:
            return

        if self.selected_chapter_id is None or not self.chapter_ids:
            return

        selected_index = self.chapter_ids.index(self.selected_chapter_id)
        ahead_ids = self.chapter_ids[selected_index:selected_index + self.auto_translate_ahead + 1]

        desired: List[int] =[]
        for chapter_id in ahead_ids:
            if chapter_id == self.current_job_id:
                continue
            if self._is_translated(chapter_id):
                continue
            if chapter_id in self.job_queue:
                continue
            desired.append(chapter_id)

        self.auto_queue = deque(desired)

    def _start_next_queued_translation(self) -> None:
        if self.current_worker is not None:
            return

        while self.job_queue:
            chapter_id = self.job_queue.popleft()
            if self._is_translated(chapter_id):
                if self.job_total_chapters > 0:
                    self._increment_job_progress()
                continue
            self._start_translation(chapter_id)
            return

        if self.progress_bar.isVisible():
            self.progress_bar.setVisible(False)
            self.job_total_chapters = 0
            self.job_completed_chapters = 0

        while self.auto_queue:
            chapter_id = self.auto_queue.popleft()
            if self._is_translated(chapter_id):
                continue
            self._start_translation(chapter_id)
            break

    def _open_output_folder(self) -> None:
        if not self.translator: return
            
        folder = self.translator.output_dir
        if not os.path.isdir(folder):
            os.makedirs(folder, exist_ok=True)

        try:
            os.startfile(os.path.abspath(folder))
        except Exception as exc:
            QMessageBox.warning(self, "Open folder failed", str(exc))

    def _apply_text_style(self) -> None:
        font = QFont(self.font_family, self.font_size)
        self.reader_box.setFont(font)
        document = self.reader_box.document()
        if document is not None:
            document.setDocumentMargin(float(self.text_margin))
        self.reader_box.setStyleSheet(
            f"QTextEdit {{ background-color: {self.bg_color}; color: {self.text_color}; }}"
        )
        self._apply_row_height()

    def _apply_row_height(self) -> None:
        document = self.reader_box.document()
        if document is None:
            return

        cursor = QTextCursor(document)
        cursor.select(QTextCursor.SelectionType.Document)
        block_format = QTextBlockFormat()
        block_format.setLineHeight(
            float(self.row_height_percent),
            QTextBlockFormat.LineHeightTypes.ProportionalHeight.value,
        )
        cursor.mergeBlockFormat(block_format)

    def _set_reader_text(self, text: str) -> None:
        self.reader_box.setPlainText(text)
        self._apply_row_height()

    def _set_font_family(self) -> None:
        current_index = 0
        if self.font_family in self.font_family_options:
            current_index = self.font_family_options.index(self.font_family)

        value, ok = QInputDialog.getItem(
            self,
            "Set Font Family",
            "Font family:",
            self.font_family_options,
            current_index,
            False,
        )
        if not ok:
            return

        self.font_family = value
        self._apply_text_style()
        self._save_settings()
        self._show_status(f"Font set to {self.font_family}")

    def _set_font_size(self) -> None:
        size_strings = [str(size) for size in self.font_size_options]
        current_index = 0
        if self.font_size in self.font_size_options:
            current_index = self.font_size_options.index(self.font_size)

        value, ok = QInputDialog.getItem(
            self,
            "Set Font Size",
            "Font size:",
            size_strings,
            current_index,
            False,
        )
        if not ok:
            return

        self.font_size = int(value)
        self._apply_text_style()
        self._save_settings()
        self._show_status(f"Font size set to {self.font_size}")

    def _set_text_margin(self) -> None:
        value, ok = QInputDialog.getInt(
            self,
            "Set Text Margin",
            "Margin (px):",
            self.text_margin,
            0,
            120,
            1,
        )
        if not ok:
            return

        self.text_margin = value
        self._apply_text_style()
        self._save_settings()
        self._show_status(f"Text margin set to {self.text_margin}px")

    def _set_row_height(self) -> None:
        row_height_strings =[str(value) for value in self.row_height_options]
        current_index = 0
        if self.row_height_percent in self.row_height_options:
            current_index = self.row_height_options.index(self.row_height_percent)

        value, ok = QInputDialog.getItem(
            self,
            "Set Row Height",
            "Row height (%):",
            row_height_strings,
            current_index,
            False,
        )
        if not ok:
            return

        self.row_height_percent = int(value)
        self._apply_row_height()
        self._save_settings()
        self._show_status(f"Row height set to {self.row_height_percent}%")

    def _set_bg_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.bg_color), self, "Select Background Color")
        if not color.isValid():
            return

        self.bg_color = color.name(QColor.NameFormat.HexRgb)
        self._apply_text_style()
        self._save_settings()
        self._show_status(f"Background color set to {self.bg_color}")

    def _set_text_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.text_color), self, "Select Text Color")
        if not color.isValid():
            return

        self.text_color = color.name(QColor.NameFormat.HexRgb)
        self._apply_text_style()
        self._save_settings()
        self._show_status(f"Text color set to {self.text_color}")

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._save_settings()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    window = TranslatorWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()