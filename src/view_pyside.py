from PySide6 import QtCore, QtGui, QtWidgets
import os
import requests
from io import BytesIO
from PIL import Image
from PIL.ImageQt import ImageQt
import threading
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
            if self.title:
                if self.artist:
                    results = self.controller.search_by_artist_title(
                        self.artist, self.title)
                else:
                    results = self.controller.search(self.title)
            elif self.query:
                results = self.controller.search(self.query)
            else:
                self.error.emit(
                    "Ingrese un término de búsqueda, canción o artista.")
                return
            self.results.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class DownloadWorker(QtCore.QObject):
    progress = QtCore.Signal(object)
    finished = QtCore.Signal(bool, str)

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
            self.controller.download_multiple_songs(
                self.song_list, self.save_path, self.progress_hook)
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

        self.download_button = QtWidgets.QPushButton("Descargar")
        self.download_button.clicked.connect(self.download_thread)
        layout.addWidget(self.download_button)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QtWidgets.QLabel("")
        layout.addWidget(self.status_label)

        self.cover_label = QtWidgets.QLabel("Portada")
        self.cover_label.setFixedSize(140, 140)
        layout.addWidget(self.cover_label)

        self.log = QtWidgets.QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        # Internal state
        self.song_list = []
        self.controller.last_results = []
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
        self.controller.last_results = results
        for r in results:
            artist = r.get('artist', '')
            title = r.get('title', '')
            self.results_list.addItem(f"{artist} - {title}")
        self.search_button.setEnabled(True)

    def on_search_error(self, msg):
        QtWidgets.QMessageBox.critical(self, "Error", msg)
        self.search_button.setEnabled(True)

    def add_song(self, item=None):
        idx = self.results_list.currentRow()
        if idx < 0:
            QtWidgets.QMessageBox.warning(
                self, "Error", "Seleccione una canción de los resultados.")
            return
        result = self.controller.last_results[idx]
        fmt = 'mp3' if self.mp3_radio.isChecked() else 'mp4'
        display = f"({'MP3' if fmt == 'mp3' else 'MP4'}) {result.get('artist', '')} - {result.get('title', '')}"
        self.song_list.append({
            'artist': result.get('artist', ''),
            'title': result.get('title', ''),
            'format': fmt,
            'display': display
        })
        self.downloads_list.addItem(display)

    def remove_song(self, item=None):
        idx = self.downloads_list.currentRow()
        if idx >= 0:
            self.downloads_list.takeItem(idx)
            self.song_list.pop(idx)

    def select_all_results(self):
        results = getattr(self.controller, 'last_results', [])
        fmt = 'mp3' if self.mp3_radio.isChecked() else 'mp4'
        for r in results:
            display = f"({'MP3' if fmt == 'mp3' else 'MP4'}) {r.get('artist', '')} - {r.get('title', '')}"
            self.song_list.append({
                'artist': r.get('artist', ''),
                'title': r.get('title', ''),
                'format': fmt,
                'display': display
            })
            self.downloads_list.addItem(display)

    def download_thread(self):
        if not self.song_list:
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
            self.controller, list(self.song_list), save_path)
        self.download_thread_qt = QtCore.QThread()
        self.download_worker.moveToThread(self.download_thread_qt)
        self.download_worker.progress.connect(self.on_progress)
        self.download_worker.finished.connect(self.on_finished)
        self.download_thread_qt.started.connect(self.download_worker.run)
        self.download_thread_qt.start()
        self.threads.append(self.download_thread_qt)
        self.progress_bar.setVisible(True)
        self.append_log(f"Iniciando descarga en: {save_path}")

    def on_progress(self, info):
        status = info.get('status')
        if status == 'downloading':
            total = info.get('total_bytes') or info.get('total_bytes_estimate')
            downloaded = info.get('downloaded_bytes')
            if total and downloaded is not None:
                percent = int(downloaded * 100 / total)
                self.progress_bar.setValue(percent)
        elif status == 'finished':
            self.progress_bar.setValue(100)

    def on_finished(self, success, message):
        self.append_log(f"Finalizado: success={success} message={message}")
        self.progress_bar.setVisible(False)
        if hasattr(self, 'download_thread_qt') and self.download_thread_qt.isRunning():
            self.download_thread_qt.quit()
            self.download_thread_qt.wait()
