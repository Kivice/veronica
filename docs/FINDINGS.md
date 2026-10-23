# Veronica — Findings: verified facts vs recommendations vs assumptions

Collected 2026-10-21 on the target laptop. Commands were read-only except project-local venv creation
(`services/voice/.venv`) and `pip install -e services/voice[dev]` into it. **No system software was installed.**

## 1. Verified facts (observed directly)

### Machine
| Item | Observed |
|---|---|
| OS | Windows 11 Pro 10.0.26300, 64-bit |
| CPU | Intel Core i7-8665U, 4 cores / 8 threads; AVX2 = **True**, AVX-512F = **False** (`IsProcessorFeaturePresent`) |
| RAM | 15.8 GB total; **6.1 GB free** at inspection (Chrome, Edge WebView2, Defender, WhatsApp, IDE running) |
| GPU | Intel UHD Graphics 620, driver 31.0.101.2141, adapter RAM reported 1 GB (shared). No discrete GPU |
| Disk | C: 75.8 GB free / 345.2 GB used |
| Audio devices | Realtek HD Audio, Intel Display Audio, plus virtual: Steam Streaming Microphone/Speakers, FxSound |
| Mic privacy setting | Windows microphone consent = `Allow` (user and machine level) |
| Power | Battery 100 %, on AC (BatteryStatus 2) — **no battery-mode measurements taken** |
| Network | PyPI reachable but slow: a ~1 KB-class JSON fetch took 8.6 s; bulk metadata probes took ~10–15 s per package |

### Toolchain
| Tool | State |
|---|---|
| git 2.51.0 | present; repo `master` had **no commits** and was empty (only `.git`) |
| Node 24.13.1, npm 11.10.0, pnpm 12.5.1 | present |
| Python | 3.14.4 (default via `py`/`python`), **3.13.7 at `C:\Python313`**; pip present; `python` also resolves first to a WindowsApps stub path |
| uv | **missing** |
| Rust (`cargo`/`rustc`/`rustup`) | **missing** |
| MSVC (`cl`/`link`) | **missing**; "Visual Studio Build Tools 2019" is registered but no `VC\Tools\MSVC` or Windows Kits `Include` directory was found |
| Go | missing |
| .NET | runtimes 6/8/9 present; **no SDK** (`dotnet --list-sdks` empty) |
| ffmpeg 9.0 | present (WinGet) |
| ollama | missing |
| WebView2 runtime | 155.0.4283.62 present |
| winget 1.29, pwsh 7.6.7, VS Code 1.142 | present |

### PyPI wheel availability (metadata only, latest release; "True" = a pure-Python or win_amd64/abi3 wheel exists)
| package | latest | cp313 | cp314 |
|---|---|---|---|
| numpy | 2.5.4 | ✔ | ✔ |
| onnxruntime | 1.31.0 | ✔ | ✔ |
| ctranslate2 | 4.8.3 | ✔ | ✔ |
| faster-whisper | 1.2.1 | ✔ | ✔ |
| sounddevice | 0.5.6 | ✔ | ✔ |
| torch | 2.14.1 | ✔ | ✔ |
| silero-vad | 6.2.3 | ✔ | ✔ |
| openwakeword | 0.6.0 | ✔ | ✔ |
| piper-tts | 1.8.0 | ✔ | ✔ |
| websockets | 17.3 | ✔ | ✔ |
| fastapi / uvicorn | 0.159.1 / 0.54.0 | ✔ | ✔ |

**Incomplete:** the probe stalled on `pydantic-core` and was stopped; `webrtcvad`, `pyaudio`, `llama-cpp-python`, `openvino`, `av`,
`tokenizers`, `pywhispercpp`, `keyring`, `pytest` were **not checked**. Wheel *existence* ≠ the wheel *works* on this machine.
Probe script: `scratch/wheelcheck.py` (kept outside the repo).

### Foundation tests (run on this machine)
- `pwsh scripts/verify.ps1` → **18 pytest passed** (`protocol` ×12 incl. hostile frames; `server` ×6) + **1 Node↔Python integration test passed**
  → `VERIFY OK`. Python 3.13.7, websockets 15.0.1, pytest 9.1.1, pytest-asyncio 1.4.0.
- Loopback ping round-trip Node→Python→Node: **0.85 ms** (one sample; says nothing about audio/model latency).
- Whole integration test including spawning the Python service and handshake: **~386 ms**.
- **Mutation checks:** disabling the Origin check made `test_browser_origin_is_rejected` fail; disabling the token comparison made
  `test_wrong_token_is_closed` fail; both restored, suite back to 18 passed. So those two security tests are not vacuous.
- Server binds only `127.0.0.1` (asserted by test).
- Bugs found and fixed while testing: (a) pytest auto-IDs for a 64 KB parameter exceeded Windows' 32,767-char env var limit → explicit `id=`;
  (b) `node --test <dir>` fails on Node 24 → glob pattern.

### Tooling observation
Cancelling a background command through the agent tooling left its child `python.exe` running (found PID 20420 via process list, then
terminated by me). Relevant to P1: the service must not rely on its supervisor for cleanup (parent-death detection is a P1 criterion).

## 2. Not verified (no measurement was made)
- Any audio capture, VAD, STT, TTS, LLM latency or accuracy on this CPU.
- Runtime behaviour of the ML wheels on Python 3.14 or 3.13 (only their existence).
- Electron/Tauri idle RSS, startup time, installer size.
- Behaviour on battery / thermally throttled.
- Whether SQLite here has FTS5 compiled in.
- Long-path support (`LongPathsEnabled` could not be read).
- That the Realtek mic works for capture (deliberately **not** recorded; privacy and out of scope).
- Defender's effect on model-load time.

## 3. Recommendations (judgement, backed by the facts above)
1. Shell = Electron by default, finalised by measured P4 spike; Tauri would first require installing Rust + MSVC (both absent).
2. Python 3.13 for the service; re-test 3.14 in P2.
3. Cloud LLM default, no local ≥7B model: ~6 GB free RAM is the binding fact.
4. Push-to-talk first; wake-word deferred.
5. Treat P2's latency gate as the go/no-go for local STT.

## 4. Assumptions (flagged where used in docs)
- STT `small.en`/`base.en` int8 on 4 cores is fast enough (P2 gate decides).
- Electron idle RSS 150–300 MB; Tauri 40–100 MB.
- iGPU offers no useful ML speed-up; Defender slows first model load.
- Provider data-retention terms are acceptable (must be checked per provider in P3).

## 5. Open items for the user
- Repo has **no commits**; I did not commit. Say if you want an initial commit.
- `websockets` is pinned `<16`, but 17.3 is current; untested against 17 — bump deliberately.
- Decision needed before P2: is cloud STT ever acceptable as an opt-in fallback?
