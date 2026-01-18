import customtkinter as ctk
from database import get_user_by_username
from utils import verify_password


class LoginWindow(ctk.CTk):
    """Login window for The-Uplink application."""

    def __init__(self, on_login_success: callable):
        super().__init__()

        self.on_login_success = on_login_success
        self.logged_in_user = None

        self.title("The-Uplink - Login")
        self.geometry("400x300")
        self.resizable(False, False)

        self._center_window()
        self._create_widgets()

    def _center_window(self):
        """Center the window on the screen."""
        self.update_idletasks()
        width = 400
        height = 300
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _create_widgets(self):
        """Create and layout all widgets."""
        # Main frame with padding
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(expand=True, fill="both", padx=40, pady=40)

        # Title
        title_label = ctk.CTkLabel(
            main_frame,
            text="The-Uplink",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(pady=(0, 30))

        # Username
        username_label = ctk.CTkLabel(main_frame, text="Username")
        username_label.pack(anchor="w")

        self.username_entry = ctk.CTkEntry(main_frame, width=320)
        self.username_entry.pack(pady=(5, 15))

        # Password
        password_label = ctk.CTkLabel(main_frame, text="Password")
        password_label.pack(anchor="w")

        self.password_entry = ctk.CTkEntry(main_frame, width=320, show="*")
        self.password_entry.pack(pady=(5, 20))

        # Error message label (hidden by default)
        self.error_label = ctk.CTkLabel(
            main_frame,
            text="",
            text_color="red"
        )
        self.error_label.pack(pady=(0, 10))

        # Login button
        login_button = ctk.CTkButton(
            main_frame,
            text="Login",
            width=320,
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
