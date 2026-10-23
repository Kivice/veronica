# Veronica — Incremental Roadmap

Rule: a phase is "done" only when its acceptance criteria are *measured on this class of hardware*
(i7-8665U, 4C/8T, 16 GB, UHD 620, no discrete GPU), not on a faster dev machine. Each phase ends in a tagged commit.

## P0 — Foundation (this deliverable) ✅
- Repo skeleton, wire protocol v1, token-authenticated loopback service, fake LLM, tests.
- **Accept:** `scripts/verify.ps1` exits 0 from a clean clone after `scripts/setup.ps1`; threat-model items L1–L3 have tests.

## P1 — Hardening the skeleton (≈1–2 days)
- Lockfile with hashes (`pip-compile --generate-hashes` or `uv`), CI-equivalent script, log policy (no payload text), service lifecycle
  (parent-death detection: service exits when the shell dies), graceful shutdown.
- **Accept:** killing the parent leaves **0** orphan `python.exe` within 3 s (tested); `pip install --require-hashes` succeeds on clean venv; logs grep-clean of payload text in a test.

## P2 — Local speech in, text out (the latency-critical phase)
- Audio capture (`sounddevice`/WASAPI) → VAD (Silero via onnxruntime) → STT (faster-whisper `small.en` int8 *or* `base.en`; benchmark both) with push-to-talk first.
- **Accept (measured, 20-utterance fixed corpus, plugged-in and on battery):**
  - end-of-speech → final transcript p50 ≤ 1.2 s, p95 ≤ 2.5 s for ≤ 8 s utterances;
  - service RSS ≤ 1.2 GB steady with model loaded; no growth > 5 % over 30 min idle;
  - WER on corpus recorded (no target set before the baseline exists);
  - mic stream demonstrably closed when muted (device-level test).
- **Go/no-go gate:** if p95 > 2.5 s with `base.en`, stop and move STT to a cloud adapter (opt-in) before building more.

## P3 — LLM adapters + streaming text
- `LlmAdapter` implementations: one cloud provider and one local fallback (≤ 3B Q4, optional). Streaming deltas already in protocol.
- **Accept:** first token p50 ≤ 1.0 s (cloud, measured); budget/timeout/circuit-breaker tests; API key only in Credential Manager (test greps process env/config/logs for key).

## P4 — Speech out + desktop shell
- TTS adapter (Piper/ONNX candidate; benchmark vs. OS SAPI voices) with sentence-chunked streaming and barge-in (stop on user speech).
- Shell spike (time-boxed 1 day): Electron vs Tauri measured for idle RSS, cold start, installer size. Pick on data.
- **Accept:** speech-end → first TTS audio p50 ≤ 2.0 s end-to-end (cloud LLM); barge-in stops audio ≤ 300 ms; shell idle RSS ≤ 250 MB; signed-or-unsigned installer builds from clean machine and launches the service.

## P5 — Private memory
- SQLite + FTS5 (no vector DB until FTS5 demonstrably fails recall), DPAPI/keyring-wrapped key, list/delete/export/wipe UI.
- **Accept:** wipe leaves no recoverable rows in the DB file after `VACUUM`; encrypted at rest (file has no plaintext fixtures); per-provider "may see memory" flag enforced by test.

## P6 — Read-only tools, then confirm-gated actions
- Typed allow-listed tools (time, timers, calendar-read, file-read in one root). Confirmation UI shows literal args. Audit log.
- Messaging: written ToS review of WhatsApp options **before any code**; draft-only, allow-listed senders.
- **Accept:** injection test suite (≥ 20 hostile strings in tool results/messages) triggers **0** unconfirmed side-effect calls.

## Explicitly deferred (and why)
| Item | Reason |
|---|---|
| Autonomous planning / multi-step agents | No evidence yet that single-turn tool calling is insufficient; multiplies attack surface. |
| Unrestricted computer control | Violates T1–T4; revisit only with sandboxing + per-action confirmation. |
| Vector database / embeddings | FTS5 first; embeddings cost RAM and a model download. |
| Wake word | Continuous mic + CPU drain on a 15 W laptop CPU; push-to-talk first. |
| Local 7B+ LLM | Measured free RAM was ~6 GB with normal apps open; 7B Q4 (~4.5 GB+KV) would cause paging. |
