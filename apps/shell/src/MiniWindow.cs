using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Media.Effects;
using System.Windows.Shapes;

namespace Veronica.Shell
{
    /// <summary>
    /// Pure Native Microsoft WPF Desktop Shell Window.
    /// Hardware-accelerated DirectX vector rendering with zero browser/Chromium overhead.
    /// Features: Animated vector Arc Reactor, drag-to-move, live transcript, and telemetry badges.
    /// </summary>
    public class MiniWindow : Window
    {
        private readonly Action<string> _onTransmit;
        private readonly Action _onToggleListening;
        private readonly Action _onMinimizeToTray;

        private TextBlock _statusText;
        private Border _statusPill;
        private TextBlock _vitalsText;
        private TextBlock _transcriptText;
        private TextBox _inputBox;
        private Ellipse _coreCenter;
        private RotateTransform _arcRotate;
        private Storyboard _arcStoryboard;
        private bool _isListening = false;

        public MiniWindow(Action<string> onTransmit, Action onToggleListening, Action onMinimizeToTray)
        {
            _onTransmit = onTransmit;
            _onToggleListening = onToggleListening;
            _onMinimizeToTray = onMinimizeToTray;

            InitializeWpfComponent();
        }

        private void InitializeWpfComponent()
        {
            Title = "VERONICA // NATIVE SHELL";
            Width = 450;
            Height = 280;
            WindowStyle = WindowStyle.None;
            AllowsTransparency = true;
            Background = Brushes.Transparent;
            Topmost = true;
            ShowInTaskbar = false;
            ResizeMode = ResizeMode.NoResize;

            // Position near bottom-right above system tray
            Rect workArea = SystemParameters.WorkArea;
            Left = Math.Max(40, workArea.Right - Width - 20);
            Top = Math.Max(40, workArea.Bottom - Height - 20);

            // Drag to reposition anywhere
            MouseDown += (s, e) =>
            {
                if (e.ChangedButton == MouseButton.Left)
                {
                    DragMove();
                }
            };

            // Outer Frame Border with Stark Cyan Glow
            var outerBorder = new Border
            {
                CornerRadius = new CornerRadius(10),
                Background = new SolidColorBrush(Color.FromArgb(242, 5, 8, 17)), // #050811 with slight translucency
                BorderBrush = new SolidColorBrush(Color.FromRgb(0, 243, 255)),   // Stark Cyan #00F3FF
                BorderThickness = new Thickness(1.5),
                Padding = new Thickness(10),
                Effect = new DropShadowEffect
                {
                    Color = Color.FromRgb(0, 243, 255),
                    BlurRadius = 18,
                    ShadowDepth = 0,
                    Opacity = 0.35
                }
            };

            var mainGrid = new Grid();
            mainGrid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto }); // Header
            mainGrid.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) }); // Core
            mainGrid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto }); // Chips
            mainGrid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto }); // Footer

            // 1. Header Row
            var headerGrid = new Grid();
            headerGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            headerGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            headerGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

            var titlePanel = new StackPanel { Orientation = Orientation.Horizontal };
            var pulseDot = new Ellipse
            {
                Width = 8,
                Height = 8,
                Fill = new SolidColorBrush(Color.FromRgb(0, 243, 255)),
                Margin = new Thickness(0, 0, 6, 0),
                VerticalAlignment = VerticalAlignment.Center,
                Effect = new DropShadowEffect { Color = Color.FromRgb(0, 243, 255), BlurRadius = 6, ShadowDepth = 0 }
            };
            titlePanel.Children.Add(pulseDot);

            var titleLabel = new TextBlock
            {
                Text = "VERONICA // NATIVE SHELL",
                FontFamily = new FontFamily("Segoe UI, Rajdhani"),
                FontWeight = FontWeights.Bold,
                FontSize = 12,
                Foreground = new SolidColorBrush(Color.FromRgb(0, 243, 255)),
                VerticalAlignment = VerticalAlignment.Center
            };
            titlePanel.Children.Add(titleLabel);

            _statusPill = new Border
            {
                Background = new SolidColorBrush(Color.FromArgb(40, 0, 243, 255)),
                BorderBrush = new SolidColorBrush(Color.FromArgb(120, 0, 243, 255)),
                BorderThickness = new Thickness(1),
                CornerRadius = new CornerRadius(3),
                Padding = new Thickness(6, 1, 6, 1),
                Margin = new Thickness(8, 0, 0, 0),
                VerticalAlignment = VerticalAlignment.Center
            };
            _statusText = new TextBlock
            {
                Text = "STANDBY",
                FontFamily = new FontFamily("Consolas, Segoe UI"),
                FontSize = 9,
                FontWeight = FontWeights.Bold,
                Foreground = new SolidColorBrush(Color.FromRgb(0, 243, 255))
            };
            _statusPill.Child = _statusText;
            titlePanel.Children.Add(_statusPill);

            Grid.SetColumn(titlePanel, 0);
            headerGrid.Children.Add(titlePanel);

            // Tray Minimize Button
            var trayBtn = new Button
            {
                Content = "🗕 TRAY",
                FontFamily = new FontFamily("Segoe UI"),
                FontSize = 10,
                FontWeight = FontWeights.SemiBold,
                Foreground = new SolidColorBrush(Color.FromRgb(0, 243, 255)),
                Background = new SolidColorBrush(Color.FromArgb(30, 0, 243, 255)),
                BorderBrush = new SolidColorBrush(Color.FromArgb(80, 0, 243, 255)),
                BorderThickness = new Thickness(1),
                Padding = new Thickness(6, 2, 6, 2),
                Cursor = Cursors.Hand
            };
            trayBtn.Click += (s, e) => _onMinimizeToTray();
            Grid.SetColumn(trayBtn, 2);
            headerGrid.Children.Add(trayBtn);

            Grid.SetRow(headerGrid, 0);
            mainGrid.Children.Add(headerGrid);

            // 2. Middle Row: Arc Reactor + Live Feed
            var centerGrid = new Grid { Margin = new Thickness(0, 8, 0, 8) };
            centerGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(90) });
            centerGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });

            // Vector Arc Reactor Canvas (Hardware Accelerated)
            var arcCanvas = new Canvas
            {
                Width = 84,
                Height = 84,
                Cursor = Cursors.Hand,
                ToolTip = "Click to toggle voice listening, or say 'Hey Veronica'"
            };
            arcCanvas.MouseDown += (s, e) => _onToggleListening();

            // Outer Glow Ellipse
            var outerGlow = new Ellipse
            {
                Width = 80,
                Height = 80,
                Stroke = new SolidColorBrush(Color.FromArgb(100, 0, 243, 255)),
                StrokeThickness = 1.5,
                Margin = new Thickness(2)
            };
            arcCanvas.Children.Add(outerGlow);

            // Rotating Dashed Ring
            _arcRotate = new RotateTransform(0, 42, 42);
            var dashedRing = new Ellipse
            {
                Width = 66,
                Height = 66,
                Stroke = new SolidColorBrush(Color.FromRgb(0, 243, 255)),
                StrokeThickness = 2,
                StrokeDashArray = new DoubleCollection(new double[] { 3, 2 }),
                RenderTransform = _arcRotate,
                Margin = new Thickness(9)
            };
            arcCanvas.Children.Add(dashedRing);

            // Center Plasma Core
            _coreCenter = new Ellipse
            {
                Width = 24,
                Height = 24,
                Fill = new SolidColorBrush(Color.FromRgb(0, 243, 255)),
                Margin = new Thickness(30),
                Effect = new DropShadowEffect
                {
                    Color = Color.FromRgb(0, 243, 255),
                    BlurRadius = 12,
                    ShadowDepth = 0
                }
            };
            arcCanvas.Children.Add(_coreCenter);

            // Rotation Storyboard
            var rotateAnim = new DoubleAnimation
            {
                From = 0,
                To = 360,
                Duration = TimeSpan.FromSeconds(6),
                RepeatBehavior = RepeatBehavior.Forever
            };
            _arcStoryboard = new Storyboard();
            _arcStoryboard.Children.Add(rotateAnim);
            Storyboard.SetTarget(rotateAnim, _arcRotate);
            Storyboard.SetTargetProperty(rotateAnim, new PropertyPath(RotateTransform.AngleProperty));
            _arcStoryboard.Begin();

            Grid.SetColumn(arcCanvas, 0);
            centerGrid.Children.Add(arcCanvas);

            // Feed Panel (Right)
            var feedPanel = new Grid();
            feedPanel.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            feedPanel.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });

            _vitalsText = new TextBlock
            {
                Text = "CPU: --%   RAM: --%   SEC: ACTIVE",
                FontFamily = new FontFamily("Consolas, Segoe UI"),
                FontSize = 10,
                Foreground = new SolidColorBrush(Color.FromRgb(112, 144, 176)),
                Margin = new Thickness(4, 0, 0, 4)
            };
            Grid.SetRow(_vitalsText, 0);
            feedPanel.Children.Add(_vitalsText);

            var scroll = new ScrollViewer
            {
                VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled,
                Margin = new Thickness(4, 0, 0, 0)
            };
            _transcriptText = new TextBlock
            {
                Text = "Native .NET Shell active.\nSay \"Hey Veronica\" or type below.",
                FontFamily = new FontFamily("Segoe UI"),
                FontSize = 11,
                Foreground = new SolidColorBrush(Color.FromRgb(226, 241, 255)),
                TextWrapping = TextWrapping.Wrap,
                LineHeight = 16
            };
            scroll.Content = _transcriptText;
            Grid.SetRow(scroll, 1);
            feedPanel.Children.Add(scroll);

            Grid.SetColumn(feedPanel, 1);
            centerGrid.Children.Add(feedPanel);

            Grid.SetRow(centerGrid, 1);
            mainGrid.Children.Add(centerGrid);

            // 3. Quick Chips Row
            var chipsPanel = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                Margin = new Thickness(0, 0, 0, 6)
            };

            string[] chips = { "⚡ Vitals", "🎯 Focus", "💻 Dev Macro", "🔒 Security" };
            foreach (var chip in chips)
            {
                var btn = new Button
                {
                    Content = chip,
                    FontFamily = new FontFamily("Segoe UI"),
                    FontSize = 10,
                    FontWeight = FontWeights.SemiBold,
                    Foreground = new SolidColorBrush(Color.FromRgb(146, 213, 255)),
                    Background = new SolidColorBrush(Color.FromArgb(25, 0, 119, 255)),
                    BorderBrush = new SolidColorBrush(Color.FromArgb(70, 0, 243, 255)),
                    BorderThickness = new Thickness(1),
                    Padding = new Thickness(8, 2, 8, 2),
                    Margin = new Thickness(0, 0, 6, 0),
                    Cursor = Cursors.Hand
                };
                string query = chip.Substring(2).Trim();
                btn.Click += (s, e) =>
                {
                    if (query == "Vitals") _onTransmit("Check system vitals");
                    else if (query == "Focus") _onTransmit("Deploy focus mode");
                    else if (query == "Dev Macro") _onTransmit("Deploy dev workspace macro");
                    else if (query == "Security") _onTransmit("Check security protocols and encryption status");
                };
                chipsPanel.Children.Add(btn);
            }

            Grid.SetRow(chipsPanel, 2);
            mainGrid.Children.Add(chipsPanel);

            // 4. Input Footer Row
            var inputGrid = new Grid();
            inputGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            inputGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

            _inputBox = new TextBox
            {
                Background = new SolidColorBrush(Color.FromArgb(120, 0, 0, 0)),
                Foreground = new SolidColorBrush(Color.FromRgb(226, 241, 255)),
                BorderBrush = new SolidColorBrush(Color.FromArgb(100, 0, 243, 255)),
                BorderThickness = new Thickness(1),
                Padding = new Thickness(6, 3, 6, 3),
                FontSize = 11,
                CaretBrush = new SolidColorBrush(Color.FromRgb(0, 243, 255))
            };
            _inputBox.KeyDown += (s, e) =>
            {
                if (e.Key == Key.Enter)
                {
                    SubmitInput();
                }
            };
            Grid.SetColumn(_inputBox, 0);
            inputGrid.Children.Add(_inputBox);

            var sendBtn = new Button
            {
                Content = "➤",
                FontWeight = FontWeights.Bold,
                FontSize = 11,
                Foreground = new SolidColorBrush(Color.FromRgb(5, 8, 17)),
                Background = new SolidColorBrush(Color.FromRgb(0, 243, 255)),
                BorderThickness = new Thickness(0),
                Padding = new Thickness(10, 3, 10, 3),
                Margin = new Thickness(6, 0, 0, 0),
                Cursor = Cursors.Hand
            };
            sendBtn.Click += (s, e) => SubmitInput();
            Grid.SetColumn(sendBtn, 1);
            inputGrid.Children.Add(sendBtn);

            Grid.SetRow(inputGrid, 3);
            mainGrid.Children.Add(inputGrid);

            outerBorder.Child = mainGrid;
            Content = outerBorder;
        }

        private void SubmitInput()
        {
            string text = _inputBox.Text.Trim();
            if (!string.IsNullOrEmpty(text))
            {
                _transcriptText.Text = "You: " + text + "\nVeronica: Thinking...";
                _inputBox.Text = string.Empty;
                SetStatus("THINKING", Color.FromRgb(112, 180, 255));
                _onTransmit(text);
            }
        }

        public void SetStatus(string label, Color color)
        {
            Dispatcher.Invoke(() =>
            {
                _statusText.Text = label;
                _statusText.Foreground = new SolidColorBrush(color);
                _statusPill.BorderBrush = new SolidColorBrush(color);
            });
        }

        public void UpdateTelemetry(double cpuPercent, double ramPercent)
        {
            Dispatcher.Invoke(() =>
            {
                _vitalsText.Text = string.Format("CPU: {0:F0}%   RAM: {1:F0}%   SEC: ACTIVE", cpuPercent, ramPercent);
            });
        }

        public void UpdateTranscript(string userText, string veronicaReply)
        {
            Dispatcher.Invoke(() =>
            {
                if (!string.IsNullOrEmpty(userText))
                {
                    _transcriptText.Text = "You: " + userText + "\nVeronica: " + veronicaReply;
                }
                else
                {
                    _transcriptText.Text = "Veronica: " + veronicaReply;
                }
            });
        }

        public void AppendResponseDelta(string delta)
        {
            Dispatcher.Invoke(() =>
            {
                _transcriptText.Text += delta;
            });
        }

        public void SetListeningMode(bool listening)
        {
            _isListening = listening;
            Dispatcher.Invoke(() =>
            {
                if (listening)
                {
                    SetStatus("LISTENING", Color.FromRgb(255, 183, 0));
                    _coreCenter.Fill = new SolidColorBrush(Color.FromRgb(255, 183, 0));
                }
                else
                {
                    SetStatus("STANDBY", Color.FromRgb(0, 243, 255));
                    _coreCenter.Fill = new SolidColorBrush(Color.FromRgb(0, 243, 255));
                }
            });
        }
    }
}
