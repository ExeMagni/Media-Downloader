import json
import os
from pathlib import Path


class ConfigService:
    DEFAULT_CONFIG_FILE = "config/app_config.json"

    DEFAULT_SETTINGS = {
        "enable_youtube": True,
        "enable_spotify": False,
        "enable_cover": False,
    }

    def __init__(self, config_file: str = None):
        self.config_file = config_file or self.DEFAULT_CONFIG_FILE
        self._settings = dict(self.DEFAULT_SETTINGS)
        self._load()

    def _load(self):
        """Carga la configuración desde archivo si existe."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r") as f:
                    loaded = json.load(f)
                    # Merge con defaults para mantener compatibilidad
                    self._settings.update(loaded)
        except Exception as e:
            print(f"[CONFIG] Error cargando configuración: {e}")
            self._settings = dict(self.DEFAULT_SETTINGS)

    def _save(self):
        """Guarda la configuración en archivo."""
        try:
            os.makedirs(os.path.dirname(self.config_file)
                        or ".", exist_ok=True)
            with open(self.config_file, "w") as f:
                json.dump(self._settings, f, indent=2)
        except Exception as e:
            print(f"[CONFIG] Error guardando configuración: {e}")

    def get(self, key: str, default=None):
        """Obtiene un valor de configuración."""
        return self._settings.get(key, default)

    def set(self, key: str, value):
        """Establece y persiste un valor de configuración."""
        self._settings[key] = value
        self._save()

    def set_multiple(self, settings: dict):
        """Establece múltiples valores sin guardar repetidamente."""
        self._settings.update(settings)
        self._save()

    def get_all(self) -> dict:
        """Retorna una copia de toda la configuración."""
        return dict(self._settings)

    def reset_to_defaults(self):
        """Restaura los valores por defecto."""
        self._settings = dict(self.DEFAULT_SETTINGS)
        self._save()
