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
    export_inventory_to_csv,
    lookup_halo_po_number,
    get_email_settings, update_email_settings
)
from database.inventory_cache import (
    add_inventory_item_cached as add_inventory_item,
    get_all_inventory_cached as get_all_inventory,
    get_inventory_count_cached as get_inventory_count,
    update_inventory_item_cached as update_inventory_item,
    delete_inventory_item_cached as delete_inventory_item,
    get_all_imported_inventory_cached as get_all_imported_inventory,
    get_imported_inventory_count_cached as get_imported_inventory_count,
    move_to_imported_cached as move_inventory_to_imported,
    init_inventory_cache,
    start_inventory_sync,
    stop_inventory_sync
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
from utils import hash_password, get_gui_resource, check_for_updates, check_for_updates_shared_drive, show_update_dialog, send_csv_email, test_email_connection
from config import VERSION, GITHUB_REPO, UPDATE_PATH


class MainApplication(ctk.CTk):
    """Main application window after successful login."""

    # Font definitions for consistent sizing
    FONT_TITLE = ("", 24, "bold")
    FONT_SECTION = ("", 20, "bold")
    FONT_LABEL = ("", 14)
    FONT_LABEL_BOLD = ("", 14, "bold")
    FONT_BUTTON = ("", 14)
    PAGE_SIZE = 20

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

        # Create widgets first so GUI displays immediately
        self._create_widgets()

        # Defer all network operations until after GUI is displayed
        self.after(50, self._deferred_init)

    def _deferred_init(self):
        """Initialize network-dependent features after GUI is displayed."""
        # Run all initialization in background thread to avoid blocking GUI
        def init_background():
            # Initialize local caches first (fast, local SQLite only)
            init_sku_cache()
            init_inventory_cache()

            # Pre-load Halo SN cache from P: drive BEFORE starting sync threads
            # so the first user refresh is fast and doesn't compete for P: drive
            try:
                lookup_halo_po_number("")  # Triggers cache load from P: drive
            except Exception:
                pass

            # Start background sync threads AFTER cache is warm
            # (inventory sync has a 10s initial delay to avoid competing with user)
            start_background_sync(interval=1800)  # 30 minutes
            start_inventory_sync()

        threading.Thread(target=init_background, daemon=True).start()

        # Play login sound (safe to run on main thread)
        self._play_login_sound()

        # Check for updates only once at startup (no repeat checks)
        self.after(2000, self._check_for_updates)

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
        """Check for application updates from shared drive or GitHub."""
        def on_update_check(has_update, latest_version, download_url, release_notes):
            if has_update:
                # Schedule dialog to run on main thread
                self.after(100, lambda: show_update_dialog(
                    self, latest_version, download_url, release_notes
                ))

        # Prefer shared drive updates if configured
        if UPDATE_PATH:
            check_for_updates_shared_drive(UPDATE_PATH, VERSION, on_update_check)
        elif GITHUB_REPO and GITHUB_REPO != "YOUR_USERNAME/The-Uplink":
            check_for_updates(GITHUB_REPO, VERSION, on_update_check)

    def destroy(self):
        """Override destroy to signal background threads to stop (non-blocking)."""
        self._stop_inventory_polling()
        # Signal threads to stop but don't wait - they're daemon threads
        # and will be killed when the process exits
        try:
            from database.inventory_cache import _sync_stop_event as inv_stop
            inv_stop.set()
        except Exception:
            pass
        try:
            from database.sku_cache import _sync_stop_event as sku_stop
            sku_stop.set()
        except Exception:
            pass
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
        tabview.add("AMS INE")

        # Create content for each tab
        self._create_project_tab(tabview.tab("EcoFlow"), "ecoflow")
        self._create_project_tab(tabview.tab("Halo"), "halo")
        self._create_project_tab(tabview.tab("AMS INE"), "ams_ine")

        # No auto-loading - user clicks Refresh to load data

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
        # Add serial number lookup for Halo
        if project == "halo":
            serial_entry.bind("<KeyRelease>", lambda e, p=project: self._on_halo_serial_keyrelease(e, p))

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

        # Location (dropdown for halo/ecoflow, text entry for ams_ine)
        location_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
        location_frame.pack(side="left", padx=(0, 15))
        ctk.CTkLabel(location_frame, text="Location", font=ctk.CTkFont(size=14)).pack(anchor="w")
        if project == "ams_ine":
            # Text entry for AMS INE
            location_entry = ctk.CTkEntry(location_frame, width=140, font=ctk.CTkFont(size=14))
            location_entry.pack()
            self.project_widgets[project]['location_dropdown'] = location_entry
        else:
            # Dropdown for other projects
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
            repair_options = ["Temporary Storage","To be repaired", "To be refurbished","To be Scrapped","Storage only","Good Spare Parts","Refurbished","Repaired","Defective Products"]
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

        # Quantity counter
        qty_label = ctk.CTkLabel(
            list_header,
            text="(0 items)",
            font=ctk.CTkFont(size=14),
            text_color="gray70"
        )
        qty_label.pack(side="left", padx=(10, 0))
        self.project_widgets[project]['inventory_qty_label'] = qty_label

        refresh_button = ctk.CTkButton(
            list_header,
            text="Refresh",
            width=100,
            font=ctk.CTkFont(size=14),
            fg_color="#17a2b8",
            hover_color="#138496",
            command=lambda p=project: self._refresh_inventory_list(p)
        )
        refresh_button.pack(side="right", padx=(0, 10))

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

        # Pagination footer
        page_frame = ctk.CTkFrame(list_frame, fg_color="transparent")
        page_frame.pack(fill="x", padx=10, pady=(0, 5))

        prev_btn = ctk.CTkButton(
            page_frame, text="< Previous", width=100, font=ctk.CTkFont(size=13),
            fg_color="#6c757d", hover_color="#5a6268", state="disabled",
            command=lambda p=project: self._go_page(p, "default", -1)
        )
        prev_btn.pack(side="left")

        page_label = ctk.CTkLabel(page_frame, text="", font=ctk.CTkFont(size=13))
        page_label.pack(side="left", expand=True)

        next_btn = ctk.CTkButton(
            page_frame, text="Next >", width=100, font=ctk.CTkFont(size=13),
            fg_color="#6c757d", hover_color="#5a6268", state="disabled",
            command=lambda p=project: self._go_page(p, "default", 1)
        )
        next_btn.pack(side="right")

        self.project_widgets[project]['current_page'] = 0
        self.project_widgets[project]['prev_btn'] = prev_btn
        self.project_widgets[project]['next_btn'] = next_btn
        self.project_widgets[project]['page_label'] = page_label

    def _stop_inventory_polling(self):
        """Stop the inventory polling."""
        if self._refresh_poll_id:
            self.after_cancel(self._refresh_poll_id)
            self._refresh_poll_id = None

    def _reset_and_refresh_inventory(self, project: str):
        """Reset to page 0 and refresh (used after export clears items)."""
        self.project_widgets[project]['current_page'] = 0
        self._refresh_inventory_list(project)

    def _go_page(self, project: str, view_type: str, direction: int):
        """Navigate pagination: direction is +1 (next) or -1 (previous)."""
        if view_type == "default":
            self.project_widgets[project]['current_page'] += direction
            self._refresh_inventory_list(project)
        elif view_type == "admin_active":
            self.admin_project_widgets[project]['active_page'] += direction
            self._refresh_admin_active_inventory(project)
        elif view_type == "admin_archived":
            self.admin_project_widgets[project]['archived_page'] += direction
            self._refresh_admin_archived_inventory(project)

    def _update_pagination(self, widgets: dict, page_key: str, prev_key: str, next_key: str, label_key: str, page: int, total_count: int):
        """Update pagination button states and label."""
        import math
        total_pages = max(1, math.ceil(total_count / self.PAGE_SIZE))
        widgets[label_key].configure(text=f"Page {page + 1} of {total_pages}")
        widgets[prev_key].configure(state="normal" if page > 0 else "disabled")
        widgets[next_key].configure(state="normal" if page < total_pages - 1 else "disabled")

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

        # Show loading message
        loading_label = ctk.CTkLabel(inventory_list_frame, text="Loading...", font=ctk.CTkFont(size=14))
        loading_label.grid(row=1, column=0, columnspan=10, padx=5, pady=10)

        # Fetch data in background thread
        page = self.project_widgets[project]['current_page']
        def fetch_data():
            try:
                total_count = get_inventory_count(project)
                offset = page * self.PAGE_SIZE
                items = get_all_inventory(project, limit=self.PAGE_SIZE, offset=offset)
                # Pre-fetch PO numbers (non-blocking to avoid P: drive delay)
                for item in items:
                    if project == "halo":
                        item['_po_number'] = lookup_halo_po_number(item['serial_number'], blocking=False) or ''
                    else:
                        item['_po_number'] = item.get('order_number', '')
                # Update GUI on main thread
                self.after(0, lambda: self._populate_inventory_list(project, items, total_count))
            except Exception:
                self.after(0, lambda: self._show_inventory_error(
                    self.project_widgets[project]['inventory_list_frame'],
                    "Failed to load inventory: Network error"
                ))

        thread = threading.Thread(target=fetch_data, daemon=True)
        thread.start()

    def _show_inventory_error(self, frame, message: str):
        """Show an error message in an inventory frame."""
        if not frame.winfo_exists():
            return
        for widget in frame.winfo_children():
            widget.destroy()
        error_label = ctk.CTkLabel(
            frame,
            text=message,
            font=ctk.CTkFont(size=14),
            text_color="red"
        )
        error_label.grid(row=0, column=0, padx=20, pady=20)

    def _populate_inventory_list(self, project: str, items: list, total_count: int = 0):
        """Populate inventory list with fetched data (called on main thread)."""
        if not self.winfo_exists():
            return
        inventory_list_frame = self.project_widgets[project]['inventory_list_frame']
        if not inventory_list_frame.winfo_exists():
            return

        # Clear existing widgets (including loading message)
        for widget in inventory_list_frame.winfo_children():
            widget.destroy()

        # Header row
        headers = ["SKU", "Serial Number", "LPN", "PO #", "Location", "Repair State", "Entered By", "Date", "", ""]
        for col, header in enumerate(headers):
            label = ctk.CTkLabel(
                inventory_list_frame,
                text=header,
                font=ctk.CTkFont(size=14, weight="bold")
            )
            label.grid(row=0, column=col, padx=5, pady=(0, 10), sticky="w")

        # Inventory rows
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
            ctk.CTkLabel(inventory_list_frame, text=item['_po_number'], font=ctk.CTkFont(size=14)).grid(
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

        # Update quantity counter with total database count
        self.project_widgets[project]['inventory_qty_label'].configure(text=f"({total_count} item{'s' if total_count != 1 else ''})")

        # Update pagination buttons
        page = self.project_widgets[project]['current_page']
        self._update_pagination(
            self.project_widgets[project], 'current_page', 'prev_btn', 'next_btn', 'page_label',
            page, total_count
        )

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
        repair_options = ["Temporary Storage","To be repaired", "To be refurbished","To be Scrapped","Storage only","Good Spare Parts","Refurbished","Repaired","Defective Products"]
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

            # Validate LPN: must be exactly 11 alphanumeric characters
            if not lpn.isalnum() or len(lpn) != 11:
                status_label.configure(text="LPN must be exactly 11 alphanumeric characters")
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

        # Validate LPN: must be exactly 11 alphanumeric characters
        if not lpn.isalnum() or len(lpn) != 11:
            self._show_user_status("LPN must be exactly 11 alphanumeric characters", project, error=True)
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

        # Refresh inventory list (reset to page 0 to show new item)
        self.project_widgets[project]['current_page'] = 0
        self._refresh_inventory_list(project)

        # Focus back to first field
        widgets['sku_entry'].focus()

    def _show_user_status(self, message: str, project: str = "ecoflow", error: bool = False):
        """Display a status message for user panel."""
        color = "red" if error else "green"
        self.project_widgets[project]['status_label'].configure(text=message, text_color=color)
        if error:
            self._play_error_sound()

    def _on_halo_serial_keyrelease(self, event, project: str = "halo"):
        """Handle serial number lookup for Halo when exactly 12 characters entered."""
        serial = self.project_widgets[project]['serial_entry'].get().strip()

        # Only lookup if exactly 12 characters
        if len(serial) == 12:
            po_number = lookup_halo_po_number(serial, blocking=False)
            if po_number:
                self._show_user_status(f"PO #: {po_number}", project, error=False)
            elif po_number == '':
                self._show_user_status("Serial not found in lookup", project, error=True)
        else:
            # Clear status if not 12 chars
            self.project_widgets[project]['status_label'].configure(text="")

    def _on_halo_admin_serial_keyrelease(self, event, project: str = "halo"):
        """Handle serial number lookup for Halo in admin view when exactly 12 characters entered."""
        serial = self.admin_project_widgets[project]['serial_entry'].get().strip()

        # Only lookup if exactly 12 characters
        if len(serial) == 12:
            po_number = lookup_halo_po_number(serial, blocking=False)
            if po_number:
                self._show_admin_status(f"PO #: {po_number}", project, error=False)
            elif po_number == '':
                self._show_admin_status("Serial not found in lookup", project, error=True)
        else:
            # Clear status if not 12 chars
            self.admin_project_widgets[project]['status_label'].configure(text="")

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

        self._show_user_status("Exporting...", project, error=False)

        # Run export in background thread to avoid freezing UI
        def do_export():
            try:
                moved_items = move_inventory_to_imported(project)
                if export_inventory_to_csv(moved_items, filepath, project):
                    email_msg = ""
                    email_settings = get_email_settings()
                    if email_settings["enabled"] and email_settings["sender_email"] and email_settings["recipients"]:
                        success, msg = send_csv_email(
                            smtp_server=email_settings["smtp_server"],
                            smtp_port=email_settings["smtp_port"],
                            sender_email=email_settings["sender_email"],
                            sender_password=email_settings["sender_password"],
                            recipients=email_settings["recipients"],
                            csv_filepath=filepath,
                            project=project,
                            item_count=len(moved_items)
                        )
                        if success:
                            email_msg = f"Exported {len(moved_items)} items and emailed"
                        else:
                            email_msg = f"Exported but email failed: {msg}"
                    else:
                        email_msg = f"Exported {len(moved_items)} items and archived"
                    self.after(0, lambda: self._show_user_status(email_msg, project, error=False))
                    self.after(0, lambda: self._reset_and_refresh_inventory(project))
                    self.after(0, self._play_success_sound)
                else:
                    self.after(0, lambda: self._show_user_status("Failed to export CSV", project, error=True))
            except Exception as e:
                self.after(0, lambda: self._show_user_status(f"Export failed: {str(e)}", project, error=True))

        threading.Thread(target=do_export, daemon=True).start()

    def _create_admin_panel(self, parent):
        """Create the admin panel with tabbed interface for Users, SKUs, and Inventory."""
        # Create tabview
        tabview = ctk.CTkTabview(parent)
        tabview.pack(expand=True, fill="both", padx=10, pady=10)

        # Add tabs
        tabview.add("Users")
        tabview.add("Approved SKUs")
        tabview.add("Inventory")
        tabview.add("Email Settings")

        # Create content for each tab
        self._create_users_tab(tabview.tab("Users"))
        self._create_skus_tab(tabview.tab("Approved SKUs"))
        self._create_inventory_tab(tabview.tab("Inventory"))
        self._create_email_settings_tab(tabview.tab("Email Settings"))

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

        # Defer user list loading until after GUI is displayed
        self.after(100, self._refresh_user_list)

    def _create_skus_tab(self, parent):
        """Create the SKU management tab with project sub-tabs."""
        # Create project tabview (EcoFlow / Halo)
        project_tabview = ctk.CTkTabview(parent)
        project_tabview.pack(expand=True, fill="both", padx=5, pady=5)

        project_tabview.add("EcoFlow")
        project_tabview.add("Halo")
        project_tabview.add("AMS INE")

        # Create SKU management for each project
        self._create_project_skus_content(project_tabview.tab("EcoFlow"), "ecoflow")
        self._create_project_skus_content(project_tabview.tab("Halo"), "halo")
        self._create_project_skus_content(project_tabview.tab("AMS INE"), "ams_ine")

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
            text="Total SKUs: Loading...",
            font=ctk.CTkFont(size=14)
        )
        sku_count_label.pack(pady=(0, 10))
        self.admin_sku_widgets[project]['sku_count_label'] = sku_count_label

        # Defer SKU count loading until after GUI is displayed
        self.after(200, lambda p=project: self._update_sku_count_label(p))

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

        # Defer SKU list loading until after GUI is displayed
        self.after(150, lambda p=project: self._refresh_sku_list(project=p))

    def _create_inventory_tab(self, parent):
        """Create the inventory viewing tab for admin with project tabs."""
        # Create project tabview (EcoFlow / Halo)
        project_tabview = ctk.CTkTabview(parent)
        project_tabview.pack(expand=True, fill="both", padx=5, pady=5)

        project_tabview.add("EcoFlow")
        project_tabview.add("Halo")
        project_tabview.add("AMS INE")

        # Create inventory views for each project
        self._create_admin_project_inventory(project_tabview.tab("EcoFlow"), "ecoflow")
        self._create_admin_project_inventory(project_tabview.tab("Halo"), "halo")
        self._create_admin_project_inventory(project_tabview.tab("AMS INE"), "ams_ine")

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

        # Add serial number lookup for Halo in admin view
        if project == "halo":
            admin_serial_entry.bind("<KeyRelease>", lambda e, p=project: self._on_halo_admin_serial_keyrelease(e, p))

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

        # Location (dropdown for halo/ecoflow, text entry for ams_ine)
        location_frame = ctk.CTkFrame(fields_frame, fg_color="transparent")
        location_frame.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(location_frame, text="Location", font=ctk.CTkFont(size=13)).pack(anchor="w")
        if project == "ams_ine":
            # Text entry for AMS INE
            admin_location_entry = ctk.CTkEntry(location_frame, width=120, font=ctk.CTkFont(size=13))
            admin_location_entry.pack()
            self.admin_project_widgets[project]['location_dropdown'] = admin_location_entry
        else:
            # Dropdown for other projects
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
            repair_options = ["Temporary Storage", "To be repaired", "To be refurbished", "To be Scrapped", "Storage only", "Good Spare Parts", "Refurbished", "Repaired", "Defective Products"]
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
        header_frame.pack(fill="x", padx=10, pady=(10, 5))

        title = ctk.CTkLabel(
            header_frame,
            text="Active Inventory Items",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title.pack(side="left")

        # Quantity counter
        admin_active_qty_label = ctk.CTkLabel(
            header_frame,
            text="(0 items)",
            font=ctk.CTkFont(size=14),
            text_color="gray70"
        )
        admin_active_qty_label.pack(side="left", padx=(10, 0))
        self.admin_project_widgets[project]['active_inventory_qty_label'] = admin_active_qty_label

        refresh_btn = ctk.CTkButton(
            header_frame,
            text="Refresh",
            width=100,
            font=ctk.CTkFont(size=14),
            fg_color="#17a2b8",
            hover_color="#138496",
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

        # Pagination footer
        page_frame = ctk.CTkFrame(parent, fg_color="transparent")
        page_frame.pack(fill="x", padx=10, pady=(0, 5))

        prev_btn = ctk.CTkButton(
            page_frame, text="< Previous", width=100, font=ctk.CTkFont(size=13),
            fg_color="#6c757d", hover_color="#5a6268", state="disabled",
            command=lambda p=project: self._go_page(p, "admin_active", -1)
        )
        prev_btn.pack(side="left")

        page_label = ctk.CTkLabel(page_frame, text="", font=ctk.CTkFont(size=13))
        page_label.pack(side="left", expand=True)

        next_btn = ctk.CTkButton(
            page_frame, text="Next >", width=100, font=ctk.CTkFont(size=13),
            fg_color="#6c757d", hover_color="#5a6268", state="disabled",
            command=lambda p=project: self._go_page(p, "admin_active", 1)
        )
        next_btn.pack(side="right")

        self.admin_project_widgets[project]['active_page'] = 0
        self.admin_project_widgets[project]['active_prev_btn'] = prev_btn
        self.admin_project_widgets[project]['active_next_btn'] = next_btn
        self.admin_project_widgets[project]['active_page_label'] = page_label

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

        # Quantity counter
        admin_archived_qty_label = ctk.CTkLabel(
            header_frame,
            text="(0 items)",
            font=ctk.CTkFont(size=14),
            text_color="gray70"
        )
        admin_archived_qty_label.pack(side="left", padx=(10, 0))
        self.admin_project_widgets[project]['archived_qty_label'] = admin_archived_qty_label

        refresh_btn = ctk.CTkButton(
            header_frame,
            text="Refresh",
            width=100,
            font=ctk.CTkFont(size=14),
            fg_color="#17a2b8",
            hover_color="#138496",
            command=lambda p=project: self._refresh_admin_archived_inventory(p)
        )
        refresh_btn.pack(side="right", padx=(5, 0))

        # Export All button
        export_all_btn = ctk.CTkButton(
            header_frame,
            text="Export All to CSV",
            width=140,
            font=ctk.CTkFont(size=14),
            fg_color="#6c757d",
            hover_color="#5a6268",
            command=lambda p=project: self._export_all_archived_inventory(p)
        )
        export_all_btn.pack(side="right")

        # Scrollable frame for inventory list
        admin_archived_inventory_frame = ctk.CTkScrollableFrame(parent)
        admin_archived_inventory_frame.pack(expand=True, fill="both", padx=10, pady=(0, 10))
        self.admin_project_widgets[project]['archived_inventory_frame'] = admin_archived_inventory_frame

        # Configure columns (EcoFlow has extra Order # column)
        num_columns = 8 if project != "halo" else 7
        for i in range(num_columns):
            admin_archived_inventory_frame.grid_columnconfigure(i, weight=1)

        # Pagination footer
        page_frame = ctk.CTkFrame(parent, fg_color="transparent")
        page_frame.pack(fill="x", padx=10, pady=(0, 5))

        prev_btn = ctk.CTkButton(
            page_frame, text="< Previous", width=100, font=ctk.CTkFont(size=13),
            fg_color="#6c757d", hover_color="#5a6268", state="disabled",
            command=lambda p=project: self._go_page(p, "admin_archived", -1)
        )
        prev_btn.pack(side="left")

        page_label = ctk.CTkLabel(page_frame, text="", font=ctk.CTkFont(size=13))
        page_label.pack(side="left", expand=True)

        next_btn = ctk.CTkButton(
            page_frame, text="Next >", width=100, font=ctk.CTkFont(size=13),
            fg_color="#6c757d", hover_color="#5a6268", state="disabled",
            command=lambda p=project: self._go_page(p, "admin_archived", 1)
        )
        next_btn.pack(side="right")

        self.admin_project_widgets[project]['archived_page'] = 0
        self.admin_project_widgets[project]['archived_prev_btn'] = prev_btn
        self.admin_project_widgets[project]['archived_next_btn'] = next_btn
        self.admin_project_widgets[project]['archived_page_label'] = page_label

    def _create_email_settings_tab(self, parent):
        """Create the email settings configuration tab."""
        # Main container
        container = ctk.CTkFrame(parent)
        container.pack(expand=True, fill="both", padx=20, pady=20)

        # Title
        title = ctk.CTkLabel(
            container,
            text="Email Settings",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title.pack(pady=(0, 20))

        # Load current settings
        settings = get_email_settings()

        # Settings form
        form_frame = ctk.CTkFrame(container)
        form_frame.pack(fill="x", padx=20, pady=10)

        # Enable/Disable toggle
        enable_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        enable_frame.pack(fill="x", pady=10, padx=15)
        ctk.CTkLabel(enable_frame, text="Enable Email on Export:", font=ctk.CTkFont(size=14)).pack(side="left")
        self.email_enabled_var = ctk.BooleanVar(value=settings["enabled"])
        email_toggle = ctk.CTkSwitch(enable_frame, text="", variable=self.email_enabled_var)
        email_toggle.pack(side="left", padx=10)

        # SMTP Server
        server_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        server_frame.pack(fill="x", pady=5, padx=15)
        ctk.CTkLabel(server_frame, text="SMTP Server:", font=ctk.CTkFont(size=14), width=120, anchor="w").pack(side="left")
        self.smtp_server_entry = ctk.CTkEntry(server_frame, width=300, font=ctk.CTkFont(size=14))
        self.smtp_server_entry.insert(0, settings["smtp_server"])
        self.smtp_server_entry.pack(side="left", padx=10)

        # SMTP Port
        port_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        port_frame.pack(fill="x", pady=5, padx=15)
        ctk.CTkLabel(port_frame, text="SMTP Port:", font=ctk.CTkFont(size=14), width=120, anchor="w").pack(side="left")
        self.smtp_port_entry = ctk.CTkEntry(port_frame, width=100, font=ctk.CTkFont(size=14))
        self.smtp_port_entry.insert(0, str(settings["smtp_port"]))
        self.smtp_port_entry.pack(side="left", padx=10)

        # Sender Email
        sender_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        sender_frame.pack(fill="x", pady=5, padx=15)
        ctk.CTkLabel(sender_frame, text="Sender Email:", font=ctk.CTkFont(size=14), width=120, anchor="w").pack(side="left")
        self.sender_email_entry = ctk.CTkEntry(sender_frame, width=300, font=ctk.CTkFont(size=14))
        self.sender_email_entry.insert(0, settings["sender_email"])
        self.sender_email_entry.pack(side="left", padx=10)

        # Sender Password
        password_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        password_frame.pack(fill="x", pady=5, padx=15)
        ctk.CTkLabel(password_frame, text="Password:", font=ctk.CTkFont(size=14), width=120, anchor="w").pack(side="left")
        self.sender_password_entry = ctk.CTkEntry(password_frame, width=300, font=ctk.CTkFont(size=14), show="*")
        self.sender_password_entry.insert(0, settings["sender_password"])
        self.sender_password_entry.pack(side="left", padx=10)

        # Recipients
        recipients_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        recipients_frame.pack(fill="x", pady=5, padx=15)
        ctk.CTkLabel(recipients_frame, text="Recipients:", font=ctk.CTkFont(size=14), width=120, anchor="w").pack(side="left")
        self.recipients_entry = ctk.CTkEntry(recipients_frame, width=400, font=ctk.CTkFont(size=14))
        self.recipients_entry.insert(0, settings["recipients"])
        self.recipients_entry.pack(side="left", padx=10)

        # Help text
        help_label = ctk.CTkLabel(
            form_frame,
            text="Separate multiple recipients with commas",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        help_label.pack(pady=(0, 10), padx=15, anchor="w")

        # Buttons frame
        buttons_frame = ctk.CTkFrame(container, fg_color="transparent")
        buttons_frame.pack(fill="x", pady=20, padx=20)

        # Test Connection button
        test_btn = ctk.CTkButton(
            buttons_frame,
            text="Test Connection",
            width=150,
            font=ctk.CTkFont(size=14),
            command=self._test_email_connection
        )
        test_btn.pack(side="left", padx=(0, 10))

        # Save button
        save_btn = ctk.CTkButton(
            buttons_frame,
            text="Save Settings",
            width=150,
            font=ctk.CTkFont(size=14),
            fg_color="#28a745",
            hover_color="#218838",
            command=self._save_email_settings
        )
        save_btn.pack(side="left")

        # Status label
        self.email_status_label = ctk.CTkLabel(
            container,
            text="",
            font=ctk.CTkFont(size=14)
        )
        self.email_status_label.pack(pady=10)

    def _test_email_connection(self):
        """Test the SMTP connection with current settings."""
        smtp_server = self.smtp_server_entry.get().strip()
        try:
            smtp_port = int(self.smtp_port_entry.get().strip())
        except ValueError:
            self.email_status_label.configure(text="Invalid port number", text_color="red")
            return

        sender_email = self.sender_email_entry.get().strip()
        sender_password = self.sender_password_entry.get()

        if not all([smtp_server, sender_email, sender_password]):
            self.email_status_label.configure(text="Please fill in all fields", text_color="red")
            return

        self.email_status_label.configure(text="Testing connection...", text_color="gray")
        self.update()

        success, message = test_email_connection(smtp_server, smtp_port, sender_email, sender_password)
        color = "green" if success else "red"
        self.email_status_label.configure(text=message, text_color=color)

    def _save_email_settings(self):
        """Save email settings to the database."""
        smtp_server = self.smtp_server_entry.get().strip()
        try:
            smtp_port = int(self.smtp_port_entry.get().strip())
        except ValueError:
            self.email_status_label.configure(text="Invalid port number", text_color="red")
            return

        sender_email = self.sender_email_entry.get().strip()
        sender_password = self.sender_password_entry.get()
        recipients = self.recipients_entry.get().strip()
        enabled = self.email_enabled_var.get()

        update_email_settings(
            smtp_server=smtp_server,
            smtp_port=smtp_port,
            sender_email=sender_email,
            sender_password=sender_password,
            recipients=recipients,
            enabled=enabled
        )
        self.email_status_label.configure(text="Settings saved", text_color="green")

    def _refresh_admin_active_inventory(self, project: str = "ecoflow"):
        """Refresh the admin active inventory list for a specific project."""
        admin_active_inventory_frame = self.admin_project_widgets[project]['active_inventory_frame']
        for widget in admin_active_inventory_frame.winfo_children():
            widget.destroy()

        # Header row
        headers = ["SKU", "Serial Number", "LPN", "PO #", "Repair State", "Entered By", "Date", "Actions"]
        for col, header in enumerate(headers):
            label = ctk.CTkLabel(
                admin_active_inventory_frame,
                text=header,
                font=ctk.CTkFont(size=14, weight="bold")
            )
            label.grid(row=0, column=col, padx=5, pady=(0, 10), sticky="w")

        # Show loading message
        loading_label = ctk.CTkLabel(admin_active_inventory_frame, text="Loading...", font=ctk.CTkFont(size=13))
        loading_label.grid(row=1, column=0, columnspan=8, padx=5, pady=10)

        # Fetch data in background thread
        page = self.admin_project_widgets[project]['active_page']
        def fetch_data():
            try:
                total_count = get_inventory_count(project)
                offset = page * self.PAGE_SIZE
                items = get_all_inventory(project, limit=self.PAGE_SIZE, offset=offset)
                for item in items:
                    if project == "halo":
                        item['_po_number'] = lookup_halo_po_number(item['serial_number'], blocking=False) or ''
                    else:
                        item['_po_number'] = item.get('order_number', '')
                self.after(0, lambda: self._populate_admin_active_inventory(project, items, total_count))
            except Exception:
                self.after(0, lambda: self._show_inventory_error(
                    self.admin_project_widgets[project]['active_inventory_frame'],
                    "Failed to load inventory: Network error"
                ))

        thread = threading.Thread(target=fetch_data, daemon=True)
        thread.start()

    def _populate_admin_active_inventory(self, project: str, items: list, total_count: int = 0):
        """Populate admin active inventory with fetched data."""
        if not self.winfo_exists():
            return
        admin_active_inventory_frame = self.admin_project_widgets[project]['active_inventory_frame']
        if not admin_active_inventory_frame.winfo_exists():
            return
        for widget in admin_active_inventory_frame.winfo_children():
            widget.destroy()

        # Header row
        headers = ["SKU", "Serial Number", "LPN", "PO #", "Repair State", "Entered By", "Date", "Actions"]
        for col, header in enumerate(headers):
            label = ctk.CTkLabel(
                admin_active_inventory_frame,
                text=header,
                font=ctk.CTkFont(size=14, weight="bold")
            )
            label.grid(row=0, column=col, padx=5, pady=(0, 10), sticky="w")

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
            ctk.CTkLabel(admin_active_inventory_frame, text=item['_po_number'], font=ctk.CTkFont(size=13)).grid(
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

        # Update quantity counter with total database count
        self.admin_project_widgets[project]['active_inventory_qty_label'].configure(text=f"({total_count} item{'s' if total_count != 1 else ''})")

        # Update pagination buttons
        page = self.admin_project_widgets[project]['active_page']
        self._update_pagination(
            self.admin_project_widgets[project], 'active_page', 'active_prev_btn', 'active_next_btn', 'active_page_label',
            page, total_count
        )

    def _refresh_admin_archived_inventory(self, project: str = "ecoflow"):
        """Refresh the admin archived inventory list for a specific project."""
        admin_archived_inventory_frame = self.admin_project_widgets[project]['archived_inventory_frame']
        for widget in admin_archived_inventory_frame.winfo_children():
            widget.destroy()

        # Header row
        headers = ["SKU", "Serial Number", "LPN", "PO #", "Repair State", "Entered By", "Created", "Archived"]
        for col, header in enumerate(headers):
            label = ctk.CTkLabel(
                admin_archived_inventory_frame,
                text=header,
                font=ctk.CTkFont(size=14, weight="bold")
            )
            label.grid(row=0, column=col, padx=5, pady=(0, 10), sticky="w")

        # Show loading message
        loading_label = ctk.CTkLabel(admin_archived_inventory_frame, text="Loading...", font=ctk.CTkFont(size=13))
        loading_label.grid(row=1, column=0, columnspan=8, padx=5, pady=10)

        # Fetch data in background thread
        page = self.admin_project_widgets[project]['archived_page']
        def fetch_data():
            try:
                total_count = get_imported_inventory_count(project)
                offset = page * self.PAGE_SIZE
                items = get_all_imported_inventory(project, limit=self.PAGE_SIZE, offset=offset)
                for item in items:
                    if project == "halo":
                        item['_po_number'] = lookup_halo_po_number(item['serial_number'], blocking=False) or ''
                    else:
                        item['_po_number'] = item.get('order_number', '')
                self.after(0, lambda: self._populate_admin_archived_inventory(project, items, total_count))
            except Exception as e:
                self.after(0, lambda: self._show_inventory_error(
                    self.admin_project_widgets[project]['archived_inventory_frame'],
                    f"Failed to load archived inventory: Network error"
                ))

        thread = threading.Thread(target=fetch_data, daemon=True)
        thread.start()

    def _populate_admin_archived_inventory(self, project: str, items: list, total_count: int = 0):
        """Populate admin archived inventory with fetched data."""
        if not self.winfo_exists():
            return
        admin_archived_inventory_frame = self.admin_project_widgets[project]['archived_inventory_frame']
        if not admin_archived_inventory_frame.winfo_exists():
            return
        for widget in admin_archived_inventory_frame.winfo_children():
            widget.destroy()

        # Update quantity counter with total database count
        qty_label = self.admin_project_widgets[project].get('archived_qty_label')
        if qty_label:
            qty_label.configure(text=f"({total_count} item{'s' if total_count != 1 else ''})")

        # Header row
        headers = ["SKU", "Serial Number", "LPN", "PO #", "Repair State", "Entered By", "Created", "Archived"]
        for col, header in enumerate(headers):
            label = ctk.CTkLabel(
                admin_archived_inventory_frame,
                text=header,
                font=ctk.CTkFont(size=14, weight="bold")
            )
            label.grid(row=0, column=col, padx=5, pady=(0, 10), sticky="w")

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
            ctk.CTkLabel(admin_archived_inventory_frame, text=item['_po_number'], font=ctk.CTkFont(size=13)).grid(
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

        # Update pagination buttons
        page = self.admin_project_widgets[project]['archived_page']
        self._update_pagination(
            self.admin_project_widgets[project], 'archived_page', 'archived_prev_btn', 'archived_next_btn', 'archived_page_label',
            page, total_count
        )

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

            # Validate LPN: must be exactly 11 alphanumeric characters
            if not lpn.isalnum() or len(lpn) != 11:
                status_label.configure(text="LPN must be exactly 11 alphanumeric characters", text_color="red")
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

        filepath = filedialog.asksaveasfilename(
            title="Save CSV Export",
            defaultextension=".csv",
            initialdir=default_dir if os.path.exists(default_dir) else None,
            initialfile=default_filename,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )

        if not filepath:
            return  # User cancelled

        self._show_admin_status("Exporting...", project, error=False)

        # Run export in background thread to avoid freezing UI
        def do_export():
            try:
                moved_items = move_inventory_to_imported(project)
                if export_inventory_to_csv(moved_items, filepath, project):
                    email_msg = ""
                    email_settings = get_email_settings()
                    if email_settings["enabled"] and email_settings["sender_email"] and email_settings["recipients"]:
                        success, msg = send_csv_email(
                            smtp_server=email_settings["smtp_server"],
                            smtp_port=email_settings["smtp_port"],
                            sender_email=email_settings["sender_email"],
                            sender_password=email_settings["sender_password"],
                            recipients=email_settings["recipients"],
                            csv_filepath=filepath,
                            project=project,
                            item_count=len(moved_items)
                        )
                        if success:
                            email_msg = "\nEmail sent successfully"
                        else:
                            email_msg = f"\nEmail failed: {msg}"

                    def show_success():
                        self.admin_project_widgets[project]['active_page'] = 0
                        self.admin_project_widgets[project]['archived_page'] = 0
                        self._refresh_admin_active_inventory(project)
                        self._refresh_admin_archived_inventory(project)
                        self._play_success_sound()
                        dialog = ctk.CTkToplevel(self)
                        dialog.title("Export Complete")
                        dialog.geometry("350x120")
                        dialog.resizable(False, False)
                        dialog.transient(self)
                        ctk.CTkLabel(dialog, text=f"Exported {len(moved_items)} items{email_msg}", font=ctk.CTkFont(size=14)).pack(pady=20)
                        ctk.CTkButton(dialog, text="OK", width=80, command=dialog.destroy).pack()
                        dialog.wait_visibility()
                        dialog.grab_set()

                    self.after(0, show_success)
                else:
                    self.after(0, lambda: self._show_admin_status("Failed to export CSV", project, error=True))
            except Exception as e:
                self.after(0, lambda: self._show_admin_status(f"Export failed: {str(e)}", project, error=True))

        threading.Thread(target=do_export, daemon=True).start()

    def _export_all_archived_inventory(self, project: str = "ecoflow"):
        """Export ALL archived inventory items from remote database to CSV."""
        from database.inventory_cache import _get_remote_imported_connection

        # Show loading dialog
        loading_dialog = ctk.CTkToplevel(self)
        loading_dialog.title("Exporting...")
        loading_dialog.geometry("300x100")
        loading_dialog.resizable(False, False)
        loading_dialog.transient(self)
        ctk.CTkLabel(loading_dialog, text="Fetching all archived items...", font=ctk.CTkFont(size=14)).pack(pady=30)
        loading_dialog.update()

        def fetch_and_export():
            try:
                # Fetch ALL items from remote database
                remote_conn = _get_remote_imported_connection(project)
                remote_cursor = remote_conn.cursor()

                remote_cursor.execute("""
                    SELECT item_sku, serial_number, lpn, location, repair_state,
                           entered_by, created_at, imported_at, order_number
                    FROM imported_inventory
                    ORDER BY imported_at DESC
                """)
                items = remote_cursor.fetchall()
                remote_conn.close()

                # Close loading dialog and show file picker on main thread
                self.after(0, lambda: self._finish_archived_export(loading_dialog, items, project))

            except Exception as e:
                self.after(0, lambda: self._show_archived_export_error(loading_dialog, str(e)))

        # Run in background thread
        import threading
        thread = threading.Thread(target=fetch_and_export, daemon=True)
        thread.start()

    def _finish_archived_export(self, loading_dialog, items, project: str):
        """Finish the archived export after fetching data."""
        loading_dialog.destroy()

        if not items:
            dialog = ctk.CTkToplevel(self)
            dialog.title("Export")
            dialog.geometry("300x100")
            dialog.resizable(False, False)
            dialog.transient(self)
            ctk.CTkLabel(dialog, text="No archived items to export", font=ctk.CTkFont(size=14)).pack(pady=20)
            ctk.CTkButton(dialog, text="OK", width=80, command=dialog.destroy).pack()
            dialog.wait_visibility()
            dialog.grab_set()
            return

        # Generate filename
        now = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        project_name = project.capitalize()
        default_filename = f"{project_name} archived inventory({now}).csv"

        # Ask user where to save
        filepath = filedialog.asksaveasfilename(
            title="Save Archived Inventory CSV",
            defaultextension=".csv",
            initialfile=default_filename,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )

        if not filepath:
            return  # User cancelled

        try:
            # Write CSV
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Header row
                if project == "halo":
                    writer.writerow(["SKU", "Serial Number", "LPN", "Repair State", "Entered By", "Created", "Archived"])
                else:
                    writer.writerow(["SKU", "Serial Number", "LPN", "Order #", "Repair State", "Entered By", "Created", "Archived"])

                # Data rows
                for item in items:
                    sku, serial, lpn, loc, state, entered, created, archived, order = item
                    if project == "halo":
                        writer.writerow([sku, serial, lpn, state, entered, created, archived])
                    else:
                        writer.writerow([sku, serial, lpn, order or '', state, entered, created, archived])

            # Show success dialog
            dialog = ctk.CTkToplevel(self)
            dialog.title("Export Complete")
            dialog.geometry("350x120")
            dialog.resizable(False, False)
            dialog.transient(self)
            ctk.CTkLabel(dialog, text=f"Exported {len(items)} archived items", font=ctk.CTkFont(size=14)).pack(pady=20)
            ctk.CTkButton(dialog, text="OK", width=80, command=dialog.destroy).pack()
            dialog.wait_visibility()
            dialog.grab_set()

        except Exception as e:
            dialog = ctk.CTkToplevel(self)
            dialog.title("Export Error")
            dialog.geometry("350x120")
            dialog.resizable(False, False)
            dialog.transient(self)
            ctk.CTkLabel(dialog, text=f"Export failed: {str(e)}", font=ctk.CTkFont(size=14)).pack(pady=20)
            ctk.CTkButton(dialog, text="OK", width=80, command=dialog.destroy).pack()
            dialog.wait_visibility()
            dialog.grab_set()

    def _show_archived_export_error(self, loading_dialog, error_msg: str):
        """Show error dialog for archived export."""
        loading_dialog.destroy()
        dialog = ctk.CTkToplevel(self)
        dialog.title("Export Error")
        dialog.geometry("350x120")
        dialog.resizable(False, False)
        dialog.transient(self)
        ctk.CTkLabel(dialog, text=f"Failed to fetch data: Network error", font=ctk.CTkFont(size=14)).pack(pady=20)
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

        # Validate LPN: must be exactly 11 alphanumeric characters
        if not lpn.isalnum() or len(lpn) != 11:
            self._show_admin_status("LPN must be exactly 11 alphanumeric characters", project, error=True)
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

        # Refresh inventory list (reset to page 0 to show new item)
        self.admin_project_widgets[project]['active_page'] = 0
        self._refresh_admin_active_inventory(project)

        # Focus back to first field
        widgets['sku_entry'].focus()

    def _show_admin_status(self, message: str, project: str = "ecoflow", error: bool = False):
        """Display a status message for admin panel."""
        color = "red" if error else "green"
        self.admin_project_widgets[project]['status_label'].configure(text=message, text_color=color)
        if error:
            self._play_error_sound()

    def _update_sku_count_label(self, project: str = "ecoflow"):
        """Update the SKU count label for a specific project (called after GUI is displayed)."""
        try:
            count = get_sku_count(project)
            self.admin_sku_widgets[project]['sku_count_label'].configure(text=f"Total SKUs: {count}")
        except Exception:
            pass  # Ignore errors - label will stay as "Loading..."

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

        # Show loading message
        loading_label = ctk.CTkLabel(sku_list_frame, text="Loading...", font=ctk.CTkFont(size=14))
        loading_label.grid(row=1, column=0, columnspan=3, padx=5, pady=10)

        # Fetch data in background thread
        def fetch_data():
            if filter_text:
                skus = search_skus(filter_text, limit=20, project=project)
            else:
                skus = get_all_skus(project)[:20]  # Limit to 20 items
            count = get_sku_count(project)
            self.after(0, lambda: self._populate_sku_list(project, skus, count))

        thread = threading.Thread(target=fetch_data, daemon=True)
        thread.start()

    def _populate_sku_list(self, project: str, skus: list, count: int):
        """Populate SKU list with fetched data."""
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
        widgets['sku_count_label'].configure(text=f"Total SKUs: {count}")

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

        # Show loading message
        loading_label = ctk.CTkLabel(self.user_list_frame, text="Loading...", font=ctk.CTkFont(size=14))
        loading_label.grid(row=1, column=0, columnspan=5, padx=5, pady=10)

        # Fetch data in background thread
        def fetch_data():
            users = get_all_users()[:20]  # Limit to 20 items
            self.after(0, lambda: self._populate_user_list(users))

        thread = threading.Thread(target=fetch_data, daemon=True)
        thread.start()

    def _populate_user_list(self, users: list):
        """Populate user list with fetched data."""
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
