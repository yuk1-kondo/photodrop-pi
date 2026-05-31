import time
import json
import urllib.request
import urllib.error

from gpiozero import Button

BUTTON_GPIO = 5
PHOTODROP_BASE = "http://127.0.0.1"
DEBOUNCE_SECONDS = 0.08
LONG_PRESS_SECONDS = 3.0
COOLDOWN_SECONDS = 0.8


def post_api(path, timeout=60):
    url = f"{PHOTODROP_BASE}{path}"
    req = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            body = res.read().decode("utf-8", errors="replace")
            try:
                return res.status, json.loads(body)
            except json.JSONDecodeError:
                return res.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return e.code, body
    except Exception as e:
        return 0, str(e)


def handle_short_press():
    print("[INFO] short press: toggle QR")
    status, body = post_api("/api/admin/display/toggle")
    if status == 200:
        print(f"[INFO] toggle ok: {body}")
    else:
        print(f"[WARN] toggle failed: status={status} body={body}")


def handle_long_press():
    print("[INFO] long press: refresh session")
    status, body = post_api("/api/admin/session/refresh")
    if status == 200:
        print(f"[INFO] refresh ok: {body}")
    else:
        print(f"[WARN] refresh failed: status={status} body={body}")


def main():
    print("[INFO] PhotoDrop button watcher started")
    print(f"[INFO] GPIO: {BUTTON_GPIO}")
    print("[INFO] short press = toggle Wi-Fi/AP/LAN QR")
    print("[INFO] long press  = refresh session")
    button = Button(BUTTON_GPIO, pull_up=True, bounce_time=DEBOUNCE_SECONDS)
    last_action_time = 0
    while True:
        button.wait_for_press()
        pressed_at = time.time()
        print("[INFO] button pressed")
        button.wait_for_release()
        duration = time.time() - pressed_at
        now = time.time()
        if now - last_action_time < COOLDOWN_SECONDS:
            print("[INFO] ignored: cooldown")
            continue
        last_action_time = now
        print(f"[INFO] button released duration={duration:.2f}s")
        if duration >= LONG_PRESS_SECONDS:
            handle_long_press()
        else:
            handle_short_press()
        time.sleep(0.05)


if __name__ == "__main__":
    main()
