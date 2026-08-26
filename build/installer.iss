; Inno Setup script for ShoppingApp (Windows)
; Compile with:  iscc build/installer.iss
; (expects the PyInstaller onedir output in dist\ShoppingApp)

#define AppName "Shopping App"
#define AppVersion "1.3.2"
#define AppPublisher "Simon Spellman"
#define SrcDir "..\dist\ShoppingApp"

[Setup]
AppId={{B7E3C1A2-4D5F-4C8E-9A1B-5C6D7E8F90AB}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\ShoppingApp
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
#if VER >= 70000
OutputBaseFilename=ShoppingApp-Setup-{#AppVersion}
#else
OutputBaseName=ShoppingApp-Setup-{#AppVersion}
#endif
Compression=lzma2/max
SolidCompression=no
WizardStyle=modern
PrivilegesRequired=lowest
; x64compatible is an Inno 7 value; keep the script buildable with Inno 6 too
#if VER >= 70000
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
#else
ArchitecturesInstallIn64BitMode=x64
#endif
UninstallDisplayIcon={app}\ShoppingApp.exe
SetupIconFile=app.ico
ShowLanguageDialog=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "{#SrcDir}\ShoppingApp.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SrcDir}\resources\*"; DestDir: "{app}\resources"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\ShoppingApp.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\ShoppingApp.exe"; Tasks: desktopicon

[Run]
; Launch the app once after install and let it open the browser
Filename: "{app}\ShoppingApp.exe"; Flags: postinstall nowait skipifsilent
