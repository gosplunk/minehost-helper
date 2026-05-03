# MineHost Helper Networking Guide

Minecraft Java server gameplay uses TCP, normally port `25565`. MineHost Helper focuses on opening only the configured Minecraft TCP port.

## Local IP Vs Public IP

- Local IP looks like `192.168.1.50` or `10.0.0.25`.
- Public IP often looks like `73.x.x.x`.
- Friends inside your house usually connect to `LOCAL_IP:25565`.
- Friends outside your house usually connect to `PUBLIC_IP:25565`.

Your router must forward the public TCP port to this PC's local IP.

## Windows Firewall

Windows Firewall may block inbound Minecraft connections. MineHost Helper can create an inbound rule for the configured TCP port after you click Fix Windows Firewall.

If Administrator permission is required, run MineHost Helper as Administrator or copy a command like this into an Administrator PowerShell or Command Prompt:

```powershell
netsh advfirewall firewall add rule name="MineHost Helper Minecraft TCP 25565" dir=in action=allow protocol=TCP localport=25565
```

Check a rule:

```powershell
netsh advfirewall firewall show rule name="MineHost Helper Minecraft TCP 25565"
```

PowerShell alternative:

```powershell
New-NetFirewallRule -DisplayName "MineHost Helper Minecraft TCP 25565" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 25565
```

## Router Port Forwarding

1. Open your router app or router admin page.
2. Find Port Forwarding, NAT, Gaming, or Advanced.
3. Add a rule:
   - Name: Minecraft
   - Protocol: TCP
   - External Port: `25565` or your configured port
   - Internal Port: `25565` or your configured port
   - Internal IP: this PC's detected LAN IP
4. Save.
5. Restart the router only if needed.
6. Come back and test again.

## DHCP Reservation

Your PC's local IP can change after reboot. Set a DHCP reservation in your router so the same PC always receives the same local IP. This keeps the port forwarding rule from pointing to the wrong device.

## CGNAT

CGNAT means your internet provider does not give your router a real public IPv4 address. Port forwarding may not work even when your router settings look correct.

Common signs:

- Your router WAN IP is different from the public IP shown by MineHost Helper.
- Router WAN IP starts with `100.64.x.x` through `100.127.x.x`.
- Your provider calls your plan "shared IPv4".

Fixes:

- Ask your internet provider for a public IPv4 address.
- Use a VPN/tunnel service designed for hosting.
- Host on a cloud/VPS server instead of home internet.

## Double NAT

Double NAT means two routers are between your PC and the internet. Example: ISP modem/router plus your own Wi-Fi router.

Fixes:

- Put one device in bridge mode.
- Forward the port on both devices.
- Connect the server PC to the primary router that owns the public connection.

## Public Port Testing

MineHost Helper first checks whether the local Minecraft port is listening. When you click Test Public Port, it asks an external TCP port-check service to attempt a connection back to your public IP and configured Minecraft port.

Possible results:

- Publicly reachable: an outside service confirmed TCP access.
- Local server not running: start the Minecraft server first.
- Router forwarding likely missing: the outside service could not connect, so check Windows Firewall, router forwarding, double NAT, or CGNAT.
- Unknown: the external test service could not be reached or returned an unexpected result.

MineHost Helper uses this only as a best-effort check. Never claim public access works unless the test confirms it or a real outside Minecraft client connects successfully.
