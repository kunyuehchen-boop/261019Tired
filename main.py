
import network
import socket
import time
import json
import gc

try:
    import requests
except ImportError:
    requests = None

# ==========================================
# Wi-Fi 設定
# ==========================================
SSID = "labor"
PASSWORD = "98668800"

HOST = "esp32"
WEB_USER = "king"
WEB_PASSWORD = "king"

CURRENT_VERSION = "0.0.06"

VERSION_URL = (
    "https://kunyuehchen-boop.github.io/"
    "261019Tired/version.json"
)

FIRMWARE_PREFIX = (
    "https://kunyuehchen-boop.github.io/"
    "261019Tired/"
)

UPDATE_INTERVAL = 6 * 60 * 60 * 1000
last_update_check = time.ticks_ms()

authenticated = False
latest_version = "尚未檢查"
description = ""
update_status = "等待檢查更新"

# ==========================================
# Wi-Fi 連線
# ==========================================
wlan = network.WLAN(network.STA_IF)
wlan.active(True)

def connect_wifi():
    if wlan.isconnected():
        return True

    print("Connecting to Wi-Fi:", SSID)
    wlan.connect(SSID, PASSWORD)

    for _ in range(30):
        if wlan.isconnected():
            print("Wi-Fi connected:", wlan.ifconfig()[0])
            return True
        time.sleep(1)

    print("Wi-Fi connection failed")
    return False

# ==========================================
# 版本比較
# ==========================================
def is_newer_version(latest, current):
    try:
        a = tuple(int(x) for x in latest.strip().split("."))
        b = tuple(int(x) for x in current.strip().split("."))

        length = max(len(a), len(b))
        a += (0,) * (length - len(a))
        b += (0,) * (length - len(b))

        return a > b
    except Exception:
        return False

# ==========================================
# GitHub 版本檢查
# ==========================================
def check_github_update():
    global latest_version, description, update_status

    if not wlan.isconnected():
        update_status = "Wi-Fi 尚未連線"
        return

    if requests is None:
        update_status = "缺少 requests 套件"
        return

    response = None

    try:
        url = VERSION_URL + "?t=" + str(time.ticks_ms())
        print("[OTA] Checking:", url)

        response = requests.get(url, timeout=15)

        if response.status_code != 200:
            update_status = "HTTP 錯誤：" + str(
                response.status_code
            )
            return

        data = response.json()

        version = data.get("version")
        firmware = data.get("firmware")

        if not version or not firmware:
            update_status = "version.json 格式錯誤"
            return

        latest_version = str(version)
        description = str(data.get("description", ""))

        if not firmware.startswith(FIRMWARE_PREFIX):
            update_status = "韌體網址不符合允許的前綴"
        elif not firmware.endswith(".bin"):
            update_status = "韌體網址必須以 .bin 結尾"
        elif is_newer_version(
            latest_version, CURRENT_VERSION
        ):
            update_status = (
                "發現新版 " + latest_version +
                "；尚未執行韌體寫入"
            )
        else:
            update_status = "目前已是最新版本"

        print("[OTA] Current:", CURRENT_VERSION)
        print("[OTA] Latest:", latest_version)
        print("[OTA]", update_status)

    except Exception as e:
        update_status = "檢查失敗：" + str(e)
        print("[OTA] Error:", e)

    finally:
        if response is not None:
            response.close()
        gc.collect()

# ==========================================
# HTML 頁面
# ==========================================
LOGIN_PAGE = """<!DOCTYPE html>
<html lang="zh-Hant">
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ESP32 Login</title>
<style>
body{font-family:Arial;background:#eee;text-align:center;padding:30px 10px}
.card{background:white;padding:24px;margin:auto;max-width:380px;border-radius:12px}
input,button{box-sizing:border-box;width:100%;padding:12px;margin:8px 0}
</style>
<div class="card">
<h2>ESP32 登入</h2>
<form method="POST" action="/login">
<input name="userid" placeholder="帳號" required>
<input name="pwd" type="password" placeholder="密碼" required>
<button type="submit">登入</button>
</form>
</div>
</html>
"""

def dashboard():
    return """<!DOCTYPE html>
<html lang="zh-Hant">
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ESP32 OTA</title>
<style>
body{font-family:Arial;background:#eee;padding:20px 10px}
.card{background:white;padding:22px;margin:15px auto;max-width:520px;border-radius:12px}
button{padding:10px 16px;margin:8px 0}
</style>
<div class="card">
<h2>ESP32 韌體管理</h2>
<p>目前版本：<b>""" + CURRENT_VERSION + """</b></p>
<p>最新版本：""" + latest_version + """</p>
<p>版本說明：""" + description + """</p>
<p>更新狀態：""" + update_status + """</p>
<form action="/check" method="POST">
<button>重新檢查版本</button>
</form>
</div>
<div class="card">
<h3>手動韌體更新</h3>
<p>目前尚未啟用韌體寫入。請先確認 ESP32 使用支援 OTA 的
MicroPython 韌體及雙 OTA 分割區，再整合更新程式。</p>
<p>不可直接將任意 Arduino .bin 或整包 MicroPython
安裝映像寫入執行中的程式分割區。</p>
</div>
</html>
"""

# ==========================================
# HTTP 回應
# ==========================================
def send_response(client, status, content_type, body):
    if isinstance(body, str):
        body = body.encode("utf-8")

    header = (
        "HTTP/1.1 " + status + "\r\n"
        "Content-Type: " + content_type + "\r\n"
        "Content-Length: " + str(len(body)) + "\r\n"
        "Connection: close\r\n"
        "Cache-Control: no-store\r\n\r\n"
    )

    client.send(header.encode("utf-8"))
    client.send(body)

# ==========================================
# HTTP 伺服器
# ==========================================
def start_server():
    addr = socket.getaddrinfo("0.0.0.0", 80)[0][-1]
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(addr)
    server.listen(3)
    server.settimeout(1)

    print("Web server started")
    print("Open http://" + wlan.ifconfig()[0] + "/")

    return server

def handle_client(client):
    global authenticated

    client.settimeout(3)

    request = b""
    while b"\r\n\r\n" not in request and len(request) < 8192:
        chunk = client.recv(1024)
        if not chunk:
            break
        request += chunk

    if not request:
        return

    header_end = request.find(b"\r\n\r\n")
    header = request[:header_end].decode("utf-8", "ignore")
    lines = header.split("\r\n")
    parts = lines[0].split()

    if len(parts) < 2:
        send_response(client, "400 Bad Request",
                      "text/plain; charset=utf-8", "Bad request")
        return

    method, path = parts[0], parts[1].split("?")[0]

    if path == "/" and method == "GET":
        send_response(client, "200 OK",
                      "text/html; charset=utf-8", LOGIN_PAGE)
        return

    if path == "/login" and method == "POST":
        # 本範例限制登入表單大小
        content_length = 0
        for line in lines[1:]:
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":")[1].strip())

        body = request[header_end + 4:]

        if content_length > 1024:
            send_response(client, "413 Content Too Large",
                          "text/plain", "Request too large")
            return

        while len(body) < content_length:
            chunk = client.recv(min(512, content_length - len(body)))
            if not chunk:
                break
            body += chunk

        form = {}
        try:
            from urllib.parse import parse_qs
            values = parse_qs(body.decode("utf-8"))
            form = {
                key: value[0] for key, value in values.items()
            }
        except Exception:
            # 若韌體沒有 urllib.parse，請改用相容的表單解析器
            pass

        if (form.get("userid") == WEB_USER and
                form.get("pwd") == WEB_PASSWORD):
            authenticated = True
            client.send(
                b"HTTP/1.1 303 See Other\r\n"
                b"Location: /serverIndex\r\n"
                b"Connection: close\r\n\r\n"
            )
        else:
            send_response(
                client, "401 Unauthorized",
                "text/html; charset=utf-8",
                "<h3>帳號或密碼錯誤</h3><a href='/'>返回</a>"
            )
        return

    if path in ("/serverIndex", "/check"):
        if not authenticated:
            client.send(
                b"HTTP/1.1 303 See Other\r\n"
                b"Location: /\r\nConnection: close\r\n\r\n"
            )
            return

        if path == "/check" and method == "POST":
            check_github_update()
            client.send(
                b"HTTP/1.1 303 See Other\r\n"
                b"Location: /serverIndex\r\nConnection: close\r\n\r\n"
            )
            return

        send_response(
            client, "200 OK",
            "text/html; charset=utf-8", dashboard()
        )
        return

    send_response(client, "404 Not Found",
                  "text/plain; charset=utf-8", "Not found")

# ==========================================
# 主程式
# ==========================================
if connect_wifi():
    check_github_update()

server = start_server()

while True:
    try:
        if not wlan.isconnected():
            connect_wifi()

        try:
            client, address = server.accept()
        except OSError:
            client = None

        if client:
            try:
                handle_client(client)
            except Exception as e:
                print("HTTP error:", e)
            finally:
                client.close()

        if time.ticks_diff(
            time.ticks_ms(), last_update_check
        ) >= UPDATE_INTERVAL:
            last_update_check = time.ticks_ms()
            check_github_update()

    except Exception as e:
        print("Main loop error:", e)
        time.sleep(1)

    gc.collect()
