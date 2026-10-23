# PROJECT VERONICA // TACTICAL DESKTOP AGENT

> **Veronica**: Stark Industries-inspired tactical personal AI desktop agent with real-time neural speech synthesis, hardware telemetry monitoring, desktop tool execution, multi-model cloud fallbacks, and a high-tech sci-fi HUD.

![Veronica Mark-IV](https://img.shields.io/badge/Architecture-Stark_Tactical_HUD-00f3ff?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Fully_Operational-00ff88?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.13-blue?style=for-the-badge)
![Platform](https://img.shields.io/badge/Platform-Windows_11-purple?style=for-the-badge)

---

## ⚡ Key Capabilities ("Cool Shit")

1. **Audio-Reactive 3D Holographic Core (Arc Reactor)**:
   - Dynamic 60fps canvas visualizer responding in real-time to audio frequencies when either you or Veronica speak.
2. **Real Expressive Neural Speech (Edge TTS)**:
   - Zero-key, high-fidelity neural audio streaming (`Ava`, `Jenny`, `Sonia`, `Guy`, `Christopher`).
3. **Multi-Model Intelligence Pipeline with Cloud Fallbacks**:
   - **Groq Cloud** (`llama-3.3-70b-versatile` / `llama-3.1-8b-instant` — ultra-fast ~400 tok/sec).
   - **OpenAI Cloud** (`gpt-4o` / `gpt-4o-mini`).
   - **Google Gemini** (`gemini-2.0-flash`).
   - **Anthropic Claude** (`claude-3-5-sonnet`).
   - **Local Ollama** (`llama3.2`).
   - **Veronica Tactical Offline Core**: Zero-key offline engine with natural language intent detection, proactive personality, and instant desktop tool execution.
4. **Desktop Automation & Tool Matrix**:
   - **Live Hardware Vitals**: Real-time CPU per-core load, RAM utilization, battery charging state, disk headroom, and top memory-consuming processes.
   - **Quick Deploy App Launcher**: Launch VS Code, Windows Terminal, Task Manager, Calculator, Chrome, Notepad, or Spotify with one click or a voice command.
   - **Terminal Execution**: Run PowerShell commands directly through Veronica's command drawer.
   - **OS Media & Volume Control**: Volume up/down, mute, and play/pause via Windows virtual key codes.
   - **Persistent Tactical Memory**: Save, query, and clear notes stored in `~/.veronica/memory.json`.
   - **Web Recon**: Open targeted search queries directly in your browser.
5. **Speech Input & Push-to-Talk**:
   - Hold **[SPACEBAR]** or click the central glowing Mic button to speak.

---

## 🚀 Quick Launch (1-Click)

To launch Veronica (starts the backend voice service and opens the tactical desktop HUD in a borderless app window):

```powershell
pwsh scripts/start.ps1
```

If you prefer to run the verification test suite first (24 unit and integration tests):

```powershell
pwsh scripts/verify.ps1
```

---

## 🛠️ Repository Structure

```
veronica/
├── apps/
│   └── desktop/               # Tactical Desktop HUD (Iron Man / Veronica UI)
│       ├── index.html         # HUD interface layout & audio canvas
│       ├── styles.css         # Glassmorphism, neon HUD styling, animations
│       └── app.js             # 60fps audio visualizer, STT, TTS player, WS client
├── services/
│   └── voice/                 # Python 3.13 Voice & Intelligence Service
│       ├── src/veronica_voice/
│       │   ├── brain.py       # Multi-model intelligence engine (Groq, OpenAI, Gemini, Tactical Core)
│       │   ├── tts.py         # Real Microsoft Edge Neural TTS streaming engine
│       │   ├── tools.py       # Desktop tool execution: telemetry, app launcher, commands, media
│       │   ├── server.py      # Authenticated loopback WebSocket server
│       │   └── protocol.py    # Strict wire protocol & frame validation
│       └── tests/             # 24 automated unit & integration tests
├── scripts/
│   ├── start.ps1              # 1-click startup script (service + desktop HUD)
│   ├── setup.ps1              # Local venv setup (no system contamination)
│   └── verify.ps1             # One-command full verification test runner
└── docs/                      # Architecture, Threat Model, and Hardware Records
```

---

## ⚙️ Configuration & API Keys

You can use Veronica **completely offline with zero API keys** right out of the box. 

To enable cloud intelligence, click the **Settings Gear (⚙️)** in the top right of the HUD or export them into your environment:

- `GROQ_API_KEY`: Groq Cloud (Recommended for instant conversational voice responses)
- `OPENAI_API_KEY`: OpenAI GPT-4o
- `GEMINI_API_KEY`: Google Gemini Flash
- `ANTHROPIC_API_KEY`: Claude 3.5 Sonnet
