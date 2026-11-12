; Instalador do Vorticis PDF Editor (Inno Setup 6 — gratuito: https://jrsoftware.org)
; Compile depois do PyInstaller:  iscc installer\vorticis.iss
;
; Instalação sem travas: não exige administrador (instala para o usuário atual em
; %LOCALAPPDATA%\Programs), não altera configurações de segurança do Windows e funciona
; em qualquer Windows 10/11 de 64 bits. Silenciosa: VorticisPDF-Setup.exe /VERYSILENT

#define AppName "Vorticis PDF Editor"
#ifndef AppVersion
  #define AppVersion "1.5.0"
#endif
#define AppExe "VorticisPDF.exe"

[Setup]
AppId={{6E3C2B1A-7F4D-4C8E-9A51-0B7D2E5F9C11}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Vorticis
AppComments=Desenvolvido integralmente com IA. Gratuito para sempre.
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} - Instalador
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
OutputDir=Output
OutputBaseFilename=VorticisPDF-Instalador-{#AppVersion}
SetupIconFile=..\vorticis_pdf\resources\icon.ico
LicenseFile=..\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; sem pedir administrador; o usuário pode escolher "para todos" se quiser
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
UsedUserAreasWarning=no
CloseApplications=yes
RestartApplications=no
ChangesAssociations=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"
Name: "contextmenu"; Description: "Adicionar opções ao menu do botão direito (Unir, Separar, Organizar, Converter)"; GroupDescription: "Integração com o Windows:"
Name: "win11menu"; Description: "Windows 11: mostrar as opções direto no botão direito (sem precisar de ""Mostrar mais opções"")"; GroupDescription: "Integração com o Windows:"; Check: IsWindows11
Name: "defaultpdf"; Description: "Usar o Vorticis como leitor de PDF padrão"; GroupDescription: "Integração com o Windows:"; Flags: unchecked

[Files]
Source: "..\dist\VorticisPDF\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; remove arquivos de versões anteriores antes de copiar a nova
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
; AppUserModelID igual ao do programa: a barra de tarefas agrupa a janela com o atalho e usa o ícone dele
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\{#AppExe}"; AppUserModelID: "Vorticis.PDFEditor"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\{#AppExe}"; AppUserModelID: "Vorticis.PDFEditor"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.pdf"; ValueType: string; ValueName: ""; ValueData: "VorticisPDF.Document"; Flags: uninsdeletevalue; Tasks: defaultpdf

[Run]
Filename: "{app}\{#AppExe}"; Parameters: "--register-shell"; Flags: runhidden waituntilterminated; Tasks: contextmenu
Filename: "{app}\{#AppExe}"; Parameters: "--full-menu-on"; Flags: runhidden waituntilterminated; Tasks: win11menu
Filename: "{app}\{#AppExe}"; Description: "Abrir o {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#AppExe}"; Parameters: "--unregister-shell"; Flags: runhidden; RunOnceId: "UnregShell"

[Code]
function IsWindows11: Boolean;
var
  V: TWindowsVersion;
begin
  GetWindowsVersionEx(V);
  Result := (V.Major = 10) and (V.Build >= 22000);
end;
