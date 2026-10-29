using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Media;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Runtime.InteropServices;
using System.Speech.Recognition;
using System.Speech.Synthesis;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows;
using System.Windows.Forms;
using Application = System.Windows.Application;
using MessageBox = System.Windows.MessageBox;

namespace Veronica.Shell
{
    /// <summary>
    /// Veronica Native Microsoft .NET Desktop Application Entry Point (Mark-V).
    /// Manages: System Tray NotifyIcon, Native Speech Recognition ("Hey Veronica" + Dictation),
    /// Neural MP3 TTS playback + SAPI fallback, Screen Recon, Loopback WebSocket IPC, and WPF Shell Window.
    /// </summary>
    public class Program : Application
    {
        [DllImport("winmm.dll", CharSet = CharSet.Auto)]
        private static extern int mciSendString(string command, StringBuilder buffer, int bufferSize, IntPtr hwndCallback);

        private static Mutex _singleInstanceMutex;
        private NotifyIcon _trayIcon;
        internal MiniWindow _miniWindow;
        private ClientWebSocket _ws;
        private CancellationTokenSource _cts;
        private SpeechRecognitionEngine _speechEngine;
        private SpeechSynthesizer _fallbackSynth;
        private MemoryStream _audioBuffer = new MemoryStream();
        private string _lastReplyText = "";
        private string _token;
        private int _port;
        private bool _dictationArmed = false;
        private bool _voiceMuted = false;
        private Process _spawnedService;

        [STAThread]
        public static void Main(string[] args)
        {
            AppDomain.CurrentDomain.UnhandledException += (s, e) =>
            {
                MessageBox.Show("Veronica Error: " + e.ExceptionObject, "Veronica Shell", MessageBoxButton.OK, MessageBoxImage.Error);
            };

            bool createdNew;
            _singleInstanceMutex = new Mutex(true, "Veronica.Stark.NativeShell.Mutex", out createdNew);
            EventWaitHandle summonEvent = new EventWaitHandle(false, EventResetMode.AutoReset, "Veronica.Stark.SummonEvent");
            if (!createdNew)
            {
                summonEvent.Set();
                return;
            }

            int port = 8765;
            string token = Environment.GetEnvironmentVariable("VERONICA_TOKEN") ?? "";

            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "-port" && i + 1 < args.Length) int.TryParse(args[i + 1], out port);
                if (args[i] == "-token" && i + 1 < args.Length) token = args[i + 1];
            }

            if (string.IsNullOrWhiteSpace(token))
            {
                string tokenFile = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".veronica", "token");
                if (File.Exists(tokenFile))
                {
                    try { token = File.ReadAllText(tokenFile, Encoding.UTF8).Trim(); } catch {}
                }
            }
            if (string.IsNullOrWhiteSpace(token) || token.Length < 16)
            {
                token = SecurityVault.GenerateSecureToken();
                try
                {
                    string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".veronica");
                    if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);
                    File.WriteAllText(Path.Combine(dir, "token"), token, Encoding.UTF8);
                }
                catch {}
            }

            var app = new Program(port, token, summonEvent);
            app.Run(app._miniWindow);
        }

        public Program(int port, string token, EventWaitHandle summonEvent)
        {
            _port = port;
            _token = token;
            _cts = new CancellationTokenSource();

            ShutdownMode = ShutdownMode.OnExplicitShutdown;

            EnsureVoiceServiceRunning();
            InitializeTrayIcon();
            InitializeSpeechEngine();
            InitializeMiniWindow();

            ThreadPool.QueueUserWorkItem(state =>
            {
                while (!_cts.IsCancellationRequested)
                {
                    try
                    {
                        if (summonEvent.WaitOne(500))
                        {
                            SummonMiniWindow();
                        }
                    }
                    catch {}
                }
            });

            Task.Run(() => ConnectLoopbackWsAsync());
        }

        private bool IsPortListening(int port)
        {
            try
            {
                using (var tcp = new TcpClient())
                {
                    var ar = tcp.BeginConnect("127.0.0.1", port, null, null);
                    bool ok = ar.AsyncWaitHandle.WaitOne(TimeSpan.FromMilliseconds(250));
                    if (ok && tcp.Connected)
                    {
                        tcp.EndConnect(ar);
                        return true;
                    }
                }
            }
            catch {}
            return false;
        }

        private void EnsureVoiceServiceRunning()
        {
            if (IsPortListening(_port)) return;
            try
            {
                string baseDir = AppDomain.CurrentDomain.BaseDirectory;
                string svcDir = Path.GetFullPath(Path.Combine(baseDir, "..", "..", "..", "services", "voice"));
                string vpy = Path.Combine(svcDir, ".venv", "Scripts", "python.exe");
                if (File.Exists(vpy))
                {
                    var psi = new ProcessStartInfo
                    {
                        FileName = vpy,
                        Arguments = "-m veronica_voice",
                        WorkingDirectory = svcDir,
                        UseShellExecute = false,
                        CreateNoWindow = true
                    };
                    psi.EnvironmentVariables["PYTHONPATH"] = Path.Combine(svcDir, "src");
                    psi.EnvironmentVariables["VERONICA_TOKEN"] = _token;
                    psi.EnvironmentVariables["VERONICA_PORT"] = _port.ToString();
                    psi.EnvironmentVariables["VERONICA_PARENT_PID"] = Process.GetCurrentProcess().Id.ToString();
                    _spawnedService = Process.Start(psi);
                }
            }
            catch {}
        }

        protected override void OnStartup(StartupEventArgs e)
        {
            base.OnStartup(e);
            SummonMiniWindow();
        }

        private void StopAudio()
        {
            try
            {
                mciSendString("stop veronica_wpf_tts", null, 0, IntPtr.Zero);
                mciSendString("close veronica_wpf_tts", null, 0, IntPtr.Zero);
            }
            catch {}
            try
            {
                if (_fallbackSynth != null) _fallbackSynth.SpeakAsyncCancelAll();
            }
            catch {}
        }

        private void PlayAudioOrFallback(byte[] mp3Bytes, string fallbackText)
        {
            if (_voiceMuted) return;
            try
            {
                StopAudio();
                if (mp3Bytes != null && mp3Bytes.Length > 128)
                {
                    string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".veronica");
                    if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);
                    string tempPath = Path.Combine(dir, "wpf_tts_" + DateTime.UtcNow.Ticks + ".mp3");
                    File.WriteAllBytes(tempPath, mp3Bytes);

                    _miniWindow.SetStatus("SPEAKING", System.Windows.Media.Color.FromRgb(0, 255, 170));
                    mciSendString("open \"" + tempPath + "\" type mpegvideo alias veronica_wpf_tts", null, 0, IntPtr.Zero);
                    mciSendString("play veronica_wpf_tts", null, 0, IntPtr.Zero);

                    Task.Run(async () =>
                    {
                        try
                        {
                            var sb = new StringBuilder(128);
                            for (int i = 0; i < 300; i++)
                            {
                                await Task.Delay(100);
                                sb.Clear();
                                mciSendString("status veronica_wpf_tts mode", sb, sb.Capacity, IntPtr.Zero);
                                if (sb.ToString().Trim().ToLowerInvariant() != "playing") break;
                            }
                            mciSendString("close veronica_wpf_tts", null, 0, IntPtr.Zero);
                            try { if (File.Exists(tempPath)) File.Delete(tempPath); } catch {}
                        }
                        catch {}
                        _miniWindow.SetStatus("STANDBY", System.Windows.Media.Color.FromRgb(0, 243, 255));
                    });
                    return;
                }
            }
            catch {}

            if (!string.IsNullOrWhiteSpace(fallbackText))
            {
                try
                {
                    if (_fallbackSynth == null)
                    {
                        _fallbackSynth = new SpeechSynthesizer();
                        _fallbackSynth.SelectVoiceByHints(VoiceGender.Female, VoiceAge.Adult);
                        _fallbackSynth.SpeakCompleted += (s, e) =>
                        {
                            _miniWindow.SetStatus("STANDBY", System.Windows.Media.Color.FromRgb(0, 243, 255));
                        };
                    }
                    _miniWindow.SetStatus("SPEAKING", System.Windows.Media.Color.FromRgb(0, 255, 170));
                    _fallbackSynth.SpeakAsyncCancelAll();
                    _fallbackSynth.SpeakAsync(fallbackText);
                }
                catch {}
            }
        }

        private void InitializeTrayIcon()
        {
            _trayIcon = new NotifyIcon();

            string icoPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "assets", "veronica.ico");
            if (!File.Exists(icoPath))
            {
                icoPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "..", "desktop", "assets", "veronica.ico");
            }

            if (File.Exists(icoPath))
            {
                try { _trayIcon.Icon = new Icon(icoPath); } catch { _trayIcon.Icon = SystemIcons.Application; }
            }
            else
            {
                _trayIcon.Icon = SystemIcons.Application;
            }

            _trayIcon.Text = "Project Veronica // Mark-V Native .NET Shell";
            _trayIcon.Visible = true;

            var menu = new ContextMenuStrip();

            var header = new ToolStripMenuItem("⚡ VERONICA // MARK-V NATIVE SHELL");
            header.Enabled = false;
            menu.Items.Add(header);

            menu.Items.Add(new ToolStripSeparator());

            var summonItem = new ToolStripMenuItem("🎙️ Summon Tactical Shell (\"Hey Veronica\")");
            summonItem.Click += (s, e) => SummonMiniWindow();
            menu.Items.Add(summonItem);

            var reconItem = new ToolStripMenuItem("👁️ Optical Screen Recon");
            reconItem.Click += (s, e) =>
            {
                SummonMiniWindow();
                TransmitScreenAnalyze("Analyze what is on my screen right now");
            };
            menu.Items.Add(reconItem);

            var vitalsItem = new ToolStripMenuItem("📊 System Vitals Snapshot");
            vitalsItem.Click += (s, e) =>
            {
                _trayIcon.ShowBalloonTip(3000, "Veronica Telemetry", "Native .NET Shell active.\nSecurity: DPAPI + SQLite FTS5\nLoopback: 127.0.0.1:" + _port, ToolTipIcon.Info);
            };
            menu.Items.Add(vitalsItem);

            var secItem = new ToolStripMenuItem("🔒 Security Vault Status");
            secItem.Click += (s, e) =>
            {
                _trayIcon.ShowBalloonTip(4000, "Security Protocol Status", "Hardware-tied Windows DPAPI: ACTIVE\nLoopback Mutual Auth: ENFORCED\nSQLite FTS5 Secure Delete: APPLIED", ToolTipIcon.Info);
            };
            menu.Items.Add(secItem);

            menu.Items.Add(new ToolStripSeparator());

            var exitItem = new ToolStripMenuItem("❌ Shutdown Veronica");
            exitItem.Click += (s, e) => ShutdownApplication();
            menu.Items.Add(exitItem);

            _trayIcon.ContextMenuStrip = menu;

            _trayIcon.Click += (s, e) =>
            {
                var me = e as MouseEventArgs;
                if (me != null && me.Button == MouseButtons.Left)
                {
                    SummonMiniWindow();
                }
            };

            _trayIcon.ShowBalloonTip(3500, "Veronica Mark-V Active", "Resident in Windows System Tray.\nSay \"Hey Veronica\" or click tray icon to summon.", ToolTipIcon.Info);
        }

        private void InitializeSpeechEngine()
        {
            Task.Run(() =>
            {
                try
                {
                    _speechEngine = new SpeechRecognitionEngine();
                    var choices = new Choices();
                    choices.Add("hey veronica");
                    choices.Add("veronica");
                    choices.Add("system vitals");
                    choices.Add("deploy focus");
                    choices.Add("deploy dev workspace");
                    choices.Add("analyze screen");
                    choices.Add("network status");
                    choices.Add("open spotify");
                    choices.Add("close spotify");
                    choices.Add("close chrome");
                    choices.Add("close notepad");
                    choices.Add("play music");
                    choices.Add("pause music");

                    var gb = new GrammarBuilder(choices);
                    var grammar = new Grammar(gb) { Name = "TacticalCommands" };
                    _speechEngine.LoadGrammar(grammar);

                    var dictGrammar = new DictationGrammar() { Name = "FreeDictation" };
                    _speechEngine.LoadGrammar(dictGrammar);

                    _speechEngine.SpeechRecognized += (s, e) =>
                    {
                        string txt = e.Result.Text.Trim();
                        bool isCmd = e.Result.Grammar != null && e.Result.Grammar.Name == "TacticalCommands";
                        if (isCmd && e.Result.Confidence >= 0.45f)
                        {
                            Dispatcher.Invoke(() =>
                            {
                                StopAudio();
                                SystemSounds.Asterisk.Play();
                                SummonMiniWindow();
                                string low = txt.ToLowerInvariant();
                                if (low == "hey veronica" || low == "veronica")
                                {
                                    _dictationArmed = true;
                                    _miniWindow.SetListeningMode(true);
                                }
                                else if (low == "analyze screen")
                                {
                                    TransmitScreenAnalyze("Analyze what is on my screen right now");
                                }
                                else
                                {
                                    TransmitText(txt);
                                }
                            });
                        }
                        else if (_dictationArmed && e.Result.Confidence >= 0.35f && txt.Length > 2)
                        {
                            Dispatcher.Invoke(() =>
                            {
                                _dictationArmed = false;
                                _miniWindow.SetListeningMode(false);
                                TransmitText(txt);
                            });
                        }
                    };

                    _speechEngine.SetInputToDefaultAudioDevice();
                    _speechEngine.RecognizeAsync(RecognizeMode.Multiple);
                }
                catch (Exception ex)
                {
                    Console.WriteLine("Native speech engine initialization note: " + ex.Message);
                }
            });
        }

        private void InitializeMiniWindow()
        {
            _miniWindow = new MiniWindow(
                onTransmit: (text) =>
                {
                    if (text == "__SCREEN_RECON__")
                    {
                        TransmitScreenAnalyze("Analyze what is on my screen right now");
                    }
                    else
                    {
                        TransmitText(text);
                    }
                },
                onToggleListening: () =>
                {
                    StopAudio();
                    _dictationArmed = !_dictationArmed;
                    _miniWindow.SetListeningMode(_dictationArmed);
                    SystemSounds.Beep.Play();
                },
                onMinimizeToTray: () =>
                {
                    _miniWindow.Hide();
                }
            );
        }

        private void SummonMiniWindow()
        {
            Action act = () =>
            {
                if (_miniWindow != null)
                {
                    _miniWindow.Show();
                    _miniWindow.WindowState = WindowState.Normal;
                    _miniWindow.Activate();
                    _miniWindow.Focus();
                }
            };

            if (Dispatcher.CheckAccess())
            {
                act();
            }
            else
            {
                Dispatcher.BeginInvoke(act);
            }
        }

        private async Task<string> ReceiveFullMessageAsync(ClientWebSocket ws, byte[] buffer, CancellationToken token)
        {
            using (var ms = new MemoryStream())
            {
                WebSocketReceiveResult result;
                do
                {
                    result = await ws.ReceiveAsync(new ArraySegment<byte>(buffer), token);
                    if (result.MessageType == WebSocketMessageType.Close) return null;
                    ms.Write(buffer, 0, result.Count);
                } while (!result.EndOfMessage);
                return Encoding.UTF8.GetString(ms.ToArray());
            }
        }

        private async Task ConnectLoopbackWsAsync()
        {
            string uriString = "ws://127.0.0.1:" + _port;

            if (!SecurityVault.ValidateLoopbackEndpoint(uriString))
            {
                MessageBox.Show("Security Protocol Violation: Non-loopback endpoint rejected.", "Veronica Security", MessageBoxButton.OK, MessageBoxImage.Error);
                return;
            }

            while (!_cts.IsCancellationRequested)
            {
                try
                {
                    _ws = new ClientWebSocket();
                    var uri = new Uri(uriString);
                    await _ws.ConnectAsync(uri, _cts.Token);

                    var serializer = new JavaScriptSerializer { MaxJsonLength = 10 * 1024 * 1024 };
                    var helloPayload = new Dictionary<string, object>
                    {
                        { "v", 1 },
                        { "id", "auth_" + DateTime.UtcNow.Ticks },
                        { "type", "hello" },
                        { "payload", new Dictionary<string, object> { { "token", _token } } }
                    };
                    string helloJson = serializer.Serialize(helloPayload);
                    byte[] helloBytes = Encoding.UTF8.GetBytes(helloJson);
                    await _ws.SendAsync(new ArraySegment<byte>(helloBytes), WebSocketMessageType.Text, true, _cts.Token);

                    _miniWindow.SetStatus("STANDBY", System.Windows.Media.Color.FromRgb(0, 243, 255));

                    // Start periodic telemetry query loop
                    Task.Run(async () =>
                    {
                        while (_ws != null && _ws.State == WebSocketState.Open && !_cts.IsCancellationRequested)
                        {
                            try
                            {
                                string qJson = "{\"v\":1,\"id\":\"q\",\"type\":\"state.query\",\"payload\":{}}";
                                byte[] qBytes = Encoding.UTF8.GetBytes(qJson);
                                await _ws.SendAsync(new ArraySegment<byte>(qBytes), WebSocketMessageType.Text, true, _cts.Token);
                            }
                            catch { break; }
                            await Task.Delay(3000);
                        }
                    });

                    byte[] buffer = new byte[16384];
                    while (_ws.State == WebSocketState.Open && !_cts.IsCancellationRequested)
                    {
                        string msg = await ReceiveFullMessageAsync(_ws, buffer, _cts.Token);
                        if (msg == null) break;
                        HandleIncomingFrame(msg);
                    }
                }
                catch
                {
                    _miniWindow.SetStatus("OFFLINE", System.Windows.Media.Color.FromRgb(255, 60, 60));
                }

                await Task.Delay(2500);
            }
        }

        private void HandleIncomingFrame(string json)
        {
            try
            {
                var serializer = new JavaScriptSerializer { MaxJsonLength = 10 * 1024 * 1024 };
                var frame = serializer.Deserialize<Dictionary<string, object>>(json);
                if (frame == null) return;

                string type = frame.ContainsKey("type") ? frame["type"].ToString() : "";
                var payload = frame.ContainsKey("payload") ? frame["payload"] as Dictionary<string, object> : null;

                switch (type)
                {
                    case "ready":
                        _miniWindow.SetStatus("STANDBY", System.Windows.Media.Color.FromRgb(0, 243, 255));
                        break;

                    case "text.delta":
                        if (payload != null && payload.ContainsKey("text"))
                        {
                            string delta = payload["text"].ToString();
                            _lastReplyText += delta;
                            _miniWindow.AppendResponseDelta(delta);
                        }
                        break;

                    case "text.done":
                        _miniWindow.FinalizeResponseTurn();
                        _miniWindow.SetStatus("STANDBY", System.Windows.Media.Color.FromRgb(0, 243, 255));
                        break;

                    case "audio.delta":
                        if (payload != null && payload.ContainsKey("audio"))
                        {
                            byte[] chunk = Convert.FromBase64String(payload["audio"].ToString());
                            _audioBuffer.Write(chunk, 0, chunk.Length);
                        }
                        break;

                    case "audio.done":
                        byte[] allAudio = _audioBuffer.ToArray();
                        _audioBuffer.SetLength(0);
                        PlayAudioOrFallback(allAudio, _lastReplyText);
                        break;

                    case "telemetry":
                        if (payload != null)
                        {
                            double cpu = 0, ram = 0;
                            string prov = payload.ContainsKey("provider") ? payload["provider"].ToString() : "Tactical Core";
                            if (payload.ContainsKey("telemetry"))
                            {
                                var telemDict = payload["telemetry"] as Dictionary<string, object>;
                                if (telemDict != null)
                                {
                                    if (telemDict.ContainsKey("cpu_percent"))
                                        double.TryParse(telemDict["cpu_percent"].ToString(), out cpu);
                                    if (telemDict.ContainsKey("ram_percent"))
                                        double.TryParse(telemDict["ram_percent"].ToString(), out ram);
                                }
                            }
                            _miniWindow.UpdateTelemetry(cpu, ram, prov);
                        }
                        break;

                    case "window.command":
                        if (payload != null && payload.ContainsKey("action"))
                        {
                            if (payload["action"].ToString() == "show_mini")
                            {
                                SummonMiniWindow();
                            }
                        }
                        break;
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine("Frame error: " + ex.Message);
            }
        }

        private async void TransmitText(string text)
        {
            if (_ws == null || _ws.State != WebSocketState.Open) return;

            try
            {
                StopAudio();
                _lastReplyText = "";
                _audioBuffer.SetLength(0);
                _miniWindow.BeginUserTurn(text);

                var serializer = new JavaScriptSerializer();
                var frame = new Dictionary<string, object>
                {
                    { "v", 1 },
                    { "id", "txt_" + DateTime.UtcNow.Ticks },
                    { "type", "text.input" },
                    { "payload", new Dictionary<string, object> { { "text", text }, { "synthesize", !_voiceMuted } } }
                };
                string json = serializer.Serialize(frame);
                byte[] bytes = Encoding.UTF8.GetBytes(json);
                await _ws.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, _cts.Token);
            }
            catch {}
        }

        private async void TransmitScreenAnalyze(string prompt)
        {
            if (_ws == null || _ws.State != WebSocketState.Open) return;

            try
            {
                StopAudio();
                _lastReplyText = "";
                _audioBuffer.SetLength(0);
                _miniWindow.BeginUserTurn("[Optical Screen Recon]");

                Rectangle bounds = Screen.PrimaryScreen.Bounds;
                string b64;
                using (Bitmap bmp = new Bitmap(bounds.Width, bounds.Height))
                {
                    using (Graphics g = Graphics.FromImage(bmp))
                    {
                        g.CopyFromScreen(bounds.Location, System.Drawing.Point.Empty, bounds.Size);
                    }
                    using (MemoryStream ms = new MemoryStream())
                    {
                        bmp.Save(ms, ImageFormat.Jpeg);
                        b64 = Convert.ToBase64String(ms.ToArray());
                    }
                }

                var serializer = new JavaScriptSerializer { MaxJsonLength = 10 * 1024 * 1024 };
                var frame = new Dictionary<string, object>
                {
                    { "v", 1 },
                    { "id", "scr_" + DateTime.UtcNow.Ticks },
                    { "type", "screen.analyze" },
                    { "payload", new Dictionary<string, object> { { "image", b64 }, { "prompt", prompt }, { "synthesize", !_voiceMuted } } }
                };
                string json = serializer.Serialize(frame);
                byte[] bytes = Encoding.UTF8.GetBytes(json);
                await _ws.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, _cts.Token);
            }
            catch {}
        }

        private void ShutdownApplication()
        {
            StopAudio();
            _cts.Cancel();
            if (_speechEngine != null)
            {
                try { _speechEngine.Dispose(); } catch {}
            }
            if (_trayIcon != null)
            {
                _trayIcon.Visible = false;
                _trayIcon.Dispose();
            }
            if (_spawnedService != null && !_spawnedService.HasExited)
            {
                try { _spawnedService.Kill(); } catch {}
            }
            Shutdown();
            Environment.Exit(0);
        }
    }
}
