#!/usr/bin/env python3
"""The-Uplink - Main entry point."""

import customtkinter as ctk
from database import init_db, init_inventory_db, create_user, get_user_by_username
from database.sku_cache import init_sku_cache
from database.inventory_cache import init_inventory_cache
from utils import hash_password
from gui import LoginWindow, MainApplication

# Configure CustomTkinter
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Default admin credentials
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"


def create_default_user():
    """Create default admin user if no users exist."""
    if get_user_by_username(DEFAULT_USERNAME) is None:
        password_hash = hash_password(DEFAULT_PASSWORD)
        create_user(DEFAULT_USERNAME, password_hash)
        print(f"Created default user: {DEFAULT_USERNAME} / {DEFAULT_PASSWORD}")


def close_splash():
    """Close the splash screen if running as frozen executable."""
    try:
        import pyi_splash
        pyi_splash.close()
    except ImportError:
        pass  # Not running as frozen executable


def main():
    """Main entry point."""
    # Initialize databases
    init_db()
    for project in ["ecoflow", "halo", "ams_ine"]:
        init_inventory_db(project)

    # Initialize SKU cache
    init_sku_cache()

    # Initialize inventory cache (local-first for fast submits)
    init_inventory_cache()

    # Create default user if needed
    create_default_user()

    # Close splash screen before showing login window
    close_splash()

    # Main application loop - avoids recursive mainloop calls on logout
    while True:
        logged_in_user = [None]
        should_restart = [False]

        def on_login_success(user: dict):
            logged_in_user[0] = user

        login_window = LoginWindow(on_login_success=on_login_success)
        login_window.mainloop()

        if logged_in_user[0] is None:
            break  # User closed login window

        def on_logout():
            should_restart[0] = True

        app = MainApplication(logged_in_user[0], on_logout=on_logout)
        app.mainloop()

        if not should_restart[0]:
            break  # User closed app window normally


if __name__ == "__main__":
    main()
