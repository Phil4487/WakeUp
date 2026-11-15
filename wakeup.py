import ctypes
import hmac
import ipaddress
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import tkinter as tk
import urllib.error
import urllib.request
import uuid
import winsound
import winreg
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from tkinter import messagebox
from typing import Optional


PORT = 8765
ENDPOINT = "/api/wakeup"
PAIR_ENDPOINT = "/api/pair"
STARTUP_REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_REGISTRY_VALUE = "WakeupReceiver"


def settings_path(name: str) -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "Wakeup" / name


def load_settings(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as settings_file:
            data = json.load(settings_file)
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Ungueltige Einstellungen in {path}")
    return data


def save_settings(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as settings_file:
        json.dump(data, settings_file)


def set_receiver_autostart(enabled: bool) -> None:
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER,
        STARTUP_REGISTRY_KEY,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        if enabled:
            pythonw = Path(sys.executable).with_name("pythonw.exe")
            executable = pythonw if pythonw.exists() else Path(sys.executable)
            receiver_script = Path(__file__).with_name("receiver.py").resolve()
            command = f'"{executable}" "{receiver_script}"'
            winreg.SetValueEx(key, STARTUP_REGISTRY_VALUE, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, STARTUP_REGISTRY_VALUE)
            except FileNotFoundError:
                pass


def find_tailscale_ipv4(output: str) -> Optional[str]:
    tailnet_range = ipaddress.ip_network("100.64.0.0/10")
    for line in output.splitlines():
        try:
            address = ipaddress.ip_address(line.strip())
        except ValueError:
            continue
        if address.version == 4 and address in tailnet_range:
            return str(address)
    return None


def get_tailscale_ipv4() -> Optional[str]:
    executable = shutil.which("tailscale")
    if not executable:
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        for candidate in (
            program_files / "Tailscale" / "tailscale.exe",
            program_files / "Tailscale IPN" / "tailscale.exe",
        ):
            if candidate.is_file():
                executable = str(candidate)
                break
    if not executable:
        return None

    try:
        result = subprocess.run(
            [executable, "ip", "-4"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return find_tailscale_ipv4(result.stdout)


def _check_hresult(result: int) -> None:
    if result < 0:
        raise OSError(f"Windows-Audiofehler (HRESULT 0x{result & 0xFFFFFFFF:08X})")


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_string(cls, value: str) -> "_GUID":
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


def _com_call(interface: ctypes.c_void_p, index: int, result_type, arg_types, *args):
    vtable = ctypes.cast(interface, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    function_type = ctypes.WINFUNCTYPE(result_type, ctypes.c_void_p, *arg_types)
    function = ctypes.cast(vtable[index], function_type)
    return function(interface, *args)


def set_master_volume_to_max() -> None:
    ole32 = ctypes.OleDLL("ole32")
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(_GUID),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    ole32.CoCreateInstance.restype = ctypes.c_long

    initialized = False
    enumerator = ctypes.c_void_p()
    device = ctypes.c_void_p()
    endpoint = ctypes.c_void_p()
    try:
        _check_hresult(ole32.CoInitializeEx(None, 0))
        initialized = True

        class_id = _GUID.from_string("BCDE0395-E52F-467C-8E3D-C4579291692E")
        enumerator_id = _GUID.from_string("A95664D2-9614-4F35-A746-DE8DB63617E6")
        _check_hresult(
            ole32.CoCreateInstance(
                ctypes.byref(class_id),
                None,
                23,
                ctypes.byref(enumerator_id),
                ctypes.byref(enumerator),
            )
        )
        _check_hresult(
            _com_call(
                enumerator,
                4,
                ctypes.c_long,
                [ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)],
                0,
                1,
                ctypes.byref(device),
            )
        )
        endpoint_id = _GUID.from_string("5CDF2C82-841E-4546-9722-0CF74078229A")
        _check_hresult(
            _com_call(
                device,
                3,
                ctypes.c_long,
                [
                    ctypes.POINTER(_GUID),
                    wintypes.DWORD,
                    ctypes.c_void_p,
                    ctypes.POINTER(ctypes.c_void_p),
                ],
                ctypes.byref(endpoint_id),
                23,
                None,
                ctypes.byref(endpoint),
            )
        )
        _check_hresult(
            _com_call(
                endpoint,
                7,
                ctypes.c_long,
                [ctypes.c_float, ctypes.c_void_p],
                1.0,
                None,
            )
        )
    finally:
        for interface in (endpoint, device, enumerator):
            if interface:
                _com_call(interface, 2, wintypes.ULONG, [])
        if initialized:
            ole32.CoUninitialize()


def perform_wakeup() -> None:
    set_master_volume_to_max()
    winsound.Beep(880, 600)


class WakeupServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, token: str, action=perform_wakeup):
        self.token = token
        self.action = action
        super().__init__(address, WakeupRequestHandler)


class WakeupRequestHandler(BaseHTTPRequestHandler):
    def _is_authorized(self) -> bool:
        supplied_token = self.headers.get("Authorization", "")
        expected_token = f"Bearer {self.server.token}"
        return hmac.compare_digest(supplied_token, expected_token)

    def do_GET(self):
        if self.path != PAIR_ENDPOINT:
            self.send_error(404)
            return
        if not self._is_authorized():
            self.send_error(401, "Ungueltiger Kopplungscode")
            return

        response = json.dumps({"status": "paired"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def do_POST(self):
        if self.path != ENDPOINT:
            self.send_error(404)
            return
        if not self._is_authorized():
            self.send_error(401, "Ungueltiger Token")
            return

        try:
            self.server.action()
        except Exception as error:
            self.server.log_error("Wakeup-Aktion fehlgeschlagen: %s", error)
            self.send_error(500, "Aktion auf dem Ziel-PC fehlgeschlagen")
            return

        response = json.dumps({"status": "ok"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, _format, *_args):
        return


class WakeupApp:
    def __init__(self, root: tk.Tk, mode: str = "both"):
        self.root = root
        self.mode = mode
        self.root.title("Wakeup")
        self.root.resizable(False, False)
        self.server = None
        self.server_thread = None
        self.closed = False
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        if mode == "receiver":
            self.show_receiver()
        elif mode == "sender":
            self.show_sender()
        else:
            self.show_home()

    def clear(self):
        for child in self.root.winfo_children():
            child.destroy()

    def show_home(self):
        self.clear()
        frame = tk.Frame(self.root, padx=24, pady=20)
        frame.pack()
        tk.Label(frame, text="Wakeup", font=("Segoe UI", 18, "bold")).pack(pady=(0, 8))
        tk.Label(
            frame,
            text="Lautstaerke am Ziel-PC auf 100 % setzen und einen Ton abspielen.",
            wraplength=360,
        ).pack(pady=(0, 16))
        tk.Button(
            frame,
            text="Diesen PC als Ziel-PC starten",
            width=34,
            command=self.show_receiver,
        ).pack(pady=5)
        tk.Button(
            frame,
            text="Einen Ziel-PC ansteuern",
            width=34,
            command=self.show_sender,
        ).pack(pady=5)

    def show_receiver(self):
        self.clear()
        frame = tk.Frame(self.root, padx=24, pady=20)
        frame.pack()
        tk.Label(frame, text="Ziel-PC", font=("Segoe UI", 16, "bold")).pack(pady=(0, 8))
        tk.Label(
            frame,
            text="Der Sender wird einmal gekoppelt. Danach laufen Anfragen ohne Bestaetigung automatisch.",
            wraplength=360,
        ).pack(pady=(0, 12))

        try:
            receiver_settings_path = settings_path("receiver.json")
            receiver_settings = load_settings(receiver_settings_path)
            self.token = receiver_settings.get("token")
            if not isinstance(self.token, str) or not self.token:
                self.token = secrets.token_urlsafe(24)
            receiver_settings["token"] = self.token
            receiver_settings.setdefault("autostart", True)
            if not isinstance(receiver_settings["autostart"], bool):
                raise ValueError("Die gespeicherte Autostart-Einstellung ist ungueltig.")
            save_settings(receiver_settings_path, receiver_settings)
            self.receiver_settings_path = receiver_settings_path
            self.receiver_settings = receiver_settings
        except (OSError, ValueError) as error:
            messagebox.showerror("Empfaenger-Einrichtung fehlgeschlagen", str(error))
            self.show_home()
            return

        tk.Label(frame, text="Kopplungscode (auf dem Sender einmalig eingeben):").pack(anchor="w")
        token_entry = tk.Entry(frame, width=48)
        token_entry.insert(0, self.token)
        token_entry.configure(state="readonly")
        token_entry.pack(pady=(3, 10))
        tk.Label(frame, text=f"Port: {PORT}  |  LAN-IP: {self.local_ip()}").pack(pady=(0, 4))
        self.tailscale_ip_label = tk.Label(frame, text="Tailscale-IP wird gesucht ...")
        self.tailscale_ip_label.pack(pady=(0, 4))
        self.tailscale_refresh_button = tk.Button(
            frame,
            text="Tailscale-IP aktualisieren",
            command=self.refresh_tailscale_ip,
        )
        self.tailscale_refresh_button.pack(pady=(0, 8))

        self.receiver_status = tk.Label(frame, text="Empfaenger wird gestartet ...")
        self.receiver_status.pack(pady=(0, 8))
        self.receiver_autostart_var = tk.BooleanVar(value=self.receiver_settings["autostart"])
        tk.Checkbutton(
            frame,
            text="Mit Windows automatisch starten",
            variable=self.receiver_autostart_var,
            command=self.update_receiver_autostart,
        ).pack(anchor="w", pady=(0, 8))
        self.receiver_button = tk.Button(frame, text="Empfaenger stoppen", command=self.stop_server)
        self.receiver_button.pack(fill="x", pady=4)
        if self.mode == "both":
            tk.Button(frame, text="Zurueck", command=self.return_home).pack(fill="x", pady=4)
        self.update_receiver_autostart()
        self.refresh_tailscale_ip()
        self.start_server()

    def update_receiver_autostart(self):
        enabled = self.receiver_autostart_var.get()
        try:
            set_receiver_autostart(enabled)
            self.receiver_settings["autostart"] = enabled
            save_settings(self.receiver_settings_path, self.receiver_settings)
        except OSError as error:
            self.receiver_autostart_var.set(not enabled)
            messagebox.showerror("Autostart konnte nicht geaendert werden", str(error))

    def refresh_tailscale_ip(self):
        self.tailscale_refresh_button.configure(state="disabled")
        self.tailscale_ip_label.configure(text="Tailscale-IP wird gesucht ...")
        threading.Thread(target=self._lookup_tailscale_ip, daemon=True).start()

    def _lookup_tailscale_ip(self):
        address = get_tailscale_ipv4()
        if not self.closed:
            self.root.after(0, self._show_tailscale_ip, address)

    def _show_tailscale_ip(self, address: Optional[str]):
        if self.closed or not self.tailscale_ip_label.winfo_exists():
            return
        if address:
            self.tailscale_ip_label.configure(text=f"Tailscale-IP: {address}")
        else:
            self.tailscale_ip_label.configure(
                text="Keine Tailscale-IP gefunden. Tailscale starten und aktualisieren."
            )
        self.tailscale_refresh_button.configure(state="normal")

    def return_home(self):
        self.stop_server()
        self.show_home()

    @staticmethod
    def local_ip():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect(("192.0.2.1", 80))
                return probe.getsockname()[0]
        except OSError:
            return "IP nicht ermittelbar"

    def start_server(self):
        if self.server:
            return
        try:
            self.server = WakeupServer(("0.0.0.0", PORT), self.token)
        except OSError as error:
            self.receiver_status.configure(text="Empfaenger konnte nicht gestartet werden.")
            self.receiver_button.configure(text="Erneut versuchen", command=self.start_server)
            messagebox.showerror("Empfaenger konnte nicht starten", str(error))
            return
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.receiver_status.configure(
            text=f"Laeuft auf Port {PORT}. Anfragen werden automatisch ausgefuehrt."
        )
        self.receiver_button.configure(text="Empfaenger stoppen", command=self.stop_server)

    def stop_server(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if getattr(self, "receiver_status", None) and self.receiver_status.winfo_exists():
            self.receiver_status.configure(text="Empfaenger ist gestoppt.")
        if getattr(self, "receiver_button", None) and self.receiver_button.winfo_exists():
            self.receiver_button.configure(text="Empfaenger starten", command=self.start_server)

    def show_sender(self):
        self.clear()
        frame = tk.Frame(self.root, padx=24, pady=20)
        frame.pack()
        tk.Label(frame, text="Sender", font=("Segoe UI", 16, "bold")).pack(pady=(0, 12))

        try:
            self.sender_settings_path = settings_path("sender.json")
            self.sender_config = load_settings(self.sender_settings_path)
            if self.sender_config:
                self._validate_sender_config(self.sender_config)
        except (OSError, ValueError) as error:
            messagebox.showerror("Sender-Einrichtung fehlgeschlagen", str(error))
            self.show_home()
            return

        if self.sender_config:
            tk.Label(
                frame,
                text=f"Verbunden mit {self.sender_config['host']}:{self.sender_config['port']}",
            ).pack(pady=(0, 12))
            self.sender_status = tk.Label(frame, text="")
            self.sender_status.pack(pady=(0, 6))
            self.send_button = tk.Button(
                frame,
                text="Lautstaerke 100 % + Ton abspielen",
                command=self.send_wakeup,
            )
            self.send_button.pack(fill="x", pady=4)
            tk.Button(
                frame,
                text="Verbindung aendern",
                command=self.show_pairing_form,
            ).pack(fill="x", pady=4)
            if self.mode == "both":
                tk.Button(frame, text="Zurueck", command=self.return_home).pack(fill="x", pady=4)
            return

        self.show_pairing_form(frame)

    @staticmethod
    def _validate_sender_config(config: dict) -> None:
        if (
            not isinstance(config.get("host"), str)
            or not config["host"].strip()
            or not isinstance(config.get("token"), str)
            or not config["token"]
            or not isinstance(config.get("port"), int)
            or not 1 <= config["port"] <= 65535
        ):
            raise ValueError("Die gespeicherte Sender-Verbindung ist ungueltig.")

    def show_pairing_form(self, frame=None):
        if frame is None:
            self.clear()
            frame = tk.Frame(self.root, padx=24, pady=20)
            frame.pack()
            tk.Label(frame, text="Sender koppeln", font=("Segoe UI", 16, "bold")).pack(pady=(0, 12))

        tk.Label(frame, text="Ziel-PC-IP (LAN oder Tailscale)").pack(anchor="w")
        self.host_entry = tk.Entry(frame, width=42)
        if self.sender_config:
            self.host_entry.insert(0, self.sender_config["host"])
        self.host_entry.pack(pady=(3, 10))
        tk.Label(frame, text=f"Port (Standard: {PORT})").pack(anchor="w")
        self.port_entry = tk.Entry(frame, width=42)
        self.port_entry.insert(0, str(self.sender_config.get("port", PORT)))
        self.port_entry.pack(pady=(3, 10))
        tk.Label(frame, text="Kopplungscode vom Ziel-PC (nur einmal erforderlich)").pack(anchor="w")
        self.sender_token_entry = tk.Entry(frame, width=42, show="*")
        if self.sender_config:
            self.sender_token_entry.insert(0, self.sender_config["token"])
        self.sender_token_entry.pack(pady=(3, 14))

        self.pair_status = tk.Label(frame, text="")
        self.pair_status.pack(pady=(0, 6))
        self.pair_button = tk.Button(
            frame,
            text="Verbinden und speichern",
            command=self.save_sender_connection,
        )
        self.pair_button.pack(fill="x", pady=4)
        if self.mode == "both":
            tk.Button(frame, text="Zurueck", command=self.return_home).pack(fill="x", pady=4)

    def save_sender_connection(self):
        host = self.host_entry.get().strip()
        token = self.sender_token_entry.get().strip()
        try:
            port = int(self.port_entry.get().strip())
            if not host or not token or not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "Ungueltige Verbindung",
                "Bitte IP-Adresse, Port zwischen 1 und 65535 und den Kopplungscode eingeben.",
            )
            return

        self.pair_button.configure(state="disabled")
        self.pair_status.configure(text="Kopplung wird geprueft ...")
        threading.Thread(
            target=self._verify_pairing,
            args=(host, port, token),
            daemon=True,
        ).start()

    def _verify_pairing(self, host: str, port: int, token: str):
        request = urllib.request.Request(
            f"http://{host}:{port}{PAIR_ENDPOINT}",
            headers={"Authorization": f"Bearer {token}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                if response.status != 200:
                    raise OSError(f"Unerwartete Antwort: HTTP {response.status}")
            status = None
        except urllib.error.HTTPError as error:
            status = f"Ziel-PC meldet HTTP {error.code}: {error.reason}"
            error.close()
        except (urllib.error.URLError, OSError, ValueError) as error:
            status = f"Kopplung fehlgeschlagen: {error}"

        if not self.closed:
            self.root.after(0, self._finish_pairing, host, port, token, status)

    def _finish_pairing(self, host: str, port: int, token: str, status: Optional[str]):
        if (
            self.closed
            or not self.root.winfo_exists()
            or not self.pair_status.winfo_exists()
            or not self.pair_button.winfo_exists()
        ):
            return
        if status:
            self.pair_status.configure(text=status, wraplength=360)
            self.pair_button.configure(state="normal")
            return

        self.sender_config = {"host": host, "port": port, "token": token}
        try:
            save_settings(self.sender_settings_path, self.sender_config)
        except OSError as error:
            self.pair_status.configure(
                text=f"Verbindung konnte nicht gespeichert werden: {error}",
                wraplength=360,
            )
            self.pair_button.configure(state="normal")
            return
        self.show_sender()

    def send_wakeup(self):
        if not self.sender_config:
            messagebox.showerror("Sender nicht gekoppelt", "Bitte zuerst die Kopplung einrichten.")
            return

        self.send_button.configure(state="disabled")
        self.sender_status.configure(text="Sende Anfrage ...")
        threading.Thread(
            target=self._send_request,
            args=(self.sender_config["host"], self.sender_config["port"], self.sender_config["token"]),
            daemon=True,
        ).start()

    def _send_request(self, host: str, port: int, token: str):
        request = urllib.request.Request(
            f"http://{host}:{port}{ENDPOINT}",
            data=b"",
            headers={"Authorization": f"Bearer {token}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                if response.status != 200:
                    raise OSError(f"Unerwartete Antwort: HTTP {response.status}")
            status = "Anfrage erfolgreich. Der Ziel-PC spielt den Ton ab."
        except urllib.error.HTTPError as error:
            status = f"Ziel-PC meldet HTTP {error.code}: {error.reason}"
            error.close()
        except (urllib.error.URLError, OSError, ValueError) as error:
            status = f"Verbindung fehlgeschlagen: {error}"

        if not self.closed:
            self.root.after(0, self._finish_send, status)

    def _finish_send(self, status: str):
        if (
            self.closed
            or not self.root.winfo_exists()
            or not self.sender_status.winfo_exists()
            or not self.send_button.winfo_exists()
        ):
            return
        self.sender_status.configure(text=status, wraplength=360)
        self.send_button.configure(state="normal")

    def close(self):
        self.closed = True
        self.stop_server()
        self.root.destroy()


def run_app(mode: str = "both") -> None:
    if os.name != "nt":
        raise SystemExit("Wakeup ist derzeit nur fuer Windows 10/11 vorgesehen.")
    root = tk.Tk()
    WakeupApp(root, mode)
    root.mainloop()


if __name__ == "__main__":
    run_app()
