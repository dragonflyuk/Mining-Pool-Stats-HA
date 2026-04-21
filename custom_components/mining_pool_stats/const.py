DOMAIN = "mining_pool_stats"
PLATFORMS = ["sensor"]
UPDATE_INTERVAL = 60  # seconds

POWERPOOL_BASE_URL = "https://api.powerpool.io"
BRAIINS_BASE_URL = "https://pool.braiins.com"

# SHA-256 algorithm key variants used by PowerPool
SHA256_ALIASES = frozenset({"sha256", "sha-256", "btc", "bitcoin"})

# Hashrate unit → TH/s multipliers
HASHRATE_TO_TH: dict[str, float] = {
    "H": 1e-12,
    "H/S": 1e-12,
    "KH": 1e-9,
    "KH/S": 1e-9,
    "MH": 1e-6,
    "MH/S": 1e-6,
    "GH": 1e-3,
    "GH/S": 1e-3,
    "TH": 1.0,
    "TH/S": 1.0,
    "PH": 1e3,
    "PH/S": 1e3,
    "EH": 1e6,
    "EH/S": 1e6,
}
