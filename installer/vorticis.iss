; Instalador do Vorticis PDF Editor (Inno Setup 6 — gratuito: https://jrsoftware.org)
; Compile depois do PyInstaller:  iscc installer\vorticis.iss

#define AppName "Vorticis PDF Editor"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppExe "VorticisPDF.exe"

[Setup]
AppId={{6E3C2B1A-7F4D-4C8E-9A51-0B7D2E5F9C11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Vorticis
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=Output
OutputBaseFilename=VorticisPDF-Setup-{#AppVersion}
SetupIconFile=..\vorticis_pdf\resources\icon.ico
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
; instala sem pedir administrador (pode escolher "para todos os usuários")
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ChangesAssociations=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"
Name: "contextmenu"; Description: "Adicionar opções ao menu do botão direito (Unir, Separar, Organizar, Converter)"; GroupDescription: "Integração com o Windows:"
Name: "defaultpdf"; Description: "Usar o Vorticis como leitor de PDF padrão"; GroupDescription: "Integração com o Windows:"; Flags: unchecked

[Files]
Source: "..\dist\VorticisPDF\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.pdf"; ValueType: string; ValueName: ""; ValueData: "VorticisPDF.Document"; Flags: uninsdeletevalue; Tasks: defaultpdf

[Run]
Filename: "{app}\{#AppExe}"; Parameters: "--register-shell"; Flags: runhidden; Tasks: contextmenu
Filename: "{app}\{#AppExe}"; Description: "Abrir o {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#AppExe}"; Parameters: "--unregister-shell"; Flags: runhidden; RunOnceId: "UnregShell"
