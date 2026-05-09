"""File dialog strategies — abstracts OS-native file pickers.

Provides a strategy interface so the app can use native dialogs locally
and gracefully degrade to no-op in headless/cloud environments.
"""

import subprocess
import sys
from abc import ABC, abstractmethod
from typing import List


class FileDialogStrategy(ABC):
    """Interface for file selection dialogs."""

    @abstractmethod
    def pick_file(self) -> str:
        """Open a single-file dialog and return the selected path (or "")."""
        ...

    @abstractmethod
    def pick_files(self) -> List[str]:
        """Open a multi-file dialog and return selected paths (or [])."""
        ...


class NativeDialogStrategy(FileDialogStrategy):
    """Uses osascript (macOS) or tkinter (Linux/Windows) for file picking."""

    def pick_file(self) -> str:
        try:
            if sys.platform == "darwin":
                cmd = ['osascript', '-e', 'POSIX path of (choose file of type {"public.data"})']
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if res.returncode == 0:
                    return res.stdout.strip()
            else:
                code = (
                    "import tkinter as tk, tkinter.filedialog as fd; "
                    "root=tk.Tk(); root.withdraw(); "
                    "root.call('wm','attributes','.','-topmost',True); "
                    "print(fd.askopenfilename())"
                )
                res = subprocess.run(
                    [sys.executable, "-c", code],
                    capture_output=True, text=True, timeout=120,
                )
                if res.returncode == 0:
                    return res.stdout.strip()
        except subprocess.TimeoutExpired:
            pass
        except Exception:  # noqa: BLE001
            pass
        return ""

    def pick_files(self) -> List[str]:
        try:
            if sys.platform == "darwin":
                script = (
                    'set theFiles to choose file of type {"public.data"} '
                    'with multiple selections allowed\n'
                    'set thePaths to ""\n'
                    'repeat with aFile in theFiles\n'
                    'set thePaths to thePaths & POSIX path of aFile & "\\n"\n'
                    'end repeat\n'
                    'return thePaths'
                )
                cmd = ['osascript', '-e', script]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if res.returncode == 0:
                    return [p for p in res.stdout.strip().split('\n') if p]
            else:
                code = (
                    "import tkinter as tk, tkinter.filedialog as fd; "
                    "root=tk.Tk(); root.withdraw(); "
                    "root.call('wm','attributes','.','-topmost',True); "
                    "print('\\n'.join(fd.askopenfilenames()))"
                )
                res = subprocess.run(
                    [sys.executable, "-c", code],
                    capture_output=True, text=True, timeout=120,
                )
                if res.returncode == 0:
                    return [p for p in res.stdout.strip().split('\n') if p]
        except subprocess.TimeoutExpired:
            pass
        except Exception:  # noqa: BLE001
            pass
        return []


class NoOpDialogStrategy(FileDialogStrategy):
    """Headless/cloud fallback — always returns empty."""

    def pick_file(self) -> str:
        return ""

    def pick_files(self) -> List[str]:
        return []


def get_dialog_strategy() -> FileDialogStrategy:
    """Select the appropriate dialog strategy for the current environment."""
    # If DISPLAY is unset on Linux, or we're in a container, use NoOp
    if sys.platform != "darwin" and not sys.stdin.isatty():
        return NoOpDialogStrategy()
    return NativeDialogStrategy()
