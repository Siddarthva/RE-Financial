# Claude Code Connectivity Diagnostics (Windows PowerShell)

Run these commands in the same Windows environment where `claude` is installed. They do not print secrets or change configuration.

## 1. Check DNS and TCP reachability

```powershell
Resolve-DnsName api.anthropic.com
Test-NetConnection api.anthropic.com -Port 443
```

Interpretation:
- DNS lookup fails: inspect DNS/network/VPN configuration.
- `TcpTestSucceeded : False`: HTTPS port 443 is unreachable from this machine/network. Try an approved alternate network or ask the network administrator whether the domain is blocked.
- `TcpTestSucceeded : True`: basic TCP reachability works, but this does not prove TLS, account authentication, or Claude Code access is working.

## 2. Check HTTPS/TLS response

```powershell
curl.exe -I --max-time 15 https://api.anthropic.com
```

An HTTP response of any status (including 401/404) indicates that DNS/TCP/TLS reached an HTTP endpoint; it does not authenticate Claude Code. A timeout, TLS error, connection reset, or proxy error needs further network diagnosis. Do not paste authorization headers or tokens into commands.

## 3. Check proxy environment without exposing values

```powershell
Get-ChildItem Env: | Where-Object { $_.Name -match '^(HTTP|HTTPS|ALL|NO)_PROXY$' } | Select-Object Name
```

This prints only proxy variable names. If a proxy is configured, check its settings with the administrator; do not paste proxy URLs if they contain credentials.

## 4. Check Claude Code account status

```powershell
claude --version
claude
```

Inside Claude Code, run `/status`. Verify the intended account and authentication method. Do not set `ANTHROPIC_API_KEY` unless you intentionally choose API billing. A Pro subscription and network access are separate requirements; one does not guarantee the other.

## 5. Check MCP registration

```powershell
claude mcp list
```

A connected `quickbooks` entry means the local MCP server starts and its handshake succeeds. It does **not** prove a live QuickBooks API request succeeded. After Claude Code itself works, make one read-only QuickBooks query and record a sanitized result.

## Share only these diagnostic facts
- `TcpTestSucceeded` value
- Whether `curl.exe -I` returned an HTTP status, timeout, TLS error, or connection reset
- Sanitized Claude Code error text

Never share `.env` files, client secrets, refresh/access tokens, OAuth authorization codes, or screenshots containing them.
