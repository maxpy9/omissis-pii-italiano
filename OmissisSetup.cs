using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

[assembly: AssemblyTitle("Omissis Studio — Installer & Launcher")]
[assembly: AssemblyDescription("Installer ed Esecutore Locale per Omissis (pii-italiano-v2)")]
[assembly: AssemblyCompany("Omissis Open Source")]
[assembly: AssemblyProduct("Omissis Studio")]
[assembly: AssemblyVersion("2.0.0.0")]
[assembly: AssemblyFileVersion("2.0.0.0")]

namespace OmissisSetup
{
    public class MainForm : Form
    {
        private TextBox txtPath;
        private Button btnBrowse;
        private Button btnInstallRun;
        private Button btnOpenBrowser;
        private ProgressBar progressBar;
        private Label lblStatus;
        private TextBox txtLog;
        private CheckBox chkDesktopShortcut;
        private PictureBox picLogo;
        private Process serverProcess;
        private bool isRunning = false;

        private const string REPO_ZIP_URL = "https://github.com/maxpy9/omissis-pii-italiano/archive/refs/heads/main.zip";
        private const string SERVER_URL = "http://127.0.0.1:8000";

        public MainForm(bool autoRun)
        {
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
            InitializeUi();
            if (autoRun)
            {
                this.Shown += async (s, e) => await StartInstallAndLaunchAsync();
            }
        }

        private void InitializeUi()
        {
            this.Text = "Omissis Studio — Installer & Launcher (Windows x64)";
            this.Size = new Size(760, 560);
            this.MinimumSize = new Size(700, 520);
            this.StartPosition = FormStartPosition.CenterScreen;
            this.BackColor = Color.FromArgb(10, 15, 29);
            this.ForeColor = Color.FromArgb(248, 250, 252);
            this.Font = new Font("Segoe UI", 9.5f, FontStyle.Regular);

            try
            {
                this.Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            }
            catch { }

            // Header Panel
            Panel header = new Panel
            {
                Dock = DockStyle.Top,
                Height = 88,
                BackColor = Color.FromArgb(15, 23, 42),
                Padding = new Padding(20, 14, 20, 14)
            };

            picLogo = new PictureBox
            {
                Size = new Size(58, 58),
                Location = new Point(20, 15),
                SizeMode = PictureBoxSizeMode.StretchImage,
                BackColor = Color.FromArgb(6, 9, 19)
            };
            try
            {
                Icon ico = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
                if (ico != null) picLogo.Image = ico.ToBitmap();
            }
            catch { }
            header.Controls.Add(picLogo);

            Label lblTitle = new Label
            {
                Text = "Omissis Studio — Setup & Avvio Rapido",
                Font = new Font("Segoe UI", 14f, FontStyle.Bold),
                ForeColor = Color.White,
                AutoSize = true,
                Location = new Point(92, 16)
            };
            header.Controls.Add(lblTitle);

            Label lblSub = new Label
            {
                Text = "Scarica il programma da GitHub, configura l'ambiente CPU-only e avvia il server locale (127.0.0.1:8000)",
                Font = new Font("Segoe UI", 9f, FontStyle.Regular),
                ForeColor = Color.FromArgb(148, 163, 184),
                AutoSize = true,
                Location = new Point(94, 46)
            };
            header.Controls.Add(lblSub);

            this.Controls.Add(header);

            // Body container
            Panel body = new Panel
            {
                Dock = DockStyle.Fill,
                Padding = new Padding(22)
            };

            Label lblDir = new Label
            {
                Text = "Cartella di installazione:",
                AutoSize = true,
                Location = new Point(22, 102),
                ForeColor = Color.FromArgb(203, 213, 225)
            };
            this.Controls.Add(lblDir);

            txtPath = new TextBox
            {
                Text = @"C:\omissis",
                Location = new Point(22, 126),
                Width = 575,
                BackColor = Color.FromArgb(15, 23, 42),
                ForeColor = Color.White,
                BorderStyle = BorderStyle.FixedSingle,
                Font = new Font("Consolas", 10f)
            };
            this.Controls.Add(txtPath);

            btnBrowse = new Button
            {
                Text = "Sfoglia...",
                Location = new Point(608, 124),
                Size = new Size(112, 28),
                BackColor = Color.FromArgb(30, 41, 59),
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                Cursor = Cursors.Hand
            };
            btnBrowse.FlatAppearance.BorderColor = Color.FromArgb(51, 65, 85);
            btnBrowse.Click += (s, e) =>
            {
                using (var fbd = new FolderBrowserDialog())
                {
                    fbd.SelectedPath = txtPath.Text;
                    if (fbd.ShowDialog() == DialogResult.OK)
                        txtPath.Text = fbd.SelectedPath;
                }
            };
            this.Controls.Add(btnBrowse);

            chkDesktopShortcut = new CheckBox
            {
                Text = "Crea collegamento 'Omissis Studio' sul Desktop",
                Checked = true,
                AutoSize = true,
                Location = new Point(22, 162),
                ForeColor = Color.FromArgb(203, 213, 225)
            };
            this.Controls.Add(chkDesktopShortcut);

            lblStatus = new Label
            {
                Text = "Pronto. Premi 'Scarica, Installa e Avvia' per iniziare.",
                AutoSize = true,
                Location = new Point(22, 196),
                Font = new Font("Segoe UI Semibold", 9.5f, FontStyle.Bold),
                ForeColor = Color.FromArgb(52, 211, 153)
            };
            this.Controls.Add(lblStatus);

            progressBar = new ProgressBar
            {
                Location = new Point(22, 222),
                Size = new Size(698, 18),
                Style = ProgressBarStyle.Continuous,
                Value = 0
            };
            this.Controls.Add(progressBar);

            txtLog = new TextBox
            {
                Multiline = true,
                ReadOnly = true,
                ScrollBars = ScrollBars.Vertical,
                Location = new Point(22, 252),
                Size = new Size(698, 195),
                BackColor = Color.FromArgb(6, 9, 19),
                ForeColor = Color.FromArgb(203, 213, 225),
                BorderStyle = BorderStyle.FixedSingle,
                Font = new Font("Consolas", 9f)
            };
            this.Controls.Add(txtLog);

            btnInstallRun = new Button
            {
                Text = "Scarica, Installa e Avvia Omissis",
                Location = new Point(22, 462),
                Size = new Size(340, 42),
                BackColor = Color.FromArgb(99, 102, 241),
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                Font = new Font("Segoe UI", 10.5f, FontStyle.Bold),
                Cursor = Cursors.Hand
            };
            btnInstallRun.FlatAppearance.BorderSize = 0;
            btnInstallRun.Click += async (s, e) => await StartInstallAndLaunchAsync();
            this.Controls.Add(btnInstallRun);

            btnOpenBrowser = new Button
            {
                Text = "Apri Interfaccia Web (127.0.0.1:8000)",
                Location = new Point(380, 462),
                Size = new Size(340, 42),
                BackColor = Color.FromArgb(16, 185, 129),
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                Font = new Font("Segoe UI", 10f, FontStyle.Bold),
                Cursor = Cursors.Hand,
                Enabled = CheckServerAlreadyAlive()
            };
            btnOpenBrowser.FlatAppearance.BorderSize = 0;
            btnOpenBrowser.Click += (s, e) => Process.Start(SERVER_URL);
            this.Controls.Add(btnOpenBrowser);

            Log("Benvenuto nell'installer nativo Windows di Omissis Studio.");
            Log("Sorgente ufficiale GitHub: https://github.com/maxpy9/omissis-pii-italiano");
        }

        private void Log(string msg)
        {
            if (this.InvokeRequired)
            {
                this.BeginInvoke(new Action<string>(Log), msg);
                return;
            }
            string line = string.Format("[{0:HH:mm:ss}] {1}{2}", DateTime.Now, msg, Environment.NewLine);
            txtLog.AppendText(line);
        }

        private void SetStatus(string msg, int progress)
        {
            if (this.InvokeRequired)
            {
                this.BeginInvoke(new Action<string, int>(SetStatus), msg, progress);
                return;
            }
            lblStatus.Text = msg;
            if (progress >= 0 && progress <= 100)
                progressBar.Value = progress;
        }

        private bool CheckServerAlreadyAlive()
        {
            try
            {
                var req = (HttpWebRequest)WebRequest.Create(SERVER_URL + "/api/health");
                req.Timeout = 800;
                using (var resp = (HttpWebResponse)req.GetResponse())
                {
                    return resp.StatusCode == HttpStatusCode.OK;
                }
            }
            catch
            {
                return false;
            }
        }

        private async Task StartInstallAndLaunchAsync()
        {
            if (isRunning) return;
            isRunning = true;
            btnInstallRun.Enabled = false;

            string baseDir = txtPath.Text.Trim();
            string appDir = Path.Combine(baseDir, "omissis-app");
            string modelDir = Path.Combine(baseDir, "pii-italiano-v2");

            try
            {
                await Task.Run(() =>
                {
                    Directory.CreateDirectory(baseDir);

                    // PASSO 1: Scarica il programma da GitHub se non presente o aggiorna i file core
                    SetStatus("Passo 1/4 — Download del programma da GitHub...", 15);
                    DownloadOrUpdateAppFromGitHub(baseDir, appDir);

                    // PASSO 2: Verifica/copia il modello pii-italiano-v2
                    SetStatus("Passo 2/4 — Verifica del modello pii-italiano-v2...", 40);
                    EnsureModelFolder(baseDir, modelDir, appDir);

                    // PASSO 3: Configura ambiente Python e dipendenze (tramite omissis.py --setup-only)
                    SetStatus("Passo 3/4 — Verifica ambiente virtuale e dipendenze CPU...", 65);
                    RunPythonSetup(appDir);

                    // Crea collegamento sul Desktop se richiesto
                    if (chkDesktopShortcut.Checked)
                    {
                        CreateDesktopShortcut(appDir);
                    }

                    // PASSO 4: Avvia il server locale e apri il browser
                    SetStatus("Passo 4/4 — Avvio del server Omissis su http://127.0.0.1:8000 ...", 90);
                    LaunchServerAndBrowser(appDir);

                    SetStatus("Omissis Studio è attivo su http://127.0.0.1:8000 !", 100);
                });

                btnOpenBrowser.Enabled = true;
                btnInstallRun.Text = "Riavvia / Aggiorna Omissis";
            }
            catch (Exception ex)
            {
                Log("ERRORE: " + ex.Message);
                SetStatus("Errore durante l'operazione. Controlla il registro.", 0);
                MessageBox.Show(this, ex.Message, "Errore Omissis Setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            finally
            {
                btnInstallRun.Enabled = true;
                isRunning = false;
            }
        }

        private void DownloadOrUpdateAppFromGitHub(string baseDir, string appDir)
        {
            string zipFile = Path.Combine(baseDir, "omissis-github-main.zip");
            string extractTemp = Path.Combine(baseDir, "_extract_tmp");

            try
            {
                Log("Connessione a " + REPO_ZIP_URL + " ...");
                using (var wc = new WebClient())
                {
                    wc.Headers.Add("User-Agent", "OmissisSetup-Windows-Exe");
                    wc.DownloadFile(REPO_ZIP_URL, zipFile);
                }
                Log("Pacchetto scaricato con successo (" + (new FileInfo(zipFile).Length / 1024) + " KB). Estrazione...");

                if (Directory.Exists(extractTemp))
                    Directory.Delete(extractTemp, true);

                ZipFile.ExtractToDirectory(zipFile, extractTemp);

                string[] subDirs = Directory.GetDirectories(extractTemp);
                string sourceRoot = subDirs.Length > 0 ? subDirs[0] : extractTemp;

                Directory.CreateDirectory(appDir);
                CopyDirectoryContents(sourceRoot, appDir);

                Log("File dell'applicazione installati/aggiornati in: " + appDir);
            }
            catch (Exception ex)
            {
                if (File.Exists(Path.Combine(appDir, "app.py")))
                {
                    Log("Download offline o non riuscito (" + ex.Message + "), uso installazione locale esistente in " + appDir);
                }
                else
                {
                    throw new Exception("Impossibile scaricare il programma da GitHub: " + ex.Message);
                }
            }
            finally
            {
                try { if (File.Exists(zipFile)) File.Delete(zipFile); } catch { }
                try { if (Directory.Exists(extractTemp)) Directory.Delete(extractTemp, true); } catch { }
            }
        }

        private void CopyDirectoryContents(string sourceDir, string targetDir)
        {
            Directory.CreateDirectory(targetDir);
            foreach (string file in Directory.GetFiles(sourceDir))
            {
                string name = Path.GetFileName(file);
                if (name.Equals("sessions_data.json", StringComparison.OrdinalIgnoreCase))
                    continue;
                File.Copy(file, Path.Combine(targetDir, name), true);
            }
            foreach (string dir in Directory.GetDirectories(sourceDir))
            {
                string name = Path.GetFileName(dir);
                if (name.Equals(".git", StringComparison.OrdinalIgnoreCase) || name.Equals("venv", StringComparison.OrdinalIgnoreCase))
                    continue;
                CopyDirectoryContents(dir, Path.Combine(targetDir, name));
            }
        }

        private void EnsureModelFolder(string baseDir, string modelDir, string appDir)
        {
            // Se esiste una sottocartella annidata pii-italiano-v2\pii-italiano-v2, appiattiscila
            string nested = Path.Combine(modelDir, "pii-italiano-v2");
            if (Directory.Exists(nested) && !File.Exists(Path.Combine(modelDir, "model.safetensors")))
            {
                Log("Correzione doppia cartella annidata pii-italiano-v2...");
                CopyDirectoryContents(nested, modelDir);
                try { Directory.Delete(nested, true); } catch { }
            }

            if (File.Exists(Path.Combine(modelDir, "model.safetensors")))
            {
                Log("Modello pii-italiano-v2 trovato e verificato in: " + modelDir);
                return;
            }

            // Cerca in C:\omissis\pii-italiano-v2 o Downloads/Desktop
            string userProfile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            string[] candidates = new string[]
            {
                @"C:\omissis\pii-italiano-v2",
                Path.Combine(userProfile, "Downloads", "pii-italiano-v2"),
                Path.Combine(userProfile, "Desktop", "pii-italiano-v2"),
                Path.Combine(userProfile, "Documents", "pii-italiano-v2")
            };

            foreach (string c in candidates)
            {
                if (Directory.Exists(c) && File.Exists(Path.Combine(c, "model.safetensors")))
                {
                    Log("Trovato modello in " + c + ". Copia in " + modelDir + "...");
                    CopyDirectoryContents(c, modelDir);
                    return;
                }
            }

            Log("Nota: model.safetensors verrà verificato/scaricato dallo script di bootstrap Python.");
        }

        private void RunPythonSetup(string appDir)
        {
            string venvPy = Path.Combine(appDir, "venv", "Scripts", "python.exe");
            string pyExe = File.Exists(venvPy) ? venvPy : "python";

            ProcessStartInfo psi = new ProcessStartInfo
            {
                FileName = pyExe,
                Arguments = "\"" + Path.Combine(appDir, "omissis.py") + "\" --setup-only",
                WorkingDirectory = appDir,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8
            };

            using (Process p = new Process { StartInfo = psi })
            {
                p.OutputDataReceived += (s, e) => { if (!string.IsNullOrEmpty(e.Data)) Log(e.Data); };
                p.ErrorDataReceived += (s, e) => { if (!string.IsNullOrEmpty(e.Data)) Log(e.Data); };
                p.Start();
                p.BeginOutputReadLine();
                p.BeginErrorReadLine();
                p.WaitForExit();
                if (p.ExitCode != 0)
                {
                    throw new Exception("Il setup Python ha restituito codice di uscita " + p.ExitCode);
                }
            }
        }

        private void CreateDesktopShortcut(string appDir)
        {
            try
            {
                string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                string exeDest = Path.Combine(appDir, "OmissisSetup.exe");
                if ( !Application.ExecutablePath.Equals(exeDest, StringComparison.OrdinalIgnoreCase))
                {
                    File.Copy(Application.ExecutablePath, exeDest, true);
                }

                string shortcutPath = Path.Combine(desktop, "Omissis Studio.lnk");
                string psScript = string.Format(
                    "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('{0}'); $s.TargetPath = '{1}'; $s.Arguments = '--autorun'; $s.WorkingDirectory = '{2}'; $s.IconLocation = '{1},0'; $s.Save()",
                    shortcutPath.Replace("'", "''"),
                    exeDest.Replace("'", "''"),
                    appDir.Replace("'", "''")
                );

                Process proc = Process.Start(new ProcessStartInfo
                {
                    FileName = "powershell.exe",
                    Arguments = "-NoProfile -WindowStyle Hidden -Command \"" + psScript + "\"",
                    UseShellExecute = false,
                    CreateNoWindow = true
                });
                if (proc != null) proc.WaitForExit(4000);

                Log("Collegamento 'Omissis Studio' creato sul Desktop.");
            }
            catch (Exception ex)
            {
                Log("Avviso creazione collegamento Desktop: " + ex.Message);
            }
        }

        private void LaunchServerAndBrowser(string appDir)
        {
            if (CheckServerAlreadyAlive())
            {
                Log("Il server è già in ascolto su " + SERVER_URL + ". Apertura del browser...");
                Process.Start(SERVER_URL);
                return;
            }

            string venvPy = Path.Combine(appDir, "venv", "Scripts", "python.exe");
            ProcessStartInfo psi = new ProcessStartInfo
            {
                FileName = venvPy,
                Arguments = "\"" + Path.Combine(appDir, "start.py") + "\"",
                WorkingDirectory = appDir,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            };

            serverProcess = new Process { StartInfo = psi };
            serverProcess.OutputDataReceived += (s, e) => { if (!string.IsNullOrEmpty(e.Data)) Log(e.Data); };
            serverProcess.ErrorDataReceived += (s, e) => { if (!string.IsNullOrEmpty(e.Data)) Log(e.Data); };
            serverProcess.Start();
            serverProcess.BeginOutputReadLine();
            serverProcess.BeginErrorReadLine();

            for (int i = 0; i < 40; i++)
            {
                if (CheckServerAlreadyAlive())
                {
                    Log("Server pronto e attivo su " + SERVER_URL + " !");
                    return;
                }
                Thread.Sleep(500);
            }
        }
    }

    static class Program
    {
        [STAThread]
        static void Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            bool autoRun = false;
            foreach (var a in args)
            {
                if (a.Equals("--autorun", StringComparison.OrdinalIgnoreCase))
                    autoRun = true;
            }
            Application.Run(new MainForm(autoRun));
        }
    }
}
