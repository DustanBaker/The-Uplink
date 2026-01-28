"""Auto-update functionality using GitHub releases."""

import threading
import webbrowser
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
import json
import re


def parse_version(version_str: str) -> tuple:
    """Parse version string into comparable tuple.

    Handles formats like "1.0.0", "v1.0.0", "1.2.3-beta", etc.
    """
    # Remove 'v' prefix if present
    version_str = version_str.lstrip('v')
    # Extract numeric parts
    match = re.match(r'(\d+)\.(\d+)\.(\d+)', version_str)
    if match:
        return tuple(int(x) for x in match.groups())
    return (0, 0, 0)


def is_newer_version(latest: str, current: str) -> bool:
    """Check if latest version is newer than current version."""
    return parse_version(latest) > parse_version(current)


def check_for_updates(github_repo: str, current_version: str, callback: callable):
    """Check GitHub for updates in a background thread.

    Args:
        github_repo: GitHub repository in "owner/repo" format
        current_version: Current app version string
        callback: Function to call with (has_update, latest_version, download_url, release_notes)
                  Called with (False, None, None, None) if check fails or no update
    """
    def do_check():
        try:
            url = f"https://api.github.com/repos/{github_repo}/releases/latest"
            request = Request(url, headers={
                'User-Agent': 'The-Uplink-Updater',
                'Accept': 'application/vnd.github.v3+json'
            })

            with urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))

            latest_version = data.get('tag_name', '')
            release_notes = data.get('body', '')
            html_url = data.get('html_url', '')

            # Look for Windows installer in assets
            download_url = html_url  # Default to release page
            for asset in data.get('assets', []):
                name = asset.get('name', '').lower()
                if 'setup' in name or 'installer' in name or name.endswith('.exe'):
                    download_url = asset.get('browser_download_url', html_url)
                    break

            if is_newer_version(latest_version, current_version):
                callback(True, latest_version, download_url, release_notes)
            else:
                callback(False, None, None, None)

        except (URLError, HTTPError, json.JSONDecodeError, KeyError, TimeoutError):
            # Silently fail - update check is non-critical
            callback(False, None, None, None)

    thread = threading.Thread(target=do_check, daemon=True)
    thread.start()


def open_download_page(url: str):
    """Open the download URL in the default browser."""
    webbrowser.open(url)


def show_update_dialog(parent, latest_version: str, download_url: str, release_notes: str = ""):
    """Show an update available dialog.

    Args:
        parent: Parent tkinter window
        latest_version: The new version available
        download_url: URL to download the update
        release_notes: Optional release notes to display
    """
    import customtkinter as ctk

    dialog = ctk.CTkToplevel(parent)
    dialog.title("Update Available")
    dialog.geometry("500x450")
    dialog.resizable(True, True)
    dialog.minsize(400, 300)
    dialog.transient(parent)

    # Center dialog
    dialog.update_idletasks()
    x = parent.winfo_x() + (parent.winfo_width() // 2) - (500 // 2)
    y = parent.winfo_y() + (parent.winfo_height() // 2) - (450 // 2)
    dialog.geometry(f"+{x}+{y}")

    dialog.wait_visibility()
    dialog.grab_set()

    # Main container
    main_frame = ctk.CTkFrame(dialog, fg_color="transparent")
    main_frame.pack(expand=True, fill="both", padx=20, pady=20)

    # Title
    title_label = ctk.CTkLabel(
        main_frame,
        text="A new version is available!",
        font=ctk.CTkFont(size=20, weight="bold")
    )
    title_label.pack(pady=(0, 10))

    # Version
    version_label = ctk.CTkLabel(
        main_frame,
        text=f"Version {latest_version}",
        font=ctk.CTkFont(size=16)
    )
    version_label.pack(pady=(0, 20))

    # Release notes (scrollable)
    if release_notes:
        notes_frame = ctk.CTkScrollableFrame(main_frame, height=150)
        notes_frame.pack(fill="both", expand=True, pady=(0, 20))

        display_notes = release_notes[:500] + "..." if len(release_notes) > 500 else release_notes
        notes_label = ctk.CTkLabel(
            notes_frame,
            text=display_notes,
            font=ctk.CTkFont(size=13),
            wraplength=420,
            justify="left"
        )
        notes_label.pack(anchor="w")

    # Buttons frame at bottom
    button_frame = ctk.CTkFrame(main_frame, fg_color="transparent", height=60)
    button_frame.pack(fill="x", side="bottom")
    button_frame.pack_propagate(False)

    later_btn = ctk.CTkButton(
        button_frame,
        text="Later",
        width=150,
        height=45,
        font=ctk.CTkFont(size=15),
        fg_color="gray",
        command=dialog.destroy
    )
    later_btn.pack(side="left", pady=10)

    def do_download():
        open_download_page(download_url)
        dialog.destroy()

    download_btn = ctk.CTkButton(
        button_frame,
        text="Download Update",
        width=180,
        height=45,
        font=ctk.CTkFont(size=15),
        fg_color="#28a745",
        hover_color="#218838",
        command=do_download
    )
    download_btn.pack(side="right", pady=10)
