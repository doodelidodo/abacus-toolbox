"""
FSM XML -> XLSX als Windows-Dienst (ohne Docker).

Die gleiche FastAPI-App wie im Docker-Container, gestartet mit uvicorn.
Einstellungen stehen in settings.json neben der .exe:
    {
      "host": "127.0.0.1",          # 127.0.0.1 = nur lokal (Abacus auf gleichem Server)
      "port": 8000,
      "api_key": "",                # leer = kein Key nötig
      "config_path": "xml_to_xlsx_config.json",
      "log_level": "INFO"
    }

Aufruf der .exe:
    fsm-xml-service.exe run      -> im Konsolenfenster starten (zum Testen, Ctrl+C beendet)
    (ohne Argumente)             -> wird vom Windows-Dienstmanager so gestartet
Installation als Dienst: install-service.ps1
"""

import json
import logging
import logging.handlers
import os
import sys

SERVICE_NAME = "FsmXmlToXlsx"
SERVICE_DISPLAY_NAME = "FSM XML to XLSX Service"
SERVICE_DESCRIPTION = "Wandelt FSM/Abacus timeEfforts- und expenses-XML per REST-API in Excel um."

DEFAULT_SETTINGS = {
    "host": "127.0.0.1",
    "port": 8000,
    "api_key": "",
    "config_path": "xml_to_xlsx_config.json",
    "log_level": "INFO",
}


def base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def load_settings():
    settings = dict(DEFAULT_SETTINGS)
    path = os.path.join(base_dir(), "settings.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8-sig") as handle:
            settings.update(json.load(handle))
    config_path = settings["config_path"]
    if not os.path.isabs(config_path):
        config_path = os.path.join(base_dir(), config_path)
    settings["config_path"] = config_path
    settings["port"] = int(settings["port"])
    return settings


def apply_settings(settings, log_to_file):
    # main.py / converter.py lesen diese Umgebungsvariablen beim Import
    os.environ["CONFIG_PATH"] = settings["config_path"]
    os.environ["API_KEY"] = settings.get("api_key") or ""
    os.environ["LOG_LEVEL"] = settings.get("log_level") or "INFO"

    root = logging.getLogger()
    root.setLevel(os.environ["LOG_LEVEL"])
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handlers = []
    if log_to_file:
        log_dir = os.path.join(base_dir(), "logs")
        os.makedirs(log_dir, exist_ok=True)
        handlers.append(
            logging.handlers.RotatingFileHandler(
                os.path.join(log_dir, "service.log"), maxBytes=5_000_000, backupCount=5, encoding="utf-8"
            )
        )
    else:
        handlers.append(logging.StreamHandler(sys.stdout))
    for handler in handlers:
        handler.setFormatter(fmt)
    root.handlers = handlers


def build_server(settings):
    import uvicorn

    from main import app  # erst nach apply_settings importieren

    config = uvicorn.Config(
        app,
        host=settings["host"],
        port=settings["port"],
        log_config=None,     # Logging läuft über unser Root-Logging (Datei bzw. Konsole)
        loop="asyncio",
        http="h11",
        lifespan="off",
        access_log=True,
    )
    return uvicorn.Server(config)


def run_console():
    settings = load_settings()
    apply_settings(settings, log_to_file=False)
    log = logging.getLogger("fsm-service")
    log.info("Konsolenmodus: http://%s:%s  (Config: %s, API-Key: %s) - beenden mit Ctrl+C",
             settings["host"], settings["port"], settings["config_path"],
             "aktiv" if settings.get("api_key") else "aus")
    build_server(settings).run()


# ---------------------------------------------------------------------------
# Windows-Dienst (pywin32). Import nur unter Windows, damit "run" überall geht.
# ---------------------------------------------------------------------------
def run_service_dispatcher():
    import servicemanager
    import win32event  # noqa: F401  (von pywin32 für den Dienst benötigt)
    import win32service
    import win32serviceutil

    class FsmService(win32serviceutil.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY_NAME
        _svc_description_ = SERVICE_DESCRIPTION

        def __init__(self, args):
            super().__init__(args)
            self.server = None

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            if self.server is not None:
                self.server.should_exit = True

        def SvcDoRun(self):
            log = logging.getLogger("fsm-service")
            try:
                settings = load_settings()
                apply_settings(settings, log_to_file=True)
                log.info("Dienst startet auf http://%s:%s (Config: %s, API-Key: %s)",
                         settings["host"], settings["port"], settings["config_path"],
                         "aktiv" if settings.get("api_key") else "aus")
                self.server = build_server(settings)
                self.server.run()
                log.info("Dienst beendet")
            except Exception:
                log.exception("Dienst abgebrochen")
                servicemanager.LogErrorMsg(f"{SERVICE_NAME}: Start fehlgeschlagen, siehe logs\\service.log")
                raise

    servicemanager.Initialize()
    servicemanager.PrepareToHostSingle(FsmService)
    servicemanager.StartServiceCtrlDispatcher()


def main():
    if len(sys.argv) > 1 and sys.argv[1].lower() == "run":
        run_console()
        return
    if len(sys.argv) > 1:
        print(__doc__)
        return
    try:
        run_service_dispatcher()
    except Exception as exc:  # z.B. per Doppelklick gestartet statt vom Dienstmanager
        print(f"Kein Dienst-Kontext ({exc}).\n")
        print("Zum Testen im Fenster:   fsm-xml-service.exe run")
        print("Als Dienst installieren: install-service.ps1 (als Administrator)")


if __name__ == "__main__":
    main()
