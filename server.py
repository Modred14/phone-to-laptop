# server.py
#!/usr/bin/env python3
"""
Local file receiver: send files from your iPhone to this laptop over a local
network (Wi-Fi, hotspot, or USB tethering). No internet needed, no packages
to install, just Python 3.

Usage:
    python3 server.py                 # port 8000, saves to ~/Downloads
    python3 server.py 9000            # custom port
    python3 server.py 8000 /some/dir  # custom port and save folder
"""
import functools
import os
import re
import socket
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

# Show every message immediately instead of waiting for the buffer to flush.
print = functools.partial(print, flush=True)

# Windows consoles often can't print every character; never let that crash a transfer.
try:
    sys.stdout.reconfigure(errors="replace", line_buffering=True)
except Exception:
    pass

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
SAVE_DIR = os.path.abspath(
    os.path.expanduser(sys.argv[2] if len(sys.argv) > 2 else "~/Downloads")
)
CHUNK = 1024 * 1024  # 1 MB

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Send to Laptop</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 24px 16px; font-family: -apple-system, system-ui, sans-serif;
         background: #111; color: #eee; max-width: 520px; margin-inline: auto; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  p.sub { color: #999; margin: 0 0 20px; font-size: 14px; }
  label.pick { display: block; text-align: center; padding: 28px 16px; border: 2px dashed #444;
               border-radius: 14px; font-size: 17px; background: #1a1a1a; }
  input[type=file] { display: none; }
  button { width: 100%; margin-top: 14px; padding: 16px; font-size: 17px; font-weight: 600;
           border: 0; border-radius: 12px; background: #2f7df6; color: #fff; }
  button:disabled { background: #333; color: #777; }
  .file { margin-top: 12px; background: #1a1a1a; border-radius: 10px; padding: 10px 12px; font-size: 14px; }
  .file .row { display: flex; justify-content: space-between; gap: 8px; }
  .file .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bar { height: 6px; background: #333; border-radius: 3px; margin-top: 8px; overflow: hidden; }
  .bar > div { height: 100%; width: 0; background: #2f7df6; transition: width .1s; }
  .done .bar > div { background: #34c759; }
  .err .bar > div { background: #ff453a; }
  .meta { color: #999; font-size: 12px; margin-top: 4px; }
</style>
</head>
<body>
  <h1>Send to Laptop</h1>
  <p class="sub">Files go straight to the laptop over your local connection.</p>

  <label class="pick" id="pick">
    Tap to choose files
    <input type="file" id="files" multiple>
  </label>
  <button id="send" disabled>Send</button>
  <div id="list"></div>

<script>
const input = document.getElementById('files');
const send = document.getElementById('send');
const list = document.getElementById('list');
const pick = document.getElementById('pick');
let queue = [];

const fmt = n => n > 1e9 ? (n/1e9).toFixed(2)+' GB' : n > 1e6 ? (n/1e6).toFixed(1)+' MB' : (n/1e3).toFixed(0)+' KB';

input.onchange = () => {
  queue = [...input.files];
  list.innerHTML = '';
  queue.forEach((f, i) => {
    const d = document.createElement('div');
    d.className = 'file'; d.id = 'f' + i;
    d.innerHTML = '<div class="row"><span class="name"></span><span>' + fmt(f.size) + '</span></div>' +
                  '<div class="bar"><div></div></div><div class="meta">Ready</div>';
    d.querySelector('.name').textContent = f.name;
    list.appendChild(d);
  });
  send.disabled = queue.length === 0;
  pick.firstChild.textContent = queue.length ? queue.length + ' file(s) selected. Tap to change' : 'Tap to choose files';
};

function upload(file, i) {
  return new Promise(resolve => {
    const el = document.getElementById('f' + i);
    const bar = el.querySelector('.bar > div');
    const meta = el.querySelector('.meta');
    const t0 = Date.now();
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/upload?name=' + encodeURIComponent(file.name));
    xhr.upload.onprogress = e => {
      if (!e.lengthComputable) return;
      bar.style.width = (e.loaded / e.total * 100) + '%';
      const speed = e.loaded / ((Date.now() - t0) / 1000 || 1);
      meta.textContent = Math.round(e.loaded / e.total * 100) + '%  ·  ' + fmt(speed) + '/s';
    };
    xhr.onload = () => {
      if (xhr.status === 200) { el.classList.add('done'); bar.style.width = '100%'; meta.textContent = 'Sent ✓'; }
      else { el.classList.add('err'); meta.textContent = 'Failed (' + xhr.status + ')'; }
      resolve();
    };
    xhr.onerror = () => { el.classList.add('err'); meta.textContent = 'Connection lost'; resolve(); };
    xhr.send(file);
  });
}

send.onclick = async () => {
  send.disabled = true;
  for (let i = 0; i < queue.length; i++) await upload(queue[i], i);
  send.textContent = 'Send more';
  input.value = ''; queue = [];
};
</script>
</body>
</html>
"""


def safe_name(raw: str) -> str:
    name = os.path.basename(unquote(raw).replace("\\", "/")) or "file"
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name).strip(". ") or "file"
    return name[:200]


def unique_path(name: str) -> str:
    base, ext = os.path.splitext(name)
    path = os.path.join(SAVE_DIR, name)
    n = 1
    while os.path.exists(path):
        path = os.path.join(SAVE_DIR, f"{base} ({n}){ext}")
        n += 1
    return path


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass  # keep the terminal clean; we print our own lines

    def _reply(self, code, body=b"", ctype="text/plain; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlparse(self.path).path in ("/", "/index.html"):
            self._reply(200, PAGE.encode(), "text/html; charset=utf-8")
        else:
            self._reply(404, b"Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/upload":
            return self._reply(404, b"Not found")

        name = safe_name(parse_qs(parsed.query).get("name", ["file"])[0])
        try:
            remaining = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self._reply(400, b"Bad length")

        dest = unique_path(name)
        part = dest + ".part"
        t0 = time.time()
        total = remaining
        print(f"  [RECEIVING] {name}  {total/1e6:.1f} MB")
        try:
            with open(part, "wb") as f:
                while remaining > 0:
                    chunk = self.rfile.read(min(CHUNK, remaining))
                    if not chunk:
                        raise ConnectionError("client disconnected")
                    f.write(chunk)
                    remaining -= len(chunk)
            os.replace(part, dest)
        except Exception as e:
            try:
                os.remove(part)
            except OSError:
                pass
            print(f"  [FAILED] {name}: {e}")
            self.close_connection = True
            return

        secs = max(time.time() - t0, 0.001)
        self._reply(200, b"ok")
        print(f"  [OK] {os.path.basename(dest)}  {total/1e6:.1f} MB  ({total/1e6/secs:.1f} MB/s)")


def local_ips():
    ips = []
    # Trick: no packets are sent, it just asks the OS which interface would be used.
    for target in ("10.255.255.255", "172.20.10.1", "192.168.255.255"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((target, 1))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
        except OSError:
            pass
    return ips


def main():
    os.makedirs(SAVE_DIR, exist_ok=True)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    ips = local_ips()

    print("\n  Local file receiver is running")
    print(f"  Saving to: {SAVE_DIR}\n")
    if ips:
        print("  On your iPhone, open Safari and go to:")
        for ip in ips:
            print(f"    http://{ip}:{PORT}")
    else:
        print("  Couldn't detect an IP. Connect both devices to the same network,")
        print(f"  find the laptop's IP address, and open http://<that-ip>:{PORT}")
    print("\n  Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")


if __name__ == "__main__":
    main()