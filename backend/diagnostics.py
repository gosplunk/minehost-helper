from __future__ import annotations


RULES: list[tuple[str, str, str, str]] = [
    ("failed to bind to port", "Port is already in use", "Another app is using the Minecraft port. Stop the other server or change this server's port.", "error"),
    ("address already in use", "Port is already in use", "Another app is using the Minecraft port. Stop the other server or change this server's port.", "error"),
    ("unsupportedclassversionerror", "Java is too old", "Install the recommended Temurin Java runtime from Setup Wizard, then start again.", "error"),
    ("eula", "Minecraft EULA needs attention", "Open Setup Wizard or check eula.txt. The server cannot start until the EULA is accepted.", "warning"),
    ("outofmemoryerror", "Not enough memory", "Lower RAM allocation or close other apps. If the PC has enough RAM, increase this server's RAM.", "error"),
    ("can't keep up", "Server is overloaded", "The PC may be overloaded. Reduce view distance, simulation distance, or player count.", "warning"),
    ("mod loading has failed", "Mod loading failed", "A mod or loader version is incompatible. Check the mod list and Minecraft version.", "error"),
    ("failed to synchronize registry data", "Mod mismatch", "A player's mods may not match the server. Verify everyone uses the same modpack.", "error"),
    ("corrupt", "Possible world or file corruption", "Create a backup before changing files. Try restoring a known-good backup if the server will not start.", "error"),
]


def explain_lines(lines: list[str]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    seen: set[str] = set()
    text_lines = lines[-500:]
    for line in text_lines:
        lower = line.lower()
        for needle, title, advice, severity in RULES:
            if needle in lower and title not in seen:
                seen.add(title)
                findings.append({
                    "title": title,
                    "severity": severity,
                    "advice": advice,
                    "evidence": line[-300:],
                })
    if not findings:
        findings.append({
            "title": "No obvious problem found",
            "severity": "ok",
            "advice": "MineHost Helper did not recognize a common startup problem in the recent logs. Check the Console page for the exact message.",
            "evidence": "",
        })
    return findings
