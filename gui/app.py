import customtkinter as ctk
from tkinter import filedialog
from PIL import Image, ImageTk
import os
import csv
from datetime import datetime
import subprocess
import threading
import platform
from database import (
    create_user, get_all_users, update_user_password, update_user_admin_status, delete_user,
    add_inventory_item, get_all_inventory, update_inventory_item, delete_inventory_item,
    move_inventory_to_imported, export_inventory_to_csv, get_all_imported_inventory,
    lookup_halo_po_number
)
from database.sku_cache import (
    add_sku_cached as add_sku,
    add_skus_bulk_cached as add_skus_bulk,
    delete_sku_cached as delete_sku,
    get_all_skus_cached as get_all_skus,
    search_skus_cached as search_skus,
    is_valid_sku_cached as is_valid_sku,
    get_sku_count_cached as get_sku_count,
    clear_all_skus_cached as clear_all_skus,
    init_sku_cache,
    start_background_sync,
    stop_background_sync
)
from utils import hash_password, get_gui_resource, check_for_updates, show_update_dialog
from config import VERSION, GITHUB_REPO


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
        self._refresh_poll_id = None  # Track polling timer
        self.project_widgets = {}  # Store per-project widget references (user panel)
        self.admin_project_widgets = {}  # Store per-project widget references (admin panel)
        self.admin_sku_widgets = {}  # Store per-project SKU widget references (admin panel)

        self.title(f"The-Uplink v{VERSION}")
        self.geometry("1350x650")
        self.minsize(1050, 550)


        # Set window icon
        icon_path = get_gui_resource("The_Uplink_App_Icon.ico")
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

        # Initialize SKU cache and start background sync
        init_sku_cache()
        start_background_sync(interval=300)  # 5 minutes

        self._create_widgets()
        self._play_login_sound()
        self._check_for_updates()

    def _play_sound(self, filename, volume=150):
        """Play a sound file in background thread with cross-platform support."""
        def play():
            try:
                sound_path = get_gui_resource(filename)
                if not os.path.exists(sound_path):
                    return
                
                system = platform.system()
                
                if system == 'Windows':
                    # Windows audio playback
                    if filename.lower().endswith('.wav'):
                        # For WAV files, use winsound (built-in)
                        try:
                            import winsound
                            winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                            return
                        except Exception:
                            pass

                    # For MP3 files, try multiple approaches
                    # Method 1: Try pygame (if installed)
                    try:
                        import pygame
                        pygame.mixer.init()
                        pygame.mixer.music.load(sound_path)
                        pygame.mixer.music.set_volume(min(volume / 100.0, 1.0))
                        pygame.mixer.music.play()
                        # Keep thread alive while playing
                        while pygame.mixer.music.get_busy():
                            import time
                            time.sleep(0.1)
                        return
                    except (ImportError, Exception):
                        pass

                    # Method 2: Try playsound library (if installed)
                    try:
                        from playsound import playsound
                        playsound(sound_path, False)
                        return
                    except (ImportError, Exception):
                        pass

                    # Method 3: Use Windows Media Player via COM
                    try:
                        import win32com.client
                        wmp = win32com.client.Dispatch("WMPlayer.OCX")
                        wmp.settings.volume = min(volume, 100)
                        wmp.URL = sound_path
                        wmp.controls.play()
                        return
                    except (ImportError, Exception):
                        pass

                    # Method 4: PowerShell with Windows Media Player
                    try:
                        ps_script = f'''
Add-Type -AssemblyName presentationCore
$mediaPlayer = New-Object system.windows.media.mediaplayer
$mediaPlayer.open("{sound_path}")
$mediaPlayer.Volume = {min(volume / 100.0, 1.0)}
$mediaPlayer.Play()
Start-Sleep -Seconds 3
'''
                        subprocess.run(['powershell', '-Command', ps_script],
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL,
                                     creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
                        return
                    except Exception:
                        pass
                    
                else:
                    # Linux/Unix audio players
                    for player in [['mpv', '--no-video', f'--volume={volume}'], 
                                 ['ffplay', '-nodisp', '-autoexit', '-volume', str(volume)], 
                                 ['paplay']]:
                        try:
                            subprocess.run(player + [sound_path],
                                         stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL)
                            break
                        except FileNotFoundError:
                            continue
            except Exception:
                pass

        threading.Thread(target=play, daemon=True).start()

    def _play_login_sound(self):
        """Play the login sound once."""
        self._play_sound("arc_raiders.mp3")

    def _check_for_updates(self):
        """Check for application updates from GitHub releases."""
        if not GITHUB_REPO or GITHUB_REPO == "YOUR_USERNAME/The-Uplink":
            return  # Update checking not configured

        def on_update_check(has_update, latest_version, download_url, release_notes):
            if has_update:
                # Schedule dialog to run on main thread
                self.after(100, lambda: show_update_dialog(
                    self, latest_version, download_url, release_notes
                ))

        check_for_updates(GITHUB_REPO, VERSION, on_update_check)

    def destroy(self):
        """Override destroy to clean up background sync thread."""
        stop_background_sync()
        super().destroy()

    def _play_success_sound(self):
        """Play the success/loot sound."""
        self._play_sound("arc-raiders-loot.mp3")

    def _play_error_sound(self):
        """Play the error sound."""
        self._play_sound("arc-raiders-elevator.mp3")

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
        if self.user.get('is_admin', False):
            self._create_admin_panel(content_frame)
        else:
            self._create_user_panel(content_frame)

    def _create_user_panel(self, parent):
        """Create the standard user panel with tabbed interface for EcoFlow and Halo."""
        # Create tabview for projects
        tabview = ctk.CTkTabview(parent)
        tabview.pack(expand=True, fill="both", padx=10, pady=10)

        # Add tabs for each project
        tabview.add("EcoFlow")
        tabview.add("Halo")

        # Create content for each tab
        self._create_project_tab(tabview.tab("EcoFlow"), "ecoflow")
        self._create_project_tab(tabview.tab("Halo"), "halo")

        self._start_inventory_polling()

    def _create_project_tab(self, parent, project: str):
        """Create the project-specific tab content with form and inventory list."""
        # Initialize widget storage for this project
        self.project_widgets[project] = {}

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
        sku_entry = ctk.CTkEntry(sku_frame, width=180, font=ctk.CTkFont(size=14))
        sku_entry.pack()
        sku_entry.bind("<KeyRelease>", lambda e, p=project: self._on_sku_keyrelease(e, p))
        sku_entry.bind("<FocusOut>", lambda e, p=project: self._hide_sku_suggestions(e, p))
        self.project_widgets[project]['sku_entry'] = sku_entry
        self.project_widgets[project]['sku_suggestions_frame'] = None

        # Serial Number
        serial_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
        serial_frame.pack(side="left", padx=(0, 15))
        ctk.CTkLabel(serial_frame, text="Serial Number", font=ctk.CTkFont(size=14)).pack(anchor="w")
        serial_entry = ctk.CTkEntry(serial_frame, width=180, font=ctk.CTkFont(size=14))
        serial_entry.pack()
        self.project_widgets[project]['serial_entry'] = serial_entry

        # LPN
        lpn_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
        lpn_frame.pack(side="left", padx=(0, 15))
        ctk.CTkLabel(lpn_frame, text="LPN", font=ctk.CTkFont(size=14)).pack(anchor="w")
        lpn_entry = ctk.CTkEntry(lpn_frame, width=150, font=ctk.CTkFont(size=14))
        lpn_entry.pack()
        self.project_widgets[project]['lpn_entry'] = lpn_entry

        # Order # (only shown for EcoFlow, not for Halo) - between LPN and Location
        if project != "halo":
            order_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
            order_frame.pack(side="left", padx=(0, 15))
            ctk.CTkLabel(order_frame, text="Order #", font=ctk.CTkFont(size=14)).pack(anchor="w")
            order_entry = ctk.CTkEntry(order_frame, width=120, font=ctk.CTkFont(size=14))
            order_entry.pack()
            self.project_widgets[project]['order_entry'] = order_entry
        else:
            self.project_widgets[project]['order_entry'] = None

        # Location (dropdown with project-specific options)
        location_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
        location_frame.pack(side="left", padx=(0, 15))
        ctk.CTkLabel(location_frame, text="Location", font=ctk.CTkFont(size=14)).pack(anchor="w")
        if project == "halo":
            location_options = ["INPROD01","Halocage1","Halocage2","Halocage3","Halocage4"]
        else:
            location_options = ["EFINPROD01"]
        location_dropdown = ctk.CTkOptionMenu(location_frame, width=140, values=location_options, font=ctk.CTkFont(size=14))
        location_dropdown.set(location_options[0])
        location_dropdown.pack()
        self.project_widgets[project]['location_dropdown'] = location_dropdown

        # Repair State (only shown for EcoFlow, not for Halo)
        if project != "halo":
            repair_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
            repair_frame.pack(side="left", padx=(0, 15))
            ctk.CTkLabel(repair_frame, text="Repair State", font=ctk.CTkFont(size=14)).pack(anchor="w")
            repair_options = ["Temporary Storage","To be repaired", "To be refurbished","To be Scrapped","Storage only","Good Spare Parts","Refurbished","Repaired"]
            repair_dropdown = ctk.CTkOptionMenu(repair_frame, width=170, values=repair_options, font=ctk.CTkFont(size=14))
            repair_dropdown.set(repair_options[0])
            repair_dropdown.pack()
            self.project_widgets[project]['repair_dropdown'] = repair_dropdown
            self.project_widgets[project]['repair_options'] = repair_options
        else:
            self.project_widgets[project]['repair_dropdown'] = None
            self.project_widgets[project]['repair_options'] = []

        # Submit button and status
        submit_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
        submit_frame.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(submit_frame, text=" ").pack()  # Spacer for alignment
        submit_button = ctk.CTkButton(
            submit_frame,
            text="Submit",
            width=100,
            font=ctk.CTkFont(size=14),
            command=lambda p=project: self._handle_submit_entry(p)
        )
        submit_button.pack()

        # Status message
        status_label = ctk.CTkLabel(form_frame, text="", height=20, font=ctk.CTkFont(size=14))
        status_label.pack(pady=(0, 10))
        self.project_widgets[project]['status_label'] = status_label

        # Bottom section - Inventory list
        list_frame = ctk.CTkFrame(parent)
        list_frame.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")

        # Header with title and export button
        list_header = ctk.CTkFrame(list_frame, fg_color="transparent")
        list_header.pack(fill="x", padx=20, pady=(15, 10))

        list_title = ctk.CTkLabel(
            list_header,
            text="Active Inventory",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        list_title.pack(side="left")

        export_button = ctk.CTkButton(
            list_header,
            text="Export & Archive",
            width=140,
            font=ctk.CTkFont(size=14),
            fg_color="#28a745",
            hover_color="#218838",
            command=lambda p=project: self._handle_export_inventory(p)
        )
        export_button.pack(side="right")

        # Scrollable frame for inventory list
        inventory_list_frame = ctk.CTkScrollableFrame(list_frame)
        inventory_list_frame.pack(expand=True, fill="both", padx=10, pady=(0, 10))
        self.project_widgets[project]['inventory_list_frame'] = inventory_list_frame

        # Configure columns (EcoFlow has extra Order # column)
        num_columns = 7 if project != "halo" else 6
        for i in range(num_columns):
            inventory_list_frame.grid_columnconfigure(i, weight=1)

        self._refresh_inventory_list(project)

    def _start_inventory_polling(self):
        """Start polling to refresh inventory every 10 seconds."""
        self._refresh_poll_id = self.after(10000, self._poll_inventory)

    def _poll_inventory(self):
        """Poll and refresh inventory for all projects, then schedule next poll."""
        for project in self.project_widgets:
            self._refresh_inventory_list(project)
        self._refresh_poll_id = self.after(10000, self._poll_inventory)

    def _stop_inventory_polling(self):
        """Stop the inventory polling."""
        if self._refresh_poll_id:
            self.after_cancel(self._refresh_poll_id)
            self._refresh_poll_id = None

    def _refresh_inventory_list(self, project: str = "ecoflow"):
        """Refresh the inventory list display for a specific project."""
        inventory_list_frame = self.project_widgets[project]['inventory_list_frame']

        # Clear existing widgets
        for widget in inventory_list_frame.winfo_children():
            widget.destroy()

        # Header row - include PO # for both projects (between LPN and Location)
        headers = ["SKU", "Serial Number", "LPN", "PO #", "Location", "Repair State", "Entered By", "Date", "", ""]
        for col, header in enumerate(headers):
            label = ctk.CTkLabel(
                inventory_list_frame,
                text=header,
                font=ctk.CTkFont(size=14, weight="bold")
            )
            label.grid(row=0, column=col, padx=5, pady=(0, 10), sticky="w")

        # Inventory rows
        items = get_all_inventory(project)
        for row, item in enumerate(items, start=1):
            col = 0
            ctk.CTkLabel(inventory_list_frame, text=item['item_sku'], font=ctk.CTkFont(size=14)).grid(
                row=row, column=col, padx=5, pady=3, sticky="w")
            col += 1
            ctk.CTkLabel(inventory_list_frame, text=item['serial_number'], font=ctk.CTkFont(size=14)).grid(
                row=row, column=col, padx=5, pady=3, sticky="w")
            col += 1
            ctk.CTkLabel(inventory_list_frame, text=item['lpn'], font=ctk.CTkFont(size=14)).grid(
                row=row, column=col, padx=5, pady=3, sticky="w")
            col += 1
            # PO # column - EcoFlow uses order_number, Halo uses SN lookup
            if project == "halo":
                po_number = lookup_halo_po_number(item['serial_number']) or '0'
            else:
                po_number = item.get('order_number', '')
            ctk.CTkLabel(inventory_list_frame, text=po_number, font=ctk.CTkFont(size=14)).grid(
                row=row, column=col, padx=5, pady=3, sticky="w")
            col += 1
            ctk.CTkLabel(inventory_list_frame, text=item.get('location', ''), font=ctk.CTkFont(size=14)).grid(
                row=row, column=col, padx=5, pady=3, sticky="w")
            col += 1
            ctk.CTkLabel(inventory_list_frame, text=item['repair_state'], font=ctk.CTkFont(size=14)).grid(
                row=row, column=col, padx=5, pady=3, sticky="w")
            col += 1
            ctk.CTkLabel(inventory_list_frame, text=item['entered_by'], font=ctk.CTkFont(size=14)).grid(
                row=row, column=col, padx=5, pady=3, sticky="w")
            col += 1
            # Format date
            date_str = item['created_at'].replace('T', ' ')[:16] if 'T' in item['created_at'] else item['created_at'][:16]
            ctk.CTkLabel(inventory_list_frame, text=date_str, font=ctk.CTkFont(size=14)).grid(
                row=row, column=col, padx=5, pady=3, sticky="w")
            col += 1

            # Edit button
            edit_btn = ctk.CTkButton(
                inventory_list_frame,
                text="Edit",
                width=70,
                height=28,
                font=ctk.CTkFont(size=13),
                command=lambda i=item, p=project: self._show_edit_inventory_dialog(i, p)
            )
            edit_btn.grid(row=row, column=col, padx=2, pady=3)
            col += 1

            # Delete button
            delete_btn = ctk.CTkButton(
                inventory_list_frame,
                text="Delete",
                width=70,
                height=28,
                font=ctk.CTkFont(size=13),
                fg_color="#dc3545",
                hover_color="#c82333",
                command=lambda i=item, p=project: self._delete_inventory_item(i, p)
            )
            delete_btn.grid(row=row, column=col, padx=2, pady=3)

    def _show_edit_inventory_dialog(self, item: dict, project: str = "ecoflow"):
        """Show dialog to edit an inventory item."""
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Edit Item - {item['item_sku']}")
        dialog_height = 510 if project != "halo" else 450
        dialog.geometry(f"400x{dialog_height}")
        dialog.resizable(False, False)
        dialog.transient(self)

        # Center dialog
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (400 // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (dialog_height // 2)
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

        # Order # (only for EcoFlow)
        order_entry = None
        if project != "halo":
            ctk.CTkLabel(frame, text="Order #", font=ctk.CTkFont(size=14)).pack(anchor="w")
            order_entry = ctk.CTkEntry(frame, width=340, font=ctk.CTkFont(size=14))
            order_entry.insert(0, item.get('order_number', ''))
            order_entry.pack(pady=(2, 8))

        # Repair State
        ctk.CTkLabel(frame, text="Repair State", font=ctk.CTkFont(size=14)).pack(anchor="w")
        repair_options = ["Temporary Storage","To be repaired", "To be refurbished","To be Scrapped","Storage only","Good Spare Parts","Refurbished","Repaired"]
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
            order_number = order_entry.get().strip() if order_entry else ""

            if not sku or not serial or not lpn:
                status_label.configure(text="All fields are required")
                self._play_error_sound()
                return

            # Validate LPN: must be exactly 11 digits
            if not lpn.isdigit() or len(lpn) != 11:
                status_label.configure(text="LPN must be exactly 11 digits (numbers only)")
                self._play_error_sound()
                return

            if update_inventory_item(item['id'], sku, serial, lpn, item.get('location', ''), repair_state, project, order_number):
                dialog.destroy()
                self._refresh_inventory_list(project)
                self._show_user_status("Item updated successfully", project, error=False)
            else:
                status_label.configure(text="Failed to update item")
                self._play_error_sound()

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

    def _delete_inventory_item(self, item: dict, project: str = "ecoflow"):
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
            if delete_inventory_item(item['id'], project):
                dialog.destroy()
                self._refresh_inventory_list(project)
                self._show_user_status("Item deleted", project, error=False)
            else:
                dialog.destroy()
                self._show_user_status("Failed to delete item", project, error=True)

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

    def _on_sku_keyrelease(self, event, project: str = "ecoflow"):
        """Handle key release in SKU entry for autocomplete."""
        # Ignore navigation keys
        if event.keysym in ('Up', 'Down', 'Left', 'Right', 'Return', 'Tab', 'Escape'):
            if event.keysym == 'Escape':
                self._hide_sku_suggestions(None, project)
            return

        sku_entry = self.project_widgets[project]['sku_entry']
        text = sku_entry.get().strip()

        if len(text) < 1:
            self._hide_sku_suggestions(None, project)
            return

        # Get matching SKUs for this project
        matches = search_skus(text, limit=8, project=project)

        if matches:
            self._show_sku_suggestions(matches, project)
        else:
            self._hide_sku_suggestions(None, project)

    def _show_sku_suggestions(self, matches, project: str = "ecoflow"):
        """Show autocomplete suggestions dropdown."""
        # Remove existing suggestions
        self._hide_sku_suggestions(None, project)

        sku_entry = self.project_widgets[project]['sku_entry']

        # Create suggestions frame as a toplevel to float above
        suggestions_frame = ctk.CTkToplevel(self)
        suggestions_frame.withdraw()  # Hide initially
        suggestions_frame.overrideredirect(True)  # No window decorations
        self.project_widgets[project]['sku_suggestions_frame'] = suggestions_frame

        # Position below the entry
        entry_x = sku_entry.winfo_rootx()
        entry_y = sku_entry.winfo_rooty() + sku_entry.winfo_height()

        # Create scrollable frame for suggestions
        suggestions_container = ctk.CTkFrame(suggestions_frame)
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
                command=lambda s=match['sku'], p=project: self._select_sku_suggestion(s, p)
            )
            btn.pack(fill="x", padx=2, pady=1)

        # Show and position
        suggestions_frame.geometry(f"180x{min(len(matches) * 32, 250)}+{entry_x}+{entry_y}")
        suggestions_frame.deiconify()
        suggestions_frame.lift()

    def _hide_sku_suggestions(self, event, project: str = "ecoflow"):
        """Hide the autocomplete suggestions."""
        def do_hide():
            if project not in self.project_widgets:
                return
            suggestions_frame = self.project_widgets[project]['sku_suggestions_frame']
            if not suggestions_frame:
                return
            try:
                # Check if mouse is over the suggestions frame
                x, y = suggestions_frame.winfo_pointerxy()
                widget_x = suggestions_frame.winfo_rootx()
                widget_y = suggestions_frame.winfo_rooty()
                widget_w = suggestions_frame.winfo_width()
                widget_h = suggestions_frame.winfo_height()

                # If mouse is over suggestions, don't hide
                if widget_x <= x <= widget_x + widget_w and widget_y <= y <= widget_y + widget_h:
                    return

                suggestions_frame.destroy()
                self.project_widgets[project]['sku_suggestions_frame'] = None
            except:
                self.project_widgets[project]['sku_suggestions_frame'] = None
        self.after(1000, do_hide)

    def _select_sku_suggestion(self, sku, project: str = "ecoflow"):
        """Select a SKU from suggestions."""
        sku_entry = self.project_widgets[project]['sku_entry']
        serial_entry = self.project_widgets[project]['serial_entry']
        sku_entry.delete(0, 'end')
        sku_entry.insert(0, sku)
        self._hide_sku_suggestions(None, project)
        # Move focus to next field
        serial_entry.focus()

    def _handle_submit_entry(self, project: str = "ecoflow"):
        """Handle submit button click for item entry."""
        widgets = self.project_widgets[project]
        sku = widgets['sku_entry'].get().strip()
        serial = widgets['serial_entry'].get().strip()
        lpn = widgets['lpn_entry'].get().strip()
        location = widgets['location_dropdown'].get()
        repair_state = widgets['repair_dropdown'].get() if widgets['repair_dropdown'] else ""
        order_number = widgets['order_entry'].get().strip() if widgets['order_entry'] else ""

        # Basic validation
        if not sku:
            self._show_user_status("Item SKU is required", project, error=True)
            return

        # Validate SKU against approved list for this project
        if not is_valid_sku(sku, project):
            self._show_user_status(f"Invalid SKU: '{sku}' not in approved list", project, error=True)
            return

        if not serial:
            self._show_user_status("Serial Number is required", project, error=True)
            return

        # Halo serial numbers must be exactly 12 alphanumeric characters
        if project == "halo":
            if not serial.isalnum() or len(serial) != 12:
                self._show_user_status("Serial Number must be exactly 12 alphanumeric characters", project, error=True)
                return

        if not lpn:
            self._show_user_status("LPN is required", project, error=True)
            return

        # Validate LPN: must be exactly 11 digits
        if not lpn.isdigit() or len(lpn) != 11:
            self._show_user_status("LPN must be exactly 11 digits (numbers only)", project, error=True)
            return

        # Save to inventory database
        try:
            add_inventory_item(
                item_sku=sku,
                serial_number=serial,
                lpn=lpn,
                location=location,
                repair_state=repair_state,
                entered_by=self.user['username'],
                project=project,
                order_number=order_number
            )
            self._show_user_status("Entry submitted successfully", project, error=False)
            self._play_success_sound()
        except Exception as e:
            self._show_user_status(f"Failed to save: {str(e)}", project, error=True)
            return

        # Clear form
        widgets['sku_entry'].delete(0, 'end')
        widgets['serial_entry'].delete(0, 'end')
        widgets['lpn_entry'].delete(0, 'end')
        if widgets['order_entry']:
            widgets['order_entry'].delete(0, 'end')
        if widgets['repair_dropdown']:
            widgets['repair_dropdown'].set(widgets['repair_options'][0])

        # Refresh inventory list
        self._refresh_inventory_list(project)

        # Focus back to first field
        widgets['sku_entry'].focus()

    def _show_user_status(self, message: str, project: str = "ecoflow", error: bool = False):
        """Display a status message for user panel."""
        color = "red" if error else "green"
        self.project_widgets[project]['status_label'].configure(text=message, text_color=color)
        if error:
            self._play_error_sound()

    def _handle_export_inventory(self, project: str = "ecoflow"):
        """Handle export and archive of inventory."""
        items = get_all_inventory(project)

        if not items:
            self._show_user_status("No inventory items to export", project, error=True)
            return

        # Generate filename with today's date and time
        now = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        project_name = project.capitalize()
        default_filename = f"{project_name} stock import({now}).csv"
        if project == "halo":
            default_dir = r"T:\InterfacesFiles\In"
        else:
            default_dir = r"T:\3PL Files\Stock Import"

        # Ask user where to save the file
        filepath = filedialog.asksaveasfilename(
            title="Save CSV Export",
            defaultextension=".csv",
            initialdir=default_dir if os.path.exists(default_dir) else None,
            initialfile=default_filename,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )

        if not filepath:
            return  # User cancelled

        # Move items to imported inventory and export CSV
        moved_items = move_inventory_to_imported(project)

        if export_inventory_to_csv(moved_items, filepath, project):
            self._show_user_status(f"Exported {len(moved_items)} items and archived", project, error=False)
            self._refresh_inventory_list(project)
            self._play_success_sound()
        else:
            self._show_user_status("Failed to export CSV", project, error=True)

    def _create_admin_panel(self, parent):
        """Create the admin panel with tabbed interface for Users, SKUs, and Inventory."""
        # Create tabview
        tabview = ctk.CTkTabview(parent)
        tabview.pack(expand=True, fill="both", padx=10, pady=10)

        # Add tabs
        tabview.add("Users")
        tabview.add("Approved SKUs")
        tabview.add("Inventory")

        # Create content for each tab
        self._create_users_tab(tabview.tab("Users"))
        self._create_skus_tab(tabview.tab("Approved SKUs"))
        self._create_inventory_tab(tabview.tab("Inventory"))

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
        self.user_list_frame.grid_columnconfigure(4, weight=0)

        self._refresh_user_list()

    def _create_skus_tab(self, parent):
        """Create the SKU management tab with project sub-tabs."""
        # Create project tabview (EcoFlow / Halo)
        project_tabview = ctk.CTkTabview(parent)
        project_tabview.pack(expand=True, fill="both", padx=5, pady=5)

        project_tabview.add("EcoFlow")
        project_tabview.add("Halo")

        # Create SKU management for each project
        self._create_project_skus_content(project_tabview.tab("EcoFlow"), "ecoflow")
        self._create_project_skus_content(project_tabview.tab("Halo"), "halo")

    def _create_project_skus_content(self, parent, project: str):
        """Create the SKU management content for a specific project."""
        # Initialize widget storage for this project
        self.admin_sku_widgets[project] = {}

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

        sku_count_label = ctk.CTkLabel(
            stats_frame,
            text=f"Total SKUs: {get_sku_count(project)}",
            font=ctk.CTkFont(size=14)
        )
        sku_count_label.pack(pady=(0, 10))
        self.admin_sku_widgets[project]['sku_count_label'] = sku_count_label

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
            command=lambda p=project: self._import_skus_csv(p)
        )
        import_btn.pack(pady=(0, 5))

        clear_btn = ctk.CTkButton(
            add_frame,
            text="Clear All SKUs",
            width=220,
            font=ctk.CTkFont(size=14),
            fg_color="#dc3545",
            hover_color="#c82333",
            command=lambda p=project: self._clear_all_skus(p)
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
        new_sku_entry = ctk.CTkEntry(form_frame, width=220, font=ctk.CTkFont(size=14))
        new_sku_entry.grid(row=1, column=0, pady=(0, 10))
        self.admin_sku_widgets[project]['new_sku_entry'] = new_sku_entry

        ctk.CTkLabel(form_frame, text="Description (optional)", font=ctk.CTkFont(size=14)).grid(row=2, column=0, sticky="w", pady=(0, 5))
        new_sku_desc_entry = ctk.CTkEntry(form_frame, width=220, font=ctk.CTkFont(size=14))
        new_sku_desc_entry.grid(row=3, column=0, pady=(0, 10))
        self.admin_sku_widgets[project]['new_sku_desc_entry'] = new_sku_desc_entry

        sku_status_label = ctk.CTkLabel(form_frame, text="", width=220, font=ctk.CTkFont(size=14))
        sku_status_label.grid(row=4, column=0, pady=(0, 10))
        self.admin_sku_widgets[project]['sku_status_label'] = sku_status_label

        add_sku_btn = ctk.CTkButton(
            form_frame,
            text="Add SKU",
            width=220,
            font=ctk.CTkFont(size=14),
            command=lambda p=project: self._handle_add_sku(p)
        )
        add_sku_btn.grid(row=5, column=0)

        # Right side - SKU list
        list_frame = ctk.CTkFrame(parent)
        list_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="nsew")

        # Search bar
        search_frame = ctk.CTkFrame(list_frame, fg_color="transparent")
        search_frame.pack(pady=(15, 10), padx=20, fill="x")

        ctk.CTkLabel(search_frame, text="Search SKUs:", font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 10))
        sku_search_entry = ctk.CTkEntry(search_frame, width=300, font=ctk.CTkFont(size=14))
        sku_search_entry.pack(side="left", padx=(0, 10))
        sku_search_entry.bind("<KeyRelease>", lambda e, p=project: self._filter_sku_list(p))
        self.admin_sku_widgets[project]['sku_search_entry'] = sku_search_entry

        # SKU list
        list_title = ctk.CTkLabel(
            list_frame,
            text="Approved SKUs",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        list_title.pack(pady=(5, 10), padx=20)

        sku_list_frame = ctk.CTkScrollableFrame(list_frame)
        sku_list_frame.pack(expand=True, fill="both", padx=10, pady=(0, 10))
        self.admin_sku_widgets[project]['sku_list_frame'] = sku_list_frame

        sku_list_frame.grid_columnconfigure(0, weight=1)
        sku_list_frame.grid_columnconfigure(1, weight=2)
        sku_list_frame.grid_columnconfigure(2, weight=0)

        self._refresh_sku_list(project=project)

    def _create_inventory_tab(self, parent):
        """Create the inventory viewing tab for admin with project tabs."""
        # Create project tabview (EcoFlow / Halo)
        project_tabview = ctk.CTkTabview(parent)
        project_tabview.pack(expand=True, fill="both", padx=5, pady=5)

        project_tabview.add("EcoFlow")
        project_tabview.add("Halo")

        # Create inventory views for each project
        self._create_admin_project_inventory(project_tabview.tab("EcoFlow"), "ecoflow")
        self._create_admin_project_inventory(project_tabview.tab("Halo"), "halo")

    def _create_admin_project_inventory(self, parent, project: str):
        """Create the inventory sub-tabs (Active/Archived) for a specific project."""
        # Initialize widget storage for this project
        self.admin_project_widgets[project] = {}

        # Create sub-tabview for Active and Archived
        inventory_tabview = ctk.CTkTabview(parent)
        inventory_tabview.pack(expand=True, fill="both", padx=5, pady=5)

        inventory_tabview.add("Active Inventory")
        inventory_tabview.add("Archived Inventory")

        # Active inventory section
        self._create_active_inventory_view(inventory_tabview.tab("Active Inventory"), project)

        # Archived inventory section
        self._create_archived_inventory_view(inventory_tabview.tab("Archived Inventory"), project)

    def _create_active_inventory_view(self, parent, project: str = "ecoflow"):
        """Create the active inventory view for a specific project."""
        # Item Entry Form at the top
        form_frame = ctk.CTkFrame(parent)
        form_frame.pack(fill="x", padx=10, pady=(10, 5))

        # Title
        title_label = ctk.CTkLabel(
            form_frame,
            text="Item Entry",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(10, 10), padx=15, anchor="w")

        # Form fields in horizontal layout
        fields_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        fields_frame.pack(padx=15, pady=(0, 10), fill="x")

        # Item SKU with autocomplete
        sku_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
        sku_frame.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(sku_frame, text="Item SKU", font=ctk.CTkFont(size=13)).pack(anchor="w")
        admin_sku_entry = ctk.CTkEntry(sku_frame, width=150, font=ctk.CTkFont(size=13))
        admin_sku_entry.pack()
        admin_sku_entry.bind("<KeyRelease>", lambda e, p=project: self._on_admin_sku_keyrelease(e, p))
        admin_sku_entry.bind("<FocusOut>", lambda e, p=project: self._hide_admin_sku_suggestions(e, p))
        self.admin_project_widgets[project]['sku_entry'] = admin_sku_entry
        self.admin_project_widgets[project]['sku_suggestions_frame'] = None

        # Serial Number
        serial_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
        serial_frame.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(serial_frame, text="Serial Number", font=ctk.CTkFont(size=13)).pack(anchor="w")
        admin_serial_entry = ctk.CTkEntry(serial_frame, width=150, font=ctk.CTkFont(size=13))
        admin_serial_entry.pack()
        self.admin_project_widgets[project]['serial_entry'] = admin_serial_entry

        # LPN
        lpn_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
        lpn_frame.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(lpn_frame, text="LPN", font=ctk.CTkFont(size=13)).pack(anchor="w")
        admin_lpn_entry = ctk.CTkEntry(lpn_frame, width=120, font=ctk.CTkFont(size=13))
        admin_lpn_entry.pack()
        self.admin_project_widgets[project]['lpn_entry'] = admin_lpn_entry

        # Order # (only shown for EcoFlow, not for Halo)
        if project != "halo":
            order_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
            order_frame.pack(side="left", padx=(0, 10))
            ctk.CTkLabel(order_frame, text="Order #", font=ctk.CTkFont(size=13)).pack(anchor="w")
            admin_order_entry = ctk.CTkEntry(order_frame, width=100, font=ctk.CTkFont(size=13))
            admin_order_entry.pack()
            self.admin_project_widgets[project]['order_entry'] = admin_order_entry
        else:
            self.admin_project_widgets[project]['order_entry'] = None

        # Location (dropdown with project-specific options)
        location_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
        location_frame.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(location_frame, text="Location", font=ctk.CTkFont(size=13)).pack(anchor="w")
        if project == "halo":
            location_options = ["INPROD01", "Halocage1", "Halocage2", "Halocage3", "Halocage4"]
        else:
            location_options = ["EFINPROD01"]
        admin_location_dropdown = ctk.CTkOptionMenu(location_frame, width=120, values=location_options, font=ctk.CTkFont(size=13))
        admin_location_dropdown.set(location_options[0])
        admin_location_dropdown.pack()
        self.admin_project_widgets[project]['location_dropdown'] = admin_location_dropdown

        # Repair State (only shown for EcoFlow, not for Halo)
        if project != "halo":
            repair_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
            repair_frame.pack(side="left", padx=(0, 10))
            ctk.CTkLabel(repair_frame, text="Repair State", font=ctk.CTkFont(size=13)).pack(anchor="w")
            repair_options = ["Temporary Storage", "To be repaired", "To be refurbished", "To be Scrapped", "Storage only", "Good Spare Parts", "Refurbished", "Repaired"]
            admin_repair_dropdown = ctk.CTkOptionMenu(repair_frame, width=150, values=repair_options, font=ctk.CTkFont(size=13))
            admin_repair_dropdown.set(repair_options[0])
            admin_repair_dropdown.pack()
            self.admin_project_widgets[project]['repair_dropdown'] = admin_repair_dropdown
            self.admin_project_widgets[project]['repair_options'] = repair_options
        else:
            self.admin_project_widgets[project]['repair_dropdown'] = None
            self.admin_project_widgets[project]['repair_options'] = []

        # Submit button
        submit_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
        submit_frame.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(submit_frame, text=" ").pack()  # Spacer for alignment
        admin_submit_button = ctk.CTkButton(
            submit_frame,
            text="Submit",
            width=80,
            font=ctk.CTkFont(size=13),
            command=lambda p=project: self._handle_admin_submit_entry(p)
        )
        admin_submit_button.pack()

        # Status message
        admin_status_label = ctk.CTkLabel(form_frame, text="", height=18, font=ctk.CTkFont(size=13))
        admin_status_label.pack(pady=(0, 8))
        self.admin_project_widgets[project]['status_label'] = admin_status_label

        # Header with refresh button for inventory list
        header_frame = ctk.CTkFrame(parent, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=(5, 5))

        title = ctk.CTkLabel(
            header_frame,
            text="Active Inventory Items",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title.pack(side="left")

        refresh_btn = ctk.CTkButton(
            header_frame,
            text="Refresh",
            width=100,
            font=ctk.CTkFont(size=14),
            command=lambda p=project: self._refresh_admin_active_inventory(p)
        )
        refresh_btn.pack(side="right", padx=(5, 0))

        export_btn = ctk.CTkButton(
            header_frame,
            text="Export & Archive",
            width=140,
            font=ctk.CTkFont(size=14),
            fg_color="#28a745",
            hover_color="#218838",
            command=lambda p=project: self._handle_admin_export_inventory(p)
        )
        export_btn.pack(side="right")

        # Scrollable frame for inventory list
        admin_active_inventory_frame = ctk.CTkScrollableFrame(parent)
        admin_active_inventory_frame.pack(expand=True, fill="both", padx=10, pady=(0, 10))
        self.admin_project_widgets[project]['active_inventory_frame'] = admin_active_inventory_frame

        # Configure columns (EcoFlow has extra Order # column, plus Actions column)
        num_columns = 8 if project != "halo" else 7
        for i in range(num_columns):
            admin_active_inventory_frame.grid_columnconfigure(i, weight=1)

        self._refresh_admin_active_inventory(project)

    def _create_archived_inventory_view(self, parent, project: str = "ecoflow"):
        """Create the archived inventory view for a specific project."""
        # Header with refresh button
        header_frame = ctk.CTkFrame(parent, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=(10, 5))

        title = ctk.CTkLabel(
            header_frame,
            text="Archived Inventory Items",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title.pack(side="left")

        refresh_btn = ctk.CTkButton(
            header_frame,
            text="Refresh",
            width=100,
            font=ctk.CTkFont(size=14),
            command=lambda p=project: self._refresh_admin_archived_inventory(p)
        )
        refresh_btn.pack(side="right")

        # Scrollable frame for inventory list
        admin_archived_inventory_frame = ctk.CTkScrollableFrame(parent)
        admin_archived_inventory_frame.pack(expand=True, fill="both", padx=10, pady=(0, 10))
        self.admin_project_widgets[project]['archived_inventory_frame'] = admin_archived_inventory_frame

        # Configure columns (EcoFlow has extra Order # column)
        num_columns = 8 if project != "halo" else 7
        for i in range(num_columns):
            admin_archived_inventory_frame.grid_columnconfigure(i, weight=1)

        self._refresh_admin_archived_inventory(project)

    def _refresh_admin_active_inventory(self, project: str = "ecoflow"):
        """Refresh the admin active inventory list for a specific project."""
        admin_active_inventory_frame = self.admin_project_widgets[project]['active_inventory_frame']
        for widget in admin_active_inventory_frame.winfo_children():
            widget.destroy()

        # Header row - include PO # for both projects (between LPN and Repair State)
        headers = ["SKU", "Serial Number", "LPN", "PO #", "Repair State", "Entered By", "Date", "Actions"]
        for col, header in enumerate(headers):
            label = ctk.CTkLabel(
                admin_active_inventory_frame,
                text=header,
                font=ctk.CTkFont(size=14, weight="bold")
            )
            label.grid(row=0, column=col, padx=5, pady=(0, 10), sticky="w")

        # Inventory rows
        items = get_all_inventory(project)
        for row, item in enumerate(items, start=1):
            col = 0
            ctk.CTkLabel(admin_active_inventory_frame, text=item['item_sku'], font=ctk.CTkFont(size=13)).grid(
                row=row, column=col, padx=5, pady=3, sticky="w")
            col += 1
            ctk.CTkLabel(admin_active_inventory_frame, text=item['serial_number'], font=ctk.CTkFont(size=13)).grid(
                row=row, column=col, padx=5, pady=3, sticky="w")
            col += 1
            ctk.CTkLabel(admin_active_inventory_frame, text=item['lpn'], font=ctk.CTkFont(size=13)).grid(
                row=row, column=col, padx=5, pady=3, sticky="w")
            col += 1
            # PO # column - EcoFlow uses order_number, Halo uses SN lookup
            if project == "halo":
                po_number = lookup_halo_po_number(item['serial_number']) or '0'
            else:
                po_number = item.get('order_number', '')
            ctk.CTkLabel(admin_active_inventory_frame, text=po_number, font=ctk.CTkFont(size=13)).grid(
                row=row, column=col, padx=5, pady=3, sticky="w")
            col += 1
            ctk.CTkLabel(admin_active_inventory_frame, text=item['repair_state'], font=ctk.CTkFont(size=13)).grid(
                row=row, column=col, padx=5, pady=3, sticky="w")
            col += 1
            ctk.CTkLabel(admin_active_inventory_frame, text=item['entered_by'], font=ctk.CTkFont(size=13)).grid(
                row=row, column=col, padx=5, pady=3, sticky="w")
            col += 1
            date_str = item['created_at'].replace('T', ' ')[:16] if 'T' in item['created_at'] else item['created_at'][:16]
            ctk.CTkLabel(admin_active_inventory_frame, text=date_str, font=ctk.CTkFont(size=13)).grid(
                row=row, column=col, padx=5, pady=3, sticky="w")
            col += 1

            # Action buttons frame
            action_frame = ctk.CTkFrame(admin_active_inventory_frame, fg_color="transparent")
            action_frame.grid(row=row, column=col, padx=2, pady=3, sticky="w")

            edit_btn = ctk.CTkButton(
                action_frame,
                text="Edit",
                width=50,
                height=24,
                font=ctk.CTkFont(size=11),
                command=lambda i=item, p=project: self._show_admin_edit_inventory_dialog(i, p)
            )
            edit_btn.pack(side="left", padx=(0, 3))

            delete_btn = ctk.CTkButton(
                action_frame,
                text="Delete",
                width=50,
                height=24,
                font=ctk.CTkFont(size=11),
                fg_color="#dc3545",
                hover_color="#c82333",
                command=lambda i=item, p=project: self._admin_delete_inventory_item(i, p)
            )
            delete_btn.pack(side="left")

    def _refresh_admin_archived_inventory(self, project: str = "ecoflow"):
        """Refresh the admin archived inventory list for a specific project."""
        admin_archived_inventory_frame = self.admin_project_widgets[project]['archived_inventory_frame']
        for widget in admin_archived_inventory_frame.winfo_children():
            widget.destroy()

        # Header row - include PO # for both projects (between LPN and Repair State)
        headers = ["SKU", "Serial Number", "LPN", "PO #", "Repair State", "Entered By", "Created", "Archived"]
        for col, header in enumerate(headers):
            label = ctk.CTkLabel(
                admin_archived_inventory_frame,
                text=header,
                font=ctk.CTkFont(size=14, weight="bold")
            )
            label.grid(row=0, column=col, padx=5, pady=(0, 10), sticky="w")

        # Inventory rows
        items = get_all_imported_inventory(project)
        for row, item in enumerate(items, start=1):
            col = 0
            ctk.CTkLabel(admin_archived_inventory_frame, text=item['item_sku'], font=ctk.CTkFont(size=13)).grid(
                row=row, column=col, padx=5, pady=3, sticky="w")
            col += 1
            ctk.CTkLabel(admin_archived_inventory_frame, text=item['serial_number'], font=ctk.CTkFont(size=13)).grid(
                row=row, column=col, padx=5, pady=3, sticky="w")
            col += 1
            ctk.CTkLabel(admin_archived_inventory_frame, text=item['lpn'], font=ctk.CTkFont(size=13)).grid(
                row=row, column=col, padx=5, pady=3, sticky="w")
            col += 1
            # PO # column - EcoFlow uses order_number, Halo uses SN lookup
            if project == "halo":
                po_number = lookup_halo_po_number(item['serial_number']) or '0'
            else:
                po_number = item.get('order_number', '')
            ctk.CTkLabel(admin_archived_inventory_frame, text=po_number, font=ctk.CTkFont(size=13)).grid(
                row=row, column=col, padx=5, pady=3, sticky="w")
            col += 1
            ctk.CTkLabel(admin_archived_inventory_frame, text=item['repair_state'], font=ctk.CTkFont(size=13)).grid(
                row=row, column=col, padx=5, pady=3, sticky="w")
            col += 1
            ctk.CTkLabel(admin_archived_inventory_frame, text=item['entered_by'], font=ctk.CTkFont(size=13)).grid(
                row=row, column=col, padx=5, pady=3, sticky="w")
            col += 1
            created_str = item['created_at'].replace('T', ' ')[:16] if 'T' in item['created_at'] else item['created_at'][:16]
            ctk.CTkLabel(admin_archived_inventory_frame, text=created_str, font=ctk.CTkFont(size=13)).grid(
                row=row, column=col, padx=5, pady=3, sticky="w")
            col += 1
            archived_str = item['imported_at'].replace('T', ' ')[:16] if 'T' in item['imported_at'] else item['imported_at'][:16]
            ctk.CTkLabel(admin_archived_inventory_frame, text=archived_str, font=ctk.CTkFont(size=13)).grid(
                row=row, column=col, padx=5, pady=3, sticky="w")

    def _show_admin_edit_inventory_dialog(self, item: dict, project: str = "ecoflow"):
        """Show dialog to edit an inventory item from admin view."""
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Edit Item - {item['item_sku']}")
        dialog_height = 510 if project != "halo" else 450
        dialog.geometry(f"400x{dialog_height}")
        dialog.resizable(False, False)
        dialog.transient(self)

        frame = ctk.CTkFrame(dialog)
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Item SKU
        ctk.CTkLabel(frame, text="Item SKU", font=ctk.CTkFont(size=14)).pack(anchor="w")
        sku_entry = ctk.CTkEntry(frame, width=300, font=ctk.CTkFont(size=14))
        sku_entry.insert(0, item['item_sku'])
        sku_entry.pack(pady=(0, 15))

        # Serial Number
        ctk.CTkLabel(frame, text="Serial Number", font=ctk.CTkFont(size=14)).pack(anchor="w")
        serial_entry = ctk.CTkEntry(frame, width=300, font=ctk.CTkFont(size=14))
        serial_entry.insert(0, item['serial_number'])
        serial_entry.pack(pady=(0, 15))

        # LPN
        ctk.CTkLabel(frame, text="LPN", font=ctk.CTkFont(size=14)).pack(anchor="w")
        lpn_entry = ctk.CTkEntry(frame, width=300, font=ctk.CTkFont(size=14))
        lpn_entry.insert(0, item['lpn'])
        lpn_entry.pack(pady=(0, 15))

        # Order Number (EcoFlow only)
        order_entry = None
        if project != "halo":
            ctk.CTkLabel(frame, text="Order #", font=ctk.CTkFont(size=14)).pack(anchor="w")
            order_entry = ctk.CTkEntry(frame, width=300, font=ctk.CTkFont(size=14))
            order_entry.insert(0, item.get('order_number', ''))
            order_entry.pack(pady=(0, 15))

        # Repair State
        ctk.CTkLabel(frame, text="Repair State", font=ctk.CTkFont(size=14)).pack(anchor="w")
        repair_options = ["RTV", "Tested Good", "Needs Repair", "Damaged", "Unknown"]
        repair_dropdown = ctk.CTkOptionMenu(frame, values=repair_options, width=300)
        if item['repair_state'] in repair_options:
            repair_dropdown.set(item['repair_state'])
        else:
            repair_dropdown.set(repair_options[0])
        repair_dropdown.pack(pady=(0, 15))

        # Status label
        status_label = ctk.CTkLabel(frame, text="", font=ctk.CTkFont(size=12))
        status_label.pack(pady=(0, 10))

        def save_changes():
            sku = sku_entry.get().strip()
            serial = serial_entry.get().strip()
            lpn = lpn_entry.get().strip()
            repair_state = repair_dropdown.get()
            order_number = order_entry.get().strip() if order_entry else ""

            if not sku or not serial or not lpn:
                status_label.configure(text="All fields are required", text_color="red")
                self._play_error_sound()
                return

            # Validate LPN: must be exactly 11 digits
            if not lpn.isdigit() or len(lpn) != 11:
                status_label.configure(text="LPN must be exactly 11 digits", text_color="red")
                self._play_error_sound()
                return

            if update_inventory_item(item['id'], sku, serial, lpn, item.get('location', ''), repair_state, project, order_number):
                dialog.destroy()
                self._refresh_admin_active_inventory(project)
                self._play_success_sound()
            else:
                status_label.configure(text="Failed to update item", text_color="red")
                self._play_error_sound()

        # Buttons
        button_frame = ctk.CTkFrame(frame, fg_color="transparent")
        button_frame.pack(fill="x")

        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancel",
            width=100,
            fg_color="gray",
            command=dialog.destroy
        )
        cancel_btn.pack(side="left")

        save_btn = ctk.CTkButton(
            button_frame,
            text="Save",
            width=100,
            command=save_changes
        )
        save_btn.pack(side="right")

    def _admin_delete_inventory_item(self, item: dict, project: str = "ecoflow"):
        """Delete an inventory item with confirmation from admin view."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Confirm Delete")
        dialog.geometry("350x180")
        dialog.resizable(False, False)
        dialog.transient(self)

        frame = ctk.CTkFrame(dialog)
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            frame,
            text="Are you sure you want to delete this item?",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(0, 10))

        ctk.CTkLabel(
            frame,
            text=f"SKU: {item['item_sku']}\nSerial: {item['serial_number']}",
            font=ctk.CTkFont(size=13)
        ).pack(pady=(0, 20))

        def do_delete():
            if delete_inventory_item(item['id'], project):
                dialog.destroy()
                self._refresh_admin_active_inventory(project)
                self._play_success_sound()
            else:
                self._play_error_sound()

        button_frame = ctk.CTkFrame(frame, fg_color="transparent")
        button_frame.pack(fill="x")

        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancel",
            width=100,
            fg_color="gray",
            command=dialog.destroy
        )
        cancel_btn.pack(side="left")

        delete_btn = ctk.CTkButton(
            button_frame,
            text="Delete",
            width=100,
            fg_color="#dc3545",
            hover_color="#c82333",
            command=do_delete
        )
        delete_btn.pack(side="right")

    def _handle_admin_export_inventory(self, project: str = "ecoflow"):
        """Handle export and archive of inventory from admin panel."""
        items = get_all_inventory(project)

        if not items:
            # Show a simple dialog for admin since they don't have user_status_label
            dialog = ctk.CTkToplevel(self)
            dialog.title("Export")
            dialog.geometry("300x100")
            dialog.resizable(False, False)
            dialog.transient(self)
            ctk.CTkLabel(dialog, text="No inventory items to export", font=ctk.CTkFont(size=14)).pack(pady=20)
            ctk.CTkButton(dialog, text="OK", width=80, command=dialog.destroy).pack()
            dialog.wait_visibility()
            dialog.grab_set()
            return

        # Generate filename with today's date and time
        now = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        project_name = project.capitalize()
        default_filename = f"{project_name} stock import({now}).csv"
        if project == "halo":
            default_dir = r"T:\InterfacesFiles\In"
        else:
            default_dir = r"T:\3PL Files\Stock Import"

        # Ask user where to save the file
        filepath = filedialog.asksaveasfilename(
            title="Save CSV Export",
            defaultextension=".csv",
            initialdir=default_dir if os.path.exists(default_dir) else None,
            initialfile=default_filename,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )

        if not filepath:
            return  # User cancelled

        # Move items to imported inventory and export CSV
        moved_items = move_inventory_to_imported(project)

        if export_inventory_to_csv(moved_items, filepath, project):
            self._refresh_admin_active_inventory(project)
            self._refresh_admin_archived_inventory(project)
            self._play_success_sound()
            # Show success dialog
            dialog = ctk.CTkToplevel(self)
            dialog.title("Export Complete")
            dialog.geometry("300x100")
            dialog.resizable(False, False)
            dialog.transient(self)
            ctk.CTkLabel(dialog, text=f"Exported {len(moved_items)} items", font=ctk.CTkFont(size=14)).pack(pady=20)
            ctk.CTkButton(dialog, text="OK", width=80, command=dialog.destroy).pack()
            dialog.wait_visibility()
            dialog.grab_set()

    def _on_admin_sku_keyrelease(self, event, project: str = "ecoflow"):
        """Handle key release in admin SKU entry for autocomplete."""
        # Ignore navigation keys
        if event.keysym in ('Up', 'Down', 'Left', 'Right', 'Return', 'Tab', 'Escape'):
            if event.keysym == 'Escape':
                self._hide_admin_sku_suggestions(None, project)
            return

        sku_entry = self.admin_project_widgets[project]['sku_entry']
        text = sku_entry.get().strip()

        if len(text) < 1:
            self._hide_admin_sku_suggestions(None, project)
            return

        # Get matching SKUs for this project
        matches = search_skus(text, limit=8, project=project)

        if matches:
            self._show_admin_sku_suggestions(matches, project)
        else:
            self._hide_admin_sku_suggestions(None, project)

    def _show_admin_sku_suggestions(self, matches, project: str = "ecoflow"):
        """Show autocomplete suggestions dropdown for admin view."""
        # Remove existing suggestions
        self._hide_admin_sku_suggestions(None, project)

        sku_entry = self.admin_project_widgets[project]['sku_entry']

        # Create suggestions frame as a toplevel to float above
        suggestions_frame = ctk.CTkToplevel(self)
        suggestions_frame.withdraw()  # Hide initially
        suggestions_frame.overrideredirect(True)  # No window decorations
        self.admin_project_widgets[project]['sku_suggestions_frame'] = suggestions_frame

        # Position below the entry
        entry_x = sku_entry.winfo_rootx()
        entry_y = sku_entry.winfo_rooty() + sku_entry.winfo_height()

        # Create scrollable frame for suggestions
        suggestions_container = ctk.CTkFrame(suggestions_frame)
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
                command=lambda s=match['sku'], p=project: self._select_admin_sku_suggestion(s, p)
            )
            btn.pack(fill="x", padx=2, pady=1)

        # Show and position
        suggestions_frame.geometry(f"150x{min(len(matches) * 32, 250)}+{entry_x}+{entry_y}")
        suggestions_frame.deiconify()
        suggestions_frame.lift()

    def _hide_admin_sku_suggestions(self, event, project: str = "ecoflow"):
        """Hide the admin autocomplete suggestions."""
        def do_hide():
            if project not in self.admin_project_widgets:
                return
            suggestions_frame = self.admin_project_widgets[project].get('sku_suggestions_frame')
            if not suggestions_frame:
                return
            try:
                # Check if mouse is over the suggestions frame
                x, y = suggestions_frame.winfo_pointerxy()
                widget_x = suggestions_frame.winfo_rootx()
                widget_y = suggestions_frame.winfo_rooty()
                widget_w = suggestions_frame.winfo_width()
                widget_h = suggestions_frame.winfo_height()

                # If mouse is over suggestions, don't hide
                if widget_x <= x <= widget_x + widget_w and widget_y <= y <= widget_y + widget_h:
                    return

                suggestions_frame.destroy()
                self.admin_project_widgets[project]['sku_suggestions_frame'] = None
            except:
                self.admin_project_widgets[project]['sku_suggestions_frame'] = None
        self.after(1000, do_hide)

    def _select_admin_sku_suggestion(self, sku, project: str = "ecoflow"):
        """Select a SKU from admin suggestions."""
        sku_entry = self.admin_project_widgets[project]['sku_entry']
        serial_entry = self.admin_project_widgets[project]['serial_entry']
        sku_entry.delete(0, 'end')
        sku_entry.insert(0, sku)
        self._hide_admin_sku_suggestions(None, project)
        # Move focus to next field
        serial_entry.focus()

    def _handle_admin_submit_entry(self, project: str = "ecoflow"):
        """Handle submit button click for admin item entry."""
        widgets = self.admin_project_widgets[project]
        sku = widgets['sku_entry'].get().strip()
        serial = widgets['serial_entry'].get().strip()
        lpn = widgets['lpn_entry'].get().strip()
        location = widgets['location_dropdown'].get()
        repair_state = widgets['repair_dropdown'].get() if widgets['repair_dropdown'] else ""
        order_number = widgets['order_entry'].get().strip() if widgets['order_entry'] else ""

        # Basic validation
        if not sku:
            self._show_admin_status("Item SKU is required", project, error=True)
            return

        # Validate SKU against approved list for this project
        if not is_valid_sku(sku, project):
            self._show_admin_status(f"Invalid SKU: '{sku}' not in approved list", project, error=True)
            return

        if not serial:
            self._show_admin_status("Serial Number is required", project, error=True)
            return

        # Halo serial numbers must be exactly 12 alphanumeric characters
        if project == "halo":
            if not serial.isalnum() or len(serial) != 12:
                self._show_admin_status("Serial Number must be exactly 12 alphanumeric characters", project, error=True)
                return

        if not lpn:
            self._show_admin_status("LPN is required", project, error=True)
            return

        # Validate LPN: must be exactly 11 digits
        if not lpn.isdigit() or len(lpn) != 11:
            self._show_admin_status("LPN must be exactly 11 digits (numbers only)", project, error=True)
            return

        # Save to inventory database
        try:
            add_inventory_item(
                item_sku=sku,
                serial_number=serial,
                lpn=lpn,
                location=location,
                repair_state=repair_state,
                entered_by=self.user['username'],
                project=project,
                order_number=order_number
            )
            self._show_admin_status("Entry submitted successfully", project, error=False)
            self._play_success_sound()
        except Exception as e:
            self._show_admin_status(f"Failed to save: {str(e)}", project, error=True)
            return

        # Clear form
        widgets['sku_entry'].delete(0, 'end')
        widgets['serial_entry'].delete(0, 'end')
        widgets['lpn_entry'].delete(0, 'end')
        if widgets['order_entry']:
            widgets['order_entry'].delete(0, 'end')
        if widgets['repair_dropdown']:
            widgets['repair_dropdown'].set(widgets['repair_options'][0])

        # Refresh inventory list
        self._refresh_admin_active_inventory(project)

        # Focus back to first field
        widgets['sku_entry'].focus()

    def _show_admin_status(self, message: str, project: str = "ecoflow", error: bool = False):
        """Display a status message for admin panel."""
        color = "red" if error else "green"
        self.admin_project_widgets[project]['status_label'].configure(text=message, text_color=color)
        if error:
            self._play_error_sound()

    def _refresh_sku_list(self, filter_text: str = "", project: str = "ecoflow"):
        """Refresh the SKU list display for a specific project."""
        widgets = self.admin_sku_widgets[project]
        sku_list_frame = widgets['sku_list_frame']

        for widget in sku_list_frame.winfo_children():
            widget.destroy()

        # Header row
        headers = ["SKU", "Description", ""]
        for col, header in enumerate(headers):
            label = ctk.CTkLabel(
                sku_list_frame,
                text=header,
                font=ctk.CTkFont(size=14, weight="bold")
            )
            label.grid(row=0, column=col, padx=5, pady=(0, 10), sticky="w")

        # Get SKUs (filtered or all) for this project
        if filter_text:
            skus = search_skus(filter_text, limit=100, project=project)
        else:
            skus = get_all_skus(project)[:100]  # Limit display to 100 for performance

        for row, sku in enumerate(skus, start=1):
            ctk.CTkLabel(sku_list_frame, text=sku['sku'], font=ctk.CTkFont(size=14)).grid(
                row=row, column=0, padx=5, pady=3, sticky="w")
            ctk.CTkLabel(sku_list_frame, text=sku.get('description', ''), font=ctk.CTkFont(size=14)).grid(
                row=row, column=1, padx=5, pady=3, sticky="w")

            delete_btn = ctk.CTkButton(
                sku_list_frame,
                text="Delete",
                width=70,
                height=28,
                font=ctk.CTkFont(size=13),
                fg_color="#dc3545",
                hover_color="#c82333",
                command=lambda s=sku['sku'], p=project: self._handle_delete_sku(s, p)
            )
            delete_btn.grid(row=row, column=2, padx=5, pady=3)

        # Update count
        widgets['sku_count_label'].configure(text=f"Total SKUs: {get_sku_count(project)}")

    def _filter_sku_list(self, project: str = "ecoflow"):
        """Filter SKU list based on search entry for a specific project."""
        filter_text = self.admin_sku_widgets[project]['sku_search_entry'].get().strip()
        self._refresh_sku_list(filter_text, project)

    def _handle_add_sku(self, project: str = "ecoflow"):
        """Handle adding a new SKU for a specific project."""
        widgets = self.admin_sku_widgets[project]
        sku = widgets['new_sku_entry'].get().strip()
        description = widgets['new_sku_desc_entry'].get().strip()

        if not sku:
            widgets['sku_status_label'].configure(text="SKU is required", text_color="red")
            self._play_error_sound()
            return

        if add_sku(sku, description, project):
            widgets['sku_status_label'].configure(text=f"Added: {sku.upper()}", text_color="green")
            widgets['new_sku_entry'].delete(0, 'end')
            widgets['new_sku_desc_entry'].delete(0, 'end')
            self._refresh_sku_list(project=project)
            self._play_success_sound()
        else:
            widgets['sku_status_label'].configure(text="SKU already exists", text_color="red")
            self._play_error_sound()

    def _handle_delete_sku(self, sku: str, project: str = "ecoflow"):
        """Handle deleting a SKU for a specific project."""
        if delete_sku(sku, project):
            filter_text = self.admin_sku_widgets[project]['sku_search_entry'].get().strip()
            self._refresh_sku_list(filter_text, project)

    def _import_skus_csv(self, project: str = "ecoflow"):
        """Import SKUs from a CSV file for a specific project."""
        widgets = self.admin_sku_widgets[project]

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

            success, failed = add_skus_bulk(skus_to_add, project)
            widgets['sku_status_label'].configure(
                text=f"Imported {success}, skipped {failed} duplicates",
                text_color="green" if success > 0 else "orange"
            )
            self._refresh_sku_list(project=project)

        except Exception as e:
            widgets['sku_status_label'].configure(text=f"Error: {str(e)}", text_color="red")
            self._play_error_sound()

    def _clear_all_skus(self, project: str = "ecoflow"):
        """Clear all SKUs for a specific project with confirmation."""
        widgets = self.admin_sku_widgets[project]

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

        count = get_sku_count(project)
        project_name = project.capitalize()
        label = ctk.CTkLabel(
            frame,
            text=f"Delete all {count} {project_name} SKUs?\nThis cannot be undone.",
            font=ctk.CTkFont(size=16)
        )
        label.pack(pady=(0, 20))

        def do_clear():
            deleted = clear_all_skus(project)
            dialog.destroy()
            widgets['sku_status_label'].configure(text=f"Deleted {deleted} SKUs", text_color="green")
            self._refresh_sku_list(project=project)

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
        headers = ["Username", "Admin", "Created", "", ""]
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

            # Admin toggle switch
            admin_switch = ctk.CTkSwitch(
                self.user_list_frame,
                text="",
                width=50,
                command=lambda u=user['username']: self._toggle_admin_status(u)
            )
            admin_switch.grid(row=row, column=1, padx=5, pady=5)
            if user.get('is_admin', False):
                admin_switch.select()
            # Disable toggle for the 'admin' user (always admin)
            if user['username'] == 'admin':
                admin_switch.configure(state="disabled")

            # Created date (just the date part)
            created = user['created_at'].split('T')[0] if 'T' in user['created_at'] else user['created_at'][:10]
            created_label = ctk.CTkLabel(self.user_list_frame, text=created, font=ctk.CTkFont(size=14))
            created_label.grid(row=row, column=2, padx=5, pady=5, sticky="w")

            # Reset password button
            reset_btn = ctk.CTkButton(
                self.user_list_frame,
                text="Reset Password",
                width=130,
                height=32,
                font=ctk.CTkFont(size=13),
                command=lambda u=user['username']: self._show_reset_dialog(u)
            )
            reset_btn.grid(row=row, column=3, padx=5, pady=5)

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
            delete_btn.grid(row=row, column=4, padx=5, pady=5)

            # Disable delete for admin user
            if user['username'] == 'admin':
                delete_btn.configure(state="disabled", fg_color="gray")

    def _toggle_admin_status(self, username: str):
        """Toggle admin status for a user."""
        # Get current user info
        users = get_all_users()
        user = next((u for u in users if u['username'] == username), None)
        if user:
            new_status = not user.get('is_admin', False)
            if update_user_admin_status(username, new_status):
                status_text = "granted admin access" if new_status else "removed from admin"
                self._show_status(f"User '{username}' {status_text}", error=False)
            else:
                self._show_status(f"Failed to update admin status for '{username}'", error=True)
                self._refresh_user_list()  # Refresh to reset toggle state

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
                self._play_error_sound()
                return

            if len(new_pw) < 4:
                status_label.configure(text="Password must be at least 4 characters")
                self._play_error_sound()
                return

            if new_pw != confirm:
                status_label.configure(text="Passwords do not match")
                self._play_error_sound()
                return

            password_hash = hash_password(new_pw)
            if update_user_password(username, password_hash):
                dialog.destroy()
                self._show_status(f"Password reset for '{username}'", error=False)
            else:
                status_label.configure(text="Failed to reset password")
                self._play_error_sound()

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
        if error:
            self._play_error_sound()

    def _handle_logout(self):
        """Handle logout button click."""
        self._stop_inventory_polling()
        self.destroy()
        self.on_logout()
