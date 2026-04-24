import sys
from types import ModuleType

# Compatibility for Python 3.13+ (audioop was removed)
try:
    import audioop
except ImportError:
    try:
        import audioop_lts as audioop
        import sys
        sys.modules["audioop"] = audioop
    except ImportError:
        print("Error: 'audioop' module not found. Please run 'pip install audioop-lts'")

import flet as ft
import os
import json
import asyncio
import time
import threading
import uuid
import urllib.request
import webbrowser
from datetime import datetime
from re_spool_engine import Recorder, TapeProcessor

# --- Distribution Constants ---
APP_VERSION = "1.0.0"
# Pointing to your specific GitHub Raw URL
UPDATE_URL = "https://raw.githubusercontent.com/Oane-2005/Re-Spool/main/version.json"

# --- Path Logic for Distribution ---
def get_ffmpeg_path():
    # If running as a bundled executable
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
        return os.path.join(base_path, "ffmpeg", "bin")
    
    # Local development path (your machine)
    local_path = r"C:\Users\osein\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin"
    if os.path.exists(local_path):
        return local_path
    
    # Fallback to current directory
    return os.path.join(os.getcwd(), "ffmpeg", "bin")

FFMPEG_BIN = get_ffmpeg_path()
SETTINGS_FILE = "re_spool_settings.json"
PROJECTS_DIR = "projects"
PROJECTS_INDEX = "projects.json"

if not os.path.exists(PROJECTS_DIR):
    os.makedirs(PROJECTS_DIR)

class ProjectManager:
    def __init__(self):
        self.projects = []
        self.load_projects()

    def load_projects(self):
        if os.path.exists(PROJECTS_INDEX):
            try:
                with open(PROJECTS_INDEX, "r") as f:
                    self.projects = json.load(f)
            except Exception:
                self.projects = []
        else:
            self.projects = []

    def save_projects(self):
        with open(PROJECTS_INDEX, "w") as f:
            json.dump(self.projects, f, indent=4)

    def create_project(self, name, audio_segment):
        project_id = str(uuid.uuid4())
        project_path = os.path.join(PROJECTS_DIR, project_id)
        os.makedirs(project_path)

        audio_file = os.path.join(project_path, "audio.wav")
        audio_segment.export(audio_file, format="wav")

        project = {
            "id": project_id,
            "name": name,
            "audio_path": audio_file,
            "tracks": [],
            "status": "editor",
            "created_at": datetime.now().isoformat()
        }
        self.projects.append(project)
        self.save_projects()
        return project

    def update_project(self, project_id, **kwargs):
        for p in self.projects:
            if p["id"] == project_id:
                p.update(kwargs)
                break
        self.save_projects()

    def get_projects(self, status=None):
        if status:
            return [p for p in self.projects if p["status"] == status]
        return self.projects

    def delete_project(self, project_id):
        project = next((p for p in self.projects if p["id"] == project_id), None)
        if project:
            import shutil
            proj_dir = os.path.dirname(project["audio_path"])
            if os.path.exists(proj_dir):
                shutil.rmtree(proj_dir)
            self.projects.remove(project)
            self.save_projects()

class TrackCard(ft.Card):
    def __init__(self, index, track, on_change, on_delete, on_play, on_stop, on_re_id, on_play_start, on_play_end, on_export=None):
        super().__init__()
        self.index = index
        self.track = track
        self.on_change = on_change
        self.on_delete = on_delete
        self.on_play = on_play
        self.on_stop = on_stop
        self.on_re_id = on_re_id
        self.on_play_start = on_play_start
        self.on_play_end = on_play_end
        self.on_export = on_export
        
        self.artist_input = ft.TextField(value=track.get('artist', 'Unknown Artist'), label="Artist", expand=True)
        self.artist_input.on_change = self._notify_change
        self.title_input = ft.TextField(value=track.get('title', 'Unknown Title'), label="Title", expand=True)
        self.title_input.on_change = self._notify_change
        
        self.album_input = ft.TextField(value=track.get('album', ''), label="Album", expand=True)
        self.album_input.on_change = self._notify_change
        self.year_input = ft.TextField(value=track.get('year', ''), label="Year", width=100)
        self.year_input.on_change = self._notify_change
        self.genre_input = ft.TextField(value=track.get('genre', ''), label="Genre", expand=True)
        self.genre_input.on_change = self._notify_change
        self.cover_input = ft.TextField(value=track.get('cover_url', ''), label="Cover URL", expand=True)
        self.cover_input.on_change = self._notify_change

        self.status_text = ft.Text(value=track.get('status', 'Pending'), color=self.get_status_color())
        
        self.start_input = ft.TextField(value=str(track.get('start', 0)//1000), label="Start (s)", width=80)
        self.start_input.on_change = self._notify_change
        self.end_input = ft.TextField(value=str(track.get('end', 0)//1000), label="End (s)", width=80)
        self.end_input.on_change = self._notify_change

        self.cover_img = ft.Image(
            src=track.get('cover_url', ''),
            width=100,
            height=100,
            fit=ft.BoxFit.CONTAIN,
            visible=True if track.get('cover_url') else False
        )

        controls_row = ft.Row([
            ft.Text(f"#{index+1}", weight=ft.FontWeight.BOLD),
            self.start_input,
            ft.IconButton(ft.Icons.PLAY_CIRCLE_OUTLINE, icon_size=20, icon_color=ft.Colors.GREEN_200, on_click=lambda _: self.on_play_start(self.index), tooltip="Play first 5s"),
            self.end_input,
            ft.IconButton(ft.Icons.PLAY_CIRCLE_OUTLINE, icon_size=20, icon_color=ft.Colors.RED_200, on_click=lambda _: self.on_play_end(self.index), tooltip="Play last 5s"),
            ft.VerticalDivider(),
            self.status_text,
            ft.Container(expand=True),
            ft.IconButton(ft.Icons.REFRESH, icon_color=ft.Colors.AMBER_400, on_click=lambda _: self._handle_re_id(self.index), tooltip="Retry ID"),
            ft.IconButton(ft.Icons.PLAY_ARROW, icon_color=ft.Colors.GREEN_400, on_click=lambda _: self.on_play(self.index)),
            ft.IconButton(ft.Icons.STOP, icon_color=ft.Colors.GREY_400, on_click=lambda _: self.on_stop()),
        ])

        if self.on_export:
            controls_row.controls.append(ft.IconButton(ft.Icons.DOWNLOAD, icon_color=ft.Colors.BLUE_400, on_click=lambda _: self.on_export(self.index)))
        
        if self.on_delete:
            controls_row.controls.append(ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=ft.Colors.RED_400, on_click=lambda _: self.on_delete(self)))

        self.content = ft.Container(
            padding=10,
            content=ft.Row([
                self.cover_img,
                ft.Column([
                    controls_row,
                    ft.Row([self.artist_input, self.title_input]),
                    ft.Row([self.album_input, self.year_input, self.genre_input]),
                    self.cover_input
                ], expand=True)
            ], vertical_alignment=ft.CrossAxisAlignment.START)
        )

    def get_status_color(self):
        status = self.track.get('status', 'Pending')
        if status == 'Identified': return ft.Colors.GREEN
        if status == 'Failed': return ft.Colors.RED
        return ft.Colors.AMBER

    def update_track(self, track):
        self.track = track
        self.artist_input.value = track.get('artist', 'Unknown Artist')
        self.title_input.value = track.get('title', 'Unknown Title')
        self.album_input.value = track.get('album', '')
        self.year_input.value = track.get('year', '')
        self.genre_input.value = track.get('genre', '')
        self.cover_input.value = track.get('cover_url', '')
        
        self.start_input.value = str(track.get('start', 0)//1000)
        self.end_input.value = str(track.get('end', 0)//1000)
        self.status_text.value = track.get('status', 'Pending')
        self.status_text.color = self.get_status_color()
        
        if track.get('cover_url'):
            self.cover_img.src = track['cover_url']
            self.cover_img.visible = True
        else:
            self.cover_img.visible = False
            
        self.update()

    def _handle_re_id(self, idx):
        if asyncio.iscoroutinefunction(self.on_re_id):
            asyncio.create_task(self.on_re_id(idx))
        else:
            self.on_re_id(idx)

    def _notify_change(self, e):
        self.track['artist'] = self.artist_input.value
        self.track['title'] = self.title_input.value
        self.track['album'] = self.album_input.value
        self.track['year'] = self.year_input.value
        self.track['genre'] = self.genre_input.value
        self.track['cover_url'] = self.cover_input.value
        
        if self.cover_input.value:
            self.cover_img.src = self.cover_input.value
            self.cover_img.visible = True
        else:
            self.cover_img.visible = False
            
        try:
            self.track['start'] = int(self.start_input.value) * 1000
            self.track['end'] = int(self.end_input.value) * 1000
        except ValueError: pass
        
        if self.on_change:
            self.on_change()
        self.update()

class ProjectCard(ft.ExpansionTile):
    def __init__(self, project, on_update, on_move_to_vault, on_delete, ffmpeg_bin):
        self.project = project
        self.on_update = on_update
        self.on_move_to_vault = on_move_to_vault
        self.on_delete = on_delete
        self.processor = TapeProcessor(ffmpeg_bin)
        self.processor.tracks = project["tracks"]
        self.audio_loaded = False

        # Renaming field
        self.name_input = ft.TextField(
            value=project["name"], 
            label="Project Name", 
            on_change=self._handle_rename,
            text_style=ft.TextStyle(weight=ft.FontWeight.BOLD, size=18),
            expand=True
        )

        self.global_album_input = ft.TextField(
            value=project.get("album_name", project["name"]),
            label="Album Name (Bulk Edit)",
            expand=True
        )

        super().__init__(
            title=ft.Row([self.name_input], expand=True),
            subtitle=ft.Text(f"Created: {project['created_at'][:16]} | {len(project['tracks'])} tracks"),
            affinity=ft.TileAffinity.LEADING,
        )
        self.initially_expanded = False

        self.track_list = ft.ListView(spacing=5, height=400)
        self.status_text = ft.Text("Ready", size=12)
        self.progress_bar = ft.ProgressBar(value=0, visible=False)
        
        self.controls_row = ft.Row([
            ft.ElevatedButton("Split & ID", icon=ft.Icons.AUTO_AWESOME, on_click=self.run_analysis),
            self.global_album_input,
            ft.ElevatedButton("APPLY ALBUM TO ALL", icon=ft.Icons.DONE_ALL, on_click=self._apply_global_album),
            ft.ElevatedButton("Finish & Vault", icon=ft.Icons.CHECK_CIRCLE, on_click=lambda _: self.on_move_to_vault(self.project), bgcolor=ft.Colors.GREEN_800),
            ft.IconButton(ft.Icons.DELETE_FOREVER, icon_color=ft.Colors.RED_700, on_click=lambda _: self.on_delete(self.project)),
            self.status_text,
            self.progress_bar
        ], spacing=10)

        self.controls = [
            ft.Container(
                padding=10,
                content=ft.Column([
                    self.controls_row,
                    ft.Divider(),
                    self.track_list
                ])
            )
        ]
        self._refresh_tracks()

    def _handle_rename(self, e):
        self.project["name"] = self.name_input.value
        self.on_update()

    def _apply_global_album(self, e):
        album_name = self.global_album_input.value
        if not album_name:
            return
        
        for track in self.project["tracks"]:
            track["album"] = album_name
            
        self.project["album_name"] = album_name
        self.on_update()
        self._refresh_tracks()
        self.update()

    def _refresh_tracks(self):
        self.track_list.controls.clear()
        for i, track in enumerate(self.project["tracks"]):
            self.track_list.controls.append(
                TrackCard(i, track, self.on_update, self._delete_track, 
                          self._play_track, self._stop_track, self.re_identify_track,
                          self.processor.play_track_start, self.processor.play_track_end)
            )

    async def re_identify_track(self, idx):
        if not self.audio_loaded:
            self.processor.load_audio(self.project["audio_path"])
            self.audio_loaded = True
        
        self.status_text.value = f"Re-identifying track {idx+1}..."
        self.update()
        
        updated_track = await self.processor.identify_track(idx)
        if updated_track:
            # Update the specific card in the list
            self.track_list.controls[idx].update_track(updated_track)
            self.on_update()
            self.status_text.value = "Track re-identified."
        else:
            self.status_text.value = "Identification failed."
        self.update()

    def _delete_track(self, card):
        self.project["tracks"].remove(card.track)
        self.on_update()
        self._refresh_tracks()
        self.update()

    def _play_track(self, idx):
        if not self.audio_loaded:
            self.processor.load_audio(self.project["audio_path"])
            self.audio_loaded = True
        self.processor.play_track(idx)

    def _stop_track(self):
        self.processor.stop_playback()

    async def run_analysis(self, e):
        self.progress_bar.visible = True
        self.progress_bar.value = None
        self.status_text.value = "Loading audio..."
        self.update()

        try:
            if not self.audio_loaded:
                self.processor.load_audio(self.project["audio_path"])
                self.audio_loaded = True
            
            self.status_text.value = "Detecting tracks..."
            self.update()
            
            tracks = await self.processor.detect_tracks(-35)
            self.project["tracks"] = tracks
            self._refresh_tracks()
            self.on_update()
            
            for i, card in enumerate(self.track_list.controls):
                self.status_text.value = f"Identifying {i+1}/{len(tracks)}..."
                self.progress_bar.value = (i+1)/len(tracks)
                self.update()
                updated_track = await self.processor.identify_track(i)
                card.update_track(updated_track)
                self.on_update()
            
            self.status_text.value = "Analysis complete."
        except Exception as ex:
            self.status_text.value = f"Error: {ex}"
        finally:
            self.progress_bar.visible = False
            self.update()

async def check_for_updates(page: ft.Page):
    def show_update_banner(data):
        def close_banner(e):
            page.banner.open = False
            page.update()

        def download_update(e):
            webbrowser.open(data.get("url"))
            page.banner.open = False
            page.update()

        page.banner = ft.Banner(
            bgcolor=ft.Colors.AMBER_100,
            leading=ft.Icon(ft.Icons.UPGRADE, color=ft.Colors.AMBER, size=40),
            content=ft.Text(
                f"Update Available! Version {data.get('version')} is now ready. {data.get('notes', '')}",
                color=ft.Colors.BLACK
            ),
            actions=[
                ft.TextButton("Download Now", on_click=download_update),
                ft.TextButton("Later", on_click=close_banner),
            ],
        )
        page.banner.open = True
        page.update()

    try:
        # Run in executor to avoid blocking Flet UI
        loop = asyncio.get_running_loop()
        def fetch():
            with urllib.request.urlopen(UPDATE_URL, timeout=5) as response:
                return json.loads(response.read().decode())
        
        data = await loop.run_in_executor(None, fetch)
        remote_version = data.get("version")
        
        # Simple version comparison (e.g. "1.1.0" > "1.0.0")
        if remote_version and remote_version > APP_VERSION:
            show_update_banner(data)
    except Exception as e:
        print(f"Update check failed: {e}")

async def main(page: ft.Page):
    page.title = "RE-SPOOL Studio"
    page.theme_mode = ft.ThemeMode.DARK
    page.window_width = 1100
    page.window_height = 900
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO

    # --- State ---
    recorder = Recorder()
    pm = ProjectManager()
    settings = {"storage_root": "", "last_device": None}
    recorded_audio = None
    
    # --- Load Settings ---
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                settings.update(json.load(f))
        except: pass

    def save_settings():
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f)

    # --- UI Components ---
    device_dropdown = ft.Dropdown(label="Audio Interface", expand=True)
    devices = recorder.get_devices()
    for i, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            device_dropdown.options.append(ft.dropdown.Option(key=str(i), text=f"{dev['name']} ({int(dev['max_input_channels'])} in)"))
    
    if settings["last_device"]:
        device_dropdown.value = settings["last_device"]

    timer_text = ft.Text("00:00:00", size=80, weight=ft.FontWeight.BOLD, font_family="Courier New")
    level_meter = ft.ProgressBar(width=600, height=20, value=0, color=ft.Colors.ORANGE)
    
    wave_bars = []
    for _ in range(20):
        wave_bars.append(ft.Container(width=10, height=5, bgcolor=ft.Colors.ORANGE_300, border_radius=5, animate=ft.Animation(100, "decelerate")))
    waveform_row = ft.Row(wave_bars, alignment=ft.MainAxisAlignment.CENTER, height=100)

    auto_stop_input = ft.TextField(label="Auto-Stop (Minutes)", value="45", width=150)
    status_msg = ft.Text("Ready to spool.")
    
    reel_left = ft.Icon(ft.Icons.REPLAY_CIRCLE_FILLED, size=150, color=ft.Colors.GREY_800)
    reel_right = ft.Icon(ft.Icons.REPLAY_CIRCLE_FILLED, size=150, color=ft.Colors.GREY_800)
    
    # Editor Tab Components
    editor_list = ft.ListView(expand=True, spacing=10)
    editor_empty_msg = ft.Text("No projects in the editor. Record something first!", size=16, italic=True)

    # Vault Tab Components
    vault_dropdown = ft.Dropdown(label="Select Project", expand=True)
    
    vault_track_list = ft.ListView(spacing=10, height=500)
    vault_project_info = ft.Text("Select a project and click LOAD.")
    vault_progress = ft.ProgressBar(width=float("inf"), height=10, value=0, visible=False, color=ft.Colors.GREEN)
    vault_status = ft.Text("Ready.")
    
    storage_path_input = ft.TextField(label="Manual Storage Path", value=settings["storage_root"], expand=True)
    storage_path_text = ft.Text(settings["storage_root"] or "No storage root set.")
    vault_format_dropdown = ft.Dropdown(label="Format", options=[
        ft.dropdown.Option("mp3"), ft.dropdown.Option("wav"), ft.dropdown.Option("flac")
    ], width=120, value="mp3")

    # --- Actions ---

    async def vault_load_clicked(e):
        if vault_dropdown.value:
            load_vault_project(vault_dropdown.value)
            page.snack_bar = ft.SnackBar(ft.Text(f"Project loaded."), open=True)
            page.update()
        else:
            page.snack_bar = ft.SnackBar(ft.Text("Select a project first!"), open=True)
            page.update()

    async def vault_delete_clicked(e):
        print(f"Vault: Delete button pressed.")
        if not selected_vault_project:
            print("Vault: Delete failed - no project loaded.")
            page.snack_bar = ft.SnackBar(ft.Text("Load a project first!"), open=True)
            page.update()
            return
        
        # Capture the project info locally to avoid scope/nonlocal issues inside the nested function
        target_id = selected_vault_project["id"]
        target_name = selected_vault_project["name"]
        print(f"Vault: Preparing to delete '{target_name}' ({target_id})")

        def confirm_delete_action(ev):
            print(f"Vault: confirm_delete_action triggered for {target_id}")
            try:
                # 1. Delete from storage and index
                pm.delete_project(target_id)
                print("Vault: Project deleted from manager.")
                
                # 2. Reset global state
                nonlocal selected_vault_project
                selected_vault_project = None
                vault_dropdown.value = None
                
                # 3. Refresh UI
                refresh_vault_dropdown()
                vault_track_list.controls.clear()
                vault_project_info.value = f"Project '{target_name}' deleted."
                
                # 4. Close dialog and notify
                delete_dlg.open = False
                page.snack_bar = ft.SnackBar(ft.Text(f"Deleted '{target_name}'"), open=True)
                print("Vault: Deletion lifecycle complete.")
            except Exception as ex:
                print(f"Vault: Deletion error: {ex}")
                page.snack_bar = ft.SnackBar(ft.Text(f"Delete failed: {ex}"), open=True)
            page.update()

        def cancel_action(ev):
            print("Vault: Delete cancelled by user.")
            delete_dlg.open = False
            page.update()

        delete_dlg = ft.AlertDialog(
            title=ft.Text("Confirm Permanent Delete"),
            content=ft.Text(f"Are you sure you want to delete '{target_name}'? This cannot be undone."),
            actions=[
                ft.TextButton("Cancel", on_click=cancel_action),
                ft.ElevatedButton("Yes, Delete Everything", on_click=confirm_delete_action, bgcolor=ft.Colors.RED_800, color=ft.Colors.WHITE)
            ],
        )

        # Use overlay + open for maximum compatibility across Flet versions
        page.overlay.append(delete_dlg)
        delete_dlg.open = True
        page.update()
        print("Vault: Deletion dialog should be visible now.")

    async def save_manual_path(e):
        if storage_path_input.value:
            settings["storage_root"] = storage_path_input.value
            storage_path_text.value = storage_path_input.value
            save_settings()
            page.snack_bar = ft.SnackBar(ft.Text("Path saved successfully!"), open=True)
            page.update()

    async def update_recording_ui():
        start_time = time.time()
        pause_offset = 0
        last_pause_start = 0
        while recorder.recording:
            if not recorder.paused:
                if last_pause_start > 0:
                    pause_offset += (time.time() - last_pause_start)
                    last_pause_start = 0
                elapsed = time.time() - start_time - pause_offset
                timer_text.value = time.strftime('%H:%M:%S', time.gmtime(elapsed))
                reel_left.rotate = (reel_left.rotate or 0) + 0.1
                reel_right.rotate = (reel_right.rotate or 0) + 0.1
                if auto_stop_input.value:
                    try:
                        limit_s = float(auto_stop_input.value) * 60
                        if elapsed >= limit_s:
                            await stop_session(None)
                            break
                    except ValueError: pass
            else:
                if last_pause_start == 0:
                    last_pause_start = time.time()

            lvl = recorder.get_level()
            level_meter.value = lvl
            import random
            for bar in wave_bars:
                target_height = 5 + (lvl * 120 * random.uniform(0.6, 1.2))
                bar.height = target_height
            
            timer_text.update()
            reel_left.update()
            reel_right.update()
            waveform_row.update()
            level_meter.update()
            await asyncio.sleep(0.1)
        
        level_meter.value = 0
        for bar in wave_bars:
            bar.height = 5
        reel_left.rotate = 0
        reel_right.rotate = 0
        page.update()

    async def start_session(e):
        if not device_dropdown.value:
            page.snack_bar = ft.SnackBar(ft.Text("Error: Select a device first!"), open=True)
            page.update()
            return
        
        settings["last_device"] = device_dropdown.value
        save_settings()
        status_msg.value = "Recording..."
        recorder.start(int(device_dropdown.value))
        
        start_btn.disabled = True
        pause_btn.disabled = False
        stop_btn.disabled = False
        page.update()
        asyncio.create_task(update_recording_ui())

    async def toggle_pause(e):
        if not recorder.recording: return
        if not recorder.paused:
            recorder.pause()
            pause_btn.text = "RESUME"
            pause_btn.icon = ft.Icons.PLAY_ARROW
            status_msg.value = "Paused."
        else:
            recorder.resume()
            pause_btn.text = "PAUSE"
            pause_btn.icon = ft.Icons.PAUSE
            status_msg.value = "Recording..."
        page.update()

    async def stop_session(e):
        nonlocal recorded_audio
        status_msg.value = "Stopping and processing..."
        print("Stopping recording...")
        page.update()
        
        try:
            recorded_audio = recorder.stop()
            if recorded_audio:
                print(f"Audio captured: {len(recorded_audio)}ms")
            else:
                print("No audio captured from recorder.stop()")
        except Exception as ex:
            print(f"Recorder Error: {ex}")
            page.snack_bar = ft.SnackBar(ft.Text(f"Error stopping recorder: {ex}"), open=True)
            status_msg.value = "Error occurred."
            page.update()
            return
        
        start_btn.disabled = False
        pause_btn.disabled = True
        pause_btn.text = "PAUSE"
        stop_btn.disabled = True
        quick_save_btn.visible = True if recorded_audio else False
        timer_text.value = "00:00:00"
        status_msg.value = "Ready to spool."
        page.update()
        
        if recorded_audio:
            print("Audio exists, attempting to show naming dialog...")
            show_naming_dialog()
        else:
            print("No audio to save.")
            page.snack_bar = ft.SnackBar(ft.Text("No audio was captured. Check your device settings."), open=True)
            page.update()

    async def quick_save_action(e):
        if recorded_audio:
            name = f"QuickSave {datetime.now().strftime('%H-%M-%S')}"
            pm.create_project(name, recorded_audio)
            refresh_editor_list()
            quick_save_btn.visible = False
            page.snack_bar = ft.SnackBar(ft.Text(f"Saved as '{name}'"), open=True)
            page.update()

    def show_naming_dialog():
        print("Opening Naming Dialog...")
        name_input = ft.TextField(label="Project Name", autofocus=True, value=f"Recording {datetime.now().strftime('%H-%M-%S')}")
        
        def close_dlg(e):
            print("Naming Dialog Cancelled.")
            naming_dlg.open = False
            page.update()

        def confirm_name(e):
            try:
                if not name_input.value:
                    return
                
                print(f"Creating project: {name_input.value}...")
                pm.create_project(name_input.value, recorded_audio)
                print("Project created successfully.")
                naming_dlg.open = False
                refresh_editor_list()
                quick_save_btn.visible = False
                page.snack_bar = ft.SnackBar(ft.Text(f"Project '{name_input.value}' saved to Editor."), open=True)
                page.update()
            except Exception as ex:
                print(f"Project Creation Error: {ex}")
                page.snack_bar = ft.SnackBar(ft.Text(f"Error saving: {ex}"), open=True)
                page.update()

        naming_dlg = ft.AlertDialog(
            title=ft.Text("Save Recording"),
            content=name_input,
            actions=[
                ft.TextButton("Cancel", on_click=close_dlg),
                ft.ElevatedButton("Save to Editor", on_click=confirm_name, bgcolor=ft.Colors.GREEN_700)
            ]
        )
        
        page.dialog = naming_dlg
        naming_dlg.open = True
        print("Dialog state set to open.")
        page.update()

    def refresh_editor_list():
        projects = pm.get_projects(status="editor")
        editor_list.controls.clear()
        if not projects:
            editor_list.controls.append(editor_empty_msg)
        else:
            for p in projects:
                card = ProjectCard(p, pm.save_projects, move_to_vault, pm.delete_project, FFMPEG_BIN)
                editor_list.controls.append(card)
        page.update()

    def move_to_vault(project):
        pm.update_project(project["id"], status="vault")
        refresh_editor_list()
        refresh_vault_dropdown()
        page.snack_bar = ft.SnackBar(ft.Text(f"'{project['name']}' moved to Vault."), open=True)
        page.update()

    def refresh_vault_dropdown():
        vault_projects = pm.get_projects(status="vault")
        vault_dropdown.options = [ft.dropdown.Option(key=p["id"], text=p["name"]) for p in vault_projects]
        page.update()

    selected_vault_project = None
    vault_processor = TapeProcessor(FFMPEG_BIN)

    def load_vault_project(project_id):
        nonlocal selected_vault_project
        print(f"Vault: Loading project {project_id}")
        selected_vault_project = next((p for p in pm.projects if p["id"] == project_id), None)
        if selected_vault_project:
            print(f"Vault: Project '{selected_vault_project['name']}' has {len(selected_vault_project['tracks'])} tracks")
            vault_project_info.value = f"Selected: {selected_vault_project['name']} | {len(selected_vault_project['tracks'])} tracks"
            vault_processor.tracks = selected_vault_project["tracks"]
            vault_processor.audio = None # Reload on play/export
            refresh_vault_tracks()
        page.update()

    async def re_identify_vault_track(idx):
        if not selected_vault_project: return
        
        if not vault_processor.audio:
            vault_processor.load_audio(selected_vault_project["audio_path"])
        
        vault_status.value = f"Re-identifying track {idx+1}..."
        page.update()
        
        updated_track = await vault_processor.identify_track(idx)
        if updated_track:
            vault_track_list.controls[idx].update_track(updated_track)
            pm.save_projects()
            vault_status.value = "Track re-identified."
        else:
            vault_status.value = "Identification failed."
        page.update()

    def refresh_vault_tracks():
        vault_track_list.controls.clear()
        if selected_vault_project:
            for i, track in enumerate(selected_vault_project["tracks"]):
                print(f"Vault: Adding track card for {track.get('title')}")
                card = TrackCard(i, track, pm.save_projects, None, 
                                 play_vault_track, stop_vault_track, re_identify_vault_track,
                                 vault_processor.play_track_start, vault_processor.play_track_end,
                                 export_vault_track)
                vault_track_list.controls.append(card)
        page.update()

    def play_vault_track(idx):
        if not vault_processor.audio:
            vault_processor.load_audio(selected_vault_project["audio_path"])
        vault_processor.play_track(idx)

    def stop_vault_track():
        vault_processor.stop_playback()

    def export_vault_track(idx):
        if not selected_vault_project: return
        storage_root = settings["storage_root"].strip().strip('"').strip("'")
        if not storage_root:
            page.snack_bar = ft.SnackBar(ft.Text("Set storage root first!"), open=True)
            page.update()
            return

        if not vault_processor.audio:
            vault_processor.load_audio(selected_vault_project["audio_path"])
        
        try:
            track = selected_vault_project["tracks"][idx]
            path = vault_processor.export_single_track(storage_root, selected_vault_project["name"], idx+1, track, vault_format_dropdown.value)
            page.snack_bar = ft.SnackBar(ft.Text(f"Exported to {path}"), open=True)
        except Exception as ex:
            page.snack_bar = ft.SnackBar(ft.Text(f"Export failed: {ex}"), open=True)
        page.update()

    async def export_vault_album(e):
        if not selected_vault_project: return
        storage_root = settings["storage_root"].strip().strip('"').strip("'")
        if not storage_root:
            page.snack_bar = ft.SnackBar(ft.Text("Set storage root first!"), open=True)
            page.update()
            return

        vault_progress.visible = True
        vault_progress.value = 0
        vault_status.value = "Exporting album..."
        page.update()

        def update_progress(current, total, msg):
            vault_progress.value = current / total
            vault_status.value = msg
            page.update()

        def do_export():
            try:
                if not vault_processor.audio:
                    vault_processor.load_audio(selected_vault_project["audio_path"])
                
                # Split name into Band ID and Side if possible for the folder structure
                # Otherwise just use the name as album_name
                album_name = selected_vault_project["name"]
                
                total = len(selected_vault_project["tracks"])
                for i, track in enumerate(selected_vault_project["tracks"]):
                    update_progress(i, total, f"Exporting {i+1}/{total}...")
                    vault_processor.export_single_track(storage_root, album_name, i+1, track, vault_format_dropdown.value)
                
                update_progress(1, 1, "Album export complete!")
                page.snack_bar = ft.SnackBar(ft.Text("Album exported successfully!"), open=True)
            except Exception as ex:
                vault_status.value = f"Failed: {ex}"
            finally:
                vault_progress.visible = False
                page.update()

        threading.Thread(target=do_export, daemon=True).start()

    # --- UI Layout ---
    start_btn = ft.ElevatedButton("START", icon=ft.Icons.PLAY_ARROW, on_click=start_session, bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE, height=60, width=150)
    pause_btn = ft.ElevatedButton("PAUSE", icon=ft.Icons.PAUSE, on_click=toggle_pause, bgcolor=ft.Colors.AMBER_700, color=ft.Colors.BLACK, height=60, width=150, disabled=True)
    stop_btn = ft.ElevatedButton("FINISH", icon=ft.Icons.STOP, on_click=stop_session, bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE, height=60, width=150, disabled=True)
    quick_save_btn = ft.ElevatedButton("QUICK SAVE", icon=ft.Icons.SAVE, on_click=quick_save_action, bgcolor=ft.Colors.BLUE_800, color=ft.Colors.WHITE, height=60, width=150, visible=False)
    
    studio_tab = ft.Container(
        padding=30,
        content=ft.Column([
            ft.Row([timer_text], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row([
                ft.Container(reel_left, animate_rotation=ft.Animation(1000, "linear")),
                ft.Container(width=100),
                ft.Container(reel_right, animate_rotation=ft.Animation(1000, "linear")),
            ], alignment=ft.MainAxisAlignment.CENTER),
            waveform_row,
            ft.Row([start_btn, pause_btn, stop_btn, quick_save_btn], alignment=ft.MainAxisAlignment.CENTER),
            ft.Divider(),
            ft.Row([device_dropdown, auto_stop_input]),
            ft.Text("Signal Level:", weight=ft.FontWeight.BOLD),
            level_meter,
            status_msg
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)
    )

    editor_tab = ft.Container(
        padding=20,
        content=ft.Column([
            ft.Text("Editor", size=30, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            editor_list
        ])
    )

    vault_tab = ft.Container(
        padding=20,
        content=ft.Column([
            ft.Text("Master Vault", size=30, weight=ft.FontWeight.BOLD),
            ft.Card(
                content=ft.Container(
                    padding=20,
                    content=ft.Column([
                        ft.Text("Storage Settings", size=20, weight=ft.FontWeight.BOLD),
                        ft.Row([
                            storage_path_input,
                            ft.ElevatedButton("SAVE PATH", icon=ft.Icons.CHECK, on_click=save_manual_path)
                        ]),
                        storage_path_text,
                    ])
                )
            ),
            ft.Divider(),
            ft.Row([
                vault_dropdown, 
                ft.ElevatedButton("LOAD PROJECT", icon=ft.Icons.DOWNLOAD_DONE, on_click=vault_load_clicked, bgcolor=ft.Colors.BLUE_700),
                ft.ElevatedButton("DELETE PROJECT", icon=ft.Icons.DELETE_FOREVER, on_click=vault_delete_clicked, bgcolor=ft.Colors.RED_900),
                vault_format_dropdown, 
                ft.ElevatedButton("EXPORT FULL ALBUM", icon=ft.Icons.SAVE, on_click=export_vault_album, bgcolor=ft.Colors.GREEN_800)
            ]),
            vault_project_info,
            vault_status,
            vault_progress,
            ft.Divider(),
            vault_track_list
        ])
    )

    async def set_tab(index):
        studio_tab.visible = (index == 0)
        editor_tab.visible = (index == 1)
        vault_tab.visible = (index == 2)
        page.update()

    nav_row = ft.Row([
        ft.ElevatedButton("THE STUDIO", icon=ft.Icons.MIC, on_click=lambda _: asyncio.create_task(set_tab(0))),
        ft.ElevatedButton("EDITOR", icon=ft.Icons.EDIT, on_click=lambda _: asyncio.create_task(set_tab(1))),
        ft.ElevatedButton("MASTER VAULT", icon=ft.Icons.STORAGE, on_click=lambda _: asyncio.create_task(set_tab(2))),
    ], alignment=ft.MainAxisAlignment.CENTER)

    # Initial visibility
    studio_tab.visible = True
    editor_tab.visible = False
    vault_tab.visible = False

    page.add(
        ft.Row([
            ft.Text("RE-SPOOL", size=40, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE),
            ft.Text("v1.0", size=15)
        ], alignment=ft.MainAxisAlignment.CENTER),
        nav_row,
        ft.Divider(),
        studio_tab,
        editor_tab,
        vault_tab
    )

    # Initial Refresh
    refresh_editor_list()
    refresh_vault_dropdown()

    # Check for updates
    asyncio.create_task(check_for_updates(page))

if __name__ == "__main__":
    ft.app(target=main)
