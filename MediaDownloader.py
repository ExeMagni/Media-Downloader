from src.controller import MusicDownloaderController
from src.model import MediaManager
from src.services.config_service import ConfigService
import os
import sys
from PySide6 import QtWidgets

from src.view_pyside import MusicDownloaderView

# TODO: Notificación del sistema al finalizar todas las descargas (opcional).


def get_spotify_credentials_qt(parent=None):
    # Lee si ya existen
    if os.path.exists("secret/spotify_secrets.txt"):
        with open("secret/spotify_secrets.txt") as f:
            return f.read().splitlines()

    QtWidgets.QMessageBox.information(
        parent,
        "Spotify API",
        "Ingrese por favor sus claves de Spotify API para obtener metadatos."
    )
    client_id, ok1 = QtWidgets.QInputDialog.getText(
        parent, "Spotify API", "Client ID:")
    client_secret, ok2 = QtWidgets.QInputDialog.getText(
        parent, "Spotify API", "Client Secret:")
    if ok1 and ok2 and client_id and client_secret:
        os.makedirs("secret", exist_ok=True)
        with open("secret/spotify_secrets.txt", "w") as f:
            f.write(f"{client_id}\n{client_secret}")
        return [client_id, client_secret]
    else:
        continuar = QtWidgets.QMessageBox.question(
            parent,
            "Continuar sin datos",
            "¿Desea continuar sin claves de Spotify? No se obtendrán metadatos.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes,
        )
        if continuar == QtWidgets.QMessageBox.Yes:
            return [None, None]
        else:
            sys.exit(0)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)

    # Pedir credenciales con cuadros de diálogo Qt
    client_id, client_secret = get_spotify_credentials_qt()

    model = MediaManager()
    config_service = ConfigService()
    controller = MusicDownloaderController(
        model,
        client_id,
        client_secret,
        enable_spotify=False,
        enable_cover=False,
        enable_youtube=True,
        config_service=config_service,
    )
    # Cargar preferencias guardadas
    controller.load_search_preferences()

    # Crear la ventana principal (la vista se encargará de mostrarla)
    view = MusicDownloaderView(controller)
    view.show()

    # Finalizar correctamente tareas activas al cerrar la aplicación
    app.aboutToQuit.connect(controller.cancel_all_downloads)

    sys.exit(app.exec())
