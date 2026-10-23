/**
 * VERONICA // MINI HUD DESKTOP CLIENT
 * Audio-reactive compact Stark widget, wake-word ambient listener,
 * and system tray communication bridge.
 */

(function () {
  "use strict";

  const urlParams = new URLSearchParams(window.location.search);
  const WS_PORT = urlParams.get("port") || localStorage.getItem("veronica_port") || "8765";
  const WS_TOKEN = urlParams.get("token") || localStorage.getItem("veronica_token") || "";

  if (WS_TOKEN) {
    localStorage.setItem("veronica_token", WS_TOKEN);
    localStorage.setItem("veronica_port", WS_PORT);
  }

  let ws = null;
  let isConnected = false;
  let isListening = false;
  let wakeWordActive = true;
  let recognition = null;
  let wakeWordRecognition = null;
  let pingInterval = null;
  let pingStart = 0;
  let activeAudio = null;
  let audioQueue = [];
  let isPlayingAudio = false;

  // DOM
  const miniStatusPill = document.getElementById("miniStatusPill");
  const miniExpandBtn = document.getElementById("miniExpandBtn");
  const miniTrayBtn = document.getElementById("miniTrayBtn");
  const miniCoreCanvas = document.getElementById("miniCoreCanvas");
  const arcContainer = document.querySelector(".arc-container");
  const micIndicator = document.getElementById("micIndicator");
  const miniCpuVal = document.getElementById("miniCpuVal");
  const miniRamVal = document.getElementById("miniRamVal");
  const miniRttVal = document.getElementById("miniRttVal");
  const miniEngineBadge = document.getElementById("miniEngineBadge");
  const miniTranscript = document.getElementById("miniTranscript");
  const miniUserText = document.getElementById("miniUserText");
  const miniVeronicaText = document.getElementById("miniVeronicaText");
  const miniForm = document.getElementById("miniForm");
  const miniInput = document.getElementById("miniInput");
  const miniWakeWordBtn = document.getElementById("miniWakeWordBtn");
  const miniWakeLabel = document.getElementById("miniWakeLabel");

  // Web Audio & Synthesizer SFX
  let audioCtx = null;
  let analyser = null;
  let audioDataArray = null;

  function initAudioCtx() {
    if (!audioCtx) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (AudioContextClass) {
        audioCtx = new AudioContextClass();
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 64;
        audioDataArray = new Uint8Array(analyser.frequencyBinCount);
      }
    }
    if (audioCtx && audioCtx.state === "suspended") {
      audioCtx.resume();
    }
  }

  const sfx = {
    boot: function () {
      initAudioCtx();
      if (!audioCtx) return;
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(220, audioCtx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(880, audioCtx.currentTime + 0.18);
      gain.gain.setValueAtTime(0.08, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.22);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start();
      osc.stop(audioCtx.currentTime + 0.24);
    },
    blip: function () {
      initAudioCtx();
      if (!audioCtx) return;
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = "triangle";
      osc.frequency.setValueAtTime(600, audioCtx.currentTime);
      osc.frequency.setValueAtTime(1200, audioCtx.currentTime + 0.05);
      gain.gain.setValueAtTime(0.1, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.12);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start();
      osc.stop(audioCtx.currentTime + 0.13);
    },
    confirm: function () {
      initAudioCtx();
      if (!audioCtx) return;
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(440, audioCtx.currentTime);
      osc.frequency.setValueAtTime(880, audioCtx.currentTime + 0.08);
      gain.gain.setValueAtTime(0.1, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.25);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start();
      osc.stop(audioCtx.currentTime + 0.26);
    },
  };

  // Mini Arc Reactor Canvas (86x86)
  const ctx = miniCoreCanvas.getContext("2d");
  let coreRotation = 0;
  let targetEnergy = 0.1;
  let currentEnergy = 0.1;

  function renderCore() {
    requestAnimationFrame(renderCore);
    const w = 86;
    const h = 86;
    const cx = w / 2;
    const cy = h / 2;
    ctx.clearRect(0, 0, w, h);

    if (analyser) {
      analyser.getByteFrequencyData(audioDataArray);
      let sum = 0;
      for (let i = 0; i < audioDataArray.length; i++) sum += audioDataArray[i];
      targetEnergy = Math.max(0.1, sum / (audioDataArray.length * 255));
    }
    currentEnergy += (targetEnergy - currentEnergy) * 0.2;
    coreRotation += 0.02 + currentEnergy * 0.1;

    // Outer Glow
    const glowRadius = 38 + currentEnergy * 10;
    const grad = ctx.createRadialGradient(cx, cy, 10, cx, cy, glowRadius);
    grad.addColorStop(0, "rgba(0, 243, 255, " + (0.4 + currentEnergy * 0.5) + ")");
    grad.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(cx, cy, glowRadius, 0, Math.PI * 2);
    ctx.fill();

    // Rotating Ring 1
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(coreRotation);
    ctx.strokeStyle = "rgba(0, 243, 255, 0.6)";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(0, 0, 36, 0, Math.PI * 2);
    ctx.stroke();

    for (let i = 0; i < 12; i++) {
      const angle = (i * Math.PI * 2) / 12;
      ctx.beginPath();
      ctx.moveTo(Math.cos(angle) * 36, Math.sin(angle) * 36);
      ctx.lineTo(Math.cos(angle) * 32, Math.sin(angle) * 32);
      ctx.strokeStyle = i % 3 === 0 ? "#00f3ff" : "rgba(0, 243, 255, 0.4)";
      ctx.lineWidth = i % 3 === 0 ? 2 : 1;
      ctx.stroke();
    }
    ctx.restore();

    // Counter-rotating Inner Brackets
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(-coreRotation * 1.5);
    ctx.strokeStyle = "rgba(0, 119, 255, 0.8)";
    ctx.lineWidth = 2;
    for (let i = 0; i < 3; i++) {
      ctx.beginPath();
      ctx.arc(0, 0, 24 + currentEnergy * 4, (i * Math.PI * 2) / 3, ((i + 1) * Math.PI * 2) / 3 - 0.4);
      ctx.stroke();
    }
    ctx.restore();

    // Bright Center Core
    ctx.fillStyle = isListening ? "rgba(255, 183, 0, 0.85)" : "rgba(0, 243, 255, 0.85)";
    ctx.beginPath();
    ctx.arc(cx, cy, 7 + currentEnergy * 5, 0, Math.PI * 2);
    ctx.fill();
  }
  renderCore();

  // Status helper
  function setStatus(cls, label) {
    miniStatusPill.className = "mini-status-pill " + cls;
    miniStatusPill.textContent = label;
  }

  // WebSocket Connection
  function connectWs() {
    const wsUrl = `ws://127.0.0.1:${WS_PORT}`;
    setStatus("status-standby", "CONNECTING");

    try {
      ws = new WebSocket(wsUrl);
    } catch (e) {
      setStatus("status-standby", "OFFLINE");
      return;
    }

    ws.onopen = function () {
      ws.send(JSON.stringify({
        v: 1,
        id: "auth_" + Date.now(),
        type: "hello",
        payload: { token: WS_TOKEN },
      }));
    };

    ws.onmessage = function (event) {
      try {
        const frame = JSON.parse(event.data);
        handleFrame(frame);
      } catch (e) {
        console.error("Frame error:", e);
      }
    };

    ws.onclose = function () {
      isConnected = false;
      setStatus("status-standby", "OFFLINE");
      if (pingInterval) clearInterval(pingInterval);
      setTimeout(connectWs, 3000);
    };
  }

  let streamedText = "";
  let audioChunks = [];

  function handleFrame(frame) {
    switch (frame.type) {
      case "ready":
        isConnected = true;
        setStatus("status-standby", "STANDBY");
        sfx.boot();
        if (frame.payload && frame.payload.llm) {
          miniEngineBadge.textContent = frame.payload.llm.toUpperCase();
        }
        if (pingInterval) clearInterval(pingInterval);
        pingInterval = setInterval(sendPing, 4000);
        queryState();
        break;

      case "pong":
        const rtt = (performance.now() - pingStart).toFixed(1);
        miniRttVal.textContent = `${rtt}ms`;
        break;

      case "text.delta":
        setStatus("status-thinking", "THINKING");
        streamedText += frame.payload.text || "";
        miniVeronicaText.textContent = streamedText;
        miniTranscript.scrollTop = miniTranscript.scrollHeight;
        break;

      case "text.done":
        setStatus("status-standby", "STANDBY");
        break;

      case "audio.delta":
        if (frame.payload && frame.payload.audio) {
          audioChunks.push(frame.payload.audio);
        }
        break;

      case "audio.done":
        if (audioChunks.length > 0) {
          playNeuralAudio(audioChunks);
          audioChunks = [];
        }
        break;

      case "telemetry":
        if (frame.payload) {
          const t = frame.payload.telemetry || frame.payload;
          if (t.cpu && t.cpu.total_percent !== undefined) {
            miniCpuVal.textContent = `${Math.round(t.cpu.total_percent)}%`;
          }
          if (t.memory && t.memory.percent !== undefined) {
            miniRamVal.textContent = `${Math.round(t.memory.percent)}%`;
          }
        }
        break;

      case "window.command":
        if (frame.payload) {
          if (frame.payload.action === "show_mini") {
            window.focus();
            sfx.blip();
            setStatus("status-listening", "LISTENING");
            startListening();
          } else if (frame.payload.action === "show_full") {
            switchToFullDeck();
          }
        }
        break;
    }
  }

  function sendPing() {
    if (ws && isConnected) {
      pingStart = performance.now();
      ws.send(JSON.stringify({ v: 1, id: "ping_" + Date.now(), type: "ping" }));
    }
  }

  function queryState() {
    if (ws && isConnected) {
      ws.send(JSON.stringify({ v: 1, id: "state_" + Date.now(), type: "state.query" }));
    }
  }

  // Audio Playback
  function playNeuralAudio(chunks) {
    initAudioCtx();
    const b64Data = chunks.join("");
    const byteCharacters = atob(b64Data);
    const byteNumbers = new Array(byteCharacters.length);
    for (let i = 0; i < byteCharacters.length; i++) {
      byteNumbers[i] = byteCharacters.charCodeAt(i);
    }
    const byteArray = new Uint8Array(byteNumbers);
    const blob = new Blob([byteArray], { type: "audio/mp3" });
    const url = URL.createObjectURL(blob);

    const audio = new Audio(url);
    if (audioCtx && analyser) {
      try {
        const source = audioCtx.createMediaElementSource(audio);
        source.connect(analyser);
        analyser.connect(audioCtx.destination);
      } catch (e) {}
    }

    audio.onended = function () {
      URL.revokeObjectURL(url);
    };
    audio.play().catch(function (e) {
      console.warn("Audio playback error:", e);
    });
  }

  // Transmit command
  function transmitText(text) {
    if (!text || !isConnected) return;
    initAudioCtx();
    sfx.blip();
    miniUserText.style.display = "block";
    miniUserText.textContent = text;
    streamedText = "";
    miniVeronicaText.textContent = "Processing...";
    setStatus("status-thinking", "THINKING");

    ws.send(JSON.stringify({
      v: 1,
      id: "txt_" + Date.now(),
      type: "text.input",
      payload: { text: text, synthesize: true },
    }));
  }

  // Speech Recognition & Wake-Word
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (SpeechRec) {
    recognition = new SpeechRec();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    recognition.onstart = function () {
      isListening = true;
      setStatus("status-listening", "LISTENING");
      targetEnergy = 0.5;
    };

    recognition.onresult = function (event) {
      let transcript = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      miniUserText.style.display = "block";
      miniUserText.textContent = transcript;
      if (event.results[0].isFinal) {
        transmitText(transcript.trim());
      }
    };

    recognition.onerror = function () {
      isListening = false;
      setStatus("status-standby", "STANDBY");
      restartWakeWord();
    };

    recognition.onend = function () {
      isListening = false;
      setStatus("status-standby", "STANDBY");
      restartWakeWord();
    };

    // Wake Word Ambient Recognition
    wakeWordRecognition = new SpeechRec();
    wakeWordRecognition.continuous = true;
    wakeWordRecognition.interimResults = true;
    wakeWordRecognition.lang = "en-US";

    wakeWordRecognition.onresult = function (event) {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const text = event.results[i][0].transcript.toLowerCase();
        if (text.includes("hey veronica") || text.includes("veronica")) {
          wakeWordRecognition.stop();
          sfx.blip();
          if (ws && isConnected) {
            ws.send(JSON.stringify({
              v: 1,
              id: "wake_" + Date.now(),
              type: "wake_word.detected",
              payload: { phrase: text.trim() },
            }));
          }
          startListening();
          break;
        }
      }
    };

    wakeWordRecognition.onend = function () {
      if (wakeWordActive && !isListening) {
        try { wakeWordRecognition.start(); } catch (e) {}
      }
    };

    try { wakeWordRecognition.start(); } catch (e) {}
  }

  function startListening() {
    if (wakeWordRecognition) {
      try { wakeWordRecognition.stop(); } catch (e) {}
    }
    if (recognition) {
      try { recognition.start(); } catch (e) {}
    }
  }

  function restartWakeWord() {
    if (wakeWordActive && wakeWordRecognition && !isListening) {
      try { wakeWordRecognition.start(); } catch (e) {}
    }
  }

  // Push-to-Talk (Spacebar & Click)
  arcContainer.addEventListener("click", function () {
    initAudioCtx();
    if (isListening && recognition) {
      recognition.stop();
    } else {
      sfx.blip();
      startListening();
    }
  });

  window.addEventListener("keydown", function (e) {
    if (e.code === "Space" && document.activeElement !== miniInput && !isListening) {
      e.preventDefault();
      initAudioCtx();
      startListening();
    }
  });

  window.addEventListener("keyup", function (e) {
    if (e.code === "Space" && document.activeElement !== miniInput && isListening) {
      e.preventDefault();
      if (recognition) recognition.stop();
    }
  });

  // Form submit
  miniForm.addEventListener("submit", function (e) {
    e.preventDefault();
    const val = miniInput.value.trim();
    if (val) {
      transmitText(val);
      miniInput.value = "";
    }
  });

  // Chips
  document.querySelectorAll(".chip-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const act = btn.getAttribute("data-action");
      if (act === "vitals") transmitText("Check system vitals");
      else if (act === "focus") transmitText("Deploy focus mode");
      else if (act === "dev") transmitText("Deploy dev workspace macro");
      else if (act === "vision") transmitText("Analyze active screen");
    });
  });

  // Toggle Wake-Word
  miniWakeWordBtn.addEventListener("click", function () {
    wakeWordActive = !wakeWordActive;
    if (wakeWordActive) {
      miniWakeWordBtn.className = "wake-word-pill wake-active";
      miniWakeLabel.textContent = "WAKE: ON";
      restartWakeWord();
    } else {
      miniWakeWordBtn.className = "wake-word-pill";
      miniWakeLabel.textContent = "WAKE: OFF";
      if (wakeWordRecognition) {
        try { wakeWordRecognition.stop(); } catch (e) {}
      }
    }
  });

  // Switch to Full Deck
  function switchToFullDeck() {
    const fullUrl = `index.html?port=${WS_PORT}&token=${WS_TOKEN}`;
    window.location.href = fullUrl;
  }

  miniExpandBtn.addEventListener("click", function () {
    if (ws && isConnected) {
      ws.send(JSON.stringify({
        v: 1,
        id: "cmd_" + Date.now(),
        type: "window.command",
        payload: { action: "show_full" },
      }));
    }
    switchToFullDeck();
  });

  // Minimize to Tray
  miniTrayBtn.addEventListener("click", function () {
    sfx.blip();
    if (ws && isConnected) {
      ws.send(JSON.stringify({
        v: 1,
        id: "cmd_" + Date.now(),
        type: "window.command",
        payload: { action: "minimize" },
      }));
    }
    window.close();
  });

  // Init
  connectWs();
})();
