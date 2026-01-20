# Building The-Uplink for Windows

This guide explains how to create a standalone Windows executable and installer for The-Uplink.

## Prerequisites

1. **Python 3.10+** - Download from [python.org](https://python.org)
2. **Inno Setup** (for installer) - Download from [jrsoftware.org](https://jrsoftware.org/isinfo.php)

## Quick Build (Automated)

Run the build script:
```batch
build.bat
```

This will:
1. Install all dependencies
2. Build the executable with PyInstaller
3. Output the application to `dist\The-Uplink\`

## Manual Build Steps

### Step 1: Install Dependencies

```batch
pip install -r requirements.txt
pip install pyinstaller
```

### Step 2: Build the Executable

```batch
pyinstaller The-Uplink.spec --noconfirm
```

The executable will be created in `dist\The-Uplink\`.

### Step 3: Test the Executable

Run `dist\The-Uplink\The-Uplink.exe` to verify it works correctly.

## Creating the Installer

### Step 1: Install Inno Setup

Download and install Inno Setup from [jrsoftware.org](https://jrsoftware.org/isinfo.php).

### Step 2: Compile the Installer

1. Open `installer.iss` in Inno Setup Compiler
2. Click **Build** → **Compile** (or press F9)
3. The installer will be created in `installer_output\`

### Step 3: Customize the Installer (Optional)

Edit `installer.iss` to customize:
- `MyAppVersion` - Application version number
- `MyAppPublisher` - Your company name
- `MyAppURL` - Your website URL
- `AppId` - Generate a unique GUID for your application

## Output Files

After building:
```
The-Uplink/
├── dist/
│   └── The-Uplink/           # Standalone application folder
│       ├── The-Uplink.exe    # Main executable
│       └── ...               # Supporting files
└── installer_output/
    └── The-Uplink-Setup-1.0.0.exe  # Installer
```

## Distributing the Application

### Option 1: Installer (Recommended)
Distribute the `The-Uplink-Setup-X.X.X.exe` installer. Users run it and follow the wizard.

### Option 2: Portable
Zip the entire `dist\The-Uplink\` folder. Users extract and run `The-Uplink.exe` directly.

## Database Configuration

The application is configured to use a shared database at:
```
P:\Dusty\database\
```

Ensure this network path is accessible before running the application. The databases will be created automatically on first run if they don't exist.

## Troubleshooting

### "Failed to execute script"
- Ensure all dependencies are installed
- Try rebuilding with `pyinstaller The-Uplink.spec --noconfirm --clean`

### Missing DLLs
- Install the [Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe)

### Database connection errors
- Verify the network path `P:\Dusty\database\` is accessible
- Check that the user has read/write permissions to the folder

### Application won't start
- Run from command prompt to see error messages:
  ```batch
  cd dist\The-Uplink
  The-Uplink.exe
  ```
