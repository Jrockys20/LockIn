; Compilar con Inno Setup 6.7.4. Rutas relativas a este archivo.
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#ifndef BuildDir
  #define BuildDir "..\dist\LockIn"
#endif
#ifndef ReleaseDir
  #define ReleaseDir "..\dist\releases"
#endif

[Setup]
AppId={{C58C3C4F-3E11-43B0-BB8D-60E2E10AD7A5}
AppName=LockIn
AppVersion={#AppVersion}
AppVerName=LockIn {#AppVersion}
VersionInfoVersion={#AppVersion}.0
DefaultDirName={localappdata}\Programs\LockIn
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19041
OutputDir={#ReleaseDir}
OutputBaseFilename=LockIn-{#AppVersion}-Setup-x64
SetupIconFile=LockIn.ico
UninstallDisplayIcon={app}\LockIn.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
CloseApplicationsFilter=LockIn.exe
RestartApplications=no
UninstallDisplayName=LockIn

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\LockIn"; Filename: "{app}\LockIn.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\LockIn"; Filename: "{app}\LockIn.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\LockIn.exe"; Description: "Abrir LockIn"; Flags: nowait postinstall skipifsilent unchecked
