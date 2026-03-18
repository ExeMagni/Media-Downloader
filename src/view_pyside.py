from PySide6 import QtCore, QtGui, QtWidgets
import requests
from io import BytesIO
from PIL import Image
from PIL.ImageQt import ImageQt
import time


class SearchWorker(QtCore.QObject):
    results = QtCore.Signal(list)
    error = QtCore.Signal(str)

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
                try:
                    pct = int((idx) / total * 100) if total > 0 else 0
                    self.overall_progress.emit(pct)
                except Exception:
                    pass

            # per-file progress hook: emit index + progress info
            def per_file_progress_hook(idx, info):
                try:
                    self.file_progress.emit(idx, info)
                except Exception:
                    pass

            self.controller.download_multiple_songs(
                self.song_list, self.save_path, self.progress_hook,
                log_hook=self.log.emit, per_file_hook=per_file_hook,
                per_file_progress_hook=per_file_progress_hook)
            elapsed = time.time() - start_time
            self.finished.emit(True, f"Duración: {elapsed:.2f}s")
        except Exception as e:
            self.finished.emit(False, str(e))


class MusicDownloaderView(QtWidgets.QMainWindow):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowTitle("Music Downloader")
        self.resize(900, 600)

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

        grid.addWidget(QtWidgets.QLabel("Buscar:"), 0, 0)
        grid.addWidget(self.search_entry, 0, 1)
        grid.addWidget(QtWidgets.QLabel("Canción:"), 1, 0)
        grid.addWidget(self.song_entry, 1, 1)
        grid.addWidget(QtWidgets.QLabel("Artista:"), 2, 0)
        grid.addWidget(self.artist_entry, 2, 1)

        self.search_button = QtWidgets.QPushButton("Buscar")
        self.search_button.clicked.connect(self.search_thread)
        grid.addWidget(self.search_button, 0, 2, 3, 1)

        # Results and downloads list
        lists_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(lists_layout)

        left_v = QtWidgets.QVBoxLayout()
        lists_layout.addLayout(left_v)
        left_v.addWidget(QtWidgets.QLabel("Resultados de búsqueda:"))
        self.results_list = QtWidgets.QListWidget()
        left_v.addWidget(self.results_list)
        self.results_list.itemDoubleClicked.connect(self.add_song)

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
        layout.addWidget(self.cover_label)

        self.log = QtWidgets.QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        # Internal state
        # Keep widgets and progress bars parallel to the download queue.
        self.download_item_widgets = []
        self.download_item_bars = []
        self.threads = []

    def append_log(self, text: str):
        self.log.append(text)

    def show_cover(self, url):
        try:
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            img = Image.open(BytesIO(r.content)).convert('RGBA')
            img = img.resize((140, 140))
            qimg = ImageQt(img)
            pix = QtGui.QPixmap.fromImage(qimg)
            self.cover_label.setPixmap(pix)
        except Exception:
            self.cover_label.setText('Sin imagen')

    def search_thread(self):
        self.search_button.setEnabled(False)
        # Indicar visualmente que se está realizando la búsqueda
        self.status_label.setText("Buscando...")
        self.search_button.setText("Buscando...")
        # Indicar búsqueda en curso mediante estado y cursor (no global progress bar)
        # Cambiar cursor a espera
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        query = self.search_entry.text().strip()
        title = self.song_entry.text().strip()
        artist = self.artist_entry.text().strip()

        self.search_worker = SearchWorker(
            self.controller, query, artist, title)
        self.search_thread_qt = QtCore.QThread()
        self.search_worker.moveToThread(self.search_thread_qt)
        self.search_worker.results.connect(self.on_search_results)
        self.search_worker.error.connect(self.on_search_error)
        self.search_thread_qt.started.connect(self.search_worker.run)
        self.search_thread_qt.start()
        self.threads.append(self.search_thread_qt)

    def on_search_results(self, results):
        self.results_list.clear()
        for r in results:
            artist = r.get('artist', '')
            title = r.get('title', '')
            # Show only title when artist is empty (playlist fast-load case)
            if artist:
                self.results_list.addItem(f"{artist} - {title}")
            else:
                self.results_list.addItem(title)
        # Restaurar estado de la UI tras la búsqueda
        self.search_button.setEnabled(True)
        self.search_button.setText("Buscar")
        self.status_label.setText("")
        # restore search UI state
        QtWidgets.QApplication.restoreOverrideCursor()

    def on_search_error(self, msg):
        QtWidgets.QMessageBox.critical(self, "Error", msg)
        # Restaurar estado de la UI tras el error
        self.search_button.setEnabled(True)
        self.search_button.setText("Buscar")
        self.status_label.setText("")
        # restore search UI state
        QtWidgets.QApplication.restoreOverrideCursor()

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
        self.download_worker.finished.connect(self.on_finished)
        self.download_thread_qt.started.connect(self.download_worker.run)
        self.download_thread_qt.start()
        self.threads.append(self.download_thread_qt)
        self.append_log(f"Iniciando descarga en: {save_path}")

    def on_progress(self, info):
        # Global raw progress hook is no longer used for a single global bar.
        # Per-file progress is handled via `file_progress` signal.
        return

    def on_file_started(self, idx, total, title):
        # idx is 0-based
        # Show only progress count (do not display current file title)
        self.current_file_label.setText(f"Descargando {idx+1}/{total}")
        self.overall_progress_bar.setVisible(True)
        # represent completed files proportionally
        pct = int((idx) / total * 100) if total > 0 else 0
        self.overall_progress_bar.setValue(pct)
        # Ensure the corresponding per-item bar is reset/visible
        try:
            if idx < len(self.download_item_bars):
                self.download_item_bars[idx].setValue(0)
        except Exception:
            pass

    def on_overall_progress(self, percent):
        # percent 0-100
        self.overall_progress_bar.setValue(percent)

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
                    if idx < len(self.download_item_bars):
                        self.download_item_bars[idx].setValue(percent)
            elif status == 'finished':
                if idx < len(self.download_item_bars):
                    self.download_item_bars[idx].setValue(100)
        except Exception:
            pass

    def on_finished(self, success, message):
        self.append_log(f"Finalizado: success={success} message={message}")
        self.overall_progress_bar.setVisible(False)
        self.current_file_label.setText("")
        if hasattr(self, 'download_thread_qt') and self.download_thread_qt.isRunning():
            self.download_thread_qt.quit()
            self.download_thread_qt.wait()
