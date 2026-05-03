# Security Policy

MineHost Helper controls a local Minecraft server and should be treated as sensitive local administration software.

## Supported Versions

Only the latest GitHub release is supported.

## Reporting A Vulnerability

Do not open a public issue for vulnerabilities that could expose the manager UI, leak credentials, run unintended commands, or weaken firewall/network safety.

Report security issues privately to the repository owner through GitHub. Include:

- MineHost Helper version.
- Windows version.
- Clear reproduction steps.
- Relevant logs with passwords, webhook URLs, public IPs, and private details removed.

## Security Design Notes

- The manager UI binds to `127.0.0.1` by default.
- Do not expose the manager UI to the internet.
- Minecraft console commands are sent only to the selected Minecraft process stdin.
- RCON is disabled by default.
- Discord webhook URLs should be treated like passwords.
