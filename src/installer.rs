use std::env;
use std::ffi::OsStr;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitStatus, Stdio};

#[derive(Debug)]
enum InstallerError {
    Io(std::io::Error),
    Message(String),
}

impl std::fmt::Display for InstallerError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            InstallerError::Io(e) => write!(f, "IO error: {}", e),
            InstallerError::Message(m) => write!(f, "{}", m),
        }
    }
}

impl From<std::io::Error> for InstallerError {
    fn from(e: std::io::Error) -> Self {
        InstallerError::Io(e)
    }
}

type Result<T> = std::result::Result<T, InstallerError>;

fn current_platform() -> &'static str {
    if cfg!(target_os = "windows") {
        "windows"
    } else if cfg!(target_os = "macos") {
        "macos"
    } else {
        "linux"
    }
}

fn find_python() -> Option<PathBuf> {
    let candidates: &[&str] = if cfg!(target_os = "windows") {
        &["python", "python3", "py"]
    } else {
        &["python3", "python"]
    };

    for candidate in candidates {
        if let Ok(output) = Command::new(candidate)
            .arg("--version")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .output()
        {
            if output.status.success() {
                return Some(PathBuf::from(candidate));
            }
        }
    }
    None
}

fn find_pyinstaller(python: &Path) -> bool {
    Command::new(python)
        .args(["-m", "PyInstaller", "--version"])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

fn install_pyinstaller(python: &Path) -> Result<()> {
    let status = Command::new(python)
        .args(["-m", "pip", "install", "--quiet", "pyinstaller"])
        .status()?;
    if !status.success() {
        return Err(InstallerError::Message(
            "Failed to install PyInstaller via pip.".to_string(),
        ));
    }
    Ok(())
}

fn compile_with_pyinstaller(python: &Path, script: &str, workdir: &Path) -> Result<()> {
    let script_path = workdir.join(script);
    if !script_path.exists() {
        return Err(InstallerError::Message(format!(
            "Script not found: {}",
            script_path.display()
        )));
    }

    let status = Command::new(python)
        .args([
            "-m",
            "PyInstaller",
            "--noconsole",
            "--onefile",
            "--clean",
            script,
        ])
        .current_dir(workdir)
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .status()?;

    if !status.success() {
        return Err(InstallerError::Message(format!(
            "PyInstaller failed for {}",
            script
        )));
    }
    Ok(())
}

fn copy_to_start_menu(source: &Path) -> Result<PathBuf> {
    let appdata = env::var("APPDATA").map_err(|_| {
        InstallerError::Message("APPDATA environment variable not set.".to_string())
    })?;

    let target_dir = PathBuf::from(appdata)
        .join("Microsoft")
        .join("Windows")
        .join("Start Menu")
        .join("Programs");

    fs::create_dir_all(&target_dir)?;

    let file_name = source
        .file_name()
        .unwrap_or_else(|| OsStr::new("gui.exe"));
    let target = target_dir.join(file_name);

    fs::copy(source, &target)?;
    Ok(target)
}

fn create_shortcut_windows(exe_path: &Path, target_dir: &Path) -> Result<()> {
    let shortcut_name = "Shutdown Guard.lnk";
    let shortcut_path = target_dir.join(shortcut_name);
    let exe_str = exe_path.to_string_lossy();
    let shortcut_str = shortcut_path.to_string_lossy();

    let ps_script = format!(
        "$ws = New-Object -ComObject WScript.Shell; \
         $sc = $ws.CreateShortcut('{shortcut}'); \
         $sc.TargetPath = '{target}'; \
         $sc.WorkingDirectory = '{workdir}'; \
         $sc.Description = 'Shutdown Guard'; \
         $sc.Save()",
        shortcut = shortcut_str,
        target = exe_str,
        workdir = exe_path
            .parent()
            .map(|p| p.to_string_lossy().into_owned())
            .unwrap_or_default()
    );

    Command::new("powershell")
        .args(["-NoProfile", "-NonInteractive", "-Command", &ps_script])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()?;
    Ok(())
}

fn launch_executable(exe_path: &Path) -> Result<()> {
    Command::new(exe_path)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()?;
    Ok(())
}

fn launch_python_script(python: &Path, script: &Path) -> Result<()> {
    Command::new(python)
        .arg(script)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()?;
    Ok(())
}

fn windows_install(workdir: &Path) -> Result<()> {
    let python = find_python().ok_or_else(|| {
        InstallerError::Message(
            "Python not found. Install Python 3.7+ and ensure it is in PATH.".to_string(),
        )
    })?;

    if !find_pyinstaller(&python) {
        install_pyinstaller(&python)?;
    }

    compile_with_pyinstaller(&python, "gui.py", workdir)?;

    let gui_exe = workdir.join("dist").join("gui.exe");
    if !gui_exe.exists() {
        return Err(InstallerError::Message(format!(
            "Compiled executable not found at expected path: {}",
            gui_exe.display()
        )));
    }

    let installed_path = copy_to_start_menu(&gui_exe);
    match &installed_path {
        Ok(p) => {
            if let Some(parent) = p.parent() {
                let _ = create_shortcut_windows(p, parent);
            }
        }
        Err(e) => {
            eprintln!("Warning: could not copy to Start Menu: {}", e);
        }
    }

    let launch_target = installed_path
        .as_ref()
        .map(|p| p.as_path())
        .unwrap_or(&gui_exe);

    launch_executable(launch_target)?;
    Ok(())
}

fn unix_install(workdir: &Path) -> Result<()> {
    let python = find_python().ok_or_else(|| {
        InstallerError::Message(
            "Python not found. Install Python 3.7+ and ensure it is in PATH.".to_string(),
        )
    })?;

    let gui_script = workdir.join("gui.py");
    if !gui_script.exists() {
        return Err(InstallerError::Message(format!(
            "gui.py not found in working directory: {}",
            workdir.display()
        )));
    }

    launch_python_script(&python, &gui_script)?;
    Ok(())
}

fn main() {
    let workdir = env::current_dir().unwrap_or_else(|e| {
        eprintln!("Failed to determine current directory: {}", e);
        std::process::exit(1);
    });

    let result = match current_platform() {
        "windows" => windows_install(&workdir),
        _ => unix_install(&workdir),
    };

    match result {
        Ok(()) => {
            println!("Shutdown Guard installation completed successfully.");
        }
        Err(e) => {
            eprintln!("Installation failed: {}", e);
            std::process::exit(1);
        }
    }
}
