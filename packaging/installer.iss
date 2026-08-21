; Inno Setup script — 大帅网关
#define MyAppName "大帅网关"
#define MyAppVersion "0.3.0"
#define MyAppPublisher "Dashuai"
#define MyAppExeName "DashuaiGateway.exe"

[Setup]
AppId={{A7C3E2F1-9B40-4D8A-9C21-DASHUAI-GW01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\DashuaiGateway
DefaultGroupName={#MyAppName}
OutputDir=..\dist-installer
OutputBaseFilename=DashuaiGateway-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面图标"; GroupDescription: "附加图标:"

[Files]
Source: "..\dist\DashuaiGateway.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\data\*.example.json"; DestDir: "{app}\data"; Flags: ignoreversion
Source: "..\sync-workbuddy.cmd"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动大帅网关"; Flags: nowait postinstall skipifsilent
