#ifndef PayloadDir
  #error PayloadDir is required
#endif
#ifndef OutputDir
  #error OutputDir is required
#endif
#ifndef PackageVersion
  #define PackageVersion "1.2.0"
#endif
#ifndef InstallerAppId
  #define InstallerAppId "AtlasPergamo.LocalAgent.PerUser"
#endif
#ifndef OutputName
  #define OutputName "AtlasLocalAgent-Setup-1.2.0-win-x64"
#endif

[Setup]
AppId={#InstallerAppId}
AppName=Atlas Local Agent
AppVersion={#PackageVersion}
AppPublisher=Atlas Pérgamo
VersionInfoDescription=Atlas Local Agent - instalación manual por usuario
DefaultDirName={localappdata}\Programs\Atlas\LocalAgent
DefaultGroupName=Atlas Local Agent
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19045
WizardStyle=modern
DisableProgramGroupPage=yes
DisableWelcomePage=no
InfoBeforeFile=ANTES-DE-INSTALAR.txt
UninstallDisplayIcon={app}\tray\Atlas.LocalAgent.Tray.exe
AppMutex=Local\Atlas.LocalAgent.InstalledPanel
CloseApplications=no
RestartApplications=no
RestartIfNeededByRun=no
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
Compression=lzma2
SolidCompression=yes
SetupLogging=no
DisableDirPage=yes
UsePreviousAppDir=no
AllowCancelDuringInstall=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; Flags: unchecked

[Files]
Source: "{#PayloadDir}\service\*"; DestDir: "{app}\service"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#PayloadDir}\tray\*"; DestDir: "{app}\tray"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#PayloadDir}\LEEME.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\payload-sha256.json"; DestDir: "{app}"; Flags: ignoreversion

#ifndef InstallerQa
[Icons]
Name: "{autoprograms}\Atlas Local Agent"; Filename: "{app}\tray\Atlas.LocalAgent.Tray.exe"; Parameters: "--managed"; WorkingDir: "{app}\tray"
Name: "{autodesktop}\Atlas Local Agent"; Filename: "{app}\tray\Atlas.LocalAgent.Tray.exe"; Parameters: "--managed"; WorkingDir: "{app}\tray"; Tasks: desktopicon
#endif

; Deliberately no [Run], startup registry, scheduled task, firewall or Windows service.
; Application data, identity, DPAPI and SQLite are outside {app} and never removed.
