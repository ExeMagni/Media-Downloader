from src.controller import MusicDownloaderController
from src.model import MediaManager
import os
import sys
from PySide6 import QtWidgets

from src.view_pyside import MusicDownloaderView

# TODO: Mejorar la interfaz gráfica.
# TODO: Agregar un checkbox para habilitar/deshabilitar Spotify y descarga de carátulas.
# TODO: Bloquear "Buscar" mientras haya una descarga en curso.
# TODO: Botón para cancelar la descarga en curso de forma segura.
# TODO: Notificación del sistema al finalizar todas las descargas (opcional).
# FIXME: Reintentar descargas que fallen por errores transitorios de red.
# FIXME: Al cerrar la aplicación, finalizar correctamente hilos y tareas activas.


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
    # Deshabilitar búsquedas en Spotify y búsqueda/descarga de carátulas por ahora
    controller = MusicDownloaderController(model, client_id, client_secret,
                                           enable_spotify=False, enable_cover=False)

    # Crear la ventana principal (la vista se encargará de mostrarla)
    view = MusicDownloaderView(controller)
    view.show()

    sys.exit(app.exec())
