/**
 * VERONICA // TACTICAL DESKTOP ASSISTANT - CLIENT APPLICATION
 * Stark Industries HUD Architecture & Audio Reactive Core
 * Includes: 60fps Arc Reactor canvas, Web Audio SFX engine,
 * Hands-Free 'Hey Veronica' wake-word, and Multimodal Screen Vision.
 */

(function () {
  "use strict";

  // --- Configuration & State ---
  const urlParams = new URLSearchParams(window.location.search);
  const WS_PORT = urlParams.get("port") || localStorage.getItem("veronica_port") || "8765";
  const WS_TOKEN = urlParams.get("token") || localStorage.getItem("veronica_token") || "";
  if (WS_TOKEN) {
    localStorage.setItem("veronica_token", WS_TOKEN);
    localStorage.setItem("veronica_port", WS_PORT);
  }
  let wsUrl = `ws://127.0.0.1:${WS_PORT}`;

  let ws = null;
  let isConnected = false;
  let audioMuted = false;
  let sfxMuted = false;
  let wakeWordActive = false;
  let isListening = false;
  let recognition = null;
  let wakeWordRecognition = null;
  let activeAudio = null;
  let audioQueue = [];
  let isPlayingAudio = false;

  // DOM Elements
  const statusPill = document.getElementById("statusPill");
  const statusLabel = document.getElementById("statusLabel");
  const engineBadge = document.getElementById("engineBadge");
  const engineLabel = document.getElementById("engineLabel");
  const pingValue = document.getElementById("pingValue");
  const batteryValue = document.getElementById("batteryValue");
  const clockValue = document.getElementById("clockValue");
  const cpuPercent = document.getElementById("cpuPercent");
  const cpuBar = document.getElementById("cpuBar");
  const coresContainer = document.getElementById("coresContainer");
  const ramUsageText = document.getElementById("ramUsageText");
  const ramBar = document.getElementById("ramBar");
  const ramPercentText = document.getElementById("ramPercentText");
  const ramFreeText = document.getElementById("ramFreeText");
  const processList = document.getElementById("processList");
  const transcriptBox = document.getElementById("transcriptBox");
  const veronicaText = document.getElementById("veronicaText");
  const toolExecutionTag = document.getElementById("toolExecutionTag");
  const chatForm = document.getElementById("chatForm");
  const chatInput = document.getElementById("chatInput");
  const micBtn = document.getElementById("micBtn");
  const speechState = document.getElementById("speechState");
  const muteAudioBtn = document.getElementById("muteAudioBtn");
  const muteAudioIcon = document.getElementById("muteAudioIcon");
  const sfxToggleBtn = document.getElementById("sfxToggleBtn");
  const wakeWordBtn = document.getElementById("wakeWordBtn");
  const wakeWordLabel = document.getElementById("wakeWordLabel");
  const analyzeScreenBtn = document.getElementById("analyzeScreenBtn");
  const analyzeScreenChip = document.getElementById("analyzeScreenChip");
  const refreshVitalsBtn = document.getElementById("refreshVitalsBtn");
  const diagBtn = document.getElementById("diagBtn");
  const cmdInput = document.getElementById("cmdInput");
  const runCmdBtn = document.getElementById("runCmdBtn");
  const cmdOutput = document.getElementById("cmdOutput");
  const memoryKeyInput = document.getElementById("memoryKeyInput");
  const memoryValInput = document.getElementById("memoryValInput");
  const saveMemoryBtn = document.getElementById("saveMemoryBtn");
  const memoryList = document.getElementById("memoryList");
  const settingsBtn = document.getElementById("settingsBtn");
  const settingsModal = document.getElementById("settingsModal");
  const closeSettingsBtn = document.getElementById("closeSettingsBtn");
  const saveSettingsBtn = document.getElementById("saveSettingsBtn");
  const testAudioBtn = document.getElementById("testAudioBtn");
  const groqKeyInput = document.getElementById("groqKey");
  const openaiKeyInput = document.getElementById("openaiKey");
  const geminiKeyInput = document.getElementById("geminiKey");
  const anthropicKeyInput = document.getElementById("anthropicKey");
  const voiceSelect = document.getElementById("voiceSelect");
  const wsUrlInput = document.getElementById("wsUrlInput");
  const wsTokenInput = document.getElementById("wsTokenInput");

  // Load saved settings
  groqKeyInput.value = localStorage.getItem("veronica_groq_key") || "";
  openaiKeyInput.value = localStorage.getItem("veronica_openai_key") || "";
  geminiKeyInput.value = localStorage.getItem("veronica_gemini_key") || "";
  anthropicKeyInput.value = localStorage.getItem("veronica_anthropic_key") || "";
  voiceSelect.value = localStorage.getItem("veronica_voice") || "en-US-AvaNeural";
  wsUrlInput.value = wsUrl;
  wsTokenInput.value = WS_TOKEN;

  // Clock
  function updateClock() {
    const now = new Date();
    clockValue.textContent = now.toTimeString().split(" ")[0];
  }
  setInterval(updateClock, 1000);
  updateClock();

  // --- Web Audio & Stark Industries SFX Engine ---
  const canvas = document.getElementById("coreCanvas");
  const ctx = canvas.getContext("2d");
  let audioCtx = null;
  let analyser = null;
  let audioDataArray = new Uint8Array(64);
  let coreRotation = 0;
  let targetEnergy = 0.1;
  let currentEnergy = 0.1;

  function initAudioContext() {
    if (!audioCtx) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (AudioContextClass) {
        audioCtx = new AudioContextClass();
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 128;
        audioDataArray = new Uint8Array(analyser.frequencyBinCount);
      }
    }
    if (audioCtx && audioCtx.state === "suspended") {
      audioCtx.resume();
    }
  }

  // Synthesized Sound Effects (100% Native Web Audio, zero external mp3 files)
  const sfx = {
    boot: function () {
      if (sfxMuted) return;
      initAudioContext();
      if (!audioCtx) return;
      const now = audioCtx.currentTime;
      [220, 440, 660, 880].forEach(function (freq, idx) {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = "sine";
        osc.frequency.setValueAtTime(freq, now + idx * 0.08);
        gain.gain.setValueAtTime(0.001, now + idx * 0.08);
        gain.gain.exponentialRampToValueAtTime(0.12, now + idx * 0.08 + 0.05);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + idx * 0.08 + 0.35);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start(now + idx * 0.08);
        osc.stop(now + idx * 0.08 + 0.4);
      });
    },

    blip: function () {
      if (sfxMuted) return;
      initAudioContext();
      if (!audioCtx) return;
      const now = audioCtx.currentTime;
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = "triangle";
      osc.frequency.setValueAtTime(800, now);
      osc.frequency.exponentialRampToValueAtTime(1400, now + 0.08);
      gain.gain.setValueAtTime(0.15, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.09);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start(now);
      osc.stop(now + 0.1);
    },

    confirm: function () {
      if (sfxMuted) return;
      initAudioContext();
      if (!audioCtx) return;
      const now = audioCtx.currentTime;
      const osc1 = audioCtx.createOscillator();
      const osc2 = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc1.type = "sine";
      osc2.type = "sine";
      osc1.frequency.setValueAtTime(520, now);
      osc2.frequency.setValueAtTime(1040, now);
      gain.gain.setValueAtTime(0.12, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
      osc1.connect(gain);
      osc2.connect(gain);
      gain.connect(audioCtx.destination);
      osc1.start(now);
      osc2.start(now);
      osc1.stop(now + 0.25);
      osc2.stop(now + 0.25);
    },

    error: function () {
      if (sfxMuted) return;
      initAudioContext();
      if (!audioCtx) return;
      const now = audioCtx.currentTime;
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = "sawtooth";
      osc.frequency.setValueAtTime(180, now);
      gain.gain.setValueAtTime(0.15, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start(now);
      osc.stop(now + 0.3);
    },
  };

  // Toggle SFX
  sfxToggleBtn.addEventListener("click", function () {
    sfxMuted = !sfxMuted;
    sfxToggleBtn.classList.toggle("active", !sfxMuted);
    if (!sfxMuted) sfx.blip();
  });

  // Draw 60fps Arc Reactor / Core Visualizer
  function drawCore() {
    requestAnimationFrame(drawCore);

    const w = canvas.width;
    const h = canvas.height;
    const cx = w / 2;
    const cy = h / 2;

    ctx.clearRect(0, 0, w, h);

    if (analyser) {
      analyser.getByteFrequencyData(audioDataArray);
      let sum = 0;
      for (let i = 0; i < audioDataArray.length; i++) {
        sum += audioDataArray[i];
      }
      targetEnergy = Math.max(0.08, sum / (audioDataArray.length * 255));
    }
    currentEnergy += (targetEnergy - currentEnergy) * 0.15;
    coreRotation += 0.015 + currentEnergy * 0.08;

    // Outer Glow Circle
    const glowRadius = 150 + currentEnergy * 45;
    const grad = ctx.createRadialGradient(cx, cy, 30, cx, cy, glowRadius);
    grad.addColorStop(0, "rgba(0, 243, 255, " + (0.35 + currentEnergy * 0.5) + ")");
    grad.addColorStop(0.5, "rgba(0, 119, 255, " + (0.15 + currentEnergy * 0.3) + ")");
    grad.addColorStop(1, "rgba(0, 0, 0, 0)");

    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(cx, cy, glowRadius, 0, Math.PI * 2);
    ctx.fill();

    // Concentric Ring 1 (Rotating segmented outer ring)
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(coreRotation);

    ctx.strokeStyle = "rgba(0, 243, 255, 0.4)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(0, 0, 130, 0, Math.PI * 2);
    ctx.stroke();

    // Ring tick marks
    const ticks = 36;
    for (let i = 0; i < ticks; i++) {
      const angle = (i * Math.PI * 2) / ticks;
      const r1 = 130;
      const r2 = i % 4 === 0 ? 144 : 136;
      ctx.beginPath();
      ctx.moveTo(Math.cos(angle) * r1, Math.sin(angle) * r1);
      ctx.lineTo(Math.cos(angle) * r2, Math.sin(angle) * r2);
      ctx.strokeStyle = i % 4 === 0 ? "rgba(0, 243, 255, 0.9)" : "rgba(0, 243, 255, 0.3)";
      ctx.lineWidth = i % 4 === 0 ? 2 : 1;
      ctx.stroke();
    }
    ctx.restore();

    // Concentric Ring 2 (Counter-rotating brackets)
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(-coreRotation * 1.4);

    ctx.lineWidth = 3;
    ctx.strokeStyle = "rgba(0, 243, 255, 0.75)";
    for (let i = 0; i < 4; i++) {
      ctx.beginPath();
      ctx.arc(0, 0, 96 + currentEnergy * 20, (i * Math.PI) / 2 + 0.15, ((i + 1) * Math.PI) / 2 - 0.15);
      ctx.stroke();
    }
    ctx.restore();

    // Audio Waveform Ring
    ctx.save();
    ctx.translate(cx, cy);
    ctx.beginPath();
    const waveRadius = 70;
    const slices = audioDataArray.length;
    for (let i = 0; i < slices; i++) {
      const angle = (i * Math.PI * 2) / slices;
      const amp = (audioDataArray[i] / 255) * 35 * (currentEnergy * 2);
      const r = waveRadius + amp;
      const x = Math.cos(angle) * r;
      const y = Math.sin(angle) * r;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.strokeStyle = "rgba(0, 243, 255, 0.85)";
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.restore();

    // Core Center Sphere (Pulsing Arc Heart)
    const coreR = 38 + currentEnergy * 18;
    const coreGrad = ctx.createRadialGradient(cx, cy, 5, cx, cy, coreR);
    coreGrad.addColorStop(0, "#ffffff");
    coreGrad.addColorStop(0.4, "#00f3ff");
    coreGrad.addColorStop(0.8, "#0066ff");
    coreGrad.addColorStop(1, "rgba(0, 102, 255, 0)");

    ctx.fillStyle = coreGrad;
    ctx.beginPath();
    ctx.arc(cx, cy, coreR, 0, Math.PI * 2);
    ctx.fill();

    // Center Stark Triangular/Hex Symbol
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(coreRotation * 0.5);
    ctx.strokeStyle = "rgba(255, 255, 255, 0.9)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let i = 0; i < 3; i++) {
      const a = (i * Math.PI * 2) / 3 - Math.PI / 2;
      const x = Math.cos(a) * 16;
      const y = Math.sin(a) * 16;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.stroke();
    ctx.restore();
  }
  drawCore();

  // --- WebSocket Client & Event Dispatcher ---
  let pingInterval = null;
  let pingStart = 0;

  function setStatus(statusClass, label) {
    statusPill.className = "status-pill " + statusClass;
    statusLabel.textContent = label;
  }

  function connectWs() {
    const currentUrl = wsUrlInput.value.trim() || `ws://127.0.0.1:${WS_PORT}`;
    const token = wsTokenInput.value.trim() || WS_TOKEN;

    setStatus("status-standby", "CONNECTING...");
    speechState.textContent = "ATTEMPTING HANDSHAKE";

    try {
      ws = new WebSocket(currentUrl);
    } catch (e) {
      setStatus("status-standby", "OFFLINE");
      speechState.textContent = "SERVICE UNREACHABLE";
      return;
    }

    ws.onopen = function () {
      const helloFrame = {
        v: 1,
        id: "auth_" + Date.now(),
        type: "hello",
        payload: { token: token },
      };
      ws.send(JSON.stringify(helloFrame));
    };

    ws.onmessage = function (event) {
      try {
        const frame = JSON.parse(event.data);
        handleFrame(frame);
      } catch (e) {
        console.error("Frame parse error:", e);
      }
    };

    ws.onclose = function (e) {
      isConnected = false;
      setStatus("status-standby", "DISCONNECTED");
      speechState.textContent = "OFFLINE (RETRYING IN 3s)";
      if (pingInterval) clearInterval(pingInterval);
      setTimeout(connectWs, 3000);
    };

    ws.onerror = function (e) {
      console.warn("WebSocket error:", e);
    };
  }

  let currentStreamedText = "";
  let incomingAudioChunks = [];

  function handleFrame(frame) {
    switch (frame.type) {
      case "ready":
        isConnected = true;
        setStatus("status-standby", "STANDBY");
        speechState.textContent = "TACTICAL CHANNEL ONLINE";
        sfx.boot();
        if (frame.payload && frame.payload.llm) {
          engineLabel.textContent = frame.payload.llm.toUpperCase();
        }
        if (pingInterval) clearInterval(pingInterval);
        pingInterval = setInterval(sendPing, 4000);
        queryState();
        syncStoredCredentials();
        loadMemory();
        break;

      case "pong":
        const rtt = (performance.now() - pingStart).toFixed(1);
        pingValue.textContent = `${rtt} ms`;
        break;

      case "text.delta":
        setStatus("status-thinking", "THINKING");
        currentStreamedText += frame.payload.text || "";
        veronicaText.textContent = currentStreamedText;
        transcriptBox.scrollTop = transcriptBox.scrollHeight;
        break;

      case "text.done":
        setStatus("status-standby", "STANDBY");
        break;

      case "audio.delta":
        if (!audioMuted && frame.payload && frame.payload.audio) {
          incomingAudioChunks.push(frame.payload.audio);
        }
        break;

      case "audio.done":
        if (!audioMuted && incomingAudioChunks.length > 0) {
          playNeuralAudio(incomingAudioChunks);
          incomingAudioChunks = [];
        }
        break;

      case "tool.result":
        sfx.confirm();
        toolExecutionTag.style.display = "inline-flex";
        const toolBadge = document.createElement("span");
        toolBadge.className = "tool-badge-item";
        const toolName = frame.payload.tool || "";
        const res = frame.payload.result || {};

        if (toolName === "launch_application" || toolName.startsWith("launch:")) {
          const rawApp = res.app || toolName.split(":")[1] || "App";
          const display = rawApp.toLowerCase() === "vscode" ? "VS Code" : rawApp.charAt(0).toUpperCase() + rawApp.slice(1);
          toolBadge.textContent = res.status === "error" ? `⚠️ ${res.message || display}` : `🚀 Launched ${display}`;
        } else if (toolName === "close_application" || toolName.startsWith("close:")) {
          const rawApp = res.app || toolName.split(":")[1] || "App";
          const display = rawApp.toLowerCase() === "vscode" ? "VS Code" : rawApp.charAt(0).toUpperCase() + rawApp.slice(1);
          toolBadge.textContent = res.status === "success" ? `🛑 Closed ${display}` : `⚠️ ${res.message || display}`;
        } else if (toolName === "window_manager") {
          toolBadge.textContent = `🪟 Windows (${res.action || "list"})`;
        } else if (toolName === "timer_reminder") {
          toolBadge.textContent = `⏱️ Timer (${res.label || res.action || "active"})`;
        } else if (toolName === "clipboard_tool") {
          toolBadge.textContent = `📋 Clipboard`;
        } else if (toolName === "network_status") {
          toolBadge.textContent = `🌐 Network (${res.local_ip || "OK"})`;
        } else if (toolName === "media_control" || toolName.startsWith("media:")) {
          const act = res.action || toolName.split(":")[1] || "playback";
          const pctSuffix = res.volume_percent !== undefined ? ` (${res.volume_percent}%)` : "";
          const actMap = {
            play: "Playing Audio",
            play_pause: "Playback",
            pause: "Paused",
            volume_up: `Volume Up${pctSuffix}`,
            volume_down: `Volume Down${pctSuffix}`,
            set_volume: `Volume ${res.volume_percent !== undefined ? res.volume_percent + "%" : "Set"}`,
            mute: "Muted",
            next: "Next Track",
            prev: "Prev Track"
          };
          toolBadge.textContent = `🎵 ${actMap[act] || act}`;
        } else if (toolName === "iot_control" || toolName.startsWith("iot:")) {
          const iAct = res.action || "status";
          const iTgt = res.target ? ` · ${res.target}` : "";
          toolBadge.textContent = res.status === "confirmation_required"
            ? `🔒 Security Gate${iTgt}`
            : `🏠 IoT (${iAct}${iTgt})`;
        } else if (toolName === "get_veronica_logs" || toolName === "veronica_logs") {
          const aCnt = Array.isArray(res.recent_audit_events) ? res.recent_audit_events.length : 0;
          toolBadge.textContent = `📜 Audit Logs (${aCnt} events)`;
          if (cmdOutput && Array.isArray(res.recent_logs)) {
            cmdOutput.textContent = res.recent_logs.slice(-8).join("\n");
          }
        } else if (toolName === "telemetry") {
          toolBadge.textContent = `⚡ Telemetry Synced`;
        } else if (toolName === "workspace_macro") {
          toolBadge.textContent = `🎯 Workspace Macro`;
        } else if (toolName === "browser_agent" || toolName.startsWith("browser:")) {
          const bSite = res.site || res.action || "web";
          const bQuery = res.query ? `: ${res.query.slice(0, 22)}` : "";
          toolBadge.textContent = `🌐 Browser (${bSite}${bQuery})`;
        } else if (toolName === "app_interact" || toolName.startsWith("app_interact:")) {
          const aName = res.app || "App";
          const aAct = res.action ? ` · ${res.action}` : "";
          toolBadge.textContent = `🧩 ${aName}${aAct}`;
        } else if (toolName === "search_web") {
          toolBadge.textContent = `🌐 Web Search${res.query ? ": " + res.query.slice(0, 20) : ""}`;
        } else {
          toolBadge.textContent = `⚡ ${toolName}`;
        }
        toolExecutionTag.appendChild(toolBadge);

        if (toolName === "run_command" && res) {
          cmdOutput.textContent = res.stdout || res.stderr || res.message || "Executed with code " + res.exit_code;
        }
        if (toolName === "memory" && res) {
          if (res.notes !== undefined) {
            renderMemoryList(res.notes);
          } else {
            loadMemory();
          }
        }
        queryState();
        break;

      case "telemetry":
        if (frame.payload && frame.payload.telemetry) {
          renderTelemetry(frame.payload.telemetry);
        }
        if (frame.payload && frame.payload.provider) {
          engineLabel.textContent = frame.payload.provider.toUpperCase();
        }
        break;

      case "status":
        if (frame.payload && frame.payload.message) {
          speechState.textContent = frame.payload.message.toUpperCase();
        }
        if (frame.payload && frame.payload.provider) {
          engineLabel.textContent = frame.payload.provider.toUpperCase();
        }
        break;

      case "window.command":
        if (frame.payload && frame.payload.action === "show_mini") {
          window.location.href = `mini.html?port=${WS_PORT}&token=${WS_TOKEN}`;
        }
        break;

      case "error":
        sfx.error();
        speechState.textContent = "ERROR: " + (frame.payload.message || "Unknown");
        break;
    }
  }

  function sendPing() {
    if (ws && isConnected) {
      pingStart = performance.now();
      ws.send(JSON.stringify({ v: 1, id: "ping_" + Date.now(), type: "ping" }));
      queryState();
    }
  }

  function queryState() {
    if (ws && isConnected) {
      ws.send(JSON.stringify({ v: 1, id: "query_" + Date.now(), type: "state.query" }));
    }
  }

  // --- Neural Speech Audio Playback + Barge-In ---
  function stopActiveAudio() {
    if (activeAudio) {
      try {
        activeAudio.pause();
        activeAudio.src = "";
      } catch (e) {}
      activeAudio = null;
    }
    if (window.speechSynthesis) {
      try {
        window.speechSynthesis.cancel();
      } catch (e) {}
    }
  }

  function playNeuralAudio(base64Chunks) {
    stopActiveAudio();
    initAudioContext();
    setStatus("status-speaking", "SPEAKING");

    const fullBase64 = base64Chunks.join("");
    const binary = atob(fullBase64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }

    const blob = new Blob([bytes.buffer], { type: "audio/mp3" });
    const audioUrl = URL.createObjectURL(blob);
    const audio = new Audio(audioUrl);
    activeAudio = audio;

    if (audioCtx && analyser) {
      try {
        const source = audioCtx.createMediaElementSource(audio);
        source.connect(analyser);
        analyser.connect(audioCtx.destination);
      } catch (e) {
        // Element already connected or fallback
      }
    }

    audio.onended = function () {
      if (activeAudio === audio) activeAudio = null;
      setStatus("status-standby", "STANDBY");
      URL.revokeObjectURL(audioUrl);
    };

    audio.onerror = function () {
      if (activeAudio === audio) activeAudio = null;
      setStatus("status-standby", "STANDBY");
    };

    audio.play().catch(function (e) {
      console.warn("Auto-play blocked or audio error:", e);
      if (activeAudio === audio) activeAudio = null;
      setStatus("status-standby", "STANDBY");
    });
  }

  // --- System Vitals Telemetry Rendering ---
  function renderTelemetry(vit) {
    if (!vit) return;

    // CPU
    const cpu = vit.cpu_percent || 0;
    cpuPercent.textContent = `${cpu}%`;
    cpuBar.style.width = `${Math.min(100, Math.max(0, cpu))}%`;

    // CPU Cores Mini Bars
    if (Array.isArray(vit.cpu_cores)) {
      coresContainer.innerHTML = "";
      vit.cpu_cores.forEach(function (c) {
        const bar = document.createElement("div");
        bar.className = "core-mini-bar";
        bar.style.height = `${Math.max(8, c)}%`;
        coresContainer.appendChild(bar);
      });
    }

    // RAM
    const ramPct = vit.ram_percent || 0;
    ramBar.style.width = `${ramPct}%`;
    ramUsageText.textContent = `${vit.ram_used_gb || 0} / ${vit.ram_total_gb || 16} GB`;
    ramPercentText.textContent = `${ramPct}% utilized`;
    ramFreeText.textContent = `${vit.ram_free_gb || 0} GB headroom`;

    // Battery
    if (vit.battery) {
      const bPct = vit.battery.percent || 100;
      const charging = vit.battery.is_charging ? "⚡ " : "";
      batteryValue.textContent = `${charging}${bPct}%`;
    }

    // Top Processes
    if (Array.isArray(vit.top_processes)) {
      processList.innerHTML = "";
      vit.top_processes.slice(0, 5).forEach(function (p) {
        const row = document.createElement("div");
        row.className = "process-row";
        row.innerHTML = `<span class="proc-name">${p.name}</span><span class="proc-val">${p.memory_mb} MB</span>`;
        processList.appendChild(row);
      });
    }
  }

  // --- Persistent Microphone Authorization Stream ---
  let persistentMicStream = null;
  async function ensurePersistentMic() {
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      try {
        if (!persistentMicStream) {
          persistentMicStream = await navigator.mediaDevices.getUserMedia({ audio: true });
          console.log("[VERONICA] Microphone authorized persistently.");
        }
      } catch (err) {
        console.warn("[VERONICA] Microphone authorization notice:", err);
      }
    }
  }

  window.addEventListener("load", ensurePersistentMic);
  document.addEventListener("click", ensurePersistentMic, { once: true });
  document.addEventListener("keydown", ensurePersistentMic, { once: true });

  // --- Voice Input (STT via Web Speech API) ---
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    recognition.onstart = function () {
      isListening = true;
      micBtn.classList.add("active-mic");
      setStatus("status-listening", "LISTENING");
      speechState.textContent = "CAPTURING AUDIO...";
      sfx.blip();
    };

    recognition.onresult = function (event) {
      let transcript = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      chatInput.value = transcript;
    };

    recognition.onend = function () {
      isListening = false;
      micBtn.classList.remove("active-mic");
      setStatus("status-standby", "STANDBY");
      speechState.textContent = "PROCESSING DIRECTIVE";
      const query = chatInput.value.trim();
      if (query) {
        sendUserMessage(query);
      }
      // Resume wake word listener if enabled
      if (wakeWordActive) {
        setTimeout(startWakeWordListener, 400);
      }
    };

    recognition.onerror = function (e) {
      isListening = false;
      micBtn.classList.remove("active-mic");
      setStatus("status-standby", "STANDBY");
      if (wakeWordActive) {
        setTimeout(startWakeWordListener, 500);
      }
    };
  }

  // --- Hands-Free Wake-Word Recognition ("Hey Veronica") ---
  function initWakeWord() {
    if (!SpeechRecognition) return;
    wakeWordRecognition = new SpeechRecognition();
    wakeWordRecognition.continuous = true;
    wakeWordRecognition.interimResults = true;
    wakeWordRecognition.lang = "en-US";

    wakeWordRecognition.onresult = function (event) {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const phrase = event.results[i][0].transcript.toLowerCase();
        if (phrase.includes("veronica") || phrase.includes("hey veronica") || phrase.includes("jarvis")) {
          wakeWordRecognition.stop();
          sfx.blip();
          // Extract text after the wake word if any
          const cleanDirective = phrase
            .replace(/.*(?:hey\s+)?veronica/i, "")
            .replace(/.*jarvis/i, "")
            .trim();
          if (cleanDirective.length > 2) {
            sendUserMessage(cleanDirective);
          } else {
            toggleSpeech();
          }
          break;
        }
      }
    };

    wakeWordRecognition.onend = function () {
      if (wakeWordActive && !isListening) {
        try {
          wakeWordRecognition.start();
        } catch (e) {}
      }
    };
  }

  function startWakeWordListener() {
    if (!wakeWordRecognition) initWakeWord();
    if (wakeWordRecognition && wakeWordActive && !isListening) {
      try {
        wakeWordRecognition.start();
      } catch (e) {}
    }
  }

  function toggleWakeWord() {
    wakeWordActive = !wakeWordActive;
    wakeWordBtn.classList.toggle("active", wakeWordActive);
    wakeWordLabel.textContent = wakeWordActive ? "WAKE WORD: ON" : "WAKE WORD: OFF";
    if (wakeWordActive) {
      sfx.confirm();
      startWakeWordListener();
    } else {
      if (wakeWordRecognition) {
        try {
          wakeWordRecognition.stop();
        } catch (e) {}
      }
    }
  }

  wakeWordBtn.addEventListener("click", toggleWakeWord);

  const miniHudBtn = document.getElementById("miniHudBtn");
  if (miniHudBtn) {
    miniHudBtn.addEventListener("click", function () {
      sfx.blip();
      if (ws && isConnected) {
        ws.send(JSON.stringify({
          v: 1,
          id: "cmd_" + Date.now(),
          type: "window.command",
          payload: { action: "show_mini" },
        }));
      }
      window.location.href = `mini.html?port=${WS_PORT}&token=${WS_TOKEN}`;
    });
  }

  function toggleSpeech() {
    initAudioContext();
    if (!recognition) {
      alert("Microphone recognition requires Chrome, Edge, or an active speech engine.");
      return;
    }
    if (isListening) {
      recognition.stop();
    } else {
      if (wakeWordRecognition) {
        try {
          wakeWordRecognition.stop();
        } catch (e) {}
      }
      chatInput.value = "";
      recognition.start();
    }
  }

  micBtn.addEventListener("click", toggleSpeech);

  // Push-to-Talk via Spacebar
  window.addEventListener("keydown", function (e) {
    if (e.code === "Space" && document.activeElement !== chatInput && document.activeElement !== cmdInput) {
      e.preventDefault();
      if (e.repeat) return;
      stopActiveAudio();
      if (!isListening && recognition) {
        try {
          recognition.start();
        } catch (err) {}
      }
    }
  });

  window.addEventListener("keyup", function (e) {
    if (e.code === "Space" && document.activeElement !== chatInput && document.activeElement !== cmdInput) {
      e.preventDefault();
      if (isListening && recognition) {
        recognition.stop();
      }
    }
  });

  // --- Multimodal Screen Vision Capture ---
  async function captureAndAnalyzeScreen() {
    initAudioContext();
    sfx.blip();
    setStatus("status-thinking", "CAPTURING DISPLAY...");
    speechState.textContent = "OPTICAL RECON ACTIVE";

    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: { cursor: "always" },
        audio: false,
      });

      const video = document.createElement("video");
      video.srcObject = stream;
      await video.play();

      const offCanvas = document.createElement("canvas");
      offCanvas.width = 1280;
      offCanvas.height = 720;
      const offCtx = offCanvas.getContext("2d");
      offCtx.drawImage(video, 0, 0, offCanvas.width, offCanvas.height);

      // Stop stream tracks immediately
      stream.getTracks().forEach((t) => t.stop());

      const base64Data = offCanvas.toDataURL("image/jpeg", 0.75);

      toolExecutionTag.style.display = "inline-block";
      toolExecutionTag.textContent = "Optical Recon: Display Frame Captured";
      currentStreamedText = "";
      veronicaText.textContent = "Analyzing visual contents of active display...";
      incomingAudioChunks = [];

      if (ws && isConnected) {
        ws.send(
          JSON.stringify({
            v: 1,
            id: "screen_" + Date.now(),
            type: "screen.analyze",
            payload: {
              image: base64Data,
              prompt: "Analyze the user's active display. Provide concise, tactical feedback on what is open, code/errors visible, and next steps.",
              synthesize: !audioMuted,
            },
          })
        );
      }
    } catch (err) {
      sfx.error();
      console.warn("Screen capture cancelled or unavailable:", err);
      setStatus("status-standby", "STANDBY");
      speechState.textContent = "OPTICAL RECON CANCELLED";
    }
  }

  if (analyzeScreenBtn) analyzeScreenBtn.addEventListener("click", captureAndAnalyzeScreen);
  if (analyzeScreenChip) analyzeScreenChip.addEventListener("click", captureAndAnalyzeScreen);

  // --- Tactical Workspace Macros ---
  function triggerWorkspaceMacro(macroName) {
    initAudioContext();
    sfx.blip();
    toolExecutionTag.style.display = "inline-block";
    toolExecutionTag.textContent = `Deploying Workspace: ${macroName.toUpperCase()}`;
    sendUserMessage(`${macroName} mode`);
  }

  document.querySelectorAll("[data-macro]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      triggerWorkspaceMacro(this.getAttribute("data-macro"));
    });
  });

  // --- Chat Message Submission & Directive Rendering ---
  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function appendUserDirective(text) {
    if (!transcriptBox) return;
    const existingDirective = transcriptBox.querySelector(".user-directive-row");
    if (existingDirective) {
      existingDirective.remove();
    }
    const row = document.createElement("div");
    row.className = "user-directive-row";
    row.innerHTML = `<span class="user-directive-tag">DIRECTIVE:</span><span class="user-directive-text">${escapeHtml(text)}</span>`;
    const veronicaMsg = transcriptBox.querySelector(".veronica-message");
    if (veronicaMsg) {
      transcriptBox.insertBefore(row, veronicaMsg);
    } else {
      transcriptBox.appendChild(row);
    }
    transcriptBox.scrollTop = transcriptBox.scrollHeight;
  }

  function sendUserMessage(text) {
    if (!text.trim() || !ws || !isConnected) return;

    stopActiveAudio();
    initAudioContext();
    appendUserDirective(text.trim());
    toolExecutionTag.innerHTML = "";
    toolExecutionTag.style.display = "none";
    currentStreamedText = "";
    veronicaText.innerHTML = `<span class="thinking-dots"><span>•</span><span>•</span><span>•</span></span>`;
    incomingAudioChunks = [];

    const frame = {
      v: 1,
      id: "msg_" + Date.now(),
      type: "text.input",
      payload: {
        text: text.trim(),
        synthesize: !audioMuted,
      },
    };
    ws.send(JSON.stringify(frame));
    chatInput.value = "";
  }

  chatForm.addEventListener("submit", function (e) {
    e.preventDefault();
    sendUserMessage(chatInput.value);
  });

  // Quick Chips
  document.querySelectorAll(".chip[data-query]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      sendUserMessage(this.getAttribute("data-query"));
    });
  });

  // App Matrix Quick Deploy
  document.querySelectorAll(".app-card").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const app = this.getAttribute("data-app");
      executeTool("launch_app", { app: app });
    });
  });

  function executeTool(name, params) {
    if (ws && isConnected) {
      sfx.blip();
      ws.send(
        JSON.stringify({
          v: 1,
          id: "tool_" + Date.now(),
          type: "tool.execute",
          payload: { tool: name, params: params || {} },
        })
      );
    }
  }

  // Media Controls
  document.getElementById("volUpBtn").addEventListener("click", () => executeTool("media_control", { action: "volume_up" }));
  document.getElementById("volDownBtn").addEventListener("click", () => executeTool("media_control", { action: "volume_down" }));
  document.getElementById("playPauseBtn").addEventListener("click", () => executeTool("media_control", { action: "play_pause" }));
  document.getElementById("mediaMuteBtn").addEventListener("click", () => executeTool("media_control", { action: "mute" }));

  // Audio Output Toggle (Veronica's voice)
  muteAudioBtn.addEventListener("click", function () {
    audioMuted = !audioMuted;
    if (audioMuted) stopActiveAudio();
    muteAudioIcon.textContent = audioMuted ? "🔇" : "🔊";
    muteAudioBtn.classList.toggle("active", !audioMuted);
    if (!audioMuted) sfx.blip();
  });

  // Terminal Command Runner
  runCmdBtn.addEventListener("click", function () {
    const cmd = cmdInput.value.trim();
    if (cmd) {
      cmdOutput.textContent = "Executing: " + cmd + "...";
      executeTool("run_command", { command: cmd });
      cmdInput.value = "";
    }
  });

  // Vitals & Diagnostics Buttons
  refreshVitalsBtn.addEventListener("click", queryState);
  diagBtn.addEventListener("click", function () {
    triggerWorkspaceMacro("scan");
  });

  // Memory Panel
  function renderMemoryList(notes) {
    if (!memoryList) return;
    memoryList.innerHTML = "";
    if (!notes || Object.keys(notes).length === 0) {
      memoryList.innerHTML = `<div class="memory-empty-state">NO STORED MEMORIES</div>`;
      return;
    }

    Object.entries(notes).forEach(function ([key, val]) {
      const row = document.createElement("div");
      row.className = "memory-item-row";

      const infoDiv = document.createElement("div");
      infoDiv.className = "memory-content";

      const kSpan = document.createElement("span");
      kSpan.className = "memory-key";
      kSpan.textContent = `${key}:`;

      const vSpan = document.createElement("span");
      vSpan.className = "memory-val";
      vSpan.textContent = typeof val === "object" ? JSON.stringify(val) : String(val);

      infoDiv.appendChild(kSpan);
      infoDiv.appendChild(vSpan);

      const delBtn = document.createElement("button");
      delBtn.className = "memory-del-btn";
      delBtn.title = `Delete memory '${key}'`;
      delBtn.textContent = "✕";
      delBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        sfx.blip();
        executeTool("memory", { action: "delete", key: key });
      });

      row.appendChild(infoDiv);
      row.appendChild(delBtn);
      memoryList.appendChild(row);
    });
  }

  saveMemoryBtn.addEventListener("click", function () {
    const k = memoryKeyInput.value.trim();
    const v = memoryValInput.value.trim();
    if (k && v) {
      executeTool("memory", { action: "set", key: k, value: v });
      memoryKeyInput.value = "";
      memoryValInput.value = "";
    }
  });

  function loadMemory() {
    executeTool("memory", { action: "list" });
  }

  function syncStoredCredentials() {
    const groq = localStorage.getItem("veronica_groq_key") || "";
    const openai = localStorage.getItem("veronica_openai_key") || "";
    const gemini = localStorage.getItem("veronica_gemini_key") || "";
    const anthropic = localStorage.getItem("veronica_anthropic_key") || "";
    const voice = localStorage.getItem("veronica_voice") || "en-US-AvaNeural";

    if (ws && isConnected && (groq || openai || gemini || anthropic || voice)) {
      ws.send(
        JSON.stringify({
          v: 1,
          id: "sync_settings_" + Date.now(),
          type: "settings.update",
          payload: {
            keys: { groq, openai, gemini, anthropic },
            voice: voice,
            source: "auto_sync",
          },
        })
      );
    }
  }

  // Settings Modal Handlers
  settingsBtn.addEventListener("click", function () {
    settingsModal.classList.add("open");
  });

  closeSettingsBtn.addEventListener("click", function () {
    settingsModal.classList.remove("open");
  });

  saveSettingsBtn.addEventListener("click", function () {
    const groq = groqKeyInput.value.trim();
    const openai = openaiKeyInput.value.trim();
    const gemini = geminiKeyInput.value.trim();
    const anthropic = anthropicKeyInput.value.trim();
    const voice = voiceSelect.value;
    const customUrl = wsUrlInput.value.trim();
    const customToken = wsTokenInput.value.trim();

    localStorage.setItem("veronica_groq_key", groq);
    localStorage.setItem("veronica_openai_key", openai);
    localStorage.setItem("veronica_gemini_key", gemini);
    localStorage.setItem("veronica_anthropic_key", anthropic);
    localStorage.setItem("veronica_voice", voice);
    localStorage.setItem("veronica_port", customUrl.split(":").pop());
    localStorage.setItem("veronica_token", customToken);

    if (ws && isConnected) {
      ws.send(
        JSON.stringify({
          v: 1,
          id: "settings_" + Date.now(),
          type: "settings.update",
          payload: {
            keys: { groq, openai, gemini, anthropic },
            voice: voice,
            source: "user_save",
          },
        })
      );
    }

    sfx.confirm();
    settingsModal.classList.remove("open");
  });

  testAudioBtn.addEventListener("click", function () {
    const testText = "Veronica tactical speech synthesizer test. All systems operational.";
    if (ws && isConnected) {
      ws.send(
        JSON.stringify({
          v: 1,
          id: "test_tts_" + Date.now(),
          type: "tts.request",
          payload: { text: testText },
        })
      );
    }
  });

  // Initial Connection
  connectWs();
})();
