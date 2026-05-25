# Install Proxy

Cloudflare Worker for the installer domain `install.opensore.com`.

Deploy from `infra/install-proxy`:

1. Authenticate with Cloudflare:
   `npx wrangler login`
2. Deploy the Worker:
   `npx wrangler deploy`

The proxy serves installer scripts from the repository:

- `https://install.opensore.com` -> auto-detects shell from request
- `https://install.opensore.com/install.sh` -> Unix shell installer
- `https://install.opensore.com/install.ps1` -> PowerShell installer

Optional query override on the root endpoint:

- `?shell=sh`
- `?shell=powershell`
