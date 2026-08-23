; Inno Setup — 大帅网关
#define MyAppName "大帅网关"
#define MyAppVersion "0.4.0"
#define MyAppPublisher "Dashuai"
#define MyAppExeName "DashuaiGateway.exe"

[Setup]
AppId={{A7C3E2F1-9B40-4D8A-9C21-DASHUAI-GW01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\大帅网关
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist-installer
OutputBaseFilename=大帅网关-安装包-{#MyAppVersion}
SetupIconFile=assets\dashuai-gateway.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
VersionInfoVersion=0.4.0.0
VersionInfoProductName={#MyAppName}
VersionInfoCompany={#MyAppPublisher}

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"; Flags: checkedonce

[Files]
Source: "..\dist\DashuaiGateway.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\发给别人-使用说明.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
; 首次运行由 EXE 从内置 example 生成 data\*.json，勿覆盖用户已有配置
Source: "assets\dashuai-gateway.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\dashuai-gateway.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\dashuai-gateway.ico"; Tasks: desktopicon
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动大帅网关"; Flags: nowait postinstall skipifsilent
