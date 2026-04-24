# RE-SPOOL Studio: Online Distribution & Auto-Update Plan

## 1. High-Level Goal
Transform the current Python script into a professional Windows Application (.exe) that can be downloaded from the internet, installed via a standard wizard, and automatically notify users when a new version is available.

---

## 2. The Auto-Update System
We will implement a "Phone Home" mechanism inside the app.

### Components:
1.  **Version Constant:** Hardcode `APP_VERSION = "1.0.0"` in `re_spool_app.py`.
2.  **Remote Manifest:** Host a small file (e.g., `version.json`) on GitHub or a web server.
    ```json
    {
      "version": "1.1.0",
      "url": "https://github.com/user/repo/releases/latest/download/RE-SPOOL_Setup.exe",
      "notes": "Added album cover support and fixed deletion bugs."
    }
    ```
3.  **Startup Check:** Every time the app opens, it fetches this JSON.
4.  **Notification:** If the remote version is higher, a Flet `Banner` or `AlertDialog` appears:
    > "Update Available! Version 1.1.0 is now ready. [Download Now] [Later]"

---

## 3. Packaging for Distribution (PyInstaller)
Users should not need to install Python or libraries. We will bundle everything.

### Steps:
1.  **FFmpeg Inclusion:** Include a `bin` folder containing only `ffmpeg.exe` and `ffplay.exe`.
2.  **The Bundle Command:**
    Use `flet pack` to create a standalone folder containing a single `RE-SPOOL Studio.exe`.
    ```bash
    flet pack re_spool_app.py --name "RE-SPOOL Studio" --add-data "bin;ffmpeg/bin"
    ```

---

## 4. The Installer (Inno Setup)
To provide a professional experience, we use **Inno Setup** to create `RE-SPOOL_Setup.exe`.

### Features of the Installer:
*   **Wizard UI:** Standard "Next > Next > Install" experience.
*   **Desktop Shortcut:** Creates the "RE-SPOOL Studio" shortcut on the user's desktop.
*   **Start Menu:** Adds the app to the Windows Start Menu.
*   **Clean Uninstall:** Adds an entry in Windows "Add/Remove Programs."

---

## 5. Online Hosting
*   **GitHub Releases (Recommended):** Free, supports large files, and provides a stable URL for the update checker.
*   **Landing Page:** A simple site or GitHub Readme where users can click a "Download for Windows" button.

---

## 6. Implementation Roadmap
1.  **Add `check_for_updates` logic** to the Python code (needs a URL to check).
2.  **Organize FFmpeg binaries** into the project folder.
3.  **Run the Build Script** to generate the raw executable folder.
4.  **Compile the Setup Wizard** using Inno Setup.
5.  **Upload to GitHub** and share the link.
