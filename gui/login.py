import customtkinter as ctk
from PIL import Image, ImageTk
import os
from database import get_user_by_username
from utils import verify_password


class LoginWindow(ctk.CTk):
    """Login window for The-Uplink application."""

    def __init__(self, on_login_success: callable):
        super().__init__()

        self.on_login_success = on_login_success
        self.logged_in_user = None

        self.title("The-Uplink - Login")
        self.geometry("400x400")
        self.resizable(False, False)

       # Set window icon
        icon_path = os.path.join(os.path.dirname(__file__), "The_Uplink_App_Icon.ico")
        if os.path.exists(icon_path):
            try:
                # For .ico files on Windows, use wm_iconbitmap directly
                self.iconbitmap(icon_path)
            except Exception:
                # Fallback for non-Windows or if iconbitmap fails
                try:
                    icon_image = Image.open(icon_path)
                    self._icon_photo = ImageTk.PhotoImage(icon_image)
                    self.iconphoto(True, self._icon_photo)
                except Exception:
                    pass  # Icon setting failed, continue without icon

        self._center_window()
        self._create_widgets()

    def _center_window(self):
        """Center the window on the screen."""
        self.update_idletasks()
        width = 400
        height = 600
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _create_widgets(self):
        """Create and layout all widgets."""
        # Main frame with padding
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(expand=True, fill="both", padx=40, pady=40)

        # Logo
        logo_path = os.path.join(os.path.dirname(__file__), "The Uplink logo.png")
        if os.path.exists(logo_path):
            logo_image = Image.open(logo_path)
            # Resize logo maintaining aspect ratio
            logo_image = logo_image.resize((200, 200), Image.LANCZOS)
            self._logo_photo = ctk.CTkImage(light_image=logo_image, dark_image=logo_image, size=(200, 200))
            logo_label = ctk.CTkLabel(main_frame, image=self._logo_photo, text="")
            logo_label.pack(pady=(0, 30))
        else:
            # Fallback to text if image not found
            title_label = ctk.CTkLabel(
                main_frame,
                text="The-Uplink",
                font=ctk.CTkFont(size=28, weight="bold")
            )
            title_label.pack(pady=(0, 30))

        # Username row
        username_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        username_frame.pack(fill="x", pady=(0, 15))
        username_label = ctk.CTkLabel(username_frame, text="Username", font=ctk.CTkFont(size=14), width=80)
        username_label.pack(side="left")
        self.username_entry = ctk.CTkEntry(username_frame, width=280, font=ctk.CTkFont(size=14))
        self.username_entry.pack(side="left", padx=(10, 0))

        # Password row
        password_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        password_frame.pack(fill="x", pady=(0, 20))
        password_label = ctk.CTkLabel(password_frame, text="Password", font=ctk.CTkFont(size=14), width=80)
        password_label.pack(side="left")
        self.password_entry = ctk.CTkEntry(password_frame, width=280, show="*", font=ctk.CTkFont(size=14))
        self.password_entry.pack(side="left", padx=(10, 0))

        # Error message label (hidden by default)
        self.error_label = ctk.CTkLabel(
            main_frame,
            text="",
            text_color="red",
            font=ctk.CTkFont(size=14)
        )
        self.error_label.pack(pady=(0, 10))

        # Login button
        login_button = ctk.CTkButton(
            main_frame,
            text="Login",
            width=320,
            font=ctk.CTkFont(size=14),
            command=self._handle_login
        )
        login_button.pack()

        # Bind Enter key to login
        self.bind("<Return>", lambda e: self._handle_login())

    def _handle_login(self):
        """Handle login button click."""
        username = self.username_entry.get().strip()
        password = self.password_entry.get()

        if not username or not password:
            self._show_error("Please enter username and password")
            return

        user = get_user_by_username(username)

        if user and verify_password(password, user["password_hash"]):
            self.logged_in_user = user
            self.destroy()
            self.on_login_success(user)
        else:
            self._show_error("Invalid username or password")

    def _show_error(self, message: str):
        """Display an error message."""
        self.error_label.configure(text=message)
