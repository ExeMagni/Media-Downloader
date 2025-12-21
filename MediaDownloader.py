from src.controller import MusicDownloaderController
from src.model import MediaManager
import os
import sys
from PySide6 import QtWidgets

from src.view_pyside import MusicDownloaderView

# TODO: Estaría bueno que se distingan cuántas canciones se están descargando en paralelo, y tener un progreso para cada una. Luego si, tener el progreso total. Limitemos a 5 canciones en paralelo, para evitar saturar el sistema (evaluar si es posible más).
# Note: En debug también se debe mostrar de qué hilo se está descargando cada canción.
# TODO: Agregar un Checkbox para habilitar o no la búsqueda en Spotify y descarga de carátulas
# TODO: Evitar que se pueda "Buscar" si se está descargando algo.
# FIXME: Cuando se tiene un error: ConnectionResetError(10054, 'An existing connection was forcibly closed by the remote host', None, 10054, None))
#! [ERROR] download_audio falló: ERROR:
#! [download] Got error: ("Connection broken: ConnectionResetError(10054, 'An existing connection was forcibly closed by the remote host', None, 10054, None)", ConnectionResetError(10054, 'An existing connection was forcibly closed by the remote host', None, 10054, None))
#! [ERROR] download_audio falló: ERROR:
#! [download] Got error: ("Connection broken: ConnectionResetError(10054, 'An existing connection was forcibly closed by the remote host', None, 10054, None)", ConnectionResetError(10054, 'An existing connection was forcibly closed by the remote host', None, 10054, None))
#! [DEBUG] [FixupM4a] Correcting container of "G:\Rock Nacional\La Secuencia Inicial -Soda Stereo-.m4a"
# ! Se debe manejar re intentando por segunda vez con ese mismo objetivo, si vuelve a fallar, se deberá mostrar cuando se termina el proceso las canciones que no se pudieron descargar.
# TODO: Opción para limpiar toda la lista de seleccionados
# TODO: Botón para cancelar la descarga en curso de manera segura
# FIXME: Al cerrar la aplicación no se termina el proceso, queda en segundo plano. Hay que asegurarse de cerrar todos los hilos y procesos al salir.


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
