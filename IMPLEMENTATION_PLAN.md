# IMPLEMENTATION_PLAN.md — MarketPulse
*Updated: 2026-10-10*

---

## Ringkasan Arsitektur

MarketPulse adalah Telegram bot personal untuk pemantauan pasar saham dan emas Indonesia & internasional.

```
Pengguna (Telegram) ──► Bot Handler ──► Market Data Service ──► Provider (yfinance)
                            │                    │
                            ▼                    ▼
                       Formatter          Domain Schemas
                            │
                            ▼
                      Response ke User
```

---

## Phase 0 — Environment Discovery ✅ SELESAI

- [x] Audit VPS Debian 12
- [x] Konfirmasi Python 3.11.2 tersedia
- [x] Konfirmasi Hermes v0.18.2 CLI (tidak berjalan sebagai service)
- [x] Konfirmasi tidak ada konflik port/service
- [x] Buat `ENVIRONMENT_AUDIT.md`
- [x] Rencana isolasi di `/opt/marketpulse/`

---

## Phase 1 — MVP Read-Only Telegram Bot 🔄 IN PROGRESS

### Target
Bot bisa menjawab `/start`, `/help`, `/stock`, `/gold` dengan data nyata dari yfinance.

### File yang Dibuat
```
marketpulse/
├── ENVIRONMENT_AUDIT.md
├── IMPLEMENTATION_PLAN.md
├── PRD.md
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── app/
│   ├── __init__.py
│   ├── main.py              ← Entry point, setup bot
│   ├── config.py            ← Settings via pydantic-settings
│   ├── bot/
│   │   ├── __init__.py
│   │   ├── commands.py      ← Telegram command handlers
│   │   └── formatters.py   ← Message formatting
│   ├── domain/
│   │   ├── __init__.py
│   │   └── market_schemas.py ← QuoteResult, DataStatus, dll.
│   ├── market_data/
│   │   ├── __init__.py
│   │   ├── service.py       ← MarketDataService
│   │   └── providers/
│   │       ├── __init__.py
│   │       ├── base.py      ← Protocol/interface provider
│   │       └── yfinance_provider.py ← yfinance adapter
│   ├── storage/             ← Placeholder Phase 2
│   ├── alerts/              ← Placeholder Phase 3
│   ├── indicators/          ← Placeholder Phase 4
│   └── hermes_adapter/      ← Placeholder Phase 5
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── unit/
    │   ├── __init__.py
    │   ├── test_config.py
    │   ├── test_formatters.py
    │   ├── test_yfinance_provider.py
    │   └── test_commands.py
    └── integration/         ← Membutuhkan internet (tidak dijalankan di CI)
```

### Keputusan Teknis
| Keputusan | Pilihan | Alasan |
|-----------|---------|--------|
| Telegram library | python-telegram-bot v21 | Async native, aktif maintained |
| Market data | yfinance | Free, coverage bagus untuk IDX & global |
| Config | pydantic-settings | Type-safe, env loading built-in |
| Data model | pydantic BaseModel | Validasi, serialisasi, IDE support |
| Presisi finansial | Python Decimal | Hindari floating-point error |
| Async DB (future) | aiosqlite + SQLAlchemy 2.0 | Non-blocking, siap untuk production |
| Testing | pytest + pytest-asyncio | Standard, ecosystem luas |

---

## Phase 2 — Watchlist (Menunggu Approval)

- `/add <ticker>` — Tambah ke watchlist
- `/remove <ticker>` — Hapus dari watchlist
- `/watchlist` — Lihat watchlist
- `/market` — Snapshot semua asset di watchlist
- Database: SQLite via aiosqlite + SQLAlchemy 2.0

---

## Phase 3 — Advanced Alerts (Menunggu Approval)

- `/alert <ticker> <above|below> <price>`
- Alert worker terpisah (polling interval)
- Jenis: price above/below, percent change, RSI threshold
- Cooldown, deduplication, retry

---

## Phase 4 — Technical Indicators (Menunggu Approval)

- RSI (14), SMA, EMA, crossover detection
- Semua dihitung Python (bukan AI)
- Unit tests dengan fixture historis

---

## Phase 5 — Hermes Integration (Menunggu Approval)

- `/analyze <ticker> [timeframe]`
- Integrasi via subprocess CLI: `hermes -z "prompt"`
- Atau via `hermes serve` + HTTP localhost:9119
- Detail di `HERMES_INTEGRATION_PLAN.md`

---

## Deployment Plan (Production)

```bash
# Di VPS Debian 12
mkdir -p /opt/marketpulse
cd /opt/marketpulse
git clone <repo> .
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
# Edit .env dengan token dan user ID
nano .env
# Install systemd service
cp deploy/marketpulse.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable marketpulse
systemctl start marketpulse
```

---

## Risiko yang Diidentifikasi

| Risiko | Mitigasi |
|--------|---------|
| yfinance bukan API resmi, bisa break | Interface provider abstrak; mudah ganti |
| Data IDX bisa delayed 15-20 menit | Tampilkan status data dengan jelas |
| `GC=F` adalah futures, bukan spot | Label jelas di output `/gold` |
| Hermes tidak berjalan = `/analyze` gagal | Graceful fallback message |
| VPS tanpa swap bisa OOM saat install | Monitor RAM saat pip install |
