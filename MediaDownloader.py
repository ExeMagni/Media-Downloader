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
# FIXME: [DEBUG] [youtube] OPOsBv_O3uo: Downloading webpage
#! [WARNING] [youtube] Skipping unsupported client "w"
#! [WARNING] [youtube] Skipping unsupported client "e"
#! [WARNING] [youtube] Skipping unsupported client "b"
#! [WARNING] [youtube] Skipping unsupported client "_"
#! [WARNING] [youtube] Skipping unsupported client "h"
#! [WARNING] [youtube] Skipping unsupported client "t"
#! [WARNING] [youtube] Skipping unsupported client "m"
#! [WARNING] [youtube] Skipping unsupported client "l"
#! [WARNING] [youtube] Skipping unsupported client "5"
#! [WARNING] [youtube] No supported JavaScript runtime could be found. Only deno is enabled by default; to use another runtime add  --js-runtimes RUNTIME[:PATH]  to your command/config. YouTube extraction without a JS runtime has been deprecated, and some formats may be missing. See  https://github.com/yt-dlp/yt-dlp/wiki/EJS  for details on installing one
#! [DEBUG] [youtube] OPOsBv_O3uo: Downloading android sdkless player API JSON
#! [DEBUG] [youtube] OPOsBv_O3uo: Downloading web safari player API JSON
#! [WARNING] [youtube] OPOsBv_O3uo: Some web_safari client https formats have been skipped as they are missing a url. YouTube is forcing SABR streaming for this client. See  https://github.com/yt-dlp/yt-dlp/issues/12482  for more details
#! [DEBUG] [youtube] OPOsBv_O3uo: Downloading m3u8 information
#! [WARNING] [youtube] OPOsBv_O3uo: Some web client https formats have been skipped as they are missing a url. YouTube is forcing SABR streaming for this client. See  https://github.com/yt-dlp/yt-dlp/issues/12482  for more details
#! [DEBUG] [info] OPOsBv_O3uo: Downloading 1 format(s): 251
#! [DEBUG] [download] Destination: G:\Silvestre y la Naranja\Sos Todo Lo Que Está Bien.webm

# TODO: Mejorar las velocidades de descarga:
# DEBUG] [download]   1.8% of    3.34MiB at  110.58KiB/s ETA 00:30
# [DEBUG] [ExtractAudio] Destination: G:\Silvestre y la Naranja\Loca Intuición.mp3
# [DEBUG] [download]   3.7% of    3.34MiB at  115.45KiB/s ETA 00:28
# [DEBUG] [download]   7.2% of    3.34MiB at  112.51KiB/s ETA 00:28
# [DEBUG] [download]  10.4% of    3.34MiB at  160.08KiB/s ETA 00:19
# [DEBUG] [download]  16.8% of    3.34MiB at  139.31KiB/s ETA 00:20
# [DEBUG] [download]  20.2% of    3.34MiB at  146.97KiB/s ETA 00:18
# [DEBUG] [download]  26.1% of    3.34MiB at  160.23KiB/s ETA 00:15
# [DEBUG] [download]  32.9% of    3.34MiB at  157.05KiB/s ETA 00:14
# [DEBUG] [download]  37.1% of    3.34MiB at  166.47KiB/s ETA 00:12

# TODO: Emitir una notificación del sistema operativo cuando se termine la descarga de todas las canciones (opcional, checkbox)


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
