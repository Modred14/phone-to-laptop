<!-- README.md -->
# OfflineDrop

Send photos, videos and files from your phone to your computer over your own
Wi-Fi or hotspot. **No internet, no cables, no accounts, no cloud.** Free and open source.

## How to use it (no coding needed)

1. Go to the **Releases** page of this project and download the file for your computer:
   - **Windows:** `OfflineDrop-Windows.exe`
   - **Mac:** `OfflineDrop-Mac.zip` (unzip it first)
2. Connect your phone and computer to the **same Wi-Fi**, or turn on your phone's **Personal Hotspot** and connect the computer to it. Internet is not required.
3. Open the app. A black window appears and shows an address like `http://192.168.1.23:8000`.
4. On your phone, open the browser and type that address.
5. Tap **Choose files**, then **Send**.

Received files are saved in your **Downloads** folder.

To stop, close the black window (or press Ctrl+C).

## If you see a warning

The app is free and not signed with a paid certificate, so your computer may warn you.

- **Windows:** "Windows protected your PC" -> click **More info** -> **Run anyway**. When asked about network access, click **Allow**. Without this the phone cannot connect.
- **Mac:** right-click the app -> **Open** -> **Open**. If it still won't open, go to System Settings -> Privacy & Security -> **Open Anyway**. If it opens as a file, open Terminal, then drag the app into it and press Enter.

## Safety

Anyone on the same network can send files to your computer while the app is open. Use it on your home Wi-Fi or your own hotspot, not on public Wi-Fi, and close it when done.

## For developers

Needs only Python 3, no packages:

```
python3 server.py                 # port 8000, saves to ~/Downloads
python3 server.py 9000            # custom port
python3 server.py 8000 /some/dir  # custom port and folder
```

Releases are built automatically with GitHub Actions when a version tag (like `v1.0.0`) is pushed.

## License

MIT. Free to use, copy and modify.