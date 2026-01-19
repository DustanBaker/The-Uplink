import customtkinter as ctk
from tkinter import filedialog
from PIL import Image, ImageTk
import os
import csv
from database import (
    create_user, get_all_users, update_user_password, delete_user,
    add_inventory_item, get_all_inventory, update_inventory_item, delete_inventory_item,
    add_sku, add_skus_bulk, delete_sku, get_all_skus, search_skus, is_valid_sku, get_sku_count, clear_all_skus
)
from utils import hash_password


class MainApplication(ctk.CTk):
    """Main application window after successful login."""

    # Font definitions for consistent sizing
    FONT_TITLE = ("", 24, "bold")
    FONT_SECTION = ("", 20, "bold")
    FONT_LABEL = ("", 14)
    FONT_LABEL_BOLD = ("", 14, "bold")
    FONT_BUTTON = ("", 14)

    def __init__(self, user: dict, on_logout: callable):
        super().__init__()

        self.user = user
        self.on_logout = on_logout

        self.title("The-Uplink")
        self.geometry("1000x650")
        self.minsize(900, 550)

        # Set window icon
        icon_path = os.path.join(os.path.dirname(__file__), "The_Uplink_App_Icon.ico")
        if os.path.exists(icon_path):
            icon_image = Image.open(icon_path)
            self._icon_photo = ImageTk.PhotoImage(icon_image)
            self.iconphoto(True, self._icon_photo)

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
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(side="left", padx=10)

        # User info and logout
        user_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        user_frame.pack(side="right", padx=10)

        user_label = ctk.CTkLabel(
            user_frame,
            text=f"Logged in as: {self.user['username']}",
            font=ctk.CTkFont(size=14)
        )
        user_label.pack(side="left", padx=(0, 10))

        logout_button = ctk.CTkButton(
            user_frame,
            text="Logout",
            width=90,
            font=ctk.CTkFont(size=14),
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
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.pack(pady=(15, 15), padx=20)

        # Form fields in horizontal layout
        fields_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        fields_frame.pack(padx=20, pady=(0, 15), fill="x")

        # Item SKU with autocomplete
        sku_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
        sku_frame.pack(side="left", padx=(0, 15))
        ctk.CTkLabel(sku_frame, text="Item SKU", font=ctk.CTkFont(size=14)).pack(anchor="w")
        self.sku_entry = ctk.CTkEntry(sku_frame, width=180, font=ctk.CTkFont(size=14))
        self.sku_entry.pack()
        self.sku_entry.bind("<KeyRelease>", self._on_sku_keyrelease)
        self.sku_entry.bind("<FocusOut>", self._hide_sku_suggestions)

        # Autocomplete dropdown (hidden by default)
        self.sku_suggestions_frame = None

        # Serial Number
        serial_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
        serial_frame.pack(side="left", padx=(0, 15))
        ctk.CTkLabel(serial_frame, text="Serial Number", font=ctk.CTkFont(size=14)).pack(anchor="w")
        self.serial_entry = ctk.CTkEntry(serial_frame, width=180, font=ctk.CTkFont(size=14))
        self.serial_entry.pack()

        # LPN
        lpn_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
        lpn_frame.pack(side="left", padx=(0, 15))
        ctk.CTkLabel(lpn_frame, text="LPN", font=ctk.CTkFont(size=14)).pack(anchor="w")
        self.lpn_entry = ctk.CTkEntry(lpn_frame, width=150, font=ctk.CTkFont(size=14))
        self.lpn_entry.pack()

        # Repair State
        repair_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
        repair_frame.pack(side="left", padx=(0, 15))
        ctk.CTkLabel(repair_frame, text="Repair State", font=ctk.CTkFont(size=14)).pack(anchor="w")
        self.repair_options = ["To be repaired", "To be refurbished", "Storage only"]
        self.repair_dropdown = ctk.CTkOptionMenu(repair_frame, width=170, values=self.repair_options, font=ctk.CTkFont(size=14))
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
            font=ctk.CTkFont(size=14),
            command=self._handle_submit_entry
        )
        submit_button.pack()

        # Status message
        self.user_status_label = ctk.CTkLabel(form_frame, text="", height=20, font=ctk.CTkFont(size=14))
        self.user_status_label.pack(pady=(0, 10))

        # Bottom section - Inventory list
        list_frame = ctk.CTkFrame(parent)
        list_frame.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")

        list_title = ctk.CTkLabel(
            list_frame,
            text="Active Inventory",
            font=ctk.CTkFont(size=20, weight="bold")
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
                font=ctk.CTkFont(size=14, weight="bold")
            )
            label.grid(row=0, column=col, padx=5, pady=(0, 10), sticky="w")

        # Inventory rows
        items = get_all_inventory()
        for row, item in enumerate(items, start=1):
            ctk.CTkLabel(self.inventory_list_frame, text=item['item_sku'], font=ctk.CTkFont(size=14)).grid(
                row=row, column=0, padx=5, pady=3, sticky="w")
            ctk.CTkLabel(self.inventory_list_frame, text=item['serial_number'], font=ctk.CTkFont(size=14)).grid(
                row=row, column=1, padx=5, pady=3, sticky="w")
            ctk.CTkLabel(self.inventory_list_frame, text=item['lpn'], font=ctk.CTkFont(size=14)).grid(
                row=row, column=2, padx=5, pady=3, sticky="w")
            ctk.CTkLabel(self.inventory_list_frame, text=item['repair_state'], font=ctk.CTkFont(size=14)).grid(
                row=row, column=3, padx=5, pady=3, sticky="w")
            ctk.CTkLabel(self.inventory_list_frame, text=item['entered_by'], font=ctk.CTkFont(size=14)).grid(
                row=row, column=4, padx=5, pady=3, sticky="w")
            # Format date
            date_str = item['created_at'].split('T')[0] if 'T' in item['created_at'] else item['created_at'][:10]
            ctk.CTkLabel(self.inventory_list_frame, text=date_str, font=ctk.CTkFont(size=14)).grid(
                row=row, column=5, padx=5, pady=3, sticky="w")

            # Edit button
            edit_btn = ctk.CTkButton(
                self.inventory_list_frame,
                text="Edit",
                width=70,
                height=28,
                font=ctk.CTkFont(size=13),
                command=lambda i=item: self._show_edit_inventory_dialog(i)
            )
            edit_btn.grid(row=row, column=6, padx=2, pady=3)

            # Delete button
            delete_btn = ctk.CTkButton(
                self.inventory_list_frame,
                text="Delete",
                width=70,
                height=28,
                font=ctk.CTkFont(size=13),
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
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(0, 10))

        # Item SKU
        ctk.CTkLabel(frame, text="Item SKU", font=ctk.CTkFont(size=14)).pack(anchor="w")
        sku_entry = ctk.CTkEntry(frame, width=340, font=ctk.CTkFont(size=14))
        sku_entry.insert(0, item['item_sku'])
        sku_entry.pack(pady=(2, 8))

        # Serial Number
        ctk.CTkLabel(frame, text="Serial Number", font=ctk.CTkFont(size=14)).pack(anchor="w")
        serial_entry = ctk.CTkEntry(frame, width=340, font=ctk.CTkFont(size=14))
        serial_entry.insert(0, item['serial_number'])
        serial_entry.pack(pady=(2, 8))

        # LPN
        ctk.CTkLabel(frame, text="LPN", font=ctk.CTkFont(size=14)).pack(anchor="w")
        lpn_entry = ctk.CTkEntry(frame, width=340, font=ctk.CTkFont(size=14))
        lpn_entry.insert(0, item['lpn'])
        lpn_entry.pack(pady=(2, 8))

        # Repair State
        ctk.CTkLabel(frame, text="Repair State", font=ctk.CTkFont(size=14)).pack(anchor="w")
        repair_options = ["To be repaired", "To be refurbished", "Storage only"]
        repair_dropdown = ctk.CTkOptionMenu(frame, width=340, values=repair_options, font=ctk.CTkFont(size=14))
        repair_dropdown.set(item['repair_state'])
        repair_dropdown.pack(pady=(2, 10))

        # Status
        status_label = ctk.CTkLabel(frame, text="", text_color="red", font=ctk.CTkFont(size=14))
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
            font=ctk.CTkFont(size=14),
            fg_color="gray",
            command=dialog.destroy
        )
        cancel_btn.pack(side="left")

        save_btn = ctk.CTkButton(
            button_frame,
            text="Save",
            width=160,
            font=ctk.CTkFont(size=14),
            command=do_save
        )
        save_btn.pack(side="right")

    def _delete_inventory_item(self, item: dict):
        """Delete an inventory item with confirmation."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Confirm Delete")
        dialog.geometry("350x180")
        dialog.resizable(False, False)
        dialog.transient(self)

        # Center dialog
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (350 // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (180 // 2)
        dialog.geometry(f"+{x}+{y}")

        dialog.wait_visibility()
        dialog.grab_set()

        frame = ctk.CTkFrame(dialog, fg_color="transparent")
        frame.pack(expand=True, fill="both", padx=20, pady=20)

        label = ctk.CTkLabel(
            frame,
            text=f"Delete item '{item['item_sku']}'?\nThis cannot be undone.",
            font=ctk.CTkFont(size=16)
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
            width=140,
            font=ctk.CTkFont(size=14),
            fg_color="gray",
            command=dialog.destroy
        )
        cancel_btn.pack(side="left")

        delete_btn = ctk.CTkButton(
            button_frame,
            text="Delete",
            width=140,
            font=ctk.CTkFont(size=14),
            fg_color="#dc3545",
            hover_color="#c82333",
            command=do_delete
        )
        delete_btn.pack(side="right")

    def _on_sku_keyrelease(self, event):
        """Handle key release in SKU entry for autocomplete."""
        # Ignore navigation keys
        if event.keysym in ('Up', 'Down', 'Left', 'Right', 'Return', 'Tab', 'Escape'):
            if event.keysym == 'Escape':
                self._hide_sku_suggestions(None)
            return

        text = self.sku_entry.get().strip()

        if len(text) < 1:
            self._hide_sku_suggestions(None)
            return

        # Get matching SKUs
        matches = search_skus(text, limit=8)

        if matches:
            self._show_sku_suggestions(matches)
        else:
            self._hide_sku_suggestions(None)

    def _show_sku_suggestions(self, matches):
        """Show autocomplete suggestions dropdown."""
        # Remove existing suggestions
        self._hide_sku_suggestions(None)

        # Create suggestions frame as a toplevel to float above
        self.sku_suggestions_frame = ctk.CTkToplevel(self)
        self.sku_suggestions_frame.withdraw()  # Hide initially
        self.sku_suggestions_frame.overrideredirect(True)  # No window decorations

        # Position below the entry
        entry_x = self.sku_entry.winfo_rootx()
        entry_y = self.sku_entry.winfo_rooty() + self.sku_entry.winfo_height()

        # Create scrollable frame for suggestions
        suggestions_container = ctk.CTkFrame(self.sku_suggestions_frame)
        suggestions_container.pack(fill="both", expand=True)

        for match in matches:
            btn = ctk.CTkButton(
                suggestions_container,
                text=f"{match['sku']}",
                font=ctk.CTkFont(size=13),
                height=28,
                anchor="w",
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray70", "gray30"),
                command=lambda s=match['sku']: self._select_sku_suggestion(s)
            )
            btn.pack(fill="x", padx=2, pady=1)

        # Show and position
        self.sku_suggestions_frame.geometry(f"180x{min(len(matches) * 32, 250)}+{entry_x}+{entry_y}")
        self.sku_suggestions_frame.deiconify()
        self.sku_suggestions_frame.lift()

    def _hide_sku_suggestions(self, event):
        """Hide the autocomplete suggestions."""
        if self.sku_suggestions_frame:
            self.sku_suggestions_frame.destroy()
            self.sku_suggestions_frame = None

    def _select_sku_suggestion(self, sku):
        """Select a SKU from suggestions."""
        self.sku_entry.delete(0, 'end')
        self.sku_entry.insert(0, sku)
        self._hide_sku_suggestions(None)
        # Move focus to next field
        self.serial_entry.focus()

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

        # Validate SKU against approved list
        if not is_valid_sku(sku):
            self._show_user_status(f"Invalid SKU: '{sku}' not in approved list", error=True)
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
        """Create the admin panel with tabbed interface for Users and SKUs."""
        # Create tabview
        tabview = ctk.CTkTabview(parent)
        tabview.pack(expand=True, fill="both", padx=10, pady=10)

        # Add tabs
        tabview.add("Users")
        tabview.add("Approved SKUs")

        # Create content for each tab
        self._create_users_tab(tabview.tab("Users"))
        self._create_skus_tab(tabview.tab("Approved SKUs"))

    def _create_users_tab(self, parent):
        """Create the users management tab."""
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
            font=ctk.CTkFont(size=20, weight="bold")
        )
        create_title.pack(pady=(15, 15), padx=20)

        form_frame = ctk.CTkFrame(create_frame, fg_color="transparent")
        form_frame.pack(padx=20, pady=(0, 15))

        # Username
        username_label = ctk.CTkLabel(form_frame, text="Username", font=ctk.CTkFont(size=14))
        username_label.grid(row=0, column=0, sticky="w", pady=(0, 5))

        self.new_username_entry = ctk.CTkEntry(form_frame, width=220, font=ctk.CTkFont(size=14))
        self.new_username_entry.grid(row=1, column=0, pady=(0, 10))

        # Password
        password_label = ctk.CTkLabel(form_frame, text="Password", font=ctk.CTkFont(size=14))
        password_label.grid(row=2, column=0, sticky="w", pady=(0, 5))

        self.new_password_entry = ctk.CTkEntry(form_frame, width=220, show="*", font=ctk.CTkFont(size=14))
        self.new_password_entry.grid(row=3, column=0, pady=(0, 10))

        # Confirm Password
        confirm_label = ctk.CTkLabel(form_frame, text="Confirm Password", font=ctk.CTkFont(size=14))
        confirm_label.grid(row=4, column=0, sticky="w", pady=(0, 5))

        self.confirm_password_entry = ctk.CTkEntry(form_frame, width=220, show="*", font=ctk.CTkFont(size=14))
        self.confirm_password_entry.grid(row=5, column=0, pady=(0, 15))

        # Status message
        self.status_label = ctk.CTkLabel(form_frame, text="", width=220, wraplength=200, font=ctk.CTkFont(size=14))
        self.status_label.grid(row=6, column=0, pady=(0, 10))

        # Create button
        create_button = ctk.CTkButton(
            form_frame,
            text="Create User",
            width=220,
            font=ctk.CTkFont(size=14),
            command=self._handle_create_user
        )
        create_button.grid(row=7, column=0)

        # Right side - User list
        list_frame = ctk.CTkFrame(parent)
        list_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="nsew")

        list_title = ctk.CTkLabel(
            list_frame,
            text="Existing Users",
            font=ctk.CTkFont(size=20, weight="bold")
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

    def _create_skus_tab(self, parent):
        """Create the SKU management tab."""
        # Configure grid
        parent.grid_columnconfigure(0, weight=0)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        # Left side - Add SKU / Import
        add_frame = ctk.CTkFrame(parent)
        add_frame.grid(row=0, column=0, padx=10, pady=10, sticky="n")

        # Stats section
        stats_frame = ctk.CTkFrame(add_frame)
        stats_frame.pack(pady=(15, 15), padx=20, fill="x")

        stats_title = ctk.CTkLabel(
            stats_frame,
            text="SKU Statistics",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        stats_title.pack(pady=(10, 5))

        self.sku_count_label = ctk.CTkLabel(
            stats_frame,
            text=f"Total SKUs: {get_sku_count()}",
            font=ctk.CTkFont(size=14)
        )
        self.sku_count_label.pack(pady=(0, 10))

        # Import section
        import_title = ctk.CTkLabel(
            add_frame,
            text="Import SKUs",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        import_title.pack(pady=(10, 10), padx=20)

        import_btn = ctk.CTkButton(
            add_frame,
            text="Import from CSV",
            width=220,
            font=ctk.CTkFont(size=14),
            command=self._import_skus_csv
        )
        import_btn.pack(pady=(0, 5))

        clear_btn = ctk.CTkButton(
            add_frame,
            text="Clear All SKUs",
            width=220,
            font=ctk.CTkFont(size=14),
            fg_color="#dc3545",
            hover_color="#c82333",
            command=self._clear_all_skus
        )
        clear_btn.pack(pady=(0, 15))

        # Add individual SKU
        add_title = ctk.CTkLabel(
            add_frame,
            text="Add Individual SKU",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        add_title.pack(pady=(10, 10), padx=20)

        form_frame = ctk.CTkFrame(add_frame, fg_color="transparent")
        form_frame.pack(padx=20, pady=(0, 15))

        ctk.CTkLabel(form_frame, text="SKU", font=ctk.CTkFont(size=14)).grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.new_sku_entry = ctk.CTkEntry(form_frame, width=220, font=ctk.CTkFont(size=14))
        self.new_sku_entry.grid(row=1, column=0, pady=(0, 10))

        ctk.CTkLabel(form_frame, text="Description (optional)", font=ctk.CTkFont(size=14)).grid(row=2, column=0, sticky="w", pady=(0, 5))
        self.new_sku_desc_entry = ctk.CTkEntry(form_frame, width=220, font=ctk.CTkFont(size=14))
        self.new_sku_desc_entry.grid(row=3, column=0, pady=(0, 10))

        self.sku_status_label = ctk.CTkLabel(form_frame, text="", width=220, font=ctk.CTkFont(size=14))
        self.sku_status_label.grid(row=4, column=0, pady=(0, 10))

        add_sku_btn = ctk.CTkButton(
            form_frame,
            text="Add SKU",
            width=220,
            font=ctk.CTkFont(size=14),
            command=self._handle_add_sku
        )
        add_sku_btn.grid(row=5, column=0)

        # Right side - SKU list
        list_frame = ctk.CTkFrame(parent)
        list_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="nsew")

        # Search bar
        search_frame = ctk.CTkFrame(list_frame, fg_color="transparent")
        search_frame.pack(pady=(15, 10), padx=20, fill="x")

        ctk.CTkLabel(search_frame, text="Search SKUs:", font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 10))
        self.sku_search_entry = ctk.CTkEntry(search_frame, width=300, font=ctk.CTkFont(size=14))
        self.sku_search_entry.pack(side="left", padx=(0, 10))
        self.sku_search_entry.bind("<KeyRelease>", lambda e: self._filter_sku_list())

        # SKU list
        list_title = ctk.CTkLabel(
            list_frame,
            text="Approved SKUs",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        list_title.pack(pady=(5, 10), padx=20)

        self.sku_list_frame = ctk.CTkScrollableFrame(list_frame)
        self.sku_list_frame.pack(expand=True, fill="both", padx=10, pady=(0, 10))

        self.sku_list_frame.grid_columnconfigure(0, weight=1)
        self.sku_list_frame.grid_columnconfigure(1, weight=2)
        self.sku_list_frame.grid_columnconfigure(2, weight=0)

        self._refresh_sku_list()

    def _refresh_sku_list(self, filter_text: str = ""):
        """Refresh the SKU list display."""
        for widget in self.sku_list_frame.winfo_children():
            widget.destroy()

        # Header row
        headers = ["SKU", "Description", ""]
        for col, header in enumerate(headers):
            label = ctk.CTkLabel(
                self.sku_list_frame,
                text=header,
                font=ctk.CTkFont(size=14, weight="bold")
            )
            label.grid(row=0, column=col, padx=5, pady=(0, 10), sticky="w")

        # Get SKUs (filtered or all)
        if filter_text:
            skus = search_skus(filter_text, limit=100)
        else:
            skus = get_all_skus()[:100]  # Limit display to 100 for performance

        for row, sku in enumerate(skus, start=1):
            ctk.CTkLabel(self.sku_list_frame, text=sku['sku'], font=ctk.CTkFont(size=14)).grid(
                row=row, column=0, padx=5, pady=3, sticky="w")
            ctk.CTkLabel(self.sku_list_frame, text=sku.get('description', ''), font=ctk.CTkFont(size=14)).grid(
                row=row, column=1, padx=5, pady=3, sticky="w")

            delete_btn = ctk.CTkButton(
                self.sku_list_frame,
                text="Delete",
                width=70,
                height=28,
                font=ctk.CTkFont(size=13),
                fg_color="#dc3545",
                hover_color="#c82333",
                command=lambda s=sku['sku']: self._handle_delete_sku(s)
            )
            delete_btn.grid(row=row, column=2, padx=5, pady=3)

        # Update count
        self.sku_count_label.configure(text=f"Total SKUs: {get_sku_count()}")

    def _filter_sku_list(self):
        """Filter SKU list based on search entry."""
        filter_text = self.sku_search_entry.get().strip()
        self._refresh_sku_list(filter_text)

    def _handle_add_sku(self):
        """Handle adding a new SKU."""
        sku = self.new_sku_entry.get().strip()
        description = self.new_sku_desc_entry.get().strip()

        if not sku:
            self.sku_status_label.configure(text="SKU is required", text_color="red")
            return

        if add_sku(sku, description):
            self.sku_status_label.configure(text=f"Added: {sku.upper()}", text_color="green")
            self.new_sku_entry.delete(0, 'end')
            self.new_sku_desc_entry.delete(0, 'end')
            self._refresh_sku_list()
        else:
            self.sku_status_label.configure(text="SKU already exists", text_color="red")

    def _handle_delete_sku(self, sku: str):
        """Handle deleting a SKU."""
        if delete_sku(sku):
            self._refresh_sku_list(self.sku_search_entry.get().strip())

    def _import_skus_csv(self):
        """Import SKUs from a CSV file."""
        filepath = filedialog.askopenfilename(
            title="Select CSV file",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )

        if not filepath:
            return

        try:
            skus_to_add = []
            with open(filepath, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                # Skip header if present
                first_row = next(reader, None)
                if first_row and first_row[0].lower() not in ('sku', 'item', 'product'):
                    # First row is data, not header
                    sku = first_row[0].strip() if first_row else ""
                    desc = first_row[1].strip() if len(first_row) > 1 else ""
                    if sku:
                        skus_to_add.append((sku, desc))

                for row in reader:
                    if row:
                        sku = row[0].strip()
                        desc = row[1].strip() if len(row) > 1 else ""
                        if sku:
                            skus_to_add.append((sku, desc))

            success, failed = add_skus_bulk(skus_to_add)
            self.sku_status_label.configure(
                text=f"Imported {success}, skipped {failed} duplicates",
                text_color="green" if success > 0 else "orange"
            )
            self._refresh_sku_list()

        except Exception as e:
            self.sku_status_label.configure(text=f"Error: {str(e)}", text_color="red")

    def _clear_all_skus(self):
        """Clear all SKUs with confirmation."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Confirm Clear All")
        dialog.geometry("350x180")
        dialog.resizable(False, False)
        dialog.transient(self)

        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (350 // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (180 // 2)
        dialog.geometry(f"+{x}+{y}")

        dialog.wait_visibility()
        dialog.grab_set()

        frame = ctk.CTkFrame(dialog, fg_color="transparent")
        frame.pack(expand=True, fill="both", padx=20, pady=20)

        count = get_sku_count()
        label = ctk.CTkLabel(
            frame,
            text=f"Delete all {count} SKUs?\nThis cannot be undone.",
            font=ctk.CTkFont(size=16)
        )
        label.pack(pady=(0, 20))

        def do_clear():
            deleted = clear_all_skus()
            dialog.destroy()
            self.sku_status_label.configure(text=f"Deleted {deleted} SKUs", text_color="green")
            self._refresh_sku_list()

        button_frame = ctk.CTkFrame(frame, fg_color="transparent")
        button_frame.pack(fill="x")

        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancel",
            width=140,
            font=ctk.CTkFont(size=14),
            fg_color="gray",
            command=dialog.destroy
        )
        cancel_btn.pack(side="left")

        delete_btn = ctk.CTkButton(
            button_frame,
            text="Delete All",
            width=140,
            font=ctk.CTkFont(size=14),
            fg_color="#dc3545",
            hover_color="#c82333",
            command=do_clear
        )
        delete_btn.pack(side="right")

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
                font=ctk.CTkFont(size=14, weight="bold")
            )
            label.grid(row=0, column=col, padx=5, pady=(0, 10), sticky="w")

        # User rows
        users = get_all_users()
        for row, user in enumerate(users, start=1):
            # Username
            username_label = ctk.CTkLabel(self.user_list_frame, text=user['username'], font=ctk.CTkFont(size=14))
            username_label.grid(row=row, column=0, padx=5, pady=5, sticky="w")

            # Created date (just the date part)
            created = user['created_at'].split('T')[0] if 'T' in user['created_at'] else user['created_at'][:10]
            created_label = ctk.CTkLabel(self.user_list_frame, text=created, font=ctk.CTkFont(size=14))
            created_label.grid(row=row, column=1, padx=5, pady=5, sticky="w")

            # Reset password button
            reset_btn = ctk.CTkButton(
                self.user_list_frame,
                text="Reset Password",
                width=130,
                height=32,
                font=ctk.CTkFont(size=13),
                command=lambda u=user['username']: self._show_reset_dialog(u)
            )
            reset_btn.grid(row=row, column=2, padx=5, pady=5)

            # Delete button (disabled for admin)
            delete_btn = ctk.CTkButton(
                self.user_list_frame,
                text="Delete",
                width=80,
                height=32,
                font=ctk.CTkFont(size=13),
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
        dialog.geometry("400x340")
        dialog.resizable(False, False)
        dialog.transient(self)

        # Center dialog
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (400 // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (340 // 2)
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
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(0, 15))

        # New password
        new_pw_label = ctk.CTkLabel(frame, text="New Password", font=ctk.CTkFont(size=14))
        new_pw_label.pack(anchor="w")
        new_pw_entry = ctk.CTkEntry(frame, width=340, show="*", font=ctk.CTkFont(size=14))
        new_pw_entry.pack(pady=(5, 10))

        # Confirm password
        confirm_label = ctk.CTkLabel(frame, text="Confirm Password", font=ctk.CTkFont(size=14))
        confirm_label.pack(anchor="w")
        confirm_entry = ctk.CTkEntry(frame, width=340, show="*", font=ctk.CTkFont(size=14))
        confirm_entry.pack(pady=(5, 10))

        # Status
        status_label = ctk.CTkLabel(frame, text="", text_color="red", font=ctk.CTkFont(size=14))
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
            width=160,
            font=ctk.CTkFont(size=14),
            fg_color="gray",
            command=dialog.destroy
        )
        cancel_btn.pack(side="left")

        reset_btn = ctk.CTkButton(
            button_frame,
            text="Reset Password",
            width=160,
            font=ctk.CTkFont(size=14),
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
        dialog.geometry("350x180")
        dialog.resizable(False, False)
        dialog.transient(self)

        # Center dialog
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (350 // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (180 // 2)
        dialog.geometry(f"+{x}+{y}")

        # Wait for window to be visible before grabbing focus
        dialog.wait_visibility()
        dialog.grab_set()

        frame = ctk.CTkFrame(dialog, fg_color="transparent")
        frame.pack(expand=True, fill="both", padx=20, pady=20)

        label = ctk.CTkLabel(
            frame,
            text=f"Delete user '{username}'?\nThis cannot be undone.",
            font=ctk.CTkFont(size=16)
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
            width=140,
            font=ctk.CTkFont(size=14),
            fg_color="gray",
            command=dialog.destroy
        )
        cancel_btn.pack(side="left")

        delete_btn = ctk.CTkButton(
            button_frame,
            text="Delete",
            width=140,
            font=ctk.CTkFont(size=14),
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
