import sys
import qrcode
from PIL import Image, ImageDraw
from waveshare_epd import epd2in13_V4

MAX_QR_SIZE = 108


def escape_wifi_qr(value):
    return (
        value
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace(":", "\\:")
        .replace('"', '\\"')
    )


def make_wifi_payload(ssid, password):
    return f"WIFI:T:WPA;S:{escape_wifi_qr(ssid)};P:{escape_wifi_qr(password)};;"


def make_qr(data):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=3,
        border=3,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("L")
    img = img.point(lambda p: 0 if p < 128 else 255, mode="1")
    if img.width > MAX_QR_SIZE or img.height > MAX_QR_SIZE:
        img.thumbnail((MAX_QR_SIZE, MAX_QR_SIZE), Image.Resampling.NEAREST)
    return img.point(lambda p: 0 if p < 128 else 255, mode="1")


def fit_text(text, max_chars):
    return text if len(text) <= max_chars else text[:max_chars - 1] + "…"


def display_wifi(ssid, password, photo_count=0):
    epd = epd2in13_V4.EPD()
    epd.init()
    epd.Clear(0xFF)

    width = epd.height
    height = epd.width
    canvas = Image.new("1", (width, height), 255)
    draw = ImageDraw.Draw(canvas)

    qr_img = make_qr(make_wifi_payload(ssid, password))
    qr_x = 4
    qr_y = (height - qr_img.height) // 2
    canvas.paste(qr_img, (qr_x, qr_y))

    text_x = 122
    draw.text((text_x, 4), "PhotoDrop Pi", fill=0)
    draw.text((text_x, 24), "Wi-Fi Setup", fill=0)
    draw.text((text_x, 44), "SSID", fill=0)
    draw.text((text_x, 58), fit_text(ssid, 19), fill=0)
    draw.text((text_x, 76), "PASS", fill=0)
    draw.text((text_x, 90), fit_text(password, 19), fill=0)
    footer = f"{photo_count} photos" if photo_count > 0 else "Insert SD"
    draw.text((text_x, 108), fit_text(footer, 19), fill=0)

    canvas = canvas.point(lambda p: 0 if p < 128 else 255, mode="1")
    epd.display(epd.getbuffer(canvas))
    epd.sleep()


if __name__ == "__main__":
    ssid = sys.argv[1] if len(sys.argv) > 1 else "PhotoDrop-Pi"
    password = sys.argv[2] if len(sys.argv) > 2 else "photodrop1234"
    photo_count = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    display_wifi(ssid, password, photo_count)
