"""Resource path utilities for PyInstaller compatibility."""

import os
import sys


def get_resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and PyInstaller.

    Args:
        relative_path: Path relative to the application root or bundle.

    Returns:
        Absolute path to the resource.
    """
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        base_path = sys._MEIPASS
    else:
        # Running in development
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    return os.path.join(base_path, relative_path)


def get_gui_resource(filename: str) -> str:
    """Get path to a resource in the gui folder.

    Args:
        filename: Name of the file in the gui folder.

    Returns:
        Absolute path to the gui resource.
    """
    return get_resource_path(os.path.join("gui", filename))
