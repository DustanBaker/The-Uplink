#!/usr/bin/env python3
"""The-Uplink - Main entry point."""

import customtkinter as ctk
from database import init_db, init_inventory_db, create_user, get_user_by_username
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


def run_app():
    """Run the application."""

    def on_login_success(user: dict):
    
        """Callback when login is successful."""
        app = MainApplication(user, on_logout=run_app)
        app.mainloop()

    login_window = LoginWindow(on_login_success=on_login_success)
    login_window.mainloop()


def main():
    """Main entry point."""
    # Initialize databases
    init_db()
    init_inventory_db()

    # Create default user if needed
    create_default_user()

    # Run the application
    run_app()


if __name__ == "__main__":
    main()
