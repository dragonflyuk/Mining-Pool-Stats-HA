# Mining Pool Stats for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Home Assistant custom integration that pulls real-time mining stats from both **Braiins Pool** (pool.braiins.com) and **PowerPool** (powerpool.io), combining them into a unified set of sensors — giving you a single dashboard view across all your miners regardless of which pool they point to.

---

## Features

- **Braiins Pool** — hashrate (5 min / 60 min / 24 h), unpaid balance, today's reward, estimated reward, and per-state worker counts (OK / Low / Offline / Disconnected).
- **PowerPool** — current and average SHA-256 hashrate, estimated 24 h USD revenue, BTC balance, and worker count.
- **Combined view** — total hashrate, total workers, total unpaid BTC balance, and estimated daily revenue across both pools in one device.
- Cloud polling every **60 seconds** with no local hardware required.
- Full UI config flow — no YAML needed.

---

## Prerequisites

- Home Assistant 2023.11.0 or newer.
- HACS installed.
- A **Braiins Pool** API key — generate one at [pool.braiins.com/settings/api](https://pool.braiins.com/settings/api).
- A **PowerPool** API key — find yours in your PowerPool dashboard (changing your password resets the key).

---

## Installation via HACS (recommended)

1. In Home Assistant go to **HACS → Integrations**.
2. Click the three-dot menu → **Custom repositories**.
3. Paste `https://github.com/dragonflyuk/Mining-Pool-Stats-HA` and set category to **Integration**.
4. Click **Add**, then find **Mining Pool Stats** and click **Install**.
5. Restart Home Assistant.

## Manual Installation

1. Download the [latest release](https://github.com/dragonflyuk/Mining-Pool-Stats-HA/releases/latest).
2. Copy `custom_components/mining_pool_stats` into your HA `config/custom_components/` directory.
3. Restart Home Assistant.

---

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Mining Pool Stats**.
3. Enter your **Braiins Pool API Key** and **PowerPool API Key**.
4. Click **Submit** — both keys are validated against their respective APIs before saving.

---

## Devices & Entities Created

### Braiins Pool

| Entity | Unit | Description |
|---|---|---|
| `sensor.braiins_pool_hashrate_5_min` | TH/s | 5-minute hashrate |
| `sensor.braiins_pool_hashrate_60_min` | TH/s | 60-minute hashrate |
| `sensor.braiins_pool_hashrate_24_h` | TH/s | 24-hour hashrate |
| `sensor.braiins_pool_balance` | BTC | Current unpaid balance |
| `sensor.braiins_pool_todays_reward` | BTC | Reward earned today |
| `sensor.braiins_pool_estimated_reward` | BTC | Estimated next payout |
| `sensor.braiins_pool_workers_ok` | workers | Workers mining normally |
| `sensor.braiins_pool_workers_low_hashrate` | workers | Workers with low hashrate |
| `sensor.braiins_pool_workers_offline` | workers | Workers not seen recently |
| `sensor.braiins_pool_workers_disconnected` | workers | Workers disconnected |

### PowerPool

| Entity | Unit | Description |
|---|---|---|
| `sensor.powerpool_hashrate_current` | TH/s | Current SHA-256 hashrate |
| `sensor.powerpool_hashrate_average` | TH/s | Average SHA-256 hashrate |
| `sensor.powerpool_estimated_revenue_24_h` | USD | Estimated 24 h revenue |
| `sensor.powerpool_balance` | BTC | Unpaid BTC balance |
| `sensor.powerpool_workers` | workers | Active SHA-256 workers |

### Mining Combined

| Entity | Unit | Description |
|---|---|---|
| `sensor.mining_combined_total_hashrate` | TH/s | Sum of both pool hashrates |
| `sensor.mining_combined_total_workers` | workers | Total workers across pools |
| `sensor.mining_combined_total_btc_balance` | BTC | Total unpaid BTC |
| `sensor.mining_combined_estimated_revenue_24_h` | USD | Estimated daily revenue |

---

## License

MIT — see `LICENSE` for details.
