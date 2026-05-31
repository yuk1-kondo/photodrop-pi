# PhotoDrop-Pi

PhotoDrop-Pi is a Raspberry Pi based local photo sharing device.

テーマは「自分イチの作品をつくろう」。
いちいち写真をスマホに入れるのが面倒くさい。その「いちいち」を減らすために作ったプロトタイプです。

## Concept

SDカードを挿す。QRを読む。写真が届く。

PhotoDrop-Pi lets you browse and download photos from a camera SD card using only a smartphone or PC browser. It does not require a dedicated app, cloud upload, or internet connection.

## Features

- Raspberry Pi 4 based local photo sharing server
- SD card auto-detection and photo scanning
- Browser-based photo gallery
- Thumbnail generation
- Individual image view and download
- ZIP download support
- 2.13 inch e-Paper QR display
- Wi-Fi QR / AP Gallery QR / LAN Gallery QR switching
- Physical push button support
- NetworkManager shared AP mode
- Works without cloud or internet

## Stable Network Configuration

```text
SSID: PhotoDrop-Pi
PASS: photodrop1234
AP IP: 10.42.0.1
AP URL: http://10.42.0.1
Mode: NetworkManager shared
Security: WPA2-PSK / RSN / CCMP
PMF: disabled
Channel: 1
Captive Portal: disabled
```

## Hardware

- Raspberry Pi 4
- Waveshare 2.13inch e-Paper HAT V4
- USB Wi-Fi dongle
- USB SD card reader
- Push button
- 5V/3A or stronger USB-C power supply

## Button Operation

```text
Short press:
  Wi-Fi QR -> AP Gallery QR -> LAN Gallery QR -> Wi-Fi QR

Long press 3 seconds:
  Refresh session URL
```

Button wiring:

```text
GPIO5 / physical pin 29 -> Button
GND   / physical pin 39 -> Button
```

## Quick Start

```bash
git clone https://github.com/yuk1-kondo/photodrop-pi.git
cd photodrop-pi
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Run manually:

```bash
sudo venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 80
```

Check status:

```bash
curl http://127.0.0.1/api/status
```

## Documentation

- [Setup](docs/SETUP.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [System Architecture](docs/PROTOPEDIA_SYSTEM.md)
- [ProtoPedia Story](docs/PROTOPEDIA_STORY.md)

## License

MIT License.
