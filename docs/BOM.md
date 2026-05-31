# PhotoDrop-Pi 部品表 / BOM

PhotoDrop-Piで使用する部品一覧です。

価格や在庫は変動するため、購入前に販売ページで確認してください。
Amazon商品やDigiKey部品番号が確定したら、この表に追記します。

## Main Parts

| Category | Part | Qty | Supplier | Product / Part No. | Notes |
|---|---:|---:|---|---|---|
| Main board | Raspberry Pi 4 | 1 | Amazon / other | TBD | PhotoDrop-Pi本体 |
| Display | Waveshare 2.13inch e-Paper HAT V4 | 1 | Amazon / Waveshare | TBD | QRコード表示用 |
| Storage reader | USB SD Card Reader | 1 | Amazon | TBD | カメラSDカード読み取り用 |
| Wi-Fi | USB Wi-Fi Dongle | 1 | Amazon / DigiKey | TBD | APモード対応が必要 |
| Input | Push Button | 1 | Amazon / DigiKey | TBD | QR表示切替用 |
| Cable | Jumper Wire | 2 | Amazon / DigiKey | TBD | ボタン配線用 |
| Power | USB-C Power Supply 5V/3A+ | 1 | Amazon | TBD | Raspberry Pi 4用。電圧不足対策として重要 |
| Power option | Self-powered USB Hub | 1 | Amazon | TBD | USB Wi-Fi / SDカードリーダーの安定化用 |
| Case | Low-profile Case | 1 | Amazon / 3D Print | TBD | 薄型筐体向け |

## Push Button Wiring

| Button Side | Raspberry Pi Pin |
|---|---|
| One side | GPIO5 / Physical Pin 29 |
| Other side | GND / Physical Pin 39 or 6 |

## Notes

- Raspberry Pi 4は電源品質の影響を受けやすいため、5V/3A以上の電源を推奨します。
- `vcgencmd get_throttled` で `throttled=0x50005` が出る場合は、電圧不足が発生しています。
- USB Wi-FiドングルはAPモード対応品を選んでください。
- USB SDカードリーダーとUSB Wi-Fiドングルを同時使用する場合、セルフパワーUSBハブを使うと安定しやすくなります。

## DigiKey / Amazon Tracking Template

| Item | Amazon URL | DigiKey URL | DigiKey Part Number | Confirmed |
|---|---|---|---|---|
| Raspberry Pi 4 |  |  |  | No |
| Waveshare 2.13inch e-Paper HAT V4 |  |  |  | No |
| USB SD Card Reader |  |  |  | No |
| USB Wi-Fi Dongle |  |  |  | No |
| Push Button |  |  |  | No |
| Jumper Wire |  |  |  | No |
| USB-C Power Supply |  |  |  | No |
| Self-powered USB Hub |  |  |  | No |
| Case |  |  |  | No |
