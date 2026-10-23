/**
 * VERONICA // TACTICAL DESKTOP ASSISTANT - CLIENT APPLICATION
 * Stark Industries HUD Architecture & Audio Reactive Core
 */

(function () {
  "use strict";

  // --- Configuration & State ---
  const urlParams = new URLSearchParams(window.location.search);
  const WS_PORT = urlParams.get("port") || localStorage.getItem("veronica_port") || "8765";
  const WS_TOKEN = urlParams.get("token") || localStorage.getItem("veronica_token") || "";
  let wsUrl = `ws://127.0.0.1:${WS_PORT}`;

  let ws = null;
  let isConnected = false;
  let audioMuted = false;
  let isListening = false;
  let recognition = null;
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

  // --- Web Audio & Visualizer Setup ---
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
      // Send Hello with Token
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
        if (frame.payload && frame.payload.llm) {
          engineLabel.textContent = frame.payload.llm.toUpperCase();
        }
        // Start periodic ping & telemetry
        if (pingInterval) clearInterval(pingInterval);
        pingInterval = setInterval(sendPing, 4000);
        queryState();
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
        toolExecutionTag.style.display = "inline-block";
        toolExecutionTag.textContent = `Executed: ${frame.payload.tool}`;
        if (frame.payload.tool === "run_command" && frame.payload.result) {
          const res = frame.payload.result;
          cmdOutput.textContent = res.stdout || res.stderr || res.message || "Executed with code " + res.exit_code;
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
        break;

      case "error":
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

  // --- Neural Speech Audio Playback ---
  function playNeuralAudio(base64Chunks) {
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
      setStatus("status-standby", "STANDBY");
      URL.revokeObjectURL(audioUrl);
    };

    audio.onerror = function () {
      setStatus("status-standby", "STANDBY");
    };

    audio.play().catch(function (e) {
      console.warn("Auto-play blocked or audio error:", e);
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
    };

    recognition.onerror = function (e) {
      isListening = false;
      micBtn.classList.remove("active-mic");
      setStatus("status-standby", "STANDBY");
      console.warn("Recognition error:", e);
    };
  } else {
    micBtn.title = "Web Speech API not supported in this browser. Use text input.";
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
      chatInput.value = "";
      recognition.start();
    }
  }

  micBtn.addEventListener("click", toggleSpeech);

  // Push-to-Talk via Spacebar
  window.addEventListener("keydown", function (e) {
    if (e.code === "Space" && document.activeElement !== chatInput && document.activeElement !== cmdInput) {
      e.preventDefault();
      if (!isListening && recognition) {
        recognition.start();
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

  // --- Chat Message Submission ---
  function sendUserMessage(text) {
    if (!text.trim() || !ws || !isConnected) return;

    initAudioContext();
    toolExecutionTag.style.display = "none";
    currentStreamedText = "";
    veronicaText.textContent = "Analyzing directive...";
    incomingAudioChunks = [];

    const frame = {
      v: 1,
      id: "msg_" + Date.now(),
      type: "text.input",
      payload: {
        text: text,
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
  document.querySelectorAll(".chip").forEach(function (btn) {
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
      ws.send(JSON.stringify({
        v: 1,
        id: "tool_" + Date.now(),
        type: "tool.execute",
        payload: { tool: name, params: params || {} },
      }));
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
    muteAudioIcon.textContent = audioMuted ? "🔇" : "🔊";
    muteAudioBtn.classList.toggle("active", !audioMuted);
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
    sendUserMessage("Run full diagnostic report on hardware vitals, memory headroom and active processes.");
  });

  // Memory Panel
  saveMemoryBtn.addEventListener("click", function () {
    const k = memoryKeyInput.value.trim();
    const v = memoryValInput.value.trim();
    if (k && v) {
      executeTool("memory", { action: "set", key: k, value: v });
      memoryKeyInput.value = "";
      memoryValInput.value = "";
      setTimeout(loadMemory, 500);
    }
  });

  function loadMemory() {
    executeTool("memory", { action: "list" });
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
      ws.send(JSON.stringify({
        v: 1,
        id: "settings_" + Date.now(),
        type: "settings.update",
        payload: {
          keys: { groq, openai, gemini, anthropic },
          voice: voice,
        },
      }));
    }

    settingsModal.classList.remove("open");
  });

  testAudioBtn.addEventListener("click", function () {
    const testText = "Veronica tactical speech synthesizer test. All systems operational.";
    if (ws && isConnected) {
      ws.send(JSON.stringify({
        v: 1,
        id: "test_tts_" + Date.now(),
        type: "tts.request",
        payload: { text: testText },
      }));
    }
  });

  // Initial Connection
  connectWs();
})();
