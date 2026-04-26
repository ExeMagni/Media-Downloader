import subprocess
import sys
from PySide6 import QtCore, QtGui, QtWidgets
import requests
from io import BytesIO
from PIL import Image
from PIL.ImageQt import ImageQt
import time


class SearchWorker(QtCore.QObject):
    results = QtCore.Signal(list)
    error = QtCore.Signal(str)
    finished = QtCore.Signal()

    def __init__(self, controller, query, artist, title):
        super().__init__()
        self.controller = controller
        self.query = query
        self.artist = artist
        self.title = title

    @QtCore.Slot()
    def run(self):
        try:
            results = self.controller.search_from_inputs(
                self.query, self.artist, self.title)
            self.results.emit(results)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


class CoverWorker(QtCore.QRunnable):
    class Signals(QtCore.QObject):
        finished = QtCore.Signal(QtGui.QImage, str)

    def __init__(self, url):
        super().__init__()
        self.url = url
        self.signals = self.Signals()

    def run(self):
        try:
            r = requests.get(self.url, timeout=5)
            r.raise_for_status()
            img = Image.open(BytesIO(r.content)).convert('RGBA')
            img = img.resize((140, 140))
            qimg = ImageQt(img)
            # Se copia la imagen para transferirla de manera segura al hilo principal
            self.signals.finished.emit(QtGui.QImage(qimg).copy(), self.url)
        except Exception:
            self.signals.finished.emit(QtGui.QImage(), self.url)


class DownloadWorker(QtCore.QObject):
    progress = QtCore.Signal(object)
    finished = QtCore.Signal(bool, str)
    log = QtCore.Signal(str)
    # Emitted when a file download starts: index, total, title
    file_started = QtCore.Signal(int, int, str)
    # Emitted for per-file progress: index, info_dict
    file_progress = QtCore.Signal(int, object)
    # Emit overall progress percent (0-100)
    overall_progress = QtCore.Signal(int)
    # Emit aggregate stats: completed, total, failed
    download_stats = QtCore.Signal(int, int, int)
    # Emitted when a file is completely finished (success/fail)
    file_done = QtCore.Signal(int, bool)

    def __init__(self, controller, song_list, save_path):
        super().__init__()
        self.controller = controller
        self.song_list = song_list
        self.save_path = save_path

    def progress_hook(self, info):
        # Emit the raw info dict to the GUI
        self.progress.emit(info)

    @QtCore.Slot()
    def run(self):
        try:
            start_time = time.time()
            # Pass the worker's log emitter as log_hook so controller forwards yt-dlp text output
            # Provide a per_file_hook so the UI knows which file is being downloaded and overall progress

            def per_file_hook(idx, total, title):
                # emit file started and overall percent (completed files / total)
                try:
                    self.file_started.emit(idx, total, title)
                except Exception:
                    pass

            # per-file progress hook: emit index + progress info
            def per_file_progress_hook(idx, info):
                try:
                    self.file_progress.emit(idx, info)
                except Exception:
                    pass

            # per-file done hook: update completion-based progress and failures count
            def per_file_done_hook(idx, total, completed, failed, ok, title, error_message):
                try:
                    self.file_done.emit(idx, ok)
                except Exception:
                    pass
                try:
                    pct = int((completed) / total * 100) if total > 0 else 0
                    self.overall_progress.emit(pct)
                except Exception:
                    pass
                try:
                    self.download_stats.emit(completed, total, failed)
                except Exception:
                    pass

            self.controller.download_multiple_songs(
                self.song_list, self.save_path, self.progress_hook,
                log_hook=self.log.emit, per_file_hook=per_file_hook,
                per_file_progress_hook=per_file_progress_hook,
                per_file_done_hook=per_file_done_hook)
            elapsed = time.time() - start_time
            self.finished.emit(True, f"Duración: {elapsed:.2f}s")
        except Exception as e:
            self.finished.emit(False, str(e))


class UpdateWorker(QtCore.QObject):
    finished = QtCore.Signal(bool, str)
    log = QtCore.Signal(str)

    @QtCore.Slot()
    def run(self):
        try:
            self.log.emit("[UPDATE] Iniciando actualización de yt-dlp...")
            cmd = [sys.executable, "-m", "pip", "install", "-U", "yt-dlp"]
            kwargs = {}
            # Evitar que se abra una ventana de consola extra en Windows
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True, **kwargs)
            self.log.emit(f"[UPDATE]\n{result.stdout}")
            self.finished.emit(
                True, "Motor de descarga (yt-dlp) actualizado correctamente.")
        except subprocess.CalledProcessError as e:
            error_msg = f"Error al actualizar: {e.stderr}"
            self.log.emit(f"[UPDATE ERROR]\n{error_msg}")
            self.finished.emit(False, error_msg)
        except Exception as e:
            self.finished.emit(False, str(e))


class MusicDownloaderView(QtWidgets.QMainWindow):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowTitle("Music Downloader")
        self.resize(900, 600)
        self.cover_cache = {}

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        grid = QtWidgets.QGridLayout()
        layout.addLayout(grid)

        self.search_entry = QtWidgets.QLineEdit()
        self.search_entry.setPlaceholderText("Buscar")
        self.song_entry = QtWidgets.QLineEdit()
        self.song_entry.setPlaceholderText("Canción")
        self.artist_entry = QtWidgets.QLineEdit()
        self.artist_entry.setPlaceholderText("Artista")
        self.youtube_search_checkbox = QtWidgets.QCheckBox(
            "Buscar en YouTube")
        self.youtube_search_checkbox.setChecked(
            self.controller.is_youtube_search_enabled())
        self.youtube_search_checkbox.setToolTip(
            "Incluye resultados de YouTube en la búsqueda")
        self.youtube_search_checkbox.stateChanged.connect(
            self._on_search_preferences_changed)

        self.spotify_search_checkbox = QtWidgets.QCheckBox(
            "Buscar en Spotify")
        self.spotify_search_checkbox.setChecked(
            self.controller.is_spotify_search_enabled())
        self.spotify_search_checkbox.setToolTip(
            "Incluye resultados de Spotify en la búsqueda")
        self.spotify_search_checkbox.stateChanged.connect(
            self._on_search_preferences_changed)

        self.cover_search_checkbox = QtWidgets.QCheckBox(
            "Busqueda con portada")
        self.cover_search_checkbox.setChecked(
            self.controller.is_cover_search_enabled())
        self.cover_search_checkbox.setToolTip(
            "Si está activo, intenta traer portada/thumbnail en los resultados")
        self.cover_search_checkbox.stateChanged.connect(
            self._on_search_preferences_changed)

        grid.addWidget(QtWidgets.QLabel("Buscar:"), 0, 0)
        grid.addWidget(self.search_entry, 0, 1)
        grid.addWidget(QtWidgets.QLabel("Canción:"), 1, 0)
        grid.addWidget(self.song_entry, 1, 1)
        grid.addWidget(QtWidgets.QLabel("Artista:"), 2, 0)
        grid.addWidget(self.artist_entry, 2, 1)

        self.search_button = QtWidgets.QPushButton("Buscar")
        self.search_button.clicked.connect(self.search_thread)
        grid.addWidget(self.search_button, 0, 2, 2, 1)

        self.clear_cache_button = QtWidgets.QPushButton("Limpiar caché")
        self.clear_cache_button.clicked.connect(self.clear_search_cache)
        grid.addWidget(self.clear_cache_button, 2, 2)

        grid.addWidget(self.youtube_search_checkbox, 3, 0)
        grid.addWidget(self.spotify_search_checkbox, 3, 1)
        grid.addWidget(self.cover_search_checkbox, 3, 2)

        self.cache_size_label = QtWidgets.QLabel("")
        grid.addWidget(self.cache_size_label, 4, 0, 1, 2)

        self.update_button = QtWidgets.QPushButton("Actualizar motor (yt-dlp)")
        self.update_button.setToolTip(
            "Actualiza yt-dlp para solucionar problemas de descarga")
        self.update_button.clicked.connect(self.update_ytdlp)
        grid.addWidget(self.update_button, 4, 2)

        # Results and downloads list
        lists_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(lists_layout)

        left_v = QtWidgets.QVBoxLayout()
        lists_layout.addLayout(left_v)

        left_header = QtWidgets.QHBoxLayout()
        left_header.addWidget(QtWidgets.QLabel("Resultados de búsqueda:"))
        legend_layout = QtWidgets.QHBoxLayout()
        legend_layout.setContentsMargins(10, 0, 0, 0)
        for source, color_hex in [("Spotify", "#1DB954"), ("YouTube", "#FF8C73"), ("Local", "#B0B0B0")]:
            color_box = QtWidgets.QFrame()
            color_box.setFixedSize(14, 14)
            color_box.setStyleSheet(f"background-color: {color_hex};")
            legend_layout.addWidget(color_box)
            legend_label = QtWidgets.QLabel(source)
            legend_label.setStyleSheet("font-size: 12px; margin-left: 2px;")
            legend_layout.addWidget(legend_label)
        legend_layout.addStretch()
        left_header.addLayout(legend_layout)
        left_v.addLayout(left_header)

        self.results_list = QtWidgets.QListWidget()
        left_v.addWidget(self.results_list)
        self.results_list.itemDoubleClicked.connect(self.add_song)
        self.results_list.currentRowChanged.connect(
            self.on_result_selection_changed)
        left_v.addStretch()

        mid_v = QtWidgets.QVBoxLayout()
        lists_layout.addLayout(mid_v)
        mid_v.addWidget(QtWidgets.QLabel("Formato:"))
        self.format_group = QtWidgets.QButtonGroup()
        self.mp3_radio = QtWidgets.QRadioButton("MP3")
        self.mp4_radio = QtWidgets.QRadioButton("MP4")
        self.mp3_radio.setChecked(True)
        self.format_group.addButton(self.mp3_radio)
        self.format_group.addButton(self.mp4_radio)
        mid_v.addWidget(self.mp3_radio)
        mid_v.addWidget(self.mp4_radio)
        mid_v.addStretch()

        right_v = QtWidgets.QVBoxLayout()
        lists_layout.addLayout(right_v)
        right_v.addWidget(QtWidgets.QLabel("Canciones a descargar:"))
        self.downloads_list = QtWidgets.QListWidget()
        right_v.addWidget(self.downloads_list)
        self.downloads_list.itemDoubleClicked.connect(self.remove_song)
        right_v.addStretch()

        btns_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(btns_layout)
        self.add_button = QtWidgets.QPushButton("Agregar")
        self.add_button.clicked.connect(self.add_song)
        btns_layout.addWidget(self.add_button)
        self.select_all_button = QtWidgets.QPushButton("Seleccionar todo")
        self.select_all_button.clicked.connect(self.select_all_results)
        btns_layout.addWidget(self.select_all_button)
        self.remove_button = QtWidgets.QPushButton("Eliminar")
        self.remove_button.clicked.connect(self.remove_song)
        btns_layout.addWidget(self.remove_button)
        self.clear_selected_button = QtWidgets.QPushButton(
            "Limpiar seleccionados")
        self.clear_selected_button.clicked.connect(self.clear_selected_songs)
        btns_layout.addWidget(self.clear_selected_button)

        self.download_button = QtWidgets.QPushButton("Descargar")
        self.download_button.clicked.connect(self.download_thread)
        layout.addWidget(self.download_button)

        # Per-item progress bars are shown in the downloads list; removed global progress bar

        # Overall progress: number of files completed / total
        self.overall_progress_bar = QtWidgets.QProgressBar()
        self.overall_progress_bar.setRange(0, 100)
        self.overall_progress_bar.setVisible(False)
        layout.addWidget(self.overall_progress_bar)

        self.current_file_label = QtWidgets.QLabel("")
        layout.addWidget(self.current_file_label)

        self.status_label = QtWidgets.QLabel("")
        layout.addWidget(self.status_label)

        self.cover_label = QtWidgets.QLabel("Portada")
        self.cover_label.setFixedSize(140, 140)
        self.cover_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.cover_label)

        self.log = QtWidgets.QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        # Internal state
        # Keep widgets and progress bars parallel to the download queue.
        self.download_item_widgets = []
        self.download_item_bars = []
        self.search_thread_qt = None
        self.download_thread_qt = None
        self.search_has_results = False
        self.search_completed_with_no_results = False
        self.current_search_results = []
        self._download_failed_count = 0
        self._download_total_count = 0

        self.search_feedback_timer = QtCore.QTimer(self)
        self.search_feedback_timer.setSingleShot(True)
        self.search_feedback_timer.timeout.connect(
            self._on_search_feedback_timeout)

        self.refresh_cache_size_label()

    @staticmethod
    def _source_label(source: str):
        normalized = (source or "").strip().lower()
        if normalized == "spotify":
            return "Spotify"
        if normalized == "youtube":
            return "YouTube"
        return "Local"

    @staticmethod
    def _source_color(source: str):
        normalized = (source or "").strip().lower()
        if normalized == "spotify":
            return QtGui.QColor("#1DB954")
        if normalized == "youtube":
            return QtGui.QColor("#FF8C73")
        return QtGui.QColor("#B0B0B0")

    @staticmethod
    def _format_bytes(bytes_size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} TB"

    def refresh_cache_size_label(self):
        try:
            bytes_size = self.controller.get_search_cache_size_bytes()
            formatted = self._format_bytes(bytes_size)
        except Exception:
            formatted = "0 B"
        self.cache_size_label.setText(f"Caché de búsquedas: {formatted}")

    def append_log(self, text: str):
        self.log.append(text)

    def _set_cover_placeholder(self, text: str):
        self.cover_label.clear()
        self.cover_label.setPixmap(QtGui.QPixmap())
        self.cover_label.setText(text)

    def show_cover(self, url):
        if not url:
            self._set_cover_placeholder('Sin imagen')
            return

        if url in self.cover_cache:
            self.cover_label.setPixmap(self.cover_cache[url])
            self.cover_label.setText("")
            return

        self._set_cover_placeholder('Cargando...')
        worker = CoverWorker(url)
        worker.signals.finished.connect(self._on_cover_downloaded)
        QtCore.QThreadPool.globalInstance().start(worker)

    def _on_cover_downloaded(self, qimage, url):
        if not qimage.isNull():
            pixmap = QtGui.QPixmap.fromImage(qimage)
            self.cover_cache[url] = pixmap

        current_row = self.results_list.currentRow()
        if current_row >= 0 and current_row < len(self.current_search_results):
            if self.current_search_results[current_row].get('cover_url') == url:
                if qimage.isNull():
                    self._set_cover_placeholder('Sin imagen')
                else:
                    self.cover_label.setPixmap(self.cover_cache[url])
                    self.cover_label.setText("")

    def on_result_selection_changed(self, row: int):
        if row < 0 or row >= len(self.current_search_results):
            self._set_cover_placeholder('Portada')
            return

        result = self.current_search_results[row]
        cover_url = result.get('cover_url', '')
        if not self.cover_search_checkbox.isChecked():
            self._set_cover_placeholder('Busqueda rapida (sin portada)')
            return

        if not cover_url:
            self._set_cover_placeholder('Sin imagen')
            return

        self.show_cover(cover_url)

    def _on_search_preferences_changed(self):
        """Guarda preferencias de búsqueda cuando cambian los checkboxes."""
        self.controller.set_youtube_search_enabled(
            self.youtube_search_checkbox.isChecked()
        )
        self.controller.set_spotify_search_enabled(
            self.spotify_search_checkbox.isChecked()
        )
        self.controller.set_cover_search_enabled(
            self.cover_search_checkbox.isChecked()
        )

    def search_thread(self):
        # Avoid stacking search threads if the previous one is still running.
        if self.search_thread_qt is not None and self.search_thread_qt.isRunning():
            self.status_label.setText("Buscando...")
            self.append_log("[BUSQUEDA] Ya hay una búsqueda en curso...")
            return

        if self.download_thread_qt is not None and self.download_thread_qt.isRunning():
            QtWidgets.QMessageBox.warning(
                self, "Descarga en curso", "No se puede buscar mientras hay una descarga en progreso.")
            return

        self.search_has_results = False
        self.search_completed_with_no_results = False

        self.search_button.setEnabled(False)
        self.youtube_search_checkbox.setEnabled(False)
        self.spotify_search_checkbox.setEnabled(False)
        self.cover_search_checkbox.setEnabled(False)
        # Indicar visualmente que se está realizando la búsqueda
        self.status_label.setText("Buscando...")
        self.search_button.setText("Buscando...")
        # Indicar búsqueda en curso mediante estado y cursor (no global progress bar)
        # Cambiar cursor a espera
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        query = self.search_entry.text().strip()
        title = self.song_entry.text().strip()
        artist = self.artist_entry.text().strip()
        youtube_enabled = self.youtube_search_checkbox.isChecked()
        spotify_enabled = self.spotify_search_checkbox.isChecked()
        cover_enabled = self.cover_search_checkbox.isChecked()
        self.controller.set_youtube_search_enabled(youtube_enabled)
        self.controller.set_spotify_search_enabled(spotify_enabled)
        self.controller.set_cover_search_enabled(cover_enabled)
        search_context = " | ".join(
            part for part in [
                f"Buscar: {query}" if query else "",
                f"Canción: {title}" if title else "",
                f"Artista: {artist}" if artist else "",
                f"YouTube: {'si' if youtube_enabled else 'no'}",
                f"Spotify: {'si' if spotify_enabled else 'no'}",
                f"Portada: {'si' if cover_enabled else 'no'}",
            ] if part
        )
        self.append_log(
            f"[BUSQUEDA] Buscando... {search_context or 'sin filtros'}")
        self.search_feedback_timer.start(10_000)

        self.search_worker = SearchWorker(
            self.controller, query, artist, title)
        self.search_thread_qt = QtCore.QThread()
        self.search_worker.moveToThread(self.search_thread_qt)
        self.search_worker.results.connect(self.on_search_results)
        self.search_worker.error.connect(self.on_search_error)
        self.search_worker.finished.connect(self._stop_search_thread)
        self.search_thread_qt.started.connect(self.search_worker.run)
        self.search_thread_qt.finished.connect(self.search_worker.deleteLater)
        self.search_thread_qt.finished.connect(
            self.search_thread_qt.deleteLater)
        self.search_thread_qt.start()

    def on_search_results(self, results):
        self.current_search_results = list(results or [])
        self.results_list.clear()
        for r in self.current_search_results:
            artist = r.get('artist', '')
            title = r.get('title', '')
            source_raw = r.get('source', '')
            source = self._source_label(source_raw)
            # Show only title when artist is empty (playlist fast-load case)
            if artist:
                text = f"[{source}] {artist} - {title}"
            else:
                text = f"[{source}] {title}"

            item = QtWidgets.QListWidgetItem(text)
            item.setForeground(self._source_color(source_raw))
            self.results_list.addItem(item)

        result_count = len(results)
        self.search_has_results = result_count > 0
        self.search_completed_with_no_results = result_count == 0

        # La búsqueda ya terminó: no debemos esperar el timeout para actualizar estado.
        self.search_feedback_timer.stop()
        if self.search_has_results:
            self.status_label.setText("")
        else:
            self.status_label.setText(
                "No se encontraron resultados en la búsqueda")

        self.append_log(
            f"[BUSQUEDA] Finalizada. Resultados encontrados: {result_count}")
        self.refresh_cache_size_label()
        # Restaurar estado de la UI tras la búsqueda
        self.search_button.setEnabled(True)
        self.youtube_search_checkbox.setEnabled(True)
        self.spotify_search_checkbox.setEnabled(True)
        self.cover_search_checkbox.setEnabled(True)
        self.search_button.setText("Buscar")
        if result_count > 0:
            self.results_list.setCurrentRow(0)
        else:
            self._set_cover_placeholder('Portada')
        # restore search UI state
        QtWidgets.QApplication.restoreOverrideCursor()

    def on_search_error(self, msg):
        self.search_feedback_timer.stop()
        QtWidgets.QMessageBox.critical(self, "Error", msg)
        self.append_log(f"[BUSQUEDA] Error: {msg}")
        self.refresh_cache_size_label()
        # Restaurar estado de la UI tras el error
        self.search_button.setEnabled(True)
        self.youtube_search_checkbox.setEnabled(True)
        self.spotify_search_checkbox.setEnabled(True)
        self.cover_search_checkbox.setEnabled(True)
        self.search_button.setText("Buscar")
        self.status_label.setText("Error en búsqueda")
        # restore search UI state
        QtWidgets.QApplication.restoreOverrideCursor()

    def _stop_search_thread(self):
        if self.search_thread_qt is not None and self.search_thread_qt.isRunning():
            self.search_thread_qt.quit()
            self.search_thread_qt.wait()
        self.search_thread_qt = None

    def _on_search_feedback_timeout(self):
        if self.search_has_results:
            self.status_label.setText("")
            return

        if self.search_thread_qt is not None and self.search_thread_qt.isRunning():
            self.status_label.setText(
                "La búsqueda está tardando más de lo normal...")
            return

        if self.search_completed_with_no_results:
            self.status_label.setText(
                "No se encontraron resultados en la búsqueda")

    def clear_search_cache(self):
        removed = self.controller.clear_search_cache()
        self.append_log(
            f"[CACHE] Caché limpiada. Entradas eliminadas: {removed}")
        self.status_label.setText("Caché limpiada")
        self.refresh_cache_size_label()

    def add_song(self, item=None):
        idx = self.results_list.currentRow()
        if idx < 0:
            QtWidgets.QMessageBox.warning(
                self, "Error", "Seleccione una canción de los resultados.")
            return
        fmt = 'mp3' if self.mp3_radio.isChecked() else 'mp4'
        try:
            queue_item = self.controller.add_result_to_download_queue(idx, fmt)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", str(e))
            return

        display = queue_item['display']
        # Create list item with embedded progress bar
        item = QtWidgets.QListWidgetItem()
        widget = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(widget)
        lbl = QtWidgets.QLabel(display)
        bar = QtWidgets.QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setFixedWidth(160)
        bar.setFormat("%p%")
        h.addWidget(lbl)
        h.addStretch()
        h.addWidget(bar)
        h.setContentsMargins(2, 2, 2, 2)
        item.setSizeHint(widget.sizeHint())
        self.downloads_list.addItem(item)
        self.downloads_list.setItemWidget(item, widget)
        self.download_item_widgets.append((item, widget))
        self.download_item_bars.append(bar)

    def remove_song(self, item=None):
        idx = self.downloads_list.currentRow()
        if idx >= 0:
            self.downloads_list.takeItem(idx)
            self.controller.remove_from_download_queue(idx)
            try:
                self.download_item_widgets.pop(idx)
            except Exception:
                pass
            try:
                self.download_item_bars.pop(idx)
            except Exception:
                pass

    def clear_selected_songs(self):
        # Remove all items from the downloads list and clear internal structures
        try:
            self.downloads_list.clear()
        except Exception:
            pass
        self.controller.clear_download_queue()
        # Clear model/state lists
        self.download_item_widgets.clear()
        self.download_item_bars.clear()

    def select_all_results(self):
        fmt = 'mp3' if self.mp3_radio.isChecked() else 'mp4'
        added_items = self.controller.add_all_results_to_download_queue(fmt)
        for queue_item in added_items:
            display = queue_item['display']
            item = QtWidgets.QListWidgetItem()
            widget = QtWidgets.QWidget()
            h = QtWidgets.QHBoxLayout(widget)
            lbl = QtWidgets.QLabel(display)
            bar = QtWidgets.QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setFixedWidth(160)
            bar.setFormat("%p%")
            h.addWidget(lbl)
            h.addStretch()
            h.addWidget(bar)
            h.setContentsMargins(2, 2, 2, 2)
            item.setSizeHint(widget.sizeHint())
            self.downloads_list.addItem(item)
            self.downloads_list.setItemWidget(item, widget)
            self.download_item_widgets.append((item, widget))
            self.download_item_bars.append(bar)

    def download_thread(self):
        if self.controller.get_download_queue_size() == 0:
            QtWidgets.QMessageBox.information(
                self, "Info", "No hay canciones para descargar.")
            return
        dlg = QtWidgets.QFileDialog(self)
        dlg.setFileMode(QtWidgets.QFileDialog.Directory)
        if dlg.exec() == QtWidgets.QFileDialog.Accepted:
            save_path = dlg.selectedFiles()[0]
        else:
            return

        self.download_worker = DownloadWorker(
            self.controller, self.controller.get_download_queue_snapshot(), save_path)
        self.download_thread_qt = QtCore.QThread()
        self.download_worker.moveToThread(self.download_thread_qt)
        self.download_worker.progress.connect(self.on_progress)
        # connect textual logs from yt-dlp to GUI log
        self.download_worker.log.connect(self.append_log)
        # connect per-file and overall progress signals
        self.download_worker.file_started.connect(self.on_file_started)
        self.download_worker.file_progress.connect(self.on_file_progress)
        self.download_worker.overall_progress.connect(self.on_overall_progress)
        self.download_worker.download_stats.connect(self.on_download_stats)
        self.download_worker.file_done.connect(self.on_file_done)
        self.download_worker.finished.connect(self.on_finished)
        self.download_thread_qt.started.connect(self.download_worker.run)
        self.download_thread_qt.start()
        self._download_failed_count = 0
        self._download_total_count = self.controller.get_download_queue_size()
        self.current_file_label.setText(
            f"Completadas 0/{self._download_total_count} | Errores: 0")
        self.overall_progress_bar.setVisible(True)
        self.overall_progress_bar.setValue(0)
        self.append_log(f"Iniciando descarga en: {save_path}")

    def on_progress(self, info):
        # Global raw progress hook is no longer used for a single global bar.
        # Per-file progress is handled via `file_progress` signal.
        return

    def on_file_started(self, idx, total, title):
        # idx is 0-based
        # Keep a short processing hint while aggregate stats are updated on completion.
        self.current_file_label.setText(
            f"Procesando {idx+1}/{total} | Errores: {self._download_failed_count}")
        self.overall_progress_bar.setVisible(True)
        # Ensure the corresponding per-item bar is reset/visible
        try:
            if idx < len(self.download_item_bars):
                self.download_item_bars[idx].setValue(0)
        except Exception:
            pass

    def on_overall_progress(self, percent):
        # percent 0-100
        self.overall_progress_bar.setValue(percent)

    def on_download_stats(self, completed, total, failed):
        self._download_failed_count = failed
        self._download_total_count = total
        self.current_file_label.setText(
            f"Completadas {completed}/{total} | Errores: {failed}")

    def on_file_progress(self, idx, info):
        # Update the specific per-item progress bar using info dict
        try:
            status = info.get('status')
            if status == 'downloading':
                total = info.get('total_bytes') or info.get(
                    'total_bytes_estimate')
                downloaded = info.get('downloaded_bytes')
                if total and downloaded is not None and total > 0:
                    percent = int(downloaded * 100 / total)
                    # Limitar a 99% mientras descarga; el 100% se fija al terminar todo el proceso.
                    percent = min(percent, 99)

                    if idx < len(self.download_item_bars):
                        bar = self.download_item_bars[idx]
                        # Prevenir que la barra retroceda en descargas multi-flujo
                        if percent > bar.value():
                            bar.setValue(percent)
            elif status == 'retrying':
                if idx < len(self.download_item_bars):
                    bar = self.download_item_bars[idx]
                    bar.setValue(0)
                    bar.setFormat("%p%")
        except Exception:
            pass

    def on_file_done(self, idx, ok):
        try:
            if idx < len(self.download_item_bars):
                bar = self.download_item_bars[idx]
                if ok:
                    bar.setValue(100)
                else:
                    bar.setFormat("Error")
        except Exception:
            pass

    def on_finished(self, success, message):
        self.append_log(f"Finalizado: success={success} message={message}")
        if self._download_total_count > 0:
            self.overall_progress_bar.setValue(100)
            if self._download_failed_count > 0:
                self.current_file_label.setText(
                    f"Finalizado con errores: {self._download_failed_count}/{self._download_total_count}")
            else:
                self.current_file_label.setText(
                    f"Finalizado OK: {self._download_total_count}/{self._download_total_count}")
        self.overall_progress_bar.setVisible(False)
        if not success:
            QtWidgets.QMessageBox.warning(
                self, "Descarga con errores", message)
        if hasattr(self, 'download_thread_qt') and self.download_thread_qt.isRunning():
            self.download_thread_qt.quit()
            self.download_thread_qt.wait()
        self.download_thread_qt = None

    def update_ytdlp(self):
        if hasattr(self, 'update_thread_qt') and self.update_thread_qt is not None and self.update_thread_qt.isRunning():
            return

        self.update_button.setEnabled(False)
        self.update_button.setText("Actualizando...")
        self.status_label.setText("Actualizando yt-dlp...")

        self.update_worker = UpdateWorker()
        self.update_thread_qt = QtCore.QThread()
        self.update_worker.moveToThread(self.update_thread_qt)

        self.update_worker.log.connect(self.append_log)
        self.update_worker.finished.connect(self.on_update_finished)
        self.update_worker.finished.connect(self.update_thread_qt.quit)
        self.update_worker.finished.connect(self.update_worker.deleteLater)
        self.update_thread_qt.finished.connect(
            self.update_thread_qt.deleteLater)

        self.update_thread_qt.started.connect(self.update_worker.run)
        self.update_thread_qt.start()

    def on_update_finished(self, success, message):
        self.update_button.setEnabled(True)
        self.update_button.setText("Actualizar motor (yt-dlp)")
        self.status_label.setText(
            "Actualización completada" if success else "Error en actualización")

        if success:
            QtWidgets.QMessageBox.information(self, "Actualización", message)
        else:
            QtWidgets.QMessageBox.warning(
                self, "Actualización", f"No se pudo actualizar:\n{message}")

    def closeEvent(self, event):
        self.search_feedback_timer.stop()
        self._stop_search_thread()
        if self.download_thread_qt is not None and self.download_thread_qt.isRunning():
            self.download_thread_qt.quit()
            self.download_thread_qt.wait()
        self.download_thread_qt = None
        if hasattr(self, 'update_thread_qt') and self.update_thread_qt is not None and self.update_thread_qt.isRunning():
            self.update_thread_qt.quit()
            self.update_thread_qt.wait()
        super().closeEvent(event)
