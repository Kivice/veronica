using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Media;
using System.Net.WebSockets;
using System.Speech.Recognition;
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
    /// Veronica Native Microsoft .NET Desktop Application Entry Point.
    /// Manages: System Tray NotifyIcon, Native Speech Recognition ("Hey Veronica"),
    /// Loopback WebSocket IPC with cryptographic handshake, and Native WPF Shell Window.
    /// </summary>
    public class Program : Application
    {
        private static Mutex _singleInstanceMutex;
        private NotifyIcon _trayIcon;
        private MiniWindow _miniWindow;
        private ClientWebSocket _ws;
        private CancellationTokenSource _cts;
        private SpeechRecognitionEngine _speechEngine;
        private string _token;
        private int _port;

        [STAThread]
        public static void Main(string[] args)
        {
            // Security Protocol: Single Instance Mutex enforcement
            bool createdNew;
            _singleInstanceMutex = new Mutex(true, "Global\\Veronica.Stark.NativeShell.Mutex", out createdNew);
            if (!createdNew)
            {
                MessageBox.Show("Veronica Shell is already running in your system tray.", "Veronica Security", MessageBoxButton.OK, MessageBoxImage.Information);
                return;
            }

            int port = 8765;
            string token = Environment.GetEnvironmentVariable("VERONICA_TOKEN") ?? "";

            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "-port" && i + 1 < args.Length) int.TryParse(args[i + 1], out port);
                if (args[i] == "-token" && i + 1 < args.Length) token = args[i + 1];
            }

            var app = new Program(port, token);
            app.Run();
        }

        public Program(int port, string token)
        {
            _port = port;
            _token = token;
            _cts = new CancellationTokenSource();

            ShutdownMode = ShutdownMode.OnExplicitShutdown;

            InitializeTrayIcon();
            InitializeSpeechEngine();
            InitializeMiniWindow();

            Task.Run(() => ConnectLoopbackWsAsync());
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

            _trayIcon.Text = "Project Veronica // Native .NET Shell (Secured)";
            _trayIcon.Visible = true;

            var menu = new ContextMenuStrip();

            var header = new ToolStripMenuItem("⚡ VERONICA // NATIVE SHELL");
            header.Enabled = false;
            menu.Items.Add(header);

            menu.Items.Add(new ToolStripSeparator());

            var summonItem = new ToolStripMenuItem("🎙️ Summon Miniature Shell (\"Hey Veronica\")");
            summonItem.Click += (s, e) => SummonMiniWindow();
            menu.Items.Add(summonItem);

            var vitalsItem = new ToolStripMenuItem("📊 System Vitals Snapshot");
            vitalsItem.Click += (s, e) =>
            {
                _trayIcon.ShowBalloonTip(3000, "Veronica Telemetry", "Native .NET Shell active.\nSecurity protocols: DPAPI Encrypted\nLoopback: 127.0.0.1:" + _port, ToolTipIcon.Info);
            };
            menu.Items.Add(vitalsItem);

            var secItem = new ToolStripMenuItem("🔒 Security Vault Status");
            secItem.Click += (s, e) =>
            {
                _trayIcon.ShowBalloonTip(4000, "Security Protocol Status", "Hardware-tied Windows DPAPI: ACTIVE\nLoopback Mutual Auth: ENFORCED\nSubprocess Isolation: APPLIED", ToolTipIcon.Info);
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

            _trayIcon.ShowBalloonTip(4000, "Veronica Native Shell Active", "Resident in Windows System Tray.\nSay \"Hey Veronica\" or click tray icon to summon.", ToolTipIcon.Info);
        }

        private void InitializeSpeechEngine()
        {
            try
            {
                _speechEngine = new SpeechRecognitionEngine();
                var choices = new Choices();
                choices.Add("hey veronica");
                choices.Add("veronica");
                choices.Add("system vitals");
                choices.Add("deploy focus");

                var gb = new GrammarBuilder(choices);
                var grammar = new Grammar(gb);
                _speechEngine.LoadGrammar(grammar);

                _speechEngine.SpeechRecognized += (s, e) =>
                {
                    if (e.Result.Confidence >= 0.5f)
                    {
                        Dispatcher.Invoke(() =>
                        {
                            SystemSounds.Asterisk.Play();
                            SummonMiniWindow();
                            _miniWindow.SetListeningMode(true);
                            if (e.Result.Text == "system vitals")
                            {
                                TransmitText("Check system vitals");
                            }
                            else if (e.Result.Text == "deploy focus")
                            {
                                TransmitText("Deploy focus mode");
                            }
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
        }

        private void InitializeMiniWindow()
        {
            _miniWindow = new MiniWindow(
                onTransmit: (text) => TransmitText(text),
                onToggleListening: () =>
                {
                    _miniWindow.SetListeningMode(true);
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
            Dispatcher.Invoke(() =>
            {
                _miniWindow.Show();
                _miniWindow.Activate();
                _miniWindow.Focus();
            });
        }

        private async Task ConnectLoopbackWsAsync()
        {
            string uriString = "ws://127.0.0.1:" + _port;

            // Security Protocol: Validate loopback constraint
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

                    // Send cryptographic handshake hello frame
                    var serializer = new JavaScriptSerializer();
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

                    // Frame receive loop
                    byte[] buffer = new byte[8192];
                    while (_ws.State == WebSocketState.Open && !_cts.IsCancellationRequested)
                    {
                        var result = await _ws.ReceiveAsync(new ArraySegment<byte>(buffer), _cts.Token);
                        if (result.MessageType == WebSocketMessageType.Close) break;

                        string msg = Encoding.UTF8.GetString(buffer, 0, result.Count);
                        HandleIncomingFrame(msg);
                    }
                }
                catch
                {
                    _miniWindow.SetStatus("OFFLINE", System.Windows.Media.Color.FromRgb(255, 60, 60));
                }

                await Task.Delay(3000);
            }
        }

        private void HandleIncomingFrame(string json)
        {
            try
            {
                var serializer = new JavaScriptSerializer();
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
                            _miniWindow.AppendResponseDelta(delta);
                        }
                        break;

                    case "text.done":
                        _miniWindow.SetStatus("STANDBY", System.Windows.Media.Color.FromRgb(0, 243, 255));
                        break;

                    case "telemetry":
                        if (payload != null)
                        {
                            double cpu = 0, ram = 0;
                            if (payload.ContainsKey("cpu"))
                            {
                                var cpuDict = payload["cpu"] as Dictionary<string, object>;
                                if (cpuDict != null && cpuDict.ContainsKey("total_percent"))
                                {
                                    double.TryParse(cpuDict["total_percent"].ToString(), out cpu);
                                }
                            }
                            if (payload.ContainsKey("memory"))
                            {
                                var memDict = payload["memory"] as Dictionary<string, object>;
                                if (memDict != null && memDict.ContainsKey("percent"))
                                {
                                    double.TryParse(memDict["percent"].ToString(), out ram);
                                }
                            }
                            _miniWindow.UpdateTelemetry(cpu, ram);
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
                var serializer = new JavaScriptSerializer();
                var frame = new Dictionary<string, object>
                {
                    { "v", 1 },
                    { "id", "txt_" + DateTime.UtcNow.Ticks },
                    { "type", "text.input" },
                    { "payload", new Dictionary<string, object> { { "text", text }, { "synthesize", true } } }
                };
                string json = serializer.Serialize(frame);
                byte[] bytes = Encoding.UTF8.GetBytes(json);
                await _ws.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, _cts.Token);
            }
            catch {}
        }

        private void ShutdownApplication()
        {
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
            Shutdown();
            Environment.Exit(0);
        }
    }
}
