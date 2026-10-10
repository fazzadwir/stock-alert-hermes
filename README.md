# MarketPulse 🤖📊

Bot Telegram personal untuk memantau saham Indonesia, saham internasional, dan emas.

## Fitur (Phase 1)

- `/start` — Perkenalan bot
- `/help` — Panduan penggunaan
- `/stock <ticker>` — Cek harga saham (IDX, NYSE, NASDAQ, dll.)
- `/gold` — Cek harga emas futures COMEX (GC=F)

## Prerequisites

- Debian/Ubuntu Linux dengan Python 3.11+
- Telegram Bot Token dari [@BotFather](https://t.me/BotFather)
- Telegram User ID kamu (cari via [@userinfobot](https://t.me/userinfobot))

## Instalasi (VPS)

```bash
# 1. Clone atau upload kode ke VPS
mkdir -p /opt/marketpulse
cd /opt/marketpulse

# 2. Buat virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Konfigurasi environment
cp .env.example .env
chmod 600 .env
nano .env  # Isi TELEGRAM_BOT_TOKEN dan TELEGRAM_ALLOWED_USER_IDS
```

## Konfigurasi .env

```dotenv
APP_ENV=production
TELEGRAM_BOT_TOKEN=123456:ABCDEFGH...   # Dari @BotFather
TELEGRAM_ALLOWED_USER_IDS=123456789     # User ID kamu dari @userinfobot
```

## Menjalankan Bot

### Development (lokal)
```bash
source venv/bin/activate
python -m app.main
```

### Production (systemd)
```bash
# Copy service file
cp deploy/marketpulse.service /etc/systemd/system/

# Aktifkan dan jalankan
systemctl daemon-reload
systemctl enable marketpulse
systemctl start marketpulse

# Cek status
systemctl status marketpulse

# Lihat log
journalctl -u marketpulse -f
```

### Menghentikan Bot
```bash
systemctl stop marketpulse
```

## Menjalankan Tests

```bash
source venv/bin/activate

# Unit tests (tidak butuh internet/token)
pytest tests/unit/ -v

# Semua tests termasuk unit
pytest tests/ -v -m "not integration"

# Integration tests (butuh internet)
pytest tests/integration/ -v -m integration
```

## Troubleshooting

### Bot tidak merespons
1. Cek token di `.env` sudah benar
2. Cek `TELEGRAM_ALLOWED_USER_IDS` sudah berisi user ID kamu
3. Lihat log: `journalctl -u marketpulse -n 50`

### Data tidak muncul
- yfinance membutuhkan koneksi internet
- Simbol IDX harus diakhiri `.JK` (contoh: `BBCA.JK`)
- Data bisa delayed saat market ramai

### "Akses Ditolak"
- Cek user ID kamu via [@userinfobot](https://t.me/userinfobot)
- Tambahkan ID tersebut ke `TELEGRAM_ALLOWED_USER_IDS` di `.env`
- Restart bot setelah ubah `.env`

## Keterbatasan Provider

| Aspek | Detail |
|-------|--------|
| Provider | yfinance (bukan API resmi Yahoo Finance) |
| Data IDX | Delayed ~15-20 menit |
| Emas (GC=F) | Futures COMEX, bukan harga spot/Antam |
| SLA | Tidak ada garansi availability |
| Real-time | Tidak dijamin; status selalu ditampilkan |

## Arsitektur

```
app/
├── main.py              ← Entry point
├── config.py            ← Settings (pydantic-settings)
├── bot/
│   ├── commands.py      ← Telegram handlers
│   └── formatters.py   ← Message formatting
├── domain/
│   └── market_schemas.py ← Data models
└── market_data/
    ├── service.py       ← Business logic + cache
    └── providers/
        ├── base.py      ← Provider interface
        └── yfinance_provider.py
```

## Keamanan

- Token tidak pernah ada di source code
- Allowlist fail-closed (kosong = semua ditolak)
- Log tidak mencetak token atau secrets
- Service systemd menggunakan `EnvironmentFile`

---

*MarketPulse adalah alat informasi, bukan rekomendasi investasi.*
