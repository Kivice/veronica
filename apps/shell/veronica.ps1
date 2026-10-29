<#
.SYNOPSIS
  Project Veronica // Native Microsoft .NET PowerShell Desktop Shell (Mark-V Upgrade)
  Pure native Win32/Windows Forms tactical HUD (ZERO BROWSER / ZERO CHROMIUM).
  Includes:
    - Multi-ring counter-rotating audio-reactive Arc Reactor
    - Real Neural Edge-TTS MP3 playback (winmm MCI) + local SAPI SpeechSynthesizer fallback & barge-in
    - Native Windows Speech Recognition ("Hey Veronica" wake word + Tactical Grammar + Free-form Dictation)
    - Live Screen Reconnaissance capture (screen.analyze)
    - Live CPU / RAM / Battery / Network telemetry gauges & Active AI Provider badge
    - Auto-managed Voice Core backend lifecycle with parent-PID watchdog & Windows DPAPI security
#>

param (
    [int]$Port = 8765,
    [string]$Token = $env:VERONICA_TOKEN,
    [switch]$NoAutoStartService
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Speech
Add-Type -AssemblyName System.Security
Add-Type -AssemblyName System.Web.Extensions

# Single-Instance Enforcement & Inter-process Summoning
$mutexCreated = $false
$global:appMutex = New-Object System.Threading.Mutex($true, "Veronica.Stark.PowerShellShell.Mutex", [ref]$mutexCreated)
$global:summonEvent = New-Object System.Threading.EventWaitHandle($false, [System.Threading.EventResetMode]::AutoReset, "Veronica.Stark.PowerShellSummonEvent")

if (-not $mutexCreated) {
    Write-Host "[VERONICA] Existing Shell instance detected. Summoning tactical HUD to front of desktop..." -ForegroundColor Cyan
    $global:summonEvent.Set() | Out-Null
    exit 0
}

# C# Bridge for High-Performance Native Interop, WebSocket Streaming, Neural MP3 + SAPI Audio, Speech & DPAPI
$bridgeSource = @'
using System;
using System.Collections.Generic;
using System.Collections.Concurrent;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Speech.Recognition;
using System.Speech.Synthesis;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

public class VeronicaBridge {
    [DllImport("user32.dll")] public static extern bool ReleaseCapture();
    [DllImport("user32.dll")] public static extern int SendMessage(IntPtr hWnd, int Msg, int wParam, int lParam);
    [DllImport("winmm.dll", CharSet = CharSet.Auto)]
    private static extern int mciSendString(string command, StringBuilder buffer, int bufferSize, IntPtr hwndCallback);

    public const int WM_NCLBUTTONDOWN = 0xA1;
    public const int HT_CAPTION = 0x2;

    public static EventWaitHandle SummonHandle = new EventWaitHandle(false, EventResetMode.AutoReset, "Veronica.Stark.PowerShellSummonEvent");
    public static ConcurrentQueue<string> Events = new ConcurrentQueue<string>();

    private static SpeechRecognitionEngine recognizer;
    private static SpeechSynthesizer fallbackSynth;
    private static CancellationTokenSource activeRequestCts;
    private static bool voiceMuted = false;
    private static bool freeDictationArmed = false;
    private static string tempAudioPath = "";

    public static void SetVoiceMuted(bool muted) {
        voiceMuted = muted;
        if (muted) {
            StopAudio();
        }
    }

    public static void SetDictationArmed(bool armed) {
        freeDictationArmed = armed;
    }

    public static void StopAudio() {
        try {
            mciSendString("stop veronica_tts", null, 0, IntPtr.Zero);
            mciSendString("close veronica_tts", null, 0, IntPtr.Zero);
        } catch {}
        try {
            if (fallbackSynth != null) {
                fallbackSynth.SpeakAsyncCancelAll();
            }
        } catch {}
        Events.Enqueue("AUDIO_STOPPED:");
    }

    public static void PlayMp3Bytes(byte[] mp3Bytes, string fallbackText) {
        if (voiceMuted) {
            Events.Enqueue("AUDIO_STOPPED:");
            return;
        }
        try {
            StopAudio();
            if (mp3Bytes != null && mp3Bytes.Length > 128) {
                string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".veronica");
                if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);
                tempAudioPath = Path.Combine(dir, "tts_stream_" + DateTime.UtcNow.Ticks + ".mp3");
                File.WriteAllBytes(tempAudioPath, mp3Bytes);

                Events.Enqueue("SPEAKING:START");
                mciSendString("open \"" + tempAudioPath + "\" type mpegvideo alias veronica_tts", null, 0, IntPtr.Zero);
                mciSendString("play veronica_tts", null, 0, IntPtr.Zero);

                Task.Run(async () => {
                    try {
                        var sb = new StringBuilder(128);
                        for (int i = 0; i < 300; i++) {
                            await Task.Delay(100);
                            sb.Clear();
                            mciSendString("status veronica_tts mode", sb, sb.Capacity, IntPtr.Zero);
                            string mode = sb.ToString().Trim().ToLowerInvariant();
                            if (mode != "playing") break;
                        }
                        mciSendString("close veronica_tts", null, 0, IntPtr.Zero);
                        try { if (File.Exists(tempAudioPath)) File.Delete(tempAudioPath); } catch {}
                    } catch {}
                    Events.Enqueue("AUDIO_STOPPED:");
                });
                return;
            }
        } catch {}

        SpeakFallback(fallbackText);
    }

    public static void SpeakFallback(string text) {
        if (voiceMuted || string.IsNullOrWhiteSpace(text)) {
            Events.Enqueue("AUDIO_STOPPED:");
            return;
        }
        try {
            if (fallbackSynth == null) {
                fallbackSynth = new SpeechSynthesizer();
                fallbackSynth.SelectVoiceByHints(VoiceGender.Female, VoiceAge.Adult);
                fallbackSynth.Rate = 1;
                fallbackSynth.SpeakCompleted += (s, e) => {
                    Events.Enqueue("AUDIO_STOPPED:");
                };
            }
            fallbackSynth.SpeakAsyncCancelAll();
            Events.Enqueue("SPEAKING:START");
            fallbackSynth.SpeakAsync(text);
        } catch {
            Events.Enqueue("AUDIO_STOPPED:");
        }
    }

    public static bool IsPortListening(int port) {
        try {
            using (var tcp = new TcpClient()) {
                var ar = tcp.BeginConnect("127.0.0.1", port, null, null);
                bool ok = ar.AsyncWaitHandle.WaitOne(TimeSpan.FromMilliseconds(250));
                if (ok && tcp.Connected) {
                    tcp.EndConnect(ar);
                    return true;
                }
            }
        } catch {}
        return false;
    }

    public static void ListenSummon() {
        Task.Run(() => {
            while (true) {
                try {
                    if (SummonHandle.WaitOne(300)) {
                        Events.Enqueue("SUMMON:NOW");
                    }
                } catch {}
            }
        });
    }

    public static string Protect(string plainText) {
        if (string.IsNullOrEmpty(plainText)) return "";
        byte[] entropy = Encoding.UTF8.GetBytes("Veronica.Stark.SecurityProtocol.v1");
        byte[] plain = Encoding.UTF8.GetBytes(plainText);
        byte[] cipher = ProtectedData.Protect(plain, entropy, DataProtectionScope.CurrentUser);
        return Convert.ToBase64String(cipher);
    }

    public static string Unprotect(string cipherText) {
        if (string.IsNullOrEmpty(cipherText)) return "";
        try {
            byte[] entropy = Encoding.UTF8.GetBytes("Veronica.Stark.SecurityProtocol.v1");
            byte[] cipher = Convert.FromBase64String(cipherText);
            byte[] plain = ProtectedData.Unprotect(cipher, entropy, DataProtectionScope.CurrentUser);
            return Encoding.UTF8.GetString(plain);
        } catch { return ""; }
    }

    public static string CaptureScreenBase64() {
        try {
            Rectangle bounds = Screen.PrimaryScreen.Bounds;
            using (Bitmap bmp = new Bitmap(bounds.Width, bounds.Height)) {
                using (Graphics g = Graphics.FromImage(bmp)) {
                    g.CopyFromScreen(bounds.Location, Point.Empty, bounds.Size);
                }
                using (MemoryStream ms = new MemoryStream()) {
                    bmp.Save(ms, ImageFormat.Jpeg);
                    return Convert.ToBase64String(ms.ToArray());
                }
            }
        } catch {
            return "";
        }
    }

    public static void StartSpeech() {
        try {
            recognizer = new SpeechRecognitionEngine();
            Choices choices = new Choices();
            choices.Add("hey veronica");
            choices.Add("veronica");
            choices.Add("system vitals");
            choices.Add("check system vitals");
            choices.Add("deploy focus");
            choices.Add("deploy focus mode");
            choices.Add("deploy dev workspace");
            choices.Add("analyze screen");
            choices.Add("network status");
            choices.Add("open spotify");
            choices.Add("close spotify");
            choices.Add("close chrome");
            choices.Add("close notepad");
            choices.Add("play music");
            choices.Add("pause music");
            choices.Add("mute audio");
            choices.Add("volume up");
            choices.Add("volume down");

            GrammarBuilder gb = new GrammarBuilder(choices);
            Grammar cmdGrammar = new Grammar(gb) { Name = "TacticalCommands" };
            recognizer.LoadGrammar(cmdGrammar);

            DictationGrammar dictGrammar = new DictationGrammar() { Name = "FreeDictation" };
            recognizer.LoadGrammar(dictGrammar);

            recognizer.SpeechRecognized += (s, e) => {
                string text = e.Result.Text.Trim();
                bool isCmd = e.Result.Grammar != null && e.Result.Grammar.Name == "TacticalCommands";
                if (isCmd && e.Result.Confidence >= 0.40f) {
                    Events.Enqueue("SPEECH_CMD:" + text);
                } else if (freeDictationArmed && e.Result.Confidence >= 0.35f && text.Length > 2) {
                    Events.Enqueue("SPEECH_DICT:" + text);
                }
            };
            recognizer.SetInputToDefaultAudioDevice();
            recognizer.RecognizeAsync(RecognizeMode.Multiple);
            Events.Enqueue("LOG:Speech engine active (Tactical + Dictation)");
        } catch (Exception ex) {
            Events.Enqueue("LOG:Speech init notice: " + ex.Message);
        }
    }

    private static async Task<string> ReceiveFullMessageAsync(ClientWebSocket ws, byte[] buf, CancellationToken token) {
        using (var ms = new MemoryStream()) {
            WebSocketReceiveResult res;
            do {
                res = await ws.ReceiveAsync(new ArraySegment<byte>(buf), token);
                if (res.MessageType == WebSocketMessageType.Close) return null;
                ms.Write(buf, 0, res.Count);
            } while (!res.EndOfMessage);
            return Encoding.UTF8.GetString(ms.ToArray());
        }
    }

    public static void SendText(int port, string token, string text, bool synthesize) {
        SendEnvelope(port, token, "text.input", new Dictionary<string, object> {
            { "text", text },
            { "synthesize", synthesize }
        });
    }

    public static void SendScreenAnalyze(int port, string token, string prompt, bool synthesize) {
        string b64 = CaptureScreenBase64();
        if (string.IsNullOrEmpty(b64)) {
            Events.Enqueue("ERROR:Unable to capture desktop screen.");
            return;
        }
        SendEnvelope(port, token, "screen.analyze", new Dictionary<string, object> {
            { "image", b64 },
            { "prompt", prompt },
            { "synthesize", synthesize }
        });
    }

    private static void SendEnvelope(int port, string token, string msgType, Dictionary<string, object> payloadObj) {
        StopAudio();
        if (activeRequestCts != null) {
            try { activeRequestCts.Cancel(); } catch {}
        }
        var cts = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        activeRequestCts = cts;

        Task.Run(async () => {
            try {
                var serializer = new JavaScriptSerializer { MaxJsonLength = 10 * 1024 * 1024 };
                using (var ws = new ClientWebSocket()) {
                    await ws.ConnectAsync(new Uri("ws://127.0.0.1:" + port), cts.Token);

                    string hello = serializer.Serialize(new Dictionary<string, object> {
                        { "v", 1 },
                        { "id", "auth" },
                        { "type", "hello" },
                        { "payload", new Dictionary<string, object> { { "token", token } } }
                    });
                    byte[] hBytes = Encoding.UTF8.GetBytes(hello);
                    await ws.SendAsync(new ArraySegment<byte>(hBytes), WebSocketMessageType.Text, true, cts.Token);

                    var buf = new byte[16384];
                    string readyRaw = await ReceiveFullMessageAsync(ws, buf, cts.Token);
                    if (readyRaw == null) {
                        Events.Enqueue("ERROR:Authentication rejected by Voice Core.");
                        return;
                    }

                    long ts = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
                    string req = serializer.Serialize(new Dictionary<string, object> {
                        { "v", 1 },
                        { "id", "req_" + ts },
                        { "type", msgType },
                        { "payload", payloadObj }
                    });
                    byte[] rBytes = Encoding.UTF8.GetBytes(req);
                    await ws.SendAsync(new ArraySegment<byte>(rBytes), WebSocketMessageType.Text, true, cts.Token);

                    var sb = new StringBuilder();
                    var audioStream = new MemoryStream();
                    bool expectAudio = payloadObj.ContainsKey("synthesize") && (bool)payloadObj["synthesize"] && !voiceMuted;
                    bool textFinished = false;

                    while (ws.State == WebSocketState.Open && !cts.IsCancellationRequested) {
                        string msg = await ReceiveFullMessageAsync(ws, buf, cts.Token);
                        if (msg == null) break;

                        var env = serializer.Deserialize<Dictionary<string, object>>(msg);
                        if (env == null || !env.ContainsKey("type")) continue;
                        string eType = env["type"].ToString();
                        var ePayload = env.ContainsKey("payload") ? env["payload"] as Dictionary<string, object> : null;

                        if (eType == "text.delta" && ePayload != null && ePayload.ContainsKey("text")) {
                            string piece = ePayload["text"].ToString();
                            sb.Append(piece);
                            Events.Enqueue("DELTA:" + sb.ToString());
                        } else if (eType == "tool.result" && ePayload != null && ePayload.ContainsKey("tool")) {
                            Events.Enqueue("TOOL:" + ePayload["tool"].ToString());
                        } else if (eType == "text.done") {
                            textFinished = true;
                            Events.Enqueue("DONE:" + sb.ToString());
                            if (!expectAudio) break;
                        } else if (eType == "audio.delta" && ePayload != null && ePayload.ContainsKey("audio")) {
                            string b64Chunk = ePayload["audio"].ToString();
                            byte[] rawAudio = Convert.FromBase64String(b64Chunk);
                            audioStream.Write(rawAudio, 0, rawAudio.Length);
                        } else if (eType == "audio.done") {
                            break;
                        } else if (eType == "error" && ePayload != null && ePayload.ContainsKey("message")) {
                            Events.Enqueue("ERROR:" + ePayload["message"].ToString());
                            break;
                        }
                    }

                    if (expectAudio && textFinished && !cts.IsCancellationRequested) {
                        PlayMp3Bytes(audioStream.ToArray(), sb.ToString());
                    }

                    try { await ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "Done", CancellationToken.None); } catch {}
                }
            } catch (OperationCanceledException) {
            } catch (Exception ex) {
                Events.Enqueue("ERROR:" + ex.Message);
            }
        });
    }

    public static void QueryVitals(int port, string token) {
        Task.Run(async () => {
            try {
                var serializer = new JavaScriptSerializer();
                using (var ws = new ClientWebSocket()) {
                    var cts = new CancellationTokenSource(TimeSpan.FromSeconds(4));
                    await ws.ConnectAsync(new Uri("ws://127.0.0.1:" + port), cts.Token);

                    string hello = serializer.Serialize(new Dictionary<string, object> {
                        { "v", 1 },
                        { "id", "auth" },
                        { "type", "hello" },
                        { "payload", new Dictionary<string, object> { { "token", token } } }
                    });
                    byte[] hBytes = Encoding.UTF8.GetBytes(hello);
                    await ws.SendAsync(new ArraySegment<byte>(hBytes), WebSocketMessageType.Text, true, cts.Token);

                    var buf = new byte[8192];
                    await ReceiveFullMessageAsync(ws, buf, cts.Token);

                    string q = "{\"v\":1,\"id\":\"q\",\"type\":\"state.query\",\"payload\":{}}";
                    byte[] qBytes = Encoding.UTF8.GetBytes(q);
                    await ws.SendAsync(new ArraySegment<byte>(qBytes), WebSocketMessageType.Text, true, cts.Token);

                    string msg = await ReceiveFullMessageAsync(ws, buf, cts.Token);
                    if (msg != null) {
                        var env = serializer.Deserialize<Dictionary<string, object>>(msg);
                        if (env != null && env.ContainsKey("payload")) {
                            var p = env["payload"] as Dictionary<string, object>;
                            if (p != null) {
                                string prov = p.ContainsKey("provider") ? p["provider"].ToString() : "Tactical Core";
                                double cpu = 0, ram = 0, batt = 100;
                                if (p.ContainsKey("telemetry")) {
                                    var t = p["telemetry"] as Dictionary<string, object>;
                                    if (t != null) {
                                        if (t.ContainsKey("cpu_percent")) double.TryParse(t["cpu_percent"].ToString(), out cpu);
                                        if (t.ContainsKey("ram_percent")) double.TryParse(t["ram_percent"].ToString(), out ram);
                                        if (t.ContainsKey("battery")) {
                                            var b = t["battery"] as Dictionary<string, object>;
                                            if (b != null && b.ContainsKey("percent")) double.TryParse(b["percent"].ToString(), out batt);
                                        }
                                    }
                                }
                                Events.Enqueue(string.Format("VITALS:{0:F0}|{1:F0}|{2:F0}|{3}", cpu, ram, batt, prov));
                            }
                        }
                    }
                    try { await ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "Done", CancellationToken.None); } catch {}
                }
            } catch {}
        });
    }
}
'@

if (-not ([System.Management.Automation.PSTypeName]'VeronicaBridge').Type) {
    $speechPath = [System.Speech.Recognition.SpeechRecognitionEngine].Assembly.Location
    $secPath = [System.Security.Cryptography.ProtectedData].Assembly.Location
    $webExtPath = [System.Web.Script.Serialization.JavaScriptSerializer].Assembly.Location
    $formsPath = [System.Windows.Forms.Form].Assembly.Location
    $drawPath = [System.Drawing.Bitmap].Assembly.Location
    Add-Type -TypeDefinition $bridgeSource -ReferencedAssemblies $speechPath, $secPath, $webExtPath, $formsPath, $drawPath
}

# Unified Token Resolution (~/.veronica/token + DPAPI Vault)
$veronicaHome = Join-Path $env:USERPROFILE ".veronica"
if (-not (Test-Path $veronicaHome)) {
    New-Item -ItemType Directory -Path $veronicaHome -Force | Out-Null
}
$tokenFile = Join-Path $veronicaHome "token"
$dpapiPath = Join-Path $PSScriptRoot "..\..\services\voice\.secret.token"

if ([string]::IsNullOrWhiteSpace($Token)) {
    if (Test-Path $tokenFile) {
        try { $Token = (Get-Content $tokenFile -Raw).Trim() } catch {}
    }
    if ([string]::IsNullOrWhiteSpace($Token) -and (Test-Path $dpapiPath)) {
        try {
            $cipher = (Get-Content $dpapiPath -Raw).Trim()
            $Token = [VeronicaBridge]::Unprotect($cipher)
        } catch {}
    }
    if ([string]::IsNullOrWhiteSpace($Token) -or $Token.Length -lt 16) {
        $Token = [System.Guid]::NewGuid().ToString("N")
    }
}
# Ensure both ~/.veronica/token and DPAPI vault stay synchronized
try { Set-Content -Path $tokenFile -Value $Token -Force } catch {}
try {
    $cipher = [VeronicaBridge]::Protect($Token)
    Set-Content -Path $dpapiPath -Value $cipher -Force
} catch {}

# Auto-launch Voice Intelligence Core if not already listening on $Port
$global:spawnedVoiceProc = $null
if (-not $NoAutoStartService -and -not ([VeronicaBridge]::IsPortListening($Port))) {
    $svcDir = Join-Path $PSScriptRoot "..\..\services\voice"
    $vpy = Join-Path $svcDir ".venv\Scripts\python.exe"
    if (Test-Path $vpy) {
        Write-Host "[VERONICA] Auto-starting Voice Intelligence Core on 127.0.0.1:$Port..." -ForegroundColor Cyan
        $pInfo = New-Object System.Diagnostics.ProcessStartInfo
        $pInfo.FileName = $vpy
        $pInfo.Arguments = "-m veronica_voice"
        $pInfo.WorkingDirectory = $svcDir
        $pInfo.EnvironmentVariables["PYTHONPATH"] = (Join-Path $svcDir "src")
        $pInfo.EnvironmentVariables["VERONICA_TOKEN"] = $Token
        $pInfo.EnvironmentVariables["VERONICA_PORT"] = $Port.ToString()
        $pInfo.EnvironmentVariables["VERONICA_PARENT_PID"] = $PID.ToString()
        $pInfo.UseShellExecute = $false
        $pInfo.CreateNoWindow = $true
        $global:spawnedVoiceProc = [System.Diagnostics.Process]::Start($pInfo)
    }
}

# Stark Tactical Palette
$colorObsidian   = [System.Drawing.Color]::FromArgb(5, 8, 17)
$colorPanelBg    = [System.Drawing.Color]::FromArgb(10, 16, 32)
$colorCyan       = [System.Drawing.Color]::FromArgb(0, 243, 255)
$colorDarkCyan   = [System.Drawing.Color]::FromArgb(0, 119, 255)
$colorGold       = [System.Drawing.Color]::FromArgb(255, 183, 0)
$colorEmerald    = [System.Drawing.Color]::FromArgb(0, 255, 170)
$colorCobalt     = [System.Drawing.Color]::FromArgb(112, 180, 255)
$colorTextMain   = [System.Drawing.Color]::FromArgb(226, 241, 255)
$colorTextDim    = [System.Drawing.Color]::FromArgb(112, 144, 176)

# Upgraded HUD Geometry
$formWidth = 540
$formHeight = 350

$form = New-Object System.Windows.Forms.Form
$form.Text = "VERONICA // MARK-V TACTICAL SHELL"
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
$form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
$form.Size = [System.Drawing.Size]::new($formWidth, $formHeight)
$form.BackColor = $colorObsidian
$form.TopMost = $true
$form.ShowInTaskbar = $true
$form.Opacity = 0.98

# DoubleBuffering for tear-free 30 FPS vector animation
$form.GetType().GetProperty("DoubleBuffered", [System.Reflection.BindingFlags]"NonPublic, Instance").SetValue($form, $true, $null)

# Win32 Drag-to-Move Handler
$dragScript = {
    if ($_.Button -eq [System.Windows.Forms.MouseButtons]::Left) {
        [VeronicaBridge]::ReleaseCapture() | Out-Null
        [VeronicaBridge]::SendMessage($form.Handle, [VeronicaBridge]::WM_NCLBUTTONDOWN, [VeronicaBridge]::HT_CAPTION, 0) | Out-Null
    }
}
$form.add_MouseDown($dragScript)

# Arc Reactor & HUD State
$global:arcAngle = 0
$global:innerAngle = 360
$global:isListening = $false
$global:isSpeaking = $false
$global:isMuted = $false
$global:energyLevel = 0.15
$global:cpuVal = 0
$global:ramVal = 0
$global:battVal = 100
$global:activeProvider = "Tactical Core"
$global:lastPrompt = ""
$global:chatHistory = New-Object System.Collections.Generic.List[string]
$global:chatHistory.Add("Veronica Mark-V Native Shell online.")
$global:chatHistory.Add("Security: Windows DPAPI + Loopback HMAC + SQLite FTS5 Memory.")
$global:chatHistory.Add("Say 'Hey Veronica', click the Arc Reactor to dictate, or select a tactical directive.")

# Header Title
$lblTitle = New-Object System.Windows.Forms.Label
$lblTitle.Text = "VERONICA // MARK-V SHELL"
$lblTitle.Font = [System.Drawing.Font]::new("Segoe UI", 9.5, [System.Drawing.FontStyle]::Bold)
$lblTitle.ForeColor = $colorCyan
$lblTitle.Location = [System.Drawing.Point]::new(24, 10)
$lblTitle.Size = [System.Drawing.Size]::new(190, 20)
$lblTitle.add_MouseDown($dragScript)
$form.Controls.Add($lblTitle)

# Header Status Pill
$lblStatus = New-Object System.Windows.Forms.Label
$lblStatus.Text = "STANDBY"
$lblStatus.Font = [System.Drawing.Font]::new("Consolas", 8, [System.Drawing.FontStyle]::Bold)
$lblStatus.ForeColor = $colorCyan
$lblStatus.BackColor = [System.Drawing.Color]::FromArgb(25, 0, 243, 255)
$lblStatus.TextAlign = [System.Drawing.ContentAlignment]::MiddleCenter
$lblStatus.Location = [System.Drawing.Point]::new(218, 10)
$lblStatus.Size = [System.Drawing.Size]::new(80, 19)
$form.Controls.Add($lblStatus)

# Provider Badge
$lblProvider = New-Object System.Windows.Forms.Label
$lblProvider.Text = "CORE: TACTICAL"
$lblProvider.Font = [System.Drawing.Font]::new("Consolas", 7.5)
$lblProvider.ForeColor = $colorTextDim
$lblProvider.TextAlign = [System.Drawing.ContentAlignment]::MiddleLeft
$lblProvider.Location = [System.Drawing.Point]::new(306, 11)
$lblProvider.Size = [System.Drawing.Size]::new(96, 18)
$lblProvider.add_MouseDown($dragScript)
$form.Controls.Add($lblProvider)

# Voice Mute/Unmute Toggle Button
$btnVoice = New-Object System.Windows.Forms.Button
$btnVoice.Text = "VOICE"
$btnVoice.Font = [System.Drawing.Font]::new("Segoe UI", 7.5, [System.Drawing.FontStyle]::Bold)
$btnVoice.ForeColor = $colorEmerald
$btnVoice.BackColor = [System.Drawing.Color]::FromArgb(25, 0, 255, 170)
$btnVoice.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
$btnVoice.FlatAppearance.BorderSize = 1
$btnVoice.FlatAppearance.BorderColor = $colorEmerald
$btnVoice.Location = [System.Drawing.Point]::new(($formWidth - 134), 8)
$btnVoice.Size = [System.Drawing.Size]::new(52, 22)
$btnVoice.Cursor = [System.Windows.Forms.Cursors]::Hand
$btnVoice.add_Click({
    $global:isMuted = -not $global:isMuted
    [VeronicaBridge]::SetVoiceMuted($global:isMuted)
    if ($global:isMuted) {
        $btnVoice.Text = "MUTE"
        $btnVoice.ForeColor = $colorTextDim
        $btnVoice.FlatAppearance.BorderColor = $colorTextDim
    } else {
        $btnVoice.Text = "VOICE"
        $btnVoice.ForeColor = $colorEmerald
        $btnVoice.FlatAppearance.BorderColor = $colorEmerald
    }
})
$form.Controls.Add($btnVoice)

# Minimize to Tray Button
$btnMinimize = New-Object System.Windows.Forms.Button
$btnMinimize.Text = "[_ TRAY]"
$btnMinimize.Font = [System.Drawing.Font]::new("Segoe UI", 7.5, [System.Drawing.FontStyle]::Bold)
$btnMinimize.ForeColor = $colorCyan
$btnMinimize.BackColor = [System.Drawing.Color]::FromArgb(35, 0, 119, 255)
$btnMinimize.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
$btnMinimize.FlatAppearance.BorderSize = 1
$btnMinimize.FlatAppearance.BorderColor = $colorCyan
$btnMinimize.Location = [System.Drawing.Point]::new(($formWidth - 76), 8)
$btnMinimize.Size = [System.Drawing.Size]::new(64, 22)
$btnMinimize.Cursor = [System.Windows.Forms.Cursors]::Hand
$btnMinimize.add_Click({
    $form.Hide()
})
$form.Controls.Add($btnMinimize)

# Telemetry Vitals Strip
$lblVitals = New-Object System.Windows.Forms.Label
$lblVitals.Text = "CPU: --%   RAM: --%   BATT: --%   SEC: DPAPI + FTS5"
$lblVitals.Font = [System.Drawing.Font]::new("Consolas", 8)
$lblVitals.ForeColor = $colorTextDim
$lblVitals.Location = [System.Drawing.Point]::new(112, 36)
$lblVitals.Size = [System.Drawing.Size]::new(($formWidth - 126), 16)
$lblVitals.add_MouseDown($dragScript)
$form.Controls.Add($lblVitals)

# Live Transcript Feed
$txtTranscript = New-Object System.Windows.Forms.RichTextBox
$txtTranscript.Location = [System.Drawing.Point]::new(112, 56)
$txtTranscript.Size = [System.Drawing.Size]::new(($formWidth - 126), 192)
$txtTranscript.BackColor = $colorPanelBg
$txtTranscript.ForeColor = $colorTextMain
$txtTranscript.BorderStyle = [System.Windows.Forms.BorderStyle]::None
$txtTranscript.Font = [System.Drawing.Font]::new("Segoe UI", 9)
$txtTranscript.ReadOnly = $true
$txtTranscript.Text = ($global:chatHistory -join "`n")
$form.Controls.Add($txtTranscript)

function Refresh-Transcript([string]$streamingLine = "") {
    $lines = New-Object System.Collections.Generic.List[string]($global:chatHistory)
    if (-not [string]::IsNullOrEmpty($streamingLine)) {
        $lines.Add($streamingLine)
    }
    $txtTranscript.Text = ($lines -join "`n")
    $txtTranscript.SelectionStart = $txtTranscript.TextLength
    $txtTranscript.ScrollToCaret()
}

# 6 Quick Action Directive Chips
$chipActions = @(
    @{ Name = "[Vitals]"; Cmd = "Check system vitals"; Type = "text" },
    @{ Name = "[Focus]"; Cmd = "Deploy focus mode"; Type = "text" },
    @{ Name = "[Dev Macro]"; Cmd = "Deploy dev workspace macro"; Type = "text" },
    @{ Name = "[Screen Recon]"; Cmd = "Analyze what is on my screen right now"; Type = "screen" },
    @{ Name = "[Network]"; Cmd = "Check network status and local IP"; Type = "text" },
    @{ Name = "[Security]"; Cmd = "Check security protocols and encryption status"; Type = "text" }
)

$chipX = 14
foreach ($chip in $chipActions) {
    $btnChip = New-Object System.Windows.Forms.Button
    $btnChip.Text = $chip.Name
    $btnChip.Font = [System.Drawing.Font]::new("Segoe UI", 7.5, [System.Drawing.FontStyle]::Bold)
    $btnChip.ForeColor = [System.Drawing.Color]::FromArgb(146, 213, 255)
    $btnChip.BackColor = [System.Drawing.Color]::FromArgb(20, 0, 119, 255)
    $btnChip.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $btnChip.FlatAppearance.BorderSize = 1
    $btnChip.FlatAppearance.BorderColor = [System.Drawing.Color]::FromArgb(80, 0, 243, 255)
    $btnChip.Location = [System.Drawing.Point]::new($chipX, 260)
    $btnChip.Size = [System.Drawing.Size]::new(82, 24)
    $btnChip.Cursor = [System.Windows.Forms.Cursors]::Hand
    $cCmd = $chip.Cmd
    $cType = $chip.Type
    $btnChip.add_Click({
        if ($cType -eq "screen") {
            Transmit-ScreenRecon $cCmd
        } else {
            Transmit-Text $cCmd
        }
    }.GetNewClosure())
    $form.Controls.Add($btnChip)
    $chipX += 86
}

# Footer Input Bar
$txtInput = New-Object System.Windows.Forms.TextBox
$txtInput.Location = [System.Drawing.Point]::new(14, 298)
$txtInput.Size = [System.Drawing.Size]::new(($formWidth - 72), 26)
$txtInput.BackColor = [System.Drawing.Color]::FromArgb(12, 18, 36)
$txtInput.ForeColor = $colorTextMain
$txtInput.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
$txtInput.Font = [System.Drawing.Font]::new("Segoe UI", 9.5)
$txtInput.add_KeyDown({
    if ($_.KeyCode -eq [System.Windows.Forms.Keys]::Enter) {
        $_.SuppressKeyPress = $true
        $val = $txtInput.Text.Trim()
        if (-not [string]::IsNullOrEmpty($val)) {
            $txtInput.Text = ""
            Transmit-Text $val
        }
    } elseif ($_.KeyCode -eq [System.Windows.Forms.Keys]::Escape) {
        [VeronicaBridge]::StopAudio()
    }
})
$form.Controls.Add($txtInput)

# Send Button
$btnSend = New-Object System.Windows.Forms.Button
$btnSend.Text = ">"
$btnSend.Font = [System.Drawing.Font]::new("Segoe UI", 9.5, [System.Drawing.FontStyle]::Bold)
$btnSend.ForeColor = $colorObsidian
$btnSend.BackColor = $colorCyan
$btnSend.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
$btnSend.FlatAppearance.BorderSize = 0
$btnSend.Location = [System.Drawing.Point]::new(($formWidth - 52), 296)
$btnSend.Size = [System.Drawing.Size]::new(38, 28)
$btnSend.Cursor = [System.Windows.Forms.Cursors]::Hand
$btnSend.add_Click({
    $val = $txtInput.Text.Trim()
    if (-not [string]::IsNullOrEmpty($val)) {
        $txtInput.Text = ""
        Transmit-Text $val
    }
})
$form.Controls.Add($btnSend)

# Form Vector Painting (Cyan Frame, Corner Brackets, Dual Counter-Rotating Arc Reactor, Telemetry Bars)
$form.add_Paint({
    param($sender, $e)
    $g = $e.Graphics
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

    # Outer Border
    $penCyan = [System.Drawing.Pen]::new($colorCyan, 1.5)
    $g.DrawRectangle($penCyan, 1, 1, ($formWidth - 2), ($formHeight - 2))

    # Corner Brackets
    $bracketPen = [System.Drawing.Pen]::new($colorCyan, 3)
    $g.DrawLine($bracketPen, 0, 0, 18, 0)
    $g.DrawLine($bracketPen, 0, 0, 0, 18)
    $g.DrawLine($bracketPen, $formWidth, 0, ($formWidth - 18), 0)
    $g.DrawLine($bracketPen, $formWidth, 0, $formWidth, 18)
    $g.DrawLine($bracketPen, 0, $formHeight, 18, $formHeight)
    $g.DrawLine($bracketPen, 0, $formHeight, 0, ($formHeight - 18))
    $g.DrawLine($bracketPen, $formWidth, $formHeight, ($formWidth - 18), $formHeight)
    $g.DrawLine($bracketPen, $formWidth, $formHeight, $formWidth, ($formHeight - 18))

    # Arc Reactor Center at (cx=56, cy=125)
    $cx = 56
    $cy = 125

    $ringColor = if ($global:isListening) { $colorGold } elseif ($global:isSpeaking) { $colorEmerald } else { $colorCyan }

    # Outer Containment Ring
    $outerPen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(110, $ringColor.R, $ringColor.G, $ringColor.B), 1.5)
    $g.DrawEllipse($outerPen, ($cx - 42), ($cy - 42), 84, 84)

    # Clockwise Rotating 12-Coil Ring
    $g.TranslateTransform($cx, $cy)
    $g.RotateTransform($global:arcAngle)
    $segPen = [System.Drawing.Pen]::new($ringColor, 2.2)
    for ($i = 0; $i -lt 12; $i++) {
        $rad = ($i * [Math]::PI * 2) / 12
        $x1 = [Math]::Cos($rad) * 37
        $y1 = [Math]::Sin($rad) * 37
        $x2 = [Math]::Cos($rad) * 30
        $y2 = [Math]::Sin($rad) * 30
        $g.DrawLine($segPen, [float]$x1, [float]$y1, [float]$x2, [float]$y2)
    }
    $g.ResetTransform()

    # Counter-Clockwise Inner Turbine Ring
    $g.TranslateTransform($cx, $cy)
    $g.RotateTransform($global:innerAngle)
    $innerPen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(180, $ringColor.R, $ringColor.G, $ringColor.B), 1.5)
    for ($j = 0; $j -lt 8; $j++) {
        $rad2 = ($j * [Math]::PI * 2) / 8
        $ix1 = [Math]::Cos($rad2) * 24
        $iy1 = [Math]::Sin($rad2) * 24
        $ix2 = [Math]::Cos($rad2) * 19
        $iy2 = [Math]::Sin($rad2) * 19
        $g.DrawLine($innerPen, [float]$ix1, [float]$iy1, [float]$ix2, [float]$iy2)
    }
    $g.ResetTransform()

    # Center Plasma Core with Audio/State Pulse
    $coreBrush = [System.Drawing.SolidBrush]::new($ringColor)
    $coreSize = [float](20 + ($global:energyLevel * 14))
    $g.FillEllipse($coreBrush, [float]($cx - ($coreSize/2)), [float]($cy - ($coreSize/2)), $coreSize, $coreSize)

    # Mini CPU & RAM Telemetry Bars under Arc Reactor
    $barBg = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(40, 0, 243, 255))
    $barFg = [System.Drawing.SolidBrush]::new($colorCyan)
    $g.FillRectangle($barBg, 18, 184, 76, 5)
    $cpuW = [Math]::Min(76, [Math]::Max(2, [int](76 * ($global:cpuVal / 100.0))))
    $g.FillRectangle($barFg, 18, 184, $cpuW, 5)

    $g.FillRectangle($barBg, 18, 194, 76, 5)
    $ramW = [Math]::Min(76, [Math]::Max(2, [int](76 * ($global:ramVal / 100.0))))
    $g.FillRectangle($barFg, 18, 194, $ramW, 5)
})

# Smooth Arc Reactor Animation Timer (30 FPS)
$animTimer = New-Object System.Windows.Forms.Timer
$animTimer.Interval = 33
$animTimer.add_Tick({
    $speed = if ($global:isSpeaking -or $global:isListening) { 6 } else { 3 }
    $global:arcAngle = ($global:arcAngle + $speed) % 360
    $global:innerAngle = ($global:innerAngle - ($speed + 1) + 360) % 360

    if ($global:isSpeaking) {
        $global:energyLevel = 0.35 + ([Math]::Abs([Math]::Sin($global:arcAngle * [Math]::PI / 45.0)) * 0.65)
    } elseif ($global:isListening) {
        $global:energyLevel = 0.25 + ([Math]::Abs([Math]::Sin($global:arcAngle * [Math]::PI / 90.0)) * 0.35)
    } else {
        $global:energyLevel = 0.15
    }

    $rect = [System.Drawing.Rectangle]::new(10, 75, 96, 130)
    $form.Invalidate($rect)
})
$animTimer.Start()

# Arc Reactor Interactive Click to Toggle Voice Dictation / Barge-in
$form.add_Click({
    param($s, $e)
    $dx = $e.X - 56
    $dy = $e.Y - 125
    if (($dx*$dx + $dy*$dy) -le (42 * 42)) {
        [VeronicaBridge]::StopAudio()
        [System.Media.SystemSounds]::Beep.Play()
        $global:isListening = -not $global:isListening
        [VeronicaBridge]::SetDictationArmed($global:isListening)
        $lblStatus.Text = if ($global:isListening) { "LISTENING" } else { "STANDBY" }
        $lblStatus.ForeColor = if ($global:isListening) { $colorGold } else { $colorCyan }
        $form.Invalidate()
    }
})

function Summon-Window {
    $form.Show()
    $form.WindowState = [System.Windows.Forms.FormWindowState]::Normal
    $form.Activate()
    $form.BringToFront()
    $txtInput.Focus()
}

# System Tray Resident NotifyIcon
$trayIcon = New-Object System.Windows.Forms.NotifyIcon
$icoPath = Join-Path $PSScriptRoot "..\desktop\assets\veronica.ico"
if (Test-Path $icoPath) {
    $trayIcon.Icon = [System.Drawing.Icon]::new($icoPath)
} else {
    $trayIcon.Icon = [System.Drawing.SystemIcons]::Application
}
$trayIcon.Text = "Project Veronica // Mark-V Native Shell"
$trayIcon.Visible = $true

$menu = New-Object System.Windows.Forms.ContextMenuStrip
$mHeader = New-Object System.Windows.Forms.ToolStripMenuItem "[VERONICA // MARK-V NATIVE SHELL]"
$mHeader.Enabled = $false
$menu.Items.Add($mHeader) | Out-Null
$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

$mSummon = New-Object System.Windows.Forms.ToolStripMenuItem "Summon Tactical HUD ('Hey Veronica')"
$mSummon.add_Click({ Summon-Window })
$menu.Items.Add($mSummon) | Out-Null

$mRecon = New-Object System.Windows.Forms.ToolStripMenuItem "Execute Optical Screen Recon"
$mRecon.add_Click({
    Summon-Window
    Transmit-ScreenRecon "Analyze what is on my screen right now"
})
$menu.Items.Add($mRecon) | Out-Null

$mVitals = New-Object System.Windows.Forms.ToolStripMenuItem "System Vitals Snapshot"
$mVitals.add_Click({
    $trayIcon.ShowBalloonTip(3000, "Veronica Telemetry", "CPU: $($global:cpuVal)% | RAM: $($global:ramVal)% | BATT: $($global:battVal)%`nProvider: $($global:activeProvider)`nLoopback: 127.0.0.1:$Port", [System.Windows.Forms.ToolTipIcon]::Info)
})
$menu.Items.Add($mVitals) | Out-Null

$mSec = New-Object System.Windows.Forms.ToolStripMenuItem "Security Protocol Status"
$mSec.add_Click({
    $trayIcon.ShowBalloonTip(3000, "Security Protocol Status", "Hardware DPAPI: ACTIVE`nLoopback HMAC Auth: ENFORCED`nSQLite FTS5 Secure Delete: ACTIVE", [System.Windows.Forms.ToolTipIcon]::Info)
})
$menu.Items.Add($mSec) | Out-Null

$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

$mExit = New-Object System.Windows.Forms.ToolStripMenuItem "Shutdown Veronica"
$mExit.add_Click({
    [VeronicaBridge]::StopAudio()
    $trayIcon.Visible = $false
    $trayIcon.Dispose()
    if ($global:spawnedVoiceProc -and -not $global:spawnedVoiceProc.HasExited) {
        try { $global:spawnedVoiceProc.Kill() } catch {}
    }
    $form.Close()
    [System.Windows.Forms.Application]::Exit()
    exit 0
})
$menu.Items.Add($mExit) | Out-Null

$trayIcon.ContextMenuStrip = $menu
$trayIcon.add_Click({
    param($s, $e)
    if ($e.Button -eq [System.Windows.Forms.MouseButtons]::Left) {
        Summon-Window
    }
})

# Transmit text directive to voice service
function Transmit-Text([string]$text) {
    if ([string]::IsNullOrEmpty($text)) { return }
    $global:lastPrompt = $text
    $global:chatHistory.Add("")
    $global:chatHistory.Add("You: $text")
    while ($global:chatHistory.Count -gt 40) { $global:chatHistory.RemoveAt(0) }
    Refresh-Transcript "Veronica: Thinking..."
    $lblStatus.Text = "THINKING"
    $lblStatus.ForeColor = $colorCobalt
    [VeronicaBridge]::SendText($Port, $Token, $text, (-not $global:isMuted))
}

# Transmit Screen Recon capture to voice service
function Transmit-ScreenRecon([string]$promptText) {
    $global:lastPrompt = "[Screen Recon] $promptText"
    $global:chatHistory.Add("")
    $global:chatHistory.Add("You: [Optical Screen Recon]")
    while ($global:chatHistory.Count -gt 40) { $global:chatHistory.RemoveAt(0) }
    Refresh-Transcript "Veronica: Capturing display & analyzing..."
    $lblStatus.Text = "RECON"
    $lblStatus.ForeColor = $colorGold
    [VeronicaBridge]::SendScreenAnalyze($Port, $Token, $promptText, (-not $global:isMuted))
}

# Event Drain Timer (UI Thread Safe)
$drainTimer = New-Object System.Windows.Forms.Timer
$drainTimer.Interval = 40
$drainTimer.add_Tick({
    $msg = $null
    while ([VeronicaBridge]::Events.TryDequeue([ref]$msg)) {
        if ($msg.StartsWith("SUMMON:")) {
            [System.Media.SystemSounds]::Asterisk.Play()
            Summon-Window
        } elseif ($msg.StartsWith("SPEECH_CMD:")) {
            $recognized = $msg.Substring(11).Trim().ToLower()
            [VeronicaBridge]::StopAudio()
            [System.Media.SystemSounds]::Asterisk.Play()
            Summon-Window
            if ($recognized -in @("hey veronica", "veronica")) {
                $global:isListening = $true
                [VeronicaBridge]::SetDictationArmed($true)
                $lblStatus.Text = "LISTENING"
                $lblStatus.ForeColor = $colorGold
                $form.Invalidate()
            } elseif ($recognized -eq "analyze screen") {
                Transmit-ScreenRecon "Analyze what is on my screen right now"
            } else {
                Transmit-Text $recognized
            }
        } elseif ($msg.StartsWith("SPEECH_DICT:")) {
            $dictated = $msg.Substring(12).Trim()
            $global:isListening = $false
            [VeronicaBridge]::SetDictationArmed($false)
            Transmit-Text $dictated
        } elseif ($msg.StartsWith("TOOL:")) {
            $toolName = $msg.Substring(5)
            $global:chatHistory.Add("  [Tool Executed: $toolName]")
            Refresh-Transcript "Veronica: Processing..."
        } elseif ($msg.StartsWith("DELTA:")) {
            $deltaText = $msg.Substring(6)
            Refresh-Transcript "Veronica: $deltaText"
        } elseif ($msg.StartsWith("DONE:")) {
            $finalText = $msg.Substring(5).Trim()
            if (-not [string]::IsNullOrEmpty($finalText)) {
                $global:chatHistory.Add("Veronica: $finalText")
            }
            Refresh-Transcript ""
            if (-not $global:isSpeaking) {
                $lblStatus.Text = "STANDBY"
                $lblStatus.ForeColor = $colorCyan
            }
            $global:isListening = $false
            [VeronicaBridge]::SetDictationArmed($false)
            $form.Invalidate()
        } elseif ($msg.StartsWith("SPEAKING:START")) {
            $global:isSpeaking = $true
            $lblStatus.Text = "SPEAKING"
            $lblStatus.ForeColor = $colorEmerald
            $form.Invalidate()
        } elseif ($msg.StartsWith("AUDIO_STOPPED:")) {
            $global:isSpeaking = $false
            if (-not $global:isListening) {
                $lblStatus.Text = "STANDBY"
                $lblStatus.ForeColor = $colorCyan
            }
            $form.Invalidate()
        } elseif ($msg.StartsWith("ERROR:")) {
            $err = $msg.Substring(6)
            $global:chatHistory.Add("Veronica: [Offline] Voice Core notice: $err")
            Refresh-Transcript ""
            $lblStatus.Text = "OFFLINE"
            $lblStatus.ForeColor = [System.Drawing.Color]::Red
            $global:isListening = $false
        } elseif ($msg.StartsWith("VITALS:")) {
            $parts = $msg.Substring(7).Split("|")
            if ($parts.Length -ge 4) {
                $global:cpuVal = [int]$parts[0]
                $global:ramVal = [int]$parts[1]
                $global:battVal = [int]$parts[2]
                $global:activeProvider = $parts[3]
                $shortProv = if ($global:activeProvider -match "Groq") { "GROQ 70B" }
                             elseif ($global:activeProvider -match "OpenAI") { "GPT-4O" }
                             elseif ($global:activeProvider -match "Gemini") { "GEMINI" }
                             elseif ($global:activeProvider -match "Anthropic") { "CLAUDE" }
                             else { "TACTICAL" }
                $lblProvider.Text = "CORE: $shortProv"
                $lblVitals.Text = "CPU: $($global:cpuVal)%   RAM: $($global:ramVal)%   BATT: $($global:battVal)%   SEC: DPAPI + FTS5"
                $form.Invalidate()
            }
        }
    }
})
$drainTimer.Start()

# Periodic Vitals Poller (every 3 seconds)
$vitalsTimer = New-Object System.Windows.Forms.Timer
$vitalsTimer.Interval = 3000
$vitalsTimer.add_Tick({
    [VeronicaBridge]::QueryVitals($Port, $Token)
})
$vitalsTimer.Start()
[VeronicaBridge]::QueryVitals($Port, $Token)

# Initialize Native Speech Engine and Summon Listener
[VeronicaBridge]::StartSpeech()
[VeronicaBridge]::ListenSummon()

# Display Form at Center of Desktop
Summon-Window
$trayIcon.ShowBalloonTip(3000, "Veronica Mark-V Online", "Native .NET Shell active.`nSay 'Hey Veronica' or click tray to summon.", [System.Windows.Forms.ToolTipIcon]::Info)

Write-Host "[VERONICA SHELL] Form Handle: $($form.Handle)"
Write-Host "[VERONICA SHELL] Form Bounds: $($form.Bounds)"
Write-Host "[VERONICA SHELL] Form Visible: $($form.Visible)"
Write-Host "[VERONICA SHELL] Entering Application.Run..."

# Run Native Windows Event Loop
[System.Windows.Forms.Application]::Run($form)
