; Instalador do Gestor Comercial (Inno Setup).
; Gera: packaging/output/GestorComercial-Setup.exe
; Compilar com: ISCC.exe packaging\instalador.iss (a partir da raiz do repo)
;
; Instala o .exe já empacotado pelo PyInstaller (dist/GestorComercial.exe)
; em Program Files, cria atalho no Menu Iniciar e (opcional) na Área de
; Trabalho. O banco de dados fica fora do diretório de instalação, em
; %APPDATA%\GestorComercial_V2\ (ver core/caminhos.py), então desinstalar o
; app NUNCA apaga os dados de venda. A pasta %USERPROFILE%\.gestor_comercial\
; do .exe anterior não é lida nem apagada por esta versão.
;
; O AppUserModelID dos atalhos é o mesmo que o programa declara no boot
; (main.ID_DO_APP_NO_WINDOWS, conferido por tests/unit/test_empacotamento.py):
; se divergissem, o programa fixado na barra de tarefas e o aberto virariam dois
; botões separados.

#define MyAppName "Gestor Comercial"
#define MyAppVersion "1.0.0"
#define MyAppExeName "GestorComercial.exe"

[Setup]
AppId={{B7B6B1B0-6D2E-4F1C-9E63-2F1E7C1A9B21}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename=GestorComercial-Setup
SetupIconFile=..\resources\icons\app_icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
DisableWelcomePage=no
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos adicionais:"

[Files]
Source: "..\dist\GestorComercial.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; AppUserModelID: "gestor.comercial.pdv.v2"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; AppUserModelID: "gestor.comercial.pdv.v2"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName} agora"; Flags: nowait postinstall skipifsilent
