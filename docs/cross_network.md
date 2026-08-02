# VOIDLINK — Cross-Network Communication

By default VOIDLINK nodes communicate over a local network. This guide
explains three methods for connecting nodes across **different networks
(e.g. two laptops on separate Wi-Fi connections, or one home machine and
one cloud server).**

No code changes are required — VOIDLINK already binds to `0.0.0.0` and
speaks plain HTTP, so any method that makes a port publicly reachable works.

---

## Prerequisites (all methods)

- VOIDLINK installed and working locally (see `docs/getting_started.md`)
- Python 3.11+ and dependencies installed on every device
- The firewall on the **host device** (Device A) must allow inbound traffic
  on the VOIDLINK port

### Firewall quick-reference

| OS | Command |
|----|---------|
| Linux (ufw) | `sudo ufw allow 5000` |
| Linux (firewalld) | `sudo firewall-cmd --add-port=5000/tcp --permanent && sudo firewall-cmd --reload` |
| macOS | Accept the system prompt when node.py first runs |
| Windows | Allow `python3.exe` through Windows Defender Firewall, or run: `netsh advfirewall firewall add rule name="VOIDLINK" dir=in action=allow protocol=TCP localport=5000` |

---

## Method 1 — Tailscale (Recommended)

Tailscale creates an encrypted peer-to-peer mesh VPN. Every device gets a
stable private IP address (`100.x.x.x`) that stays the same across
sessions and works through any NAT or firewall — no router config needed.

### Why this is the best option

- ✅ Free for personal use (up to 100 devices)
- ✅ Stable IP — no reconfiguration between sessions
- ✅ Encrypted in transit (WireGuard under the hood)
- ✅ Works even behind double NAT (mobile hotspot, corporate network)
- ✅ No port forwarding or public IP needed

### Setup

**Step 1 — Install Tailscale on every device**

| Platform | Download |
|----------|----------|
| macOS | `brew install tailscale` or [tailscale.com/download](https://tailscale.com/download) |
| Ubuntu/Debian | `curl -fsSL https://tailscale.com/install.sh \| sh` |
| Windows | [tailscale.com/download](https://tailscale.com/download) |
| Raspberry Pi | `curl -fsSL https://tailscale.com/install.sh \| sh` |

**Step 2 — Sign in on all devices (same account)**

```bash
sudo tailscale up
```

A browser window opens — sign in with Google, GitHub, or Microsoft. Repeat
on every device using the **same account**.

**Step 3 — Find each device's Tailscale IP**

```bash
tailscale ip -4
# e.g. 100.101.102.103
```

Or open the Tailscale app — every connected device is listed with its IP.

**Step 4 — Start VOIDLINK normally**

```bash
# Device A (Tailscale IP: 100.101.102.103)
python3 node.py --id A --port 5000

# Device B (any network)
python3 node.py --id B --port 5001
```

**Step 5 — Connect across the network**

In Device B's terminal:
```
voidlink> /connect 100.101.102.103:5000
```

In Device A's terminal:
```
voidlink> /connect <Device B's Tailscale IP>:5001
```

**Step 6 — Send messages**

```
voidlink> /send Hello from across the internet!
```

### Topology example (three devices, three different networks)

```
  Device A (home)          Device B (office)        Device C (mobile)
  Tailscale: 100.1.1.1     Tailscale: 100.2.2.2     Tailscale: 100.3.3.3
  VOIDLINK port: 5000      VOIDLINK port: 5001       VOIDLINK port: 5002

  A ─────────────────────── B ─────────────────────── C
   \                                                  /
    \────────────────────────────────────────────────/
```

All connections use Tailscale IPs — routing is automatic.

---

## Method 2 — ngrok TCP Tunnel

ngrok creates a temporary public TCP tunnel to your local port. It is
ideal for quick demos and testing without any router or VPN setup.

### Limitations

- ⚠️ The public address changes every session (free tier)
- ⚠️ Requires both parties to update their `/connect` command each time
- ✅ No account required for basic use
- ✅ Works instantly, no installation of agents on remote devices

### Setup

**Step 1 — Install ngrok**

| Platform | Command |
|----------|---------|
| macOS | `brew install ngrok/ngrok/ngrok` |
| Linux | `snap install ngrok` or download from [ngrok.com/download](https://ngrok.com/download) |
| Windows | Download the `.exe` from [ngrok.com/download](https://ngrok.com/download) |

(Optional) Create a free account at [dashboard.ngrok.com](https://dashboard.ngrok.com)
and run `ngrok config add-authtoken <your-token>` to get longer session
limits.

**Step 2 — Start VOIDLINK on Device A**

```bash
python3 node.py --id A --port 5000
```

**Step 3 — Open the tunnel (in a new terminal on Device A)**

```bash
ngrok tcp 5000
```

ngrok prints a forwarding address like:

```
Forwarding  tcp://0.tcp.ngrok.io:14523 -> localhost:5000
```

Share `0.tcp.ngrok.io:14523` with Device B.

**Step 4 — Start VOIDLINK on Device B**

```bash
python3 node.py --id B --port 5001
```

**Step 5 — Connect**

In Device B's terminal:
```
voidlink> /connect 0.tcp.ngrok.io:14523
```

In Device A's terminal (Device B also needs to be reachable — run a second
ngrok tunnel on Device B if both sides need to initiate):
```
voidlink> /connect 0.tcp.ngrok.io:<Device B's tunnel port>
```

> **Note:** For one-way demos (A sends, B receives) only Device A needs a
> tunnel. For bidirectional peer connections both sides need tunnels, or
> use Tailscale instead.

### Scripted tunnel start

```bash
# Start node + tunnel together (Device A)
python3 node.py --id A --port 5000 &
ngrok tcp 5000
```

---

## Method 3 — Router Port Forwarding

If you control the router on Device A's network, you can forward a
public port directly to Device A. This creates a **permanent** entry
point that works without any extra software.

### When to use this

- You have admin access to the router
- You want a stable, always-on node (e.g. a home server or Raspberry Pi)
- You do not want to install Tailscale or ngrok

### Limitations

- ⚠️ Exposes Device A's port to the public internet
- ⚠️ Home ISPs sometimes change your public IP (use DDNS to fix this)
- ⚠️ Some ISPs block inbound connections on residential plans

### Setup

**Step 1 — Find Device A's local IP**

```bash
# Linux / macOS
ip a       # look for 192.168.x.x or 10.x.x.x
hostname -I

# Windows
ipconfig   # look for IPv4 Address under your Wi-Fi or Ethernet adapter
```

Example: `192.168.1.42`

**Step 2 — Log into your router**

Open a browser and go to `192.168.1.1` (or `192.168.0.1`). Log in with
your router admin credentials (often printed on the router itself).

**Step 3 — Add a port forwarding rule**

Navigate to **Port Forwarding** (sometimes called NAT, Virtual Server, or
Applications & Gaming depending on your router brand).

| Field | Value |
|-------|-------|
| Service name | VOIDLINK |
| External port | 5000 |
| Internal IP | 192.168.1.42 (Device A's local IP) |
| Internal port | 5000 |
| Protocol | TCP |

Save and apply.

**Step 4 — Find your public IP**

```bash
curl -s https://api.ipify.org
# e.g. 203.0.113.42
```

Or visit [whatismyip.com](https://whatismyip.com).

**Step 5 — Start VOIDLINK on Device A**

```bash
python3 node.py --id A --port 5000
```

**Step 6 — Device B connects using the public IP**

```
voidlink> /connect 203.0.113.42:5000
```

### Keep the address stable with DDNS

If your ISP assigns a dynamic public IP that changes periodically, use a
free Dynamic DNS service so you always connect by hostname instead:

| Service | Free tier |
|---------|-----------|
| [DuckDNS](https://www.duckdns.org) | ✅ Free, simple |
| [No-IP](https://noip.com) | ✅ Free (requires monthly confirmation) |
| [Cloudflare](https://cloudflare.com) | ✅ Free if you own a domain |

With DuckDNS, your address becomes something like `myvoidlink.duckdns.org`:
```
voidlink> /connect myvoidlink.duckdns.org:5000
```

---

## Comparison

| | Tailscale | ngrok TCP | Port Forwarding |
|---|---|---|---|
| Setup effort | Low | Very low | Medium |
| Stable address | ✅ Always | ❌ Changes each session | ⚠️ Depends on ISP |
| Works behind double NAT | ✅ Yes | ✅ Yes | ❌ No |
| Requires router access | ❌ No | ❌ No | ✅ Yes |
| Requires extra software | Tailscale agent | ngrok agent | Nothing |
| Encrypted in transit | ✅ WireGuard | ✅ TLS | ❌ Plain HTTP |
| Cost | Free (personal) | Free (basic) | Free |
| Best for | Regular multi-device use | Quick demos | Permanent home node |

---

## Troubleshooting

### "Connection refused" when connecting

1. Confirm the node is running on the host device (`/node` or `/peers`).
2. Confirm the port is correct and matches `--port` on the host.
3. Check the firewall on the host device (see Firewall quick-reference above).
4. For port forwarding: test from outside the home network (phone on mobile data).

### Peer connects but messages don't propagate back

Both nodes must be reachable by each other. If only one side has a public
address, messages flow in one direction only.  
→ Use Tailscale (both nodes get a reachable IP automatically).

### ngrok session expired

Free ngrok sessions time out after a few hours. Restart with `ngrok tcp 5000`
and update the `/connect` address on all remote nodes.

### Tailscale devices not seeing each other

- Confirm both devices appear in the Tailscale admin panel at
  [login.tailscale.com](https://login.tailscale.com).
- Run `tailscale ping <other device IP>` to test the link.
- Run `sudo tailscale up --reset` if a device was previously connected
  under a different account.
