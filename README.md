# Telme - End-to-End Encrypted Chat

A command-line end-to-end encrypted chat application built with FastAPI, Textual, SQLite, and PyNaCl.

## Current Design

- **End-to-end encryption**: Message payloads are encrypted on the client.
- **Ed25519 identity**: User IDs are derived from the SHA-256 hash of the public key.
- **Ephemeral server state**: The server keeps registered keys, online presence, and queued messages **only in memory**.
- **Fresh startup semantics**: Restarting `telme-server` always resets all in-memory state. No server-side state survives restart.
- **Client-local persistence**: Each client stores contacts, local message history, and polling acknowledgement state in SQLite.
- **Polling delivery**: Clients pull queued messages from the server and advance `acked_seq` locally.

## Architecture

```text
┌─────────────────┐                    ┌─────────────────┐
│  Client A       │                    │  Client B       │
│  (Textual TUI)  │                    │  (Textual TUI)  │
│  - Encryption   │                    │  - Encryption   │
│  - SQLite DB    │                    │  - SQLite DB    │
└────────┬────────┘                    └────────┬────────┘
         │                                      │
         │         REST API (HTTP/HTTPS)        │
         └──────────────┬───────────────────────┘
                        │
                ┌───────▼────────┐
                │  Server        │
                │  (FastAPI)     │
                │  - In-memory   │
                │    key store   │
                │  - In-memory   │
                │    message     │
                │    queue       │
                │  - Periodic    │
                │    cleanup     │
                └────────────────┘
```

## Installation

```bash
pip install -e .
```

## Running

### Server

```bash
telme-server
```

The server listens on `http://localhost:8000` by default.

Important behavior:
- restarting the server resets all in-memory registrations, presence state, and queued messages;
- clients must register again after restart;
- queued but unpulled messages are lost on restart.

### Client

```bash
telme-client
```

Quick non-interactive smoke check:

```bash
telme-client --show-key
```

## API Summary

### Register key

- `POST /api/v1/keys/register`

Registers a public key and returns the derived `user_id`.

### Fetch key

- `GET /api/v1/keys/{user_id}`

Returns the registered public key for a user.

### Send message

- `POST /api/v1/messages/send`

Queues a message for the recipient. Response includes:
- `message_id`
- `server_seq`
- `status` (`queued`)

### Pull messages

- `POST /api/v1/messages/pull`

Request fields:
- `user_id`
- `acked_seq`
- `limit`

Response fields:
- `messages`
- `last_seq`
- `has_more`

Each pulled message includes:
- `message_id`
- `server_seq`
- `sender_id`
- `recipient_id`
- `encrypted_message`
- `nonce`
- `signature`
- `timestamp`

## State and Cleanup

### Server-side state

The server holds the following in memory only:
- registered public keys
- online user timestamps
- queued encrypted messages
- per-recipient message sequence counters

### Cleanup behavior

A periodic background task runs inside FastAPI lifespan and performs:
- expired queued message cleanup based on `MESSAGE_TTL`
- stale online presence cleanup

### Restart behavior

`telme-server` startup always resets all in-memory state explicitly. This is intentional and part of the current design.

## Configuration

### Server

Environment variables:
- `TELME_SERVER_HOST`
- `TELME_SERVER_PORT`
- `TELME_SERVER_MESSAGE_TTL`
- `TELME_SERVER_CLEANUP_INTERVAL`

### Client

Environment variables:
- `TELME_CLIENT_SERVER_URL`
- `TELME_CLIENT_POLL_INTERVAL`
- `TELME_CLIENT_PULL_BATCH_SIZE`

## Development

### Run tests

```bash
pytest
pytest -W error
```

### Smoke checks

```bash
telme-server
curl http://localhost:8000/health

# in another shell
telme-client --show-key
```

## Notes

- This codebase currently targets internal development and does **not** preserve backwards compatibility for old message models or sync semantics.
- The server is intentionally ephemeral and should not be treated as durable storage.
- Use HTTPS for non-local deployments.
