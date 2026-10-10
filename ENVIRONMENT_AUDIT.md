# ENVIRONMENT_AUDIT.md — MarketPulse
*Generated: 2026-10-10 | Phase 0 — Environment Discovery*

---

## 1. Environment yang Ditemukan

### Server (Target Deployment)
| Komponen | Nilai |
|----------|-------|
| OS | Debian GNU/Linux 12 (bookworm) ⚠️ *bukan Ubuntu, tapi kompatibel* |
| Kernel | 6.1.0-51-cloud-amd64 x86_64 |
| Hostname | fazzadwr |
| IP Publik | 157.20.254.17 |
| Python | 3.11.2 (`/usr/bin/python3`) ✅ |
| pip | 23.0.1 (diinstall saat audit) ✅ |
| python3-venv | Tersedia ✅ |
| Git | 2.39.5 ✅ |
| curl/wget | Tersedia ✅ |
| Disk (/) | 59GB total, 5.5GB used, **52GB tersedia** ✅ |
| RAM | 1.9GB total, ~220MB used, **1.7GB tersedia** ✅ |
| Swap | Tidak ada ⚠️ |
| systemd | Tersedia dan aktif ✅ |

### Mesin Lokal (Development)
| Komponen | Nilai |
|----------|-------|
| OS | macOS 26.6.2 |
| Python | 3.9.6 (sistem) — tidak digunakan untuk MarketPulse |
| SSH Key | `~/.ssh/id_ed25519` — sudah di-copy ke VPS ✅ |

---

## 2. Hermes Agent — Temuan

### Instalasi
| Item | Detail |
|------|--------|
| Binary | `/usr/local/bin/hermes` |
| Lib Directory | `/usr/local/lib/hermes-agent/` |
| User config | `/root/.hermes/` |
| Version | **v0.18.2 (2026.7.7.2)** |
| Install method | `git` |
| Python | 3.11.2 (sama dengan sistem) |

### Status Hermes
- **Tidak ada systemd service** yang menjalankan Hermes secara otomatis
- **Tidak ada proses Hermes** yang berjalan saat audit
- **Tidak ada port** yang dibuka oleh Hermes
- Hermes tersedia sebagai **CLI tool** (`/usr/local/bin/hermes`)

### Mekanisme Integrasi yang Tersedia (dari `hermes --help`)
Hermes v0.18.2 mendukung:
- `hermes serve` — JSON-RPC/WebSocket gateway (default port 9119, hanya localhost)
- `hermes chat` — Interactive/non-interactive CLI chat
- `hermes send` — Send message non-interaktif via CLI
- `hermes -z PROMPT` — Single-shot prompt via CLI flag
- `hermes mcp` — MCP server management
- `hermes proxy` — Local OpenAI-compatible proxy

> **Kesimpulan untuk Phase 5:** Integrasi paling aman adalah via `hermes -z "prompt"` (subprocess CLI)
> atau `hermes serve` + HTTP ke localhost:9119.

---

## 3. Port yang Digunakan Saat Ini

| Port | Service | Binding |
|------|---------|---------|
| 22 | sshd | 0.0.0.0, [::] |
| 53 | systemd-resolved | 127.0.0.54, 127.0.0.53 |
| 5355 | systemd-resolved (mDNS) | 0.0.0.0, [::] |

**Port yang direncanakan untuk MarketPulse:** Tidak ada port publik (Telegram bot menggunakan long polling).

---

## 4. Service Systemd yang Aktif

| Service | Status |
|---------|--------|
| dbus.service | running |
| ssh.service | running |
| systemd-journald.service | running |
| systemd-networkd.service | running |
| systemd-resolved.service | running |
| systemd-timesyncd.service | running |
| unattended-upgrades.service | running |

**Tidak ada service Hermes yang berjalan.** MarketPulse tidak akan konflik dengan service yang ada.

---

## 5. Potensi Konflik

| Risiko | Level | Mitigasi |
|--------|-------|---------|
| Hermes menggunakan Python 3.11 yang sama | Rendah | Gunakan venv terpisah untuk MarketPulse |
| Hermes `serve` bisa buka port 9119 | Rendah | MarketPulse tidak membuka port; Hermes serve tidak aktif saat ini |
| Dua bot Telegram dengan token sama | Tinggi | Gunakan token baru terpisah; jangan jalankan dua long polling |
| pip install global bisa konflik dengan Hermes deps | Rendah | Selalu gunakan venv MarketPulse |
| unattended-upgrades bisa update Python | Rendah | Lock versi di requirements.txt |

---

## 6. Rencana Isolasi MarketPulse

```
/opt/marketpulse/          ← Working directory produksi
├── venv/                  ← Virtual environment Python 3.11 khusus
├── app/                   ← Source code
├── data/                  ← SQLite database
├── logs/                  ← Log files
└── .env                   ← Secrets (chmod 600)

/etc/systemd/system/marketpulse.service  ← systemd unit
```

---

## 7. Hal yang Masih Perlu Dikonfirmasi

- [ ] **Telegram Bot Token** — Pengguna perlu membuat bot baru via @BotFather
- [ ] **TELEGRAM_ALLOWED_USER_IDS** — User ID Telegram pengguna
- [ ] **Hermes Integration** — Mekanisme resmi untuk Phase 5 (akan dibahas di `HERMES_INTEGRATION_PLAN.md`)

---

## 8. Kesimpulan

✅ Environment **aman untuk deployment MarketPulse**
✅ Tidak ada konflik dengan Hermes yang terdeteksi
✅ Python 3.11.2 tersedia
✅ Disk dan RAM cukup untuk Phase 1-4
⚠️ **Hermes tidak sedang berjalan** — aman untuk memulai MarketPulse
⚠️ **Tidak ada Telegram token** — perlu dikonfigurasi sebelum menjalankan bot
