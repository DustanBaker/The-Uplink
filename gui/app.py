import customtkinter as ctk
from database import create_user, get_all_users, update_user_password, delete_user, add_inventory_item, get_all_inventory, update_inventory_item, delete_inventory_item
from utils import hash_password


class MainApplication(ctk.CTk):
    """Main application window after successful login."""

    def __init__(self, user: dict, on_logout: callable):
        super().__init__()

        self.user = user
        self.on_logout = on_logout

        self.title("The-Uplink")
        self.geometry("900x600")
        self.minsize(800, 500)

        self._create_widgets()

    def _create_widgets(self):
        """Create and layout all widgets."""
        # Header frame
        header_frame = ctk.CTkFrame(self)
        header_frame.pack(fill="x", padx=10, pady=10)

        # Title
        title_label = ctk.CTkLabel(
            header_frame,
            text="The-Uplink",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.pack(side="left", padx=10)

        # User info and logout
        user_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        user_frame.pack(side="right", padx=10)

        user_label = ctk.CTkLabel(
            user_frame,
            text=f"Logged in as: {self.user['username']}"
        )
        user_label.pack(side="left", padx=(0, 10))

        logout_button = ctk.CTkButton(
            user_frame,
            text="Logout",
            width=80,
            command=self._handle_logout
        )
        logout_button.pack(side="left")

        # Main content area
        content_frame = ctk.CTkFrame(self)
        content_frame.pack(expand=True, fill="both", padx=10, pady=(0, 10))

        # Show admin panel if user is admin, otherwise show data entry
        if self.user['username'] == 'admin':
            self._create_admin_panel(content_frame)
        else:
            self._create_user_panel(content_frame)

    def _create_user_panel(self, parent):
        """Create the standard user panel with data entry fields."""
        # Configure parent for vertical layout
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        # Top section - Data entry form
        form_frame = ctk.CTkFrame(parent)
        form_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        # Title
        title_label = ctk.CTkLabel(
            form_frame,
            text="Item Entry",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(15, 15), padx=20)

        # Form fields in horizontal layout
        fields_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        fields_frame.pack(padx=20, pady=(0, 15), fill="x")

        # Item SKU
        sku_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
        sku_frame.pack(side="left", padx=(0, 15))
        ctk.CTkLabel(sku_frame, text="Item SKU").pack(anchor="w")
        self.sku_entry = ctk.CTkEntry(sku_frame, width=180)
        self.sku_entry.pack()

        # Serial Number
        serial_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
        serial_frame.pack(side="left", padx=(0, 15))
        ctk.CTkLabel(serial_frame, text="Serial Number").pack(anchor="w")
        self.serial_entry = ctk.CTkEntry(serial_frame, width=180)
        self.serial_entry.pack()

        # LPN
        lpn_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
        lpn_frame.pack(side="left", padx=(0, 15))
        ctk.CTkLabel(lpn_frame, text="LPN").pack(anchor="w")
        self.lpn_entry = ctk.CTkEntry(lpn_frame, width=150)
        self.lpn_entry.pack()

        # Repair State
        repair_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
        repair_frame.pack(side="left", padx=(0, 15))
        ctk.CTkLabel(repair_frame, text="Repair State").pack(anchor="w")
        self.repair_options = ["To be repaired", "To be refurbished", "Storage only"]
        self.repair_dropdown = ctk.CTkOptionMenu(repair_frame, width=150, values=self.repair_options)
        self.repair_dropdown.set(self.repair_options[0])
        self.repair_dropdown.pack()

        # Submit button and status
        submit_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
        submit_frame.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(submit_frame, text=" ").pack()  # Spacer for alignment
        submit_button = ctk.CTkButton(
            submit_frame,
            text="Submit",
            width=100,
            command=self._handle_submit_entry
        )
        submit_button.pack()

        # Status message
        self.user_status_label = ctk.CTkLabel(form_frame, text="", height=20)
        self.user_status_label.pack(pady=(0, 10))

        # Bottom section - Inventory list
        list_frame = ctk.CTkFrame(parent)
        list_frame.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")

        list_title = ctk.CTkLabel(
            list_frame,
            text="Active Inventory",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        list_title.pack(pady=(15, 10), padx=20, anchor="w")

        # Scrollable frame for inventory list
        self.inventory_list_frame = ctk.CTkScrollableFrame(list_frame)
        self.inventory_list_frame.pack(expand=True, fill="both", padx=10, pady=(0, 10))

        # Configure columns
        self.inventory_list_frame.grid_columnconfigure(0, weight=1)
        self.inventory_list_frame.grid_columnconfigure(1, weight=1)
        self.inventory_list_frame.grid_columnconfigure(2, weight=1)
        self.inventory_list_frame.grid_columnconfigure(3, weight=1)
        self.inventory_list_frame.grid_columnconfigure(4, weight=1)
        self.inventory_list_frame.grid_columnconfigure(5, weight=1)

        self._refresh_inventory_list()

    def _refresh_inventory_list(self):
        """Refresh the inventory list display."""
        # Clear existing widgets
        for widget in self.inventory_list_frame.winfo_children():
            widget.destroy()

        # Header row
        headers = ["SKU", "Serial Number", "LPN", "Repair State", "Entered By", "Date", "", ""]
        for col, header in enumerate(headers):
            label = ctk.CTkLabel(
                self.inventory_list_frame,
                text=header,
                font=ctk.CTkFont(weight="bold")
            )
            label.grid(row=0, column=col, padx=5, pady=(0, 10), sticky="w")

        # Inventory rows
        items = get_all_inventory()
        for row, item in enumerate(items, start=1):
            ctk.CTkLabel(self.inventory_list_frame, text=item['item_sku']).grid(
                row=row, column=0, padx=5, pady=3, sticky="w")
            ctk.CTkLabel(self.inventory_list_frame, text=item['serial_number']).grid(
                row=row, column=1, padx=5, pady=3, sticky="w")
            ctk.CTkLabel(self.inventory_list_frame, text=item['lpn']).grid(
                row=row, column=2, padx=5, pady=3, sticky="w")
            ctk.CTkLabel(self.inventory_list_frame, text=item['repair_state']).grid(
                row=row, column=3, padx=5, pady=3, sticky="w")
            ctk.CTkLabel(self.inventory_list_frame, text=item['entered_by']).grid(
                row=row, column=4, padx=5, pady=3, sticky="w")
            # Format date
            date_str = item['created_at'].split('T')[0] if 'T' in item['created_at'] else item['created_at'][:10]
            ctk.CTkLabel(self.inventory_list_frame, text=date_str).grid(
                row=row, column=5, padx=5, pady=3, sticky="w")

            # Edit button
            edit_btn = ctk.CTkButton(
                self.inventory_list_frame,
                text="Edit",
                width=60,
                height=24,
                command=lambda i=item: self._show_edit_inventory_dialog(i)
            )
            edit_btn.grid(row=row, column=6, padx=2, pady=3)

            # Delete button
            delete_btn = ctk.CTkButton(
                self.inventory_list_frame,
                text="Delete",
                width=60,
                height=24,
                fg_color="#dc3545",
                hover_color="#c82333",
                command=lambda i=item: self._delete_inventory_item(i)
            )
            delete_btn.grid(row=row, column=7, padx=2, pady=3)

    def _show_edit_inventory_dialog(self, item: dict):
        """Show dialog to edit an inventory item."""
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Edit Item - {item['item_sku']}")
        dialog.geometry("400x450")
        dialog.resizable(False, False)
        dialog.transient(self)

        # Center dialog
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (400 // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (450 // 2)
        dialog.geometry(f"+{x}+{y}")

        dialog.wait_visibility()
        dialog.grab_set()

        # Content
        frame = ctk.CTkFrame(dialog, fg_color="transparent")
        frame.pack(fill="both", padx=20, pady=20)

        title_label = ctk.CTkLabel(
            frame,
            text="Edit Inventory Item",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        title_label.pack(pady=(0, 10))

        # Item SKU
        ctk.CTkLabel(frame, text="Item SKU").pack(anchor="w")
        sku_entry = ctk.CTkEntry(frame, width=340)
        sku_entry.insert(0, item['item_sku'])
        sku_entry.pack(pady=(2, 8))

        # Serial Number
        ctk.CTkLabel(frame, text="Serial Number").pack(anchor="w")
        serial_entry = ctk.CTkEntry(frame, width=340)
        serial_entry.insert(0, item['serial_number'])
        serial_entry.pack(pady=(2, 8))

        # LPN
        ctk.CTkLabel(frame, text="LPN").pack(anchor="w")
        lpn_entry = ctk.CTkEntry(frame, width=340)
        lpn_entry.insert(0, item['lpn'])
        lpn_entry.pack(pady=(2, 8))

        # Repair State
        ctk.CTkLabel(frame, text="Repair State").pack(anchor="w")
        repair_options = ["To be repaired", "To be refurbished", "Storage only"]
        repair_dropdown = ctk.CTkOptionMenu(frame, width=340, values=repair_options)
        repair_dropdown.set(item['repair_state'])
        repair_dropdown.pack(pady=(2, 10))

        # Status
        status_label = ctk.CTkLabel(frame, text="", text_color="red")
        status_label.pack(pady=(0, 5))

        def do_save():
            sku = sku_entry.get().strip()
            serial = serial_entry.get().strip()
            lpn = lpn_entry.get().strip()
            repair_state = repair_dropdown.get()

            if not sku or not serial or not lpn:
                status_label.configure(text="All fields are required")
                return

            if update_inventory_item(item['id'], sku, serial, lpn, repair_state):
                dialog.destroy()
                self._refresh_inventory_list()
                self._show_user_status("Item updated successfully", error=False)
            else:
                status_label.configure(text="Failed to update item")

        # Buttons
        button_frame = ctk.CTkFrame(frame, fg_color="transparent")
        button_frame.pack(fill="x")

        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancel",
            width=160,
            fg_color="gray",
            command=dialog.destroy
        )
        cancel_btn.pack(side="left")

        save_btn = ctk.CTkButton(
            button_frame,
            text="Save",
            width=160,
            command=do_save
        )
        save_btn.pack(side="right")

    def _delete_inventory_item(self, item: dict):
        """Delete an inventory item with confirmation."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Confirm Delete")
        dialog.geometry("300x150")
        dialog.resizable(False, False)
        dialog.transient(self)

        # Center dialog
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (300 // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (150 // 2)
        dialog.geometry(f"+{x}+{y}")

        dialog.wait_visibility()
        dialog.grab_set()

        frame = ctk.CTkFrame(dialog, fg_color="transparent")
        frame.pack(expand=True, fill="both", padx=20, pady=20)

        label = ctk.CTkLabel(
            frame,
            text=f"Delete item '{item['item_sku']}'?\nThis cannot be undone.",
            font=ctk.CTkFont(size=14)
        )
        label.pack(pady=(0, 20))

        def do_delete():
            if delete_inventory_item(item['id']):
                dialog.destroy()
                self._refresh_inventory_list()
                self._show_user_status("Item deleted", error=False)
            else:
                dialog.destroy()
                self._show_user_status("Failed to delete item", error=True)

        button_frame = ctk.CTkFrame(frame, fg_color="transparent")
        button_frame.pack(fill="x")

        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancel",
            width=120,
            fg_color="gray",
            command=dialog.destroy
        )
        cancel_btn.pack(side="left")

        delete_btn = ctk.CTkButton(
            button_frame,
            text="Delete",
            width=120,
            fg_color="#dc3545",
            hover_color="#c82333",
            command=do_delete
        )
        delete_btn.pack(side="right")

    def _handle_submit_entry(self):
        """Handle submit button click for item entry."""
        sku = self.sku_entry.get().strip()
        serial = self.serial_entry.get().strip()
        lpn = self.lpn_entry.get().strip()
        repair_state = self.repair_dropdown.get()

        # Basic validation
        if not sku:
            self._show_user_status("Item SKU is required", error=True)
            return

        if not serial:
            self._show_user_status("Serial Number is required", error=True)
            return

        if not lpn:
            self._show_user_status("LPN is required", error=True)
            return

        # Save to inventory database
        try:
            add_inventory_item(
                item_sku=sku,
                serial_number=serial,
                lpn=lpn,
                repair_state=repair_state,
                entered_by=self.user['username']
            )
            self._show_user_status("Entry submitted successfully", error=False)
        except Exception as e:
            self._show_user_status(f"Failed to save: {str(e)}", error=True)
            return

        # Clear form
        self.sku_entry.delete(0, 'end')
        self.serial_entry.delete(0, 'end')
        self.lpn_entry.delete(0, 'end')
        self.repair_dropdown.set(self.repair_options[0])

        # Refresh inventory list
        self._refresh_inventory_list()

        # Focus back to first field
        self.sku_entry.focus()

    def _show_user_status(self, message: str, error: bool = False):
        """Display a status message for user panel."""
        color = "red" if error else "green"
        self.user_status_label.configure(text=message, text_color=color)

    def _create_admin_panel(self, parent):
        """Create the admin panel with user management."""
        # Configure grid
        parent.grid_columnconfigure(0, weight=0)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        # Left side - Create user form
        create_frame = ctk.CTkFrame(parent)
        create_frame.grid(row=0, column=0, padx=10, pady=10, sticky="n")

        create_title = ctk.CTkLabel(
            create_frame,
            text="Create User",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        create_title.pack(pady=(15, 15), padx=20)

        form_frame = ctk.CTkFrame(create_frame, fg_color="transparent")
        form_frame.pack(padx=20, pady=(0, 15))

        # Username
        username_label = ctk.CTkLabel(form_frame, text="Username")
        username_label.grid(row=0, column=0, sticky="w", pady=(0, 5))

        self.new_username_entry = ctk.CTkEntry(form_frame, width=200)
        self.new_username_entry.grid(row=1, column=0, pady=(0, 10))

        # Password
        password_label = ctk.CTkLabel(form_frame, text="Password")
        password_label.grid(row=2, column=0, sticky="w", pady=(0, 5))

        self.new_password_entry = ctk.CTkEntry(form_frame, width=200, show="*")
        self.new_password_entry.grid(row=3, column=0, pady=(0, 10))

        # Confirm Password
        confirm_label = ctk.CTkLabel(form_frame, text="Confirm Password")
        confirm_label.grid(row=4, column=0, sticky="w", pady=(0, 5))

        self.confirm_password_entry = ctk.CTkEntry(form_frame, width=200, show="*")
        self.confirm_password_entry.grid(row=5, column=0, pady=(0, 15))

        # Status message
        self.status_label = ctk.CTkLabel(form_frame, text="", width=200, wraplength=180)
        self.status_label.grid(row=6, column=0, pady=(0, 10))

        # Create button
        create_button = ctk.CTkButton(
            form_frame,
            text="Create User",
            width=200,
            command=self._handle_create_user
        )
        create_button.grid(row=7, column=0)

        # Right side - User list
        list_frame = ctk.CTkFrame(parent)
        list_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="nsew")

        list_title = ctk.CTkLabel(
            list_frame,
            text="Existing Users",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        list_title.pack(pady=(15, 15), padx=20)

        # Scrollable frame for user list
        self.user_list_frame = ctk.CTkScrollableFrame(list_frame)
        self.user_list_frame.pack(expand=True, fill="both", padx=10, pady=(0, 10))

        # Configure columns for the list
        self.user_list_frame.grid_columnconfigure(0, weight=1)
        self.user_list_frame.grid_columnconfigure(1, weight=0)
        self.user_list_frame.grid_columnconfigure(2, weight=0)
        self.user_list_frame.grid_columnconfigure(3, weight=0)

        self._refresh_user_list()

    def _refresh_user_list(self):
        """Refresh the user list display."""
        # Clear existing widgets
        for widget in self.user_list_frame.winfo_children():
            widget.destroy()

        # Header row
        headers = ["Username", "Created", "", ""]
        for col, header in enumerate(headers):
            label = ctk.CTkLabel(
                self.user_list_frame,
                text=header,
                font=ctk.CTkFont(weight="bold")
            )
            label.grid(row=0, column=col, padx=5, pady=(0, 10), sticky="w")

        # User rows
        users = get_all_users()
        for row, user in enumerate(users, start=1):
            # Username
            username_label = ctk.CTkLabel(self.user_list_frame, text=user['username'])
            username_label.grid(row=row, column=0, padx=5, pady=5, sticky="w")

            # Created date (just the date part)
            created = user['created_at'].split('T')[0] if 'T' in user['created_at'] else user['created_at'][:10]
            created_label = ctk.CTkLabel(self.user_list_frame, text=created)
            created_label.grid(row=row, column=1, padx=5, pady=5, sticky="w")

            # Reset password button
            reset_btn = ctk.CTkButton(
                self.user_list_frame,
                text="Reset Password",
                width=110,
                height=28,
                command=lambda u=user['username']: self._show_reset_dialog(u)
            )
            reset_btn.grid(row=row, column=2, padx=5, pady=5)

            # Delete button (disabled for admin)
            delete_btn = ctk.CTkButton(
                self.user_list_frame,
                text="Delete",
                width=70,
                height=28,
                fg_color="#dc3545",
                hover_color="#c82333",
                command=lambda u=user['username']: self._handle_delete_user(u)
            )
            delete_btn.grid(row=row, column=3, padx=5, pady=5)

            # Disable delete for admin user
            if user['username'] == 'admin':
                delete_btn.configure(state="disabled", fg_color="gray")

    def _show_reset_dialog(self, username: str):
        """Show a dialog to reset a user's password."""
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Reset Password - {username}")
        dialog.geometry("350x300")
        dialog.resizable(False, False)
        dialog.transient(self)

        # Center dialog
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (350 // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (300 // 2)
        dialog.geometry(f"+{x}+{y}")

        # Wait for window to be visible before grabbing focus
        dialog.wait_visibility()
        dialog.grab_set()

        # Content
        frame = ctk.CTkFrame(dialog, fg_color="transparent")
        frame.pack(expand=True, fill="both", padx=20, pady=20)

        title_label = ctk.CTkLabel(
            frame,
            text=f"Reset password for '{username}'",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        title_label.pack(pady=(0, 15))

        # New password
        new_pw_label = ctk.CTkLabel(frame, text="New Password")
        new_pw_label.pack(anchor="w")
        new_pw_entry = ctk.CTkEntry(frame, width=280, show="*")
        new_pw_entry.pack(pady=(5, 10))

        # Confirm password
        confirm_label = ctk.CTkLabel(frame, text="Confirm Password")
        confirm_label.pack(anchor="w")
        confirm_entry = ctk.CTkEntry(frame, width=280, show="*")
        confirm_entry.pack(pady=(5, 10))

        # Status
        status_label = ctk.CTkLabel(frame, text="", text_color="red")
        status_label.pack(pady=(0, 10))

        def do_reset():
            new_pw = new_pw_entry.get()
            confirm = confirm_entry.get()

            if not new_pw:
                status_label.configure(text="Password is required")
                return

            if len(new_pw) < 4:
                status_label.configure(text="Password must be at least 4 characters")
                return

            if new_pw != confirm:
                status_label.configure(text="Passwords do not match")
                return

            password_hash = hash_password(new_pw)
            if update_user_password(username, password_hash):
                dialog.destroy()
                self._show_status(f"Password reset for '{username}'", error=False)
            else:
                status_label.configure(text="Failed to reset password")

        # Buttons
        button_frame = ctk.CTkFrame(frame, fg_color="transparent")
        button_frame.pack(fill="x")

        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancel",
            width=130,
            fg_color="gray",
            command=dialog.destroy
        )
        cancel_btn.pack(side="left")

        reset_btn = ctk.CTkButton(
            button_frame,
            text="Reset Password",
            width=130,
            command=do_reset
        )
        reset_btn.pack(side="right")

    def _handle_delete_user(self, username: str):
        """Handle delete user with confirmation."""
        if username == 'admin':
            self._show_status("Cannot delete admin user", error=True)
            return

        # Confirmation dialog
        dialog = ctk.CTkToplevel(self)
        dialog.title("Confirm Delete")
        dialog.geometry("300x150")
        dialog.resizable(False, False)
        dialog.transient(self)

        # Center dialog
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (300 // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (150 // 2)
        dialog.geometry(f"+{x}+{y}")

        # Wait for window to be visible before grabbing focus
        dialog.wait_visibility()
        dialog.grab_set()

        frame = ctk.CTkFrame(dialog, fg_color="transparent")
        frame.pack(expand=True, fill="both", padx=20, pady=20)

        label = ctk.CTkLabel(
            frame,
            text=f"Delete user '{username}'?\nThis cannot be undone.",
            font=ctk.CTkFont(size=14)
        )
        label.pack(pady=(0, 20))

        def do_delete():
            if delete_user(username):
                dialog.destroy()
                self._refresh_user_list()
                self._show_status(f"User '{username}' deleted", error=False)
            else:
                dialog.destroy()
                self._show_status("Failed to delete user", error=True)

        button_frame = ctk.CTkFrame(frame, fg_color="transparent")
        button_frame.pack(fill="x")

        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancel",
            width=120,
            fg_color="gray",
            command=dialog.destroy
        )
        cancel_btn.pack(side="left")

        delete_btn = ctk.CTkButton(
            button_frame,
            text="Delete",
            width=120,
            fg_color="#dc3545",
            hover_color="#c82333",
            command=do_delete
        )
        delete_btn.pack(side="right")

    def _handle_create_user(self):
        """Handle create user button click."""
        username = self.new_username_entry.get().strip()
        password = self.new_password_entry.get()
        confirm = self.confirm_password_entry.get()

        # Validation
        if not username:
            self._show_status("Username is required", error=True)
            return

        if len(username) < 3:
            self._show_status("Username must be at least 3 characters", error=True)
            return

        if not password:
            self._show_status("Password is required", error=True)
            return

        if len(password) < 4:
            self._show_status("Password must be at least 4 characters", error=True)
            return

        if password != confirm:
            self._show_status("Passwords do not match", error=True)
            return

        # Create user
        password_hash = hash_password(password)
        if create_user(username, password_hash):
            self._show_status(f"User '{username}' created", error=False)
            # Clear form
            self.new_username_entry.delete(0, 'end')
            self.new_password_entry.delete(0, 'end')
            self.confirm_password_entry.delete(0, 'end')
            # Refresh user list
            self._refresh_user_list()
        else:
            self._show_status("Username already exists", error=True)

    def _show_status(self, message: str, error: bool = False):
        """Display a status message."""
        color = "red" if error else "green"
        self.status_label.configure(text=message, text_color=color)

    def _handle_logout(self):
        """Handle logout button click."""
        self.destroy()
        self.on_logout()
