import sys
import qrcode
from PIL import Image, ImageDraw
from waveshare_epd import epd2in13_V4

MAX_QR_SIZE = 108


def make_qr(data):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=3,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("L")
    img = img.point(lambda p: 0 if p < 128 else 255, mode="1")
    if img.width > MAX_QR_SIZE or img.height > MAX_QR_SIZE:
        img.thumbnail((MAX_QR_SIZE, MAX_QR_SIZE), Image.Resampling.NEAREST)
    return img.point(lambda p: 0 if p < 128 else 255, mode="1")


def extract_host(url):
    text = url.replace("http://", "").replace("https://", "")
    return text.split("/")[0] if "/" in text else text


def normalize_mode(status):
    value = str(status or "").strip().lower()
    if value == "lan":
        return "LAN Gallery"
    if value == "ap":
        return "AP Gallery"
    return "Gallery"


def fit_text(text, max_chars):
    return text if len(text) <= max_chars else text[:max_chars - 1] + "…"


def display_qr(url, photo_count=0, status="Gallery"):
    epd = epd2in13_V4.EPD()
    epd.init()
    epd.Clear(0xFF)

    width = epd.height
    height = epd.width
    canvas = Image.new("1", (width, height), 255)
    draw = ImageDraw.Draw(canvas)
    qr_img = make_qr(url)

    qr_x = 4
    qr_y = (height - qr_img.height) // 2
    canvas.paste(qr_img, (qr_x, qr_y))

    text_x = 122
    host = extract_host(url)
    mode_label = normalize_mode(status)

    draw.text((text_x, 4), "PhotoDrop Pi", fill=0)
    draw.text((text_x, 24), fit_text(mode_label, 18), fill=0)
    draw.text((text_x, 48), f"{photo_count}", fill=0)
    draw.text((text_x, 62), "photos", fill=0)
    draw.text((text_x, 86), "URL", fill=0)
    draw.text((text_x, 100), fit_text(host, 19), fill=0)

    canvas = canvas.point(lambda p: 0 if p < 128 else 255, mode="1")
    epd.display(epd.getbuffer(canvas))
    epd.sleep()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: display_qr.py <url> [photo_count] [status]")
        sys.exit(1)
    url = sys.argv[1]
    photo_count = int(sys.argv[2]) if len(sys.argv) >= 3 else 0
    status = sys.argv[3] if len(sys.argv) >= 4 else "Gallery"
    display_qr(url, photo_count, status)
