import ctypes
from ctypes import wintypes
import os
import pathlib
import re
import subprocess
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import addonHandler
import globalPluginHandler
import gui
from logHandler import log
from scriptHandler import script
import ui
import wx


addonHandler.initTranslation()


_INT_RE = re.compile(r"-?\d+")
_FLOAT_RE = re.compile(r"-?\d+(?:[.,]\d+)?")
_PERCENT_RE = re.compile(r"(\d{1,3})\s*%")
_SIZE_RE = re.compile(r"([0-9][0-9\s.,]*)\s*(B|KB|MB|GB|TB|PB)\b", re.IGNORECASE)
_TEMP_RE = re.compile(r"(-?\d+)\s*C\b", re.IGNORECASE)
_RPM_RE = re.compile(r"(\d+)\s*RPM", re.IGNORECASE)
_DISK_LIST_ENTRY_RE = re.compile(r"^\s*\(\d{1,3}\)\s+.+?:\s+")
_DISK_HEADER_RE = re.compile(r"^\s*\((\d{1,3})\)\s+(.+?)\s*$")
_KEY_VALUE_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 #/_().+-]{1,60})\s*:\s*(.+?)\s*$")

_HEALTH_GOOD_KEYWORDS = ("good", "healthy", "ok")
_HEALTH_WARN_KEYWORDS = ("caution", "warning", "degraded")
_HEALTH_BAD_KEYWORDS = ("bad", "failed", "critical", "error")

_SEE_MASK_NOCLOSEPROCESS = 0x00000040
_SW_HIDE = 0
_WAIT_OBJECT_0 = 0x00000000
_WAIT_TIMEOUT = 0x00000102
_ERROR_CANCELLED = 1223
_CF_TEXT = 1
_CF_UNICODETEXT = 13

_SIZE_MULTIPLIERS = {
    "B": 1,
    "KB": 1000,
    "MB": 1000**2,
    "GB": 1000**3,
    "TB": 1000**4,
    "PB": 1000**5,
}


class _SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", wintypes.LPVOID),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIcon", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        match = _INT_RE.search(text)
        if not match:
            return None
        try:
            return int(match.group(0))
        except ValueError:
            return None


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    match = _FLOAT_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def _clamp_percent(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    return max(0, min(100, value))


def _first_non_empty(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _to_display_value(value: Any, fallback: str = "no data") -> str:
    text = str(value).strip() if value is not None else ""
    return text if text else fallback


def _format_size(size_value: Any) -> str:
    size = _to_int(size_value)
    if size is None:
        return "no data"
    if size <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    value = float(size)
    unit = 0
    while value >= 1024 and unit < len(units) - 1:
        value /= 1024.0
        unit += 1
    return f"{value:.2f} {units[unit]}"


def _parse_size_bytes(text: Any) -> Optional[int]:
    raw = str(text or "").strip()
    if not raw:
        return None
    match = _SIZE_RE.search(raw)
    if not match:
        return None
    value = _to_float(match.group(1))
    if value is None:
        return None
    unit = match.group(2).upper()
    multiplier = _SIZE_MULTIPLIERS.get(unit)
    if multiplier is None:
        return None
    return int(value * multiplier)


def _parse_temperature(value: Any) -> Optional[int]:
    text = str(value or "").strip()
    if not text:
        return None
    match = _TEMP_RE.search(text)
    temperature = _to_int(match.group(1) if match else text)
    if temperature is None:
        return None
    if -40 <= temperature <= 150:
        return temperature
    return None


def _parse_health_percent(status_text: str) -> Optional[int]:
    text = str(status_text or "").strip()
    if not text:
        return None
    percent_match = _PERCENT_RE.search(text)
    if percent_match:
        return _clamp_percent(_to_int(percent_match.group(1)))

    lowered = text.lower()
    if any(keyword in lowered for keyword in _HEALTH_BAD_KEYWORDS):
        return 0
    if any(keyword in lowered for keyword in _HEALTH_WARN_KEYWORDS):
        return 50
    if any(keyword in lowered for keyword in _HEALTH_GOOD_KEYWORDS):
        return 100
    return None


def _parse_health_code(status_text: str, health_percent: Optional[int]) -> Optional[int]:
    lowered = str(status_text or "").strip().lower()
    if lowered:
        if any(keyword in lowered for keyword in _HEALTH_BAD_KEYWORDS):
            return 2
        if any(keyword in lowered for keyword in _HEALTH_WARN_KEYWORDS):
            return 1
        if any(keyword in lowered for keyword in _HEALTH_GOOD_KEYWORDS):
            return 0
    if health_percent is None:
        return None
    return 0 if health_percent >= 80 else 1


def _parse_rotation_rate(text: Any) -> Optional[int]:
    raw = str(text or "").strip()
    if not raw:
        return None
    match = _RPM_RE.search(raw)
    if match:
        return _to_int(match.group(1))
    return None


def _infer_media_type(interface_text: str, rotation_text: str, model_name: str) -> str:
    rotation = _parse_rotation_rate(rotation_text)
    if rotation is not None and rotation > 0:
        return f"HDD ({rotation} RPM)"

    combined = f"{interface_text} {model_name}".upper()
    if "NVME" in combined or "NVM EXPRESS" in combined or "SSD" in combined:
        return "SSD"
    return "no data"


def _decode_text_bytes(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "mbcs"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _get_addon_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[1]


def _get_cdi_root() -> pathlib.Path:
    return _get_addon_root() / "bin" / "crystaldiskinfo"


def _find_crystaldiskinfo_exe() -> Optional[pathlib.Path]:
    cdi_root = _get_cdi_root()
    for candidate in ("DiskInfo64.exe", "DiskInfo32.exe", "DiskInfo.exe"):
        path = cdi_root / candidate
        if path.is_file():
            return path
    return None


def _run_elevated_command(executable: str, parameters: str, timeout: int = 120) -> int:
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    shell_execute_ex = shell32.ShellExecuteExW
    shell_execute_ex.argtypes = [ctypes.POINTER(_SHELLEXECUTEINFOW)]
    shell_execute_ex.restype = wintypes.BOOL

    wait_for_single_object = kernel32.WaitForSingleObject
    wait_for_single_object.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    wait_for_single_object.restype = wintypes.DWORD

    get_exit_code_process = kernel32.GetExitCodeProcess
    get_exit_code_process.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    get_exit_code_process.restype = wintypes.BOOL

    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    info = _SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(_SHELLEXECUTEINFOW)
    info.fMask = _SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = executable
    info.lpParameters = parameters
    info.nShow = _SW_HIDE

    if not shell_execute_ex(ctypes.byref(info)):
        error = ctypes.get_last_error()
        if error == _ERROR_CANCELLED:
            raise PermissionError("UAC prompt was cancelled.")
        raise RuntimeError(f"ShellExecuteEx failed with error {error}.")

    if not info.hProcess:
        raise RuntimeError("ShellExecuteEx did not return process handle.")

    try:
        wait_result = wait_for_single_object(info.hProcess, max(1, int(timeout * 1000)))
        if wait_result == _WAIT_TIMEOUT:
            raise TimeoutError("Elevated command timed out.")
        if wait_result != _WAIT_OBJECT_0:
            raise RuntimeError(f"Unexpected wait result: {wait_result}.")

        exit_code = wintypes.DWORD()
        if not get_exit_code_process(info.hProcess, ctypes.byref(exit_code)):
            raise RuntimeError("Unable to get exit code for elevated process.")
        return int(exit_code.value)
    finally:
        close_handle(info.hProcess)


def _run_elevated_background_task(executable: pathlib.Path, parameters: str, timeout: int = 120) -> int:
    task_name = f"DiscChecker_CDI_{os.getpid()}_{int(time.time() * 1000)}"
    task_command = subprocess.list2cmdline([str(executable)] + ([parameters] if parameters else []))
    script_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="mbcs",
            suffix=".cmd",
            delete=False,
        ) as temp_script:
            temp_script.write("@echo off\r\n")
            temp_script.write(f'set "DISC_CHECKER_TASK_COMMAND={task_command}"\r\n')
            temp_script.write(
                f'schtasks /Create /TN "{task_name}" /TR "%DISC_CHECKER_TASK_COMMAND%" /SC ONCE /ST 00:00 /RU SYSTEM /RL HIGHEST /F /Z >nul\r\n'
            )
            temp_script.write("if errorlevel 1 exit /b 11\r\n")
            temp_script.write(f'schtasks /Run /TN "{task_name}" >nul\r\n')
            temp_script.write("if errorlevel 1 exit /b 12\r\n")
            temp_script.write("exit /b 0\r\n")
            script_path = temp_script.name

        params = f'/C "{script_path}"'
        return _run_elevated_command("cmd.exe", params, timeout=timeout)
    finally:
        if script_path:
            try:
                os.unlink(script_path)
            except OSError:
                pass


def _to_vbs_string_literal(text: str) -> str:
    return '"' + text.replace('"', '""') + '"'


def _run_elevated_hidden_vbs_command(executable: pathlib.Path, parameters: str, timeout: int = 120) -> int:
    command_line = subprocess.list2cmdline([executable.name] + ([parameters] if parameters else []))
    script_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-16",
            suffix=".vbs",
            delete=False,
        ) as temp_script:
            temp_script.write('Set sh = CreateObject("WScript.Shell")\r\n')
            temp_script.write(f"sh.CurrentDirectory = {_to_vbs_string_literal(str(executable.parent))}\r\n")
            temp_script.write(f"WScript.Quit sh.Run({_to_vbs_string_literal(command_line)}, 0, True)\r\n")
            script_path = temp_script.name

        vbs_params = f'//B //NoLogo "{script_path}"'
        return _run_elevated_command("wscript.exe", vbs_params, timeout=timeout)
    finally:
        if script_path:
            try:
                os.unlink(script_path)
            except OSError:
                pass


def _looks_like_crystaldiskinfo_report(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    if "CrystalDiskInfo" not in raw:
        return False
    for line in raw.splitlines():
        if _DISK_HEADER_RE.match(line):
            return True
    return False


def _read_clipboard_text() -> Optional[str]:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    open_clipboard = user32.OpenClipboard
    open_clipboard.argtypes = [wintypes.HWND]
    open_clipboard.restype = wintypes.BOOL

    close_clipboard = user32.CloseClipboard
    close_clipboard.argtypes = []
    close_clipboard.restype = wintypes.BOOL

    is_clipboard_format_available = user32.IsClipboardFormatAvailable
    is_clipboard_format_available.argtypes = [wintypes.UINT]
    is_clipboard_format_available.restype = wintypes.BOOL

    get_clipboard_data = user32.GetClipboardData
    get_clipboard_data.argtypes = [wintypes.UINT]
    get_clipboard_data.restype = wintypes.HANDLE

    global_lock = kernel32.GlobalLock
    global_lock.argtypes = [wintypes.HANDLE]
    global_lock.restype = wintypes.LPVOID

    global_unlock = kernel32.GlobalUnlock
    global_unlock.argtypes = [wintypes.HANDLE]
    global_unlock.restype = wintypes.BOOL

    for _ in range(20):
        if open_clipboard(None):
            break
        time.sleep(0.05)
    else:
        return None

    try:
        if is_clipboard_format_available(_CF_UNICODETEXT):
            handle = get_clipboard_data(_CF_UNICODETEXT)
            if not handle:
                return None
            pointer = global_lock(handle)
            if not pointer:
                return None
            try:
                text = ctypes.wstring_at(pointer)
            finally:
                global_unlock(handle)
            text = str(text).strip()
            return text or None

        if is_clipboard_format_available(_CF_TEXT):
            handle = get_clipboard_data(_CF_TEXT)
            if not handle:
                return None
            pointer = global_lock(handle)
            if not pointer:
                return None
            try:
                text = ctypes.string_at(pointer).decode("mbcs", errors="replace")
            finally:
                global_unlock(handle)
            text = str(text).strip()
            return text or None
    finally:
        close_clipboard()

    return None


def _read_clipboard_text_if_ready(previous_text: str) -> Optional[str]:
    current_text = _read_clipboard_text()
    if not current_text:
        return None
    if previous_text and current_text == previous_text:
        return None
    if _looks_like_crystaldiskinfo_report(current_text):
        return current_text
    return None


def _read_diskinfo_text_if_ready(output_path: pathlib.Path, previous_data: bytes) -> Optional[str]:
    try:
        current_data = output_path.read_bytes()
    except OSError:
        return None
    if not current_data:
        return None
    decoded_text = _decode_text_bytes(current_data)
    if not _looks_like_crystaldiskinfo_report(decoded_text):
        return None
    if not previous_data or current_data != previous_data:
        return decoded_text
    return None


def _read_crystaldiskinfo_output_if_ready(
    output_path: pathlib.Path,
    previous_data: bytes,
    previous_clipboard_text: str,
) -> Optional[str]:
    diskinfo_text = _read_diskinfo_text_if_ready(output_path, previous_data)
    if diskinfo_text is not None:
        return diskinfo_text
    return _read_clipboard_text_if_ready(previous_clipboard_text)


def _wait_for_crystaldiskinfo_output(
    output_path: pathlib.Path,
    previous_data: bytes,
    previous_clipboard_text: str,
    seconds: float,
) -> Optional[str]:
    deadline = time.monotonic() + max(1.0, float(seconds))
    while time.monotonic() < deadline:
        text = _read_crystaldiskinfo_output_if_ready(output_path, previous_data, previous_clipboard_text)
        if text is not None:
            return text
        time.sleep(0.25)
    return _read_crystaldiskinfo_output_if_ready(output_path, previous_data, previous_clipboard_text)


def _run_crystaldiskinfo_dump(executable: pathlib.Path, timeout: int = 180) -> str:
    output_path = executable.parent / "DiskInfo.txt"
    previous_data = b""
    if output_path.is_file():
        try:
            previous_data = output_path.read_bytes()
        except OSError:
            previous_data = b""
        try:
            output_path.unlink()
            previous_data = b""
        except OSError:
            pass

    previous_clipboard_text = _read_clipboard_text() or ""

    launch_issues: List[str] = []
    launch_methods = [
        ("vbs-hidden", lambda: _run_elevated_hidden_vbs_command(executable, "/CopyExit", timeout=timeout)),
        ("scheduled-task-hidden", lambda: _run_elevated_background_task(executable, "/CopyExit", timeout=timeout)),
        ("direct-elevated", lambda: _run_elevated_command(str(executable), "/CopyExit", timeout=timeout)),
    ]

    for method_name, method_runner in launch_methods:
        try:
            exit_code = method_runner()
        except PermissionError:
            raise
        except Exception as exc:
            launch_issues.append(f"{method_name}: launch failed ({exc})")
            continue

        if exit_code != 0:
            launch_issues.append(f"{method_name}: exit code {exit_code}")

        wait_time = 10.0 if method_name != "direct-elevated" else 25.0
        output_text = _wait_for_crystaldiskinfo_output(
            output_path=output_path,
            previous_data=previous_data,
            previous_clipboard_text=previous_clipboard_text,
            seconds=wait_time,
        )
        if output_text is not None:
            return output_text

        launch_issues.append(f"{method_name}: no CrystalDiskInfo output")
        previous_clipboard_text = _read_clipboard_text() or previous_clipboard_text

    if launch_issues:
        log.warning("Disc Checker launch issues: %s", " | ".join(launch_issues[:6]))

    raise RuntimeError("CrystalDiskInfo did not produce readable output.")


def _parse_section_properties(lines: List[str]) -> Tuple[Dict[str, str], List[Tuple[str, str]]]:
    properties: Dict[str, str] = {}
    ordered: List[Tuple[str, str]] = []
    for line in lines:
        match = _KEY_VALUE_RE.match(line)
        if not match:
            continue
        key_display = match.group(1).strip()
        key = key_display.lower()
        value = match.group(2).strip()
        if key and value and key not in properties:
            properties[key] = value
            ordered.append((key_display, value))
    return properties, ordered


def _split_disk_sections(text: str) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if _DISK_LIST_ENTRY_RE.match(line):
            continue

        header_match = _DISK_HEADER_RE.match(line)
        if header_match:
            if current is not None:
                sections.append(current)
            current = {
                "Number": _to_int(header_match.group(1)),
                "HeaderName": header_match.group(2).strip(),
                "Lines": [],
            }
            continue

        if current is not None:
            current["Lines"].append(line)

    if current is not None:
        sections.append(current)
    return sections


def _build_entry_from_section(section: Dict[str, Any]) -> Dict[str, Any]:
    properties, ordered_properties = _parse_section_properties(section.get("Lines") or [])

    model_name = _first_non_empty(properties.get("model"), section.get("HeaderName"))
    serial_number = _first_non_empty(properties.get("serial number"))
    size_bytes = _parse_size_bytes(properties.get("disk size"))
    interface = _first_non_empty(properties.get("interface"))
    rotation = _first_non_empty(properties.get("rotation rate"))

    health_status_raw = _first_non_empty(properties.get("health status"), "Unknown")
    health_percent = _parse_health_percent(health_status_raw)
    health_code = _parse_health_code(health_status_raw, health_percent)
    temperature = _parse_temperature(properties.get("temperature"))
    power_on_hours = _to_int(properties.get("power on hours"))

    media_type = _infer_media_type(interface, rotation, model_name)
    wear: Optional[int] = None
    if isinstance(health_percent, int):
        wear = max(0, min(100, 100 - health_percent))

    health_status = health_status_raw

    return {
        "Number": section.get("Number"),
        "FriendlyName": model_name,
        "SerialNumber": serial_number,
        "Size": size_bytes,
        "BusType": interface if interface else "no data",
        "MediaType": media_type,
        "HealthStatus": health_status,
        "HealthPercent": health_percent,
        "Temperature": temperature,
        "Wear": wear,
        "PowerOnHours": power_on_hours,
        "CdiProperties": ordered_properties,
        "_healthCode": health_code,
        "_source": "crystaldiskinfo",
    }


def _parse_crystaldiskinfo_entries(text: str) -> List[Dict[str, Any]]:
    sections = _split_disk_sections(text)
    entries: List[Dict[str, Any]] = []
    for section in sections:
        entry = _build_entry_from_section(section)
        if entry.get("FriendlyName"):
            entries.append(entry)
    return entries


def _collect_disk_entries() -> List[Dict[str, Any]]:
    cdi_root = _get_cdi_root()
    executable = _find_crystaldiskinfo_exe()
    if executable is None:
        raise RuntimeError("CrystalDiskInfo executable was not found in the add-on package.")
    if not (cdi_root / "CdiResource").is_dir():
        raise RuntimeError("CrystalDiskInfo CdiResource directory is missing.")
    if not (cdi_root / "Smart").is_dir():
        raise RuntimeError("CrystalDiskInfo Smart directory is missing.")

    try:
        output_text = _run_crystaldiskinfo_dump(executable)
    except PermissionError:
        raise RuntimeError("UAC cancelled by user")
    except TimeoutError:
        raise RuntimeError("CrystalDiskInfo timeout.")
    except Exception as exc:
        raise RuntimeError(f"CrystalDiskInfo failed: {exc}")

    entries = _parse_crystaldiskinfo_entries(output_text)
    if entries:
        return entries
    raise RuntimeError("CrystalDiskInfo did not return readable disk data.")


def _is_bad_health(entry: Dict[str, Any]) -> bool:
    health_percent = entry.get("HealthPercent")
    if isinstance(health_percent, int) and health_percent < 80:
        return True
    health_code = entry.get("_healthCode")
    if health_code in (1, 2):
        return True
    temperature = entry.get("Temperature")
    if isinstance(temperature, int) and temperature >= 60:
        return True
    return False


def _build_report(entries: List[Dict[str, Any]]) -> Dict[str, str]:
    if not entries:
        return {
            "summary": "No physical disks were detected.",
            "details": "Windows did not return any physical disks.",
        }

    warnings = 0
    lines = []
    for entry in sorted(entries, key=lambda item: (item.get("Number") is None, item.get("Number"))):
        alert = _is_bad_health(entry)
        if alert:
            warnings += 1

        number = _to_display_value(entry.get("Number"), "?")
        name = _to_display_value(entry.get("FriendlyName"))

        health_percent = entry.get("HealthPercent")
        health_percent_text = f"{health_percent}%" if isinstance(health_percent, int) else "no data"

        temperature = entry.get("Temperature")
        temperature_text = f"{temperature} C" if isinstance(temperature, int) else "no data"

        cdi_properties = entry.get("CdiProperties")

        state_label = "ALERT" if alert else "OK"
        parts = [
            f"[{state_label}] Disk {number}: {name}",
            f"  Health: {health_percent_text}",
            f"  Temperature: {temperature_text}",
        ]
        if isinstance(cdi_properties, list):
            for item in cdi_properties:
                if not isinstance(item, tuple) or len(item) != 2:
                    continue
                key = str(item[0]).strip()
                value = str(item[1]).strip()
                if not key or not value:
                    continue
                parts.append(f"  {key}: {value}")
        lines.append("\n".join(parts))

    healthy = len(entries) - warnings
    summary = f"Disks: {len(entries)}. Healthy: {healthy}. Alerts: {warnings}."
    details = "\n\n".join(lines)
    return {
        "summary": summary,
        "details": details,
    }


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    scriptCategory = _("Disk Health")

    def __init__(self) -> None:
        super().__init__()
        self._checking = False
        self._state_lock = threading.Lock()
        self._tools_menu = gui.mainFrame.sysTrayIcon.toolsMenu
        self._menu_item = self._tools_menu.Append(
            wx.ID_ANY,
            _("Check disk health"),
        )
        gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self._on_menu_action, self._menu_item)

    def terminate(self) -> None:
        try:
            if self._menu_item is not None:
                gui.mainFrame.sysTrayIcon.Unbind(
                    wx.EVT_MENU,
                    handler=self._on_menu_action,
                    source=self._menu_item,
                )
                self._tools_menu.Remove(self._menu_item)
                self._menu_item = None
        except Exception:
            log.exception("Disc Checker: failed to clean up menu item.")
        super().terminate()

    @script(
        description=_("Checks all physical disks and displays a health report."),
        gesture="kb:NVDA+shift+d",
    )
    def script_check_disk_health(self, gesture) -> None:
        self._trigger_check()

    def _on_menu_action(self, event: wx.CommandEvent) -> None:
        self._trigger_check()

    def _trigger_check(self) -> None:
        with self._state_lock:
            if self._checking:
                ui.message(_("Disk health check is already running."))
                return
            self._checking = True
        ui.message(_("Checking disk health..."))
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        try:
            entries = _collect_disk_entries()
            report = _build_report(entries)
            wx.CallAfter(self._present_report, report["summary"], report["details"])
        except RuntimeError as error:
            error_text = str(error)
            if "UAC" in error_text.upper():
                wx.CallAfter(
                    ui.message,
                    _("Elevation was cancelled. Disk health check was aborted."),
                )
            else:
                log.exception("Disc Checker: disk check failed: %s", error_text)
                wx.CallAfter(
                    ui.message,
                    _("Disk health check failed. See NVDA log for details."),
                )
        except Exception:
            log.exception("Disc Checker: disk check failed.")
            wx.CallAfter(
                ui.message,
                _("Disk health check failed. See NVDA log for details."),
            )
        finally:
            with self._state_lock:
                self._checking = False

    def _present_report(self, summary: str, details: str) -> None:
        ui.message(summary)
        ui.browseableMessage(details, title=_("Disk Health Report"))
