# Manual release checks

Run on clean **Ubuntu 22.04** and **Ubuntu 24.04** desktop VMs (GNOME, Wayland and an
X11 session) before tagging a release. CI already builds every package, lints the .deb,
and runs `pdr-sign --self-test` inside each on both versions; this list covers what
needs a person.

## For each package (snap, .deb, AppImage)

Install one at a time (remove the previous one first; they share the app ID).

| Package | Install | Remove |
|---|---|---|
| Snap | `sudo snap install --dangerous pdr-sign_*.snap` | `sudo snap remove pdr-sign` |
| .deb | `sudo apt install ./pdr-sign_*_amd64.deb` | `sudo apt remove pdr-sign` |
| AppImage | `chmod +x PDR-sign-*.AppImage`; integrate with your AppImage tool or add a desktop entry | remove the file (and any entry) |

1. [ ] **Self-test:** `pdr-sign --self-test ~/pdr-selftest --show-in-folder` (AppImage:
       run the file with the same arguments) — all checks ok; the file manager opens
       with the second signed copy selected (snap: the folder opens).
2. [ ] **App menu:** "PDR Sign" with the blue icon; it
       launches; the dock shows the same icon (no generic one).
3. [ ] **No warning:** run `pdr-sign` from a terminal — no "Could not register app ID".
4. [ ] **Open With:** right-click a PDF in Files → Open With → PDR opens it. With PDR
       already running, a second PDF opens as a new tab in the same window.
5. [ ] **File dialogs** (Open, Save As, Save signed copy into a read-only folder) are
       the desktop's own dialogs (portal).
6. [ ] **Folders:** open and save a PDF in Home; snap only — on a USB stick
       (`snap connect pdr-sign:removable-media` if it isn't connected).
7. [ ] **Print:** Ctrl+P to a real printer and to "Print to File"; check page range,
       Fit to page / Actual size, and a landscape page.
8. [ ] **Fill & Sign:** fill fields of every kind, add text, check, line, date, a drawn
       signature, initials, a turned + faded stamp → **Save** → close → reopen: values
       kept; text, check, line still editable.
9. [ ] **Save signed copy:** new file "… - signed with PDR-sign.pdf" next to the
       original; a second one gets " (2)"; toast → Open and Show in folder work; the
       original tab still shows unsaved changes.
10. [ ] **Firefox:** open the saved file and the signed copy in Firefox — every value,
        signature and stamp shows; the signed copy has no editable fields.
11. [ ] **Themes:** switch the desktop between light and dark — PDR follows; Settings →
        Appearance overrides it.
12. [ ] **HiDPI:** at 200 % scaling pages and icons are sharp.

## Snap only

- [ ] `snap connections pdr-sign` shows home, removable-media, cups, desktop, wayland,
      x11, opengl, network connected (removable-media may need a manual connect).
- [ ] `sudo snap connect pdr-sign:cups-control` (until the store grants auto-connect),
      then printing lists the system printers.
- [ ] Orca reads buttons and fields (Super+Alt+S toggles the screen reader).
