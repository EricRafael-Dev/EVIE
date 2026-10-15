using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

namespace JarvisLauncher
{
    static class Program
    {
        [STAThread]
        static void Main()
        {
            try
            {
                string baseDir = AppDomain.CurrentDomain.BaseDirectory;
                string mainScript = Path.Combine(baseDir, "main.py");

                if (!File.Exists(mainScript))
                {
                    MessageBox.Show(
                        "Arquivo main.py não encontrado na pasta:\n" + baseDir,
                        "JARVIS Launcher - Erro",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error
                    );
                    return;
                }

                // Procurar executável do Python
                string pythonExe = FindPython();
                if (string.IsNullOrEmpty(pythonExe))
                {
                    MessageBox.Show(
                        "Python não foi encontrado instalado no sistema.\nCertifique-se de que o Python está instalado e configurado no PATH.",
                        "JARVIS Launcher - Erro",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error
                    );
                    return;
                }

                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = pythonExe;
                psi.Arguments = "\"" + mainScript + "\"";
                psi.WorkingDirectory = baseDir;
                psi.UseShellExecute = false;

                Process.Start(psi);
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    "Erro ao iniciar o JARVIS:\n" + ex.Message,
                    "JARVIS Launcher - Erro",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
            }
        }

        static string FindPython()
        {
            // 1. Verificar caminhos comuns conhecidos no usuário
            string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string[] knownPaths = new string[]
            {
                Path.Combine(localAppData, @"Programs\Python\Python313\pythonw.exe"),
                Path.Combine(localAppData, @"Programs\Python\Python313\python.exe"),
                Path.Combine(localAppData, @"Programs\Python\Python312\pythonw.exe"),
                Path.Combine(localAppData, @"Programs\Python\Python312\python.exe"),
                Path.Combine(localAppData, @"Programs\Python\Python311\pythonw.exe"),
                Path.Combine(localAppData, @"Programs\Python\Python311\python.exe"),
                @"C:\Python313\pythonw.exe",
                @"C:\Python313\python.exe",
                @"C:\Python312\pythonw.exe",
                @"C:\Python312\python.exe"
            };

            foreach (string p in knownPaths)
            {
                if (File.Exists(p))
                    return p;
            }

            // 2. Verificar no PATH do sistema
            string pathEnv = Environment.GetEnvironmentVariable("PATH") ?? "";
            string[] paths = pathEnv.Split(';');
            foreach (string dir in paths)
            {
                if (string.IsNullOrEmpty(dir)) continue;
                string pw = Path.Combine(dir.Trim(), "pythonw.exe");
                if (File.Exists(pw)) return pw;
                string py = Path.Combine(dir.Trim(), "python.exe");
                if (File.Exists(py)) return py;
            }

            return null;
        }
    }
}
