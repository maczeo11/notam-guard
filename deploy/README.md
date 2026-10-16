# Deploying to a small VM

NOTAM-Guard runs on one Ubuntu VM that also hosts other apps. It listens on `127.0.0.1:8001` only, and Caddy serves it over HTTPS on its own hostname.

```
browser -> Vercel (web/) -> /api/* -> https://notam.43-205-27-169.sslip.io -> Caddy -> 127.0.0.1:8001
```

| File | Goes to |
|---|---|
| `notam-guard.service` | `/etc/systemd/system/` |
| `Caddyfile.snippet` | appended to `/etc/caddy/Caddyfile` |
| `requirements-vm.txt` | installed into `/home/ubuntu/notam-guard/.venv` |

Setup, once:

```bash
sudo apt-get install -y python3-venv
python3 -m venv ~/notam-guard/.venv
~/notam-guard/.venv/bin/pip install -r ~/notam-guard/deploy/requirements-vm.txt
sudo cp deploy/notam-guard.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now notam-guard
cat deploy/Caddyfile.snippet | sudo tee -a /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile && sudo systemctl reload caddy
```

To update after a code change: copy `src/` and `data/` across, then `sudo systemctl restart notam-guard`.

## What is exposed, and why

The API is public and has no authentication, and `vercel.json` cannot add any: a rewrite only forwards requests, and Vercel has no fixed addresses to allow-list. So safety comes from exposing little and limiting the damage.

| Layer | What it does |
|---|---|
| Caddy path allow-list | Only `GET /health`, `GET /notams`, `POST /validate` and `POST /approve/T-XXXXXX` reach the app. `/docs`, `/openapi.json`, `/ticket/*`, `/drone/*/history` and every other method or path return 404 |
| Input limits | `query` is capped at 500 characters, `drone_id` at 64, and `lat`, `lon` and `alt` have ranges. Larger input returns 422 |
| Tickets stay in the process | `REDIS_URL` is empty on purpose, so a flood of requests cannot write into the Redis that serves another app. The memory cap restarts the service and clears the tickets |
| Resource caps | `MemoryMax=300M`, `TasksMax=64`, `NoNewPrivileges`, `ProtectSystem=strict` |
| TLS end to end | The browser talks to Vercel over HTTPS, and Vercel talks to the VM over HTTPS |
| Headers | Caddy removes `Server` and sets `nosniff` and `no-store`. `vercel.json` sets `nosniff`, `X-Frame-Options: DENY`, a strict referrer policy, a `Permissions-Policy` that turns off camera, microphone, location, payment and USB, and a Content-Security-Policy that allows scripts and styles only from the site itself (plus Google Fonts), map tiles only from OpenStreetMap, and API calls only to the same origin |

What this does **not** do: it cannot prove that a request came from the Vercel site, because anyone can call the public address directly. The only data is sample data, so that is acceptable here. A shared secret added by a Vercel function would close that gap, at the cost of a second moving part.

It runs in memory mode (`VECTOR_ADAPTER=memory`, `LLM_ADAPTER=rule`), so it needs no Postgres, no embedding model and no API key. The verdict logic is identical to the full stack.
