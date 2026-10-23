# Veronica — Threat Model (foundation stage)

Scope: single-user, single-machine Windows 11 assistant. Attacker models considered: (1) a malicious web page open in the
user's browser, (2) another local process/user-level malware, (3) a remote party feeding content to the assistant
(prompt injection via web, messages, files), (4) a curious/compromised third-party API provider, (5) user mistakes.
Out of scope: attacker with admin/kernel on the machine, physical access with disk unlocked.

Legend — **Status**: ✅ implemented+tested in foundation · 🟡 designed, due in a named roadmap phase · ⬜ accepted risk.

| # | Asset / surface | Threat | Mitigation | Status |
|---|---|---|---|---|
| M1 | **Microphone** | Always-on capture records private conversation | Push-to-talk is the *default*; wake-word is opt-in. Capture only in the voice service; audio buffered in RAM, never written to disk by default. Visible always-on indicator in shell. Hard "mute" kills the capture stream, not just the UI. | 🟡 P2 |
| M2 | Microphone | Raw audio sent to a cloud STT without consent | Local STT is the default adapter. Any cloud adapter requires explicit per-provider opt-in and shows an "audio leaves device" badge. | 🟡 P2 |
| M3 | Microphone | Another app/website reads the mic via our service | Service exposes no raw-audio endpoint; only transcripts/events. | ✅ (no such API exists) |
| L1 | **Local IPC** (UI ↔ service) | Malicious web page connects to `ws://127.0.0.1:<port>` (CSWSH / DNS rebinding) | Loopback bind, per-launch random token in first frame, constant-time compare, **Origin header present ⇒ 403**, 5 s hello timeout, 64 KB frame cap. | ✅ tests: wrong token, non-hello first frame, foreign Origin, oversized/malformed frames |
| L2 | Local IPC | Other local process connects and drives the assistant | Token delivered via inherited environment variable (not argv, not a file); ephemeral port. Residual: same-user malware can read process env — accepted; see ⬜. | ✅ / ⬜ |
| L3 | Local IPC | Port scan/enumeration by local processes | Ephemeral port, no banner before auth. | ✅ |
| P1 | **Private memory** (conversation store, profile facts) | Theft from disk | Stored under `%LOCALAPPDATA%\Veronica`, never in repo (`.gitignore` blocks `memory/ data/ models/`). Encrypt at rest with a key held in Windows Credential Manager/DPAPI (via `keyring`). | 🟡 P5 |
| P2 | Private memory | Leakage to model providers via context stuffing | Memory is retrieved *selectively*, with per-provider "may see memory" flag (default: off for cloud). Redaction hook before any external call. | 🟡 P5 |
| P3 | Private memory | User cannot see/erase what is stored | `memory list / delete / export / wipe` are P5 acceptance criteria. | 🟡 P5 |
| A1 | **External model APIs** | API key theft | Keys in Credential Manager only; never in env files, config, logs, or the UI process. Only the service process reads them. | 🟡 P3 |
| A2 | External APIs | Sensitive data in prompts/logs retained by provider | Provider allow-list; default to providers with no-training/zero-retention terms (to be verified per provider at P3, *not assumed*). Local fallback adapter. | 🟡 P3 |
| A3 | External APIs | Cost/DoS (runaway loop burns quota) | Per-session token & request budget, hard timeout, circuit breaker. | 🟡 P3 |
| A4 | External APIs | Provider returns hostile content | Model output is *data*, never executed; only validated tool calls (T-section) act. | ✅ by design (no executor exists) |
| T1 | **Tool execution** | Prompt injection makes the model run harmful actions | No tools exist in foundation. P4 tools are a closed allow-list of typed functions with JSON-schema args; **no shell, no arbitrary file path, no raw keystroke injection**. | ✅ (absence) / 🟡 P4 |
| T2 | Tool execution | Confused-deputy: injected text from web/message triggers a tool | Content from untrusted sources is tagged `untrusted`; any tool with side effects needs explicit user confirmation shown in the UI with the *literal* arguments. Read-only tools auto-run. | 🟡 P4 |
| T3 | Tool execution | Path traversal / data exfil via file tools | File tools restricted to a configured root; resolved-path check after symlink resolution. | 🟡 P4 |
| T4 | Tool execution | Silent persistence | Audit log (append-only, local) of every tool call, args, result, and who confirmed. | 🟡 P4 |
| W1 | **Messaging integration** | Account ban / ToS violation with unofficial WhatsApp automation | **Not implemented.** Only the official WhatsApp Business Cloud API (or a different channel) will be evaluated, in P6, after a written ToS review. | ✅ (absent) |
| W2 | Messaging | Inbound message = injection vector | Inbound text is `untrusted`, cannot trigger tools without confirmation; sender allow-list. | 🟡 P6 |
| W3 | Messaging | Assistant sends something the user did not approve | Outbound sends are always confirm-gated; drafts only by default. | 🟡 P6 |
| S1 | Supply chain | Malicious/typosquatted dependency or model file | Small pinned-range dependency set; lockfile + hash-checked installs from P1 onward; models downloaded from pinned URLs with SHA-256 verification; no `pickle`-format model loading. | 🟡 P1/P2 |
| S2 | Logging | Transcripts/keys leak via logs or crash reports | Structured logs exclude payload text by default (log lengths/types, not content). No telemetry. | 🟡 P1 (log policy) |

## Accepted / residual risks
- ⬜ Same-user malware can read the service's environment/memory and the decrypted DB while running. A desktop assistant
  that runs as the user cannot defend against this; mitigation is OS hygiene, not app code.
- ⬜ A cloud LLM necessarily sees whatever text we send it. Mitigation is *user-visible control*, not elimination.

## Verified in the foundation (see `docs/FINDINGS.md` for test output)
Loopback-only bind; token handshake; foreign-Origin rejection; malformed/oversized frame handling; no way for a client
to submit server-only message types; cross-runtime (Node→Python) handshake.
