```
╔╦╗╔═╗╦  ╔╦╗╔═╗
 ║ ║╣ ║  ║║║║╣
 ╩ ╚═╝╩═╝╩ ╩╚═╝
▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
 E2EE CLI Chat ─── Zero-Knowledge Messaging
▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
```

# Telme

End-to-end encrypted command-line chat. The server never sees your plaintext — encryption happens entirely on the client using XSalsa20-Poly1305 with Ed25519 key exchange.

## Highlights

- **Zero-knowledge server** — stateless, ephemeral, in-memory only. No database, no logs of message content, no persistence.
- **Client-side encryption** — zlib compress → XSalsa20-Poly1305 encrypt → base64 encode. Server is a blind relay.
- **Ed25519 identity** — user IDs derived from SHA-256 of public keys. No usernames, no passwords.
- **Terminal-native** — full TUI client built with Textual. Chat, contacts, key management in a single terminal.
- **Docker-ready** — one-command deployment with health checks and resource limits.
- **Battle-tested** — 112 tests covering functional, security, and stress scenarios. Handles 10,000 concurrent messages with ease.

## Architecture

```text
┌───────────────────┐                     ┌───────────────────┐
│  Client A (TUI)   │                     │  Client B (TUI)   │
│  ┌─────────────┐  │                     │  ┌─────────────┐  │
│  │ zlib+NaCl   │  │                     │  │ zlib+NaCl   │  │
│  │ encrypt/dec │  │                     │  │ encrypt/dec │  │
│  └──────┬──────┘  │                     │  └──────┬──────┘  │
│  ┌──────┴──────┐  │                     │  ┌──────┴──────┐  │
│  │ SQLite DB   │  │                     │  │ SQLite DB   │  │
│  │ (contacts,  │  │                     │  │ (contacts,  │  │
│  │  history)   │  │                     │  │  history)   │  │
│  └─────────────┘  │                     │  └─────────────┘  │
└─────────┬─────────┘                     └─────────┬─────────┘
          │           HTTPS / REST API              │
          └───────────────────┬─────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │   Server (FastAPI)  │
                    │   ┌──────────────┐  │
                    │   │ In-Memory    │  │
                    │   │ Message Queue│  │
                    │   │ (per-user    │  │
                    │   │  lock + BST) │  │
                    │   └──────────────┘  │
                    │   TTL cleanup task  │
                    └────────────────────┘
```

## Quick Start

### From source

```bash
# Clone and install
git clone https://github.com/your-org/telme.git && cd telme
pip install -e ".[dev]"

# Start server
telme-server

# In another terminal — start client
telme-client
```

### Docker

```bash
# Production
docker compose up -d

# Development (with DEBUG logging)
docker compose --profile dev up telme-server-dev
```

The server listens on port `8000`. Health check: `GET /health`.

## Performance

Benchmarked on Apple Silicon (M-series), single process, in-process transport:

| Scenario | Volume | Throughput |
|----------|--------|-----------|
| Message flood | 10,000 msgs | ~5,900 msg/s |
| Mixed workload (100 users) | 5,000 msgs | ~5,300 msg/s |
| Concurrent pull | 50 clients × 500 msgs | ~89,000 reads/s |
| Concurrent registration | 500 users | ~2,000 reg/s |
| Broadcast (fan-out) | 200 recipients | ~1,400 msg/s |

Conservative estimate for a 4C8G cloud instance: **3,000–5,000 DAU** for pure text messaging.

## Testing

```bash
# Run everything
bash run_tests.sh

# Individual suites
pytest tests/test_server_api.py tests/test_crypto.py tests/test_database.py  # functional
pytest tests/test_security.py                                                 # security
pytest tests/test_stress.py -s                                                # stress + perf output
```

The test suite covers: 77 functional tests, 26 security tests (replay attack, input validation, message isolation), and 9 stress/load tests.

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/v1/keys/register` | POST | Register a public key |
| `/api/v1/keys/{user_id}` | GET | Fetch public key |
| `/api/v1/messages/send` | POST | Queue encrypted message |
| `/api/v1/messages/pull` | POST | Pull queued messages (paginated) |

## Configuration

### Server (environment variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `TELME_SERVER_HOST` | `0.0.0.0` | Bind address |
| `TELME_SERVER_PORT` | `8000` | Bind port |
| `TELME_SERVER_MESSAGE_TTL` | `86400` | Message expiry (seconds) |
| `TELME_SERVER_CLEANUP_INTERVAL` | `60` | Cleanup task interval (seconds) |

### Client (environment variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `TELME_CLIENT_SERVER_URL` | `http://localhost:8000` | Server URL |
| `TELME_CLIENT_POLL_INTERVAL` | `3` | Polling interval (seconds) |
| `TELME_CLIENT_PULL_BATCH_SIZE` | `50` | Messages per pull |

## Project Structure

```
telme/
├── server/          # FastAPI server (stateless, in-memory)
│   ├── api/         # Route handlers
│   ├── models/      # Pydantic schemas
│   ├── services/    # Message queue, key store
│   └── utils/       # Validation, logging
├── client/          # Textual TUI client
│   ├── api/         # HTTP communication
│   ├── crypto/      # Encryption, signing, key management
│   ├── storage/     # SQLite persistence
│   ├── services/    # Chat & contact logic
│   └── tui/         # Screens & widgets
├── tests/           # 112 tests
├── Dockerfile       # Multi-stage production build
├── docker-compose.yml
└── run_tests.sh     # One-click test runner
```

## Security Design

The encryption pipeline: `plaintext → zlib compress → XSalsa20-Poly1305 encrypt (ECDH shared secret) → base64 → transmit`. Server validates structure (timestamps, signatures, sizes) but never decrypts content.

Protections include: replay attack prevention via timestamp validation, Ed25519 signature verification on all key registrations, per-message size limits (1 MB), strict input validation on user IDs and base64 fields, and per-user message isolation.

## License

MIT
