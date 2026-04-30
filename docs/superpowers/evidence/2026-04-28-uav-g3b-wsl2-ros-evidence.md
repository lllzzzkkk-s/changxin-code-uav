# UAV G3-B WSL2 ROS Evidence

Date: 2026-04-28
Spec: docs/superpowers/specs/2026-04-28-uav-g3b-wsl2-ros-design.md
Safety boundary: read-only ROS graph observation only. No action-topic publish is allowed in this evidence run.

## P0 Windows/Proxy

### P0.1 Windows Version, Virtualization, Disk, WSL Status
- Time: 2026-04-29, initial remote PowerShell attempt
- Server: remote Windows Server via RDP
- Command:
  ```powershell
  netsh winhttp show proxy | Tee-Object -FilePath C:\uav-g3b\p0-winhttp-proxy.txt
  wsl -l -v 2>&1 | Tee-Object -FilePath C:\uav-g3b\p0-wsl-list.txt
  wsl --status 2>&1 | Tee-Object -FilePath C:\uav-g3b\p0-wsl-status.txt
  Get-PSDrive C | Format-List | Tee-Object -FilePath C:\uav-g3b\p0-disk.txt
  systeminfo | findstr /i "Virtualization Hyper-V" | Tee-Object -FilePath C:\uav-g3b\p0-virtualization.txt
  Get-ComputerInfo | Select-Object OsName, OsVersion, WindowsVersion, OsBuildNumber, CsSystemType | Format-List | Tee-Object -FilePath C:\uav-g3b\p0-system.txt
  Set-Location C:\uav-g3b
  New-Item -ItemType Directory -Force C:\uav-g3b | Out-Null
  whoami /groups | findstr /i "S-1-5-32-544"
  ```
- Output:
  ```text
  Tee-Object / Out-File failed for all C:\uav-g3b\p0-*.txt files because C:\uav-g3b did not exist yet.
  Set-Location failed because C:\uav-g3b did not exist yet.
  whoami output included BUILTIN\Administrators and SID S-1-5-32-544.
  ```
- Verdict: RETRY_REQUIRED_DIRECTORY_ORDER; administrator membership confirmed.
- Next: rerun P0 with directory creation before all Tee-Object commands.

- Time: 2026-04-29, second remote PowerShell attempt
- Server: remote Windows host via RDP
- Command:
  ```powershell
  New-Item -ItemType Directory -Force C:\uav-g3b | Out-Null
  Set-Location C:\uav-g3b
  whoami /groups | findstr /i "S-1-5-32-544"
  Get-ComputerInfo | Select-Object OsName, OsVersion, WindowsVersion, OsBuildNumber, CsSystemType | Format-List | Tee-Object -FilePath C:\uav-g3b\p0-system.txt
  systeminfo | findstr /i "Virtualization Hyper-V" | Tee-Object -FilePath C:\uav-g3b\p0-virtualization.txt
  Get-PSDrive C | Format-List | Tee-Object -FilePath C:\uav-g3b\p0-disk.txt
  wsl --status 2>&1 | Tee-Object -FilePath C:\uav-g3b\p0-wsl-status.txt
  wsl -l -v 2>&1 | Tee-Object -FilePath C:\uav-g3b\p0-wsl-list.txt
  netsh winhttp show proxy | Tee-Object -FilePath C:\uav-g3b\p0-winhttp-proxy.txt
  ```
- Output:
  ```text
  Admin: BUILTIN\Administrators included SID S-1-5-32-544.
  OsName: Microsoft Windows 11 家庭中文版
  OsVersion: 10.0.22631
  WindowsVersion: 2009
  OsBuildNumber: 22631
  CsSystemType: x64-based PC
  WinHTTP proxy: 直接访问(没有代理服务器)。
  WSL list/status: mojibake output, but indicates no installed distribution and WSL2/kernel update or install is still required.
  Disk output: Get-PSDrive C did not include Free/Used fields in pasted output; needs CIM recheck.
  Virtualization output: systeminfo line was mojibake; needs CIM recheck.
  ```
- Verdict: P0_1_PARTIAL_PASS; administrator and Windows build confirmed, WSL not yet ready, disk/virtualization need cleaner recheck.
- Next: rerun focused UTF-8/CIM checks for disk, HypervisorPresent, optional features, WSL status, then run proxy download checks.

- Time: 2026-04-29, focused CIM retry
- Server: remote Windows host via RDP
- Command:
  ```powershell
  chcp 65001
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  $OutputEncoding = [System.Text.Encoding]::UTF8
  Set-Location C:\uav-g3b
  Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'" | Select-Object ...
  Get-CimInstance Win32_ComputerSystem | Select-Object ...
  Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux,VirtualMachinePlatform | Select-Object ...
  wsl --version
  wsl --status
  ```
- Output:
  ```text
  ParserError: expressions were received after pipe continuations; PowerShell displayed the pasted multi-line commands in reverse order.
  No disk, hypervisor, optional-feature, or WSL version evidence was produced in this attempt.
  ```
- Verdict: RETRY_REQUIRED_SINGLE_LINE_COMMANDS; command paste/line-continuation failure, not an environment verdict.
- Next: rerun P0 focused checks as independent one-line commands with no multi-line pipelines.

- Time: 2026-04-29, focused one-line checks
- Server: remote Windows host via RDP
- Command:
  ```powershell
  $disk=Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"; "DeviceID=$($disk.DeviceID) SizeGB=$([math]::Round($disk.Size/1GB,2)) FreeGB=$([math]::Round($disk.FreeSpace/1GB,2))" | Tee-Object -FilePath C:\uav-g3b\p0-disk-cim.txt
  $cs=Get-CimInstance Win32_ComputerSystem; "Manufacturer=$($cs.Manufacturer) Model=$($cs.Model) HypervisorPresent=$($cs.HypervisorPresent)" | Tee-Object -FilePath C:\uav-g3b\p0-hypervisor-cim.txt
  Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux,VirtualMachinePlatform | ForEach-Object { "$($_.FeatureName)=$($_.State)" } | Tee-Object -FilePath C:\uav-g3b\p0-windows-features.txt
  wsl --version 2>&1 | Tee-Object -FilePath C:\uav-g3b\p0-wsl-version.txt
  wsl --status 2>&1 | Tee-Object -FilePath C:\uav-g3b\p0-wsl-status-utf8.txt
  ```
- Output:
  ```text
  DeviceID=C: SizeGB=200 FreeGB=19.33
  Manufacturer=LENOVO Model=82WK HypervisorPresent=True
  Get-WindowsOptionalFeature: command not found in this PowerShell environment.
  wsl --version: unsupported; command printed legacy wsl.exe help text.
  wsl --status: mojibake output but indicates default WSL version 2 and asks to run wsl --update or install/update WSL2 kernel via https://aka.ms/wsl2kernel.
  ```
- Verdict: P0_1_PARTIAL_BLOCKED_DISK; virtualization present, WSL command exists but is legacy/outdated, C drive free space is below the 80GB gate.
- Next: check all local drives for an alternate WSL install target, check optional features via dism.exe, and do not install WSL until storage target is selected.

- Time: 2026-04-29, disk and Windows feature follow-up
- Server: remote Windows host via RDP
- Command:
  ```powershell
  Get-CimInstance Win32_LogicalDisk | ForEach-Object { "DeviceID=$($_.DeviceID) DriveType=$($_.DriveType) SizeGB=$([math]::Round($_.Size/1GB,2)) FreeGB=$([math]::Round($_.FreeSpace/1GB,2))" } | Tee-Object -FilePath C:\uav-g3b\p0-all-disks.txt
  dism.exe /online /Get-FeatureInfo /FeatureName:Microsoft-Windows-Subsystem-Linux 2>&1 | Tee-Object -FilePath C:\uav-g3b\p0-feature-wsl-dism.txt
  dism.exe /online /Get-FeatureInfo /FeatureName:VirtualMachinePlatform 2>&1 | Tee-Object -FilePath C:\uav-g3b\p0-feature-vmp-dism.txt
  netsh winhttp show proxy | Tee-Object -FilePath C:\uav-g3b\p0-winhttp-proxy.txt
  ```
- Output:
  ```text
  DeviceID=C: DriveType=3 SizeGB=200 FreeGB=19.33
  DeviceID=D: DriveType=3 SizeGB=751.64 FreeGB=296.57
  Microsoft-Windows-Subsystem-Linux: 状态 : 已启用
  VirtualMachinePlatform: 状态 : 已启用
  WinHTTP proxy: 直接访问(没有代理服务器)。
  ```
- Verdict: P0_1_PASS_WITH_D_DRIVE_TARGET; WSL and VirtualMachinePlatform are enabled, HypervisorPresent is true, D: has enough free space for WSL/Diff-planner work.
- Next: complete P0.2 proxy/download checks. Because C: has only 19.33GB free, P1 must use D:\WSL as the Ubuntu install/import location instead of default C: profile storage.

### P0.2 PowerShell Proxy Download Check
- Time: 2026-04-29
- Server: remote Windows host via RDP
- Command:
  ```powershell
  Invoke-WebRequest https://aka.ms/wsl2kernel -UseBasicParsing -TimeoutSec 30 | Select-Object StatusCode, StatusDescription | Tee-Object -FilePath C:\uav-g3b\p0-wsl-kernel-download-check.txt
  Invoke-WebRequest https://aka.ms/wslubuntu2004 -UseBasicParsing -TimeoutSec 30 | Select-Object StatusCode, StatusDescription | Tee-Object -FilePath C:\uav-g3b\p0-ubuntu2004-download-check.txt
  Invoke-WebRequest https://packages.ros.org -UseBasicParsing -TimeoutSec 30 | Select-Object StatusCode, StatusDescription | Tee-Object -FilePath C:\uav-g3b\p0-ros-download-check.txt
  ```
- Output:
  ```text
  https://aka.ms/wsl2kernel: StatusCode 200 OK
  https://aka.ms/wslubuntu2004: StatusCode 200 OK
  https://packages.ros.org: Invoke-WebRequest failed: 基础连接已经关闭: 未能为 SSL/TLS 安全通道建立信任关系。
  ```
- Verdict: P0_2_PASS_WITH_ROS_TLS_RISK; WSL kernel and Ubuntu 20.04 downloads are reachable, ROS Windows-side TLS trust needs follow-up.
- Next: run a plain HTTP ROS source check and defer final ROS apt verdict to Ubuntu P2 after ca-certificates/apt are configured.

- Time: 2026-04-29, ROS apt/key follow-up
- Server: remote Windows host via RDP
- Command:
  ```powershell
  Invoke-WebRequest http://packages.ros.org/ros/ubuntu -UseBasicParsing -TimeoutSec 30 | Select-Object StatusCode, StatusDescription | Tee-Object -FilePath C:\uav-g3b\p0-ros-http-download-check.txt
  Invoke-WebRequest https://raw.githubusercontent.com/ros/rosdistro/master/ros.asc -UseBasicParsing -TimeoutSec 30 | Select-Object StatusCode, StatusDescription | Tee-Object -FilePath C:\uav-g3b\p0-ros-key-download-check.txt
  ```
- Output:
  ```text
  http://packages.ros.org/ros/ubuntu: StatusCode 200 OK
  https://raw.githubusercontent.com/ros/rosdistro/master/ros.asc: StatusCode 200 OK
  ```
- Verdict: P0_2_PASS_WITH_ROS_TLS_RISK; WSL kernel, Ubuntu 20.04, ROS apt HTTP source, and ROS key URL are reachable from Windows.
- Next: P0 complete enough to proceed. Use D:\WSL as the P1 install/import target because C: has only 19.33GB free. Use the tested `https://aka.ms/wslubuntu2004` AppxBundle path, extract `install.tar.gz`, then import it with `wsl --import`; the current Ubuntu focal cloud-images release listing no longer exposes the WSL rootfs tarball.

## P1 WSL2 Ubuntu

### P1.1 WSL Feature Install
- Time: 2026-04-29, first P1 remote PowerShell attempt
- Server: remote Windows host via RDP
- Command:
  ```powershell
  Get-Item D:\WSL\Downloads\Ubuntu2004.AppxBundle ...
  Invoke-WebRequest https://aka.ms/wslubuntu2004 -OutFile D:\WSL\Downloads\Ubuntu2004.AppxBundle
  wsl --set-default-version 2 ...
  msiexec.exe /i D:\WSL\Downloads\wsl_update_x64.msi /quiet /norestart
  Invoke-WebRequest https://aka.ms/wsl2kernel -OutFile D:\WSL\Downloads\wsl_update_x64.msi
  Get-CimInstance Win32_LogicalDisk ...
  New-Item -ItemType Directory -Force D:\WSL\Ubuntu-20.04
  New-Item -ItemType Directory -Force D:\WSL\Downloads
  New-Item -ItemType Directory -Force C:\uav-g3b
  ```
- Output:
  ```text
  Get-Item failed because D:\WSL\Downloads\Ubuntu2004.AppxBundle did not exist yet.
  Invoke-WebRequest to D:\WSL\Downloads\Ubuntu2004.AppxBundle failed because D:\WSL\Downloads did not exist yet.
  wsl --set-default-version 2 reported WSL2 kernel/component update guidance.
  Invoke-WebRequest to D:\WSL\Downloads\wsl_update_x64.msi failed because D:\WSL\Downloads did not exist yet.
  Disk check succeeded: C: FreeGB=19.35, D: FreeGB=296.57.
  Directory creation ran at the end and succeeded.
  ```
- Verdict: RETRY_REQUIRED_DIRECTORY_ORDER; not an install failure.
- Next: rerun P1 in smaller top-down chunks now that `C:\uav-g3b`, `D:\WSL\Downloads`, and `D:\WSL\Ubuntu-20.04` exist.

- Time: 2026-04-29, P1 kernel and Ubuntu bundle retry
- Server: remote Windows host via RDP
- Command:
  ```powershell
  Invoke-WebRequest https://aka.ms/wsl2kernel -UseBasicParsing -OutFile D:\WSL\Downloads\wsl_update_x64.msi
  msiexec.exe /i D:\WSL\Downloads\wsl_update_x64.msi /quiet /norestart
  wsl --set-default-version 2 2>&1 | Tee-Object -FilePath C:\uav-g3b\p1-default-version.txt
  Invoke-WebRequest https://aka.ms/wslubuntu2004 -UseBasicParsing -OutFile D:\WSL\Downloads\Ubuntu2004.AppxBundle
  Get-Item D:\WSL\Downloads\Ubuntu2004.AppxBundle | Select-Object FullName,Length | Format-List | Tee-Object -FilePath C:\uav-g3b\p1-ubuntu-appxbundle-download.txt
  ```
- Output:
  ```text
  wsl2kernel download command returned to prompt, but later evidence showed `https://aka.ms/wsl2kernel` can resolve to the Microsoft Learn HTML page instead of the MSI binary.
  msiexec returned to the prompt without an explicit fatal error.
  wsl --set-default-version 2 printed mojibake Chinese output with https://aka.ms/wsl2 reference.
  Ubuntu2004.AppxBundle downloaded.
  FullName : D:\WSL\Downloads\Ubuntu2004.AppxBundle
  Length   : 937972031
  ```
- Verdict: P1_1_PARTIAL_PASS_WITH_KERNEL_URL_RISK; Ubuntu 20.04 AppxBundle download completed, but WSL kernel MSI install remains unverified.
- Next: extract `install.tar.gz` from the AppxBundle and import it into `D:\WSL\Ubuntu-20.04`; if WSL2 import fails, verify the downloaded kernel MSI is the real 17MB binary.

- Time: 2026-04-29, first AppxBundle extraction attempt
- Server: remote Windows host via RDP
- Command:
  ```powershell
  Remove-Item -Recurse -Force D:\WSL\Downloads\Ubuntu2004Bundle,D:\WSL\Downloads\Ubuntu2004Appx -ErrorAction SilentlyContinue
  Copy-Item D:\WSL\Downloads\Ubuntu2004.AppxBundle D:\WSL\Downloads\Ubuntu2004.AppxBundle.zip -Force
  Expand-Archive D:\WSL\Downloads\Ubuntu2004.AppxBundle.zip -DestinationPath D:\WSL\Downloads\Ubuntu2004Bundle -Force
  ```
- Output:
  ```text
  Expand-Archive: command was found in Microsoft.PowerShell.Archive, but the module could not be loaded.
  ```
- Verdict: RETRY_REQUIRED_ARCHIVE_TOOL; downloaded AppxBundle is still usable, but PowerShell archive module is unavailable.
- Next: retry extraction with Windows `tar.exe` instead of `Expand-Archive`.

- Time: 2026-04-29, AppxBundle extraction with tar.exe
- Server: remote Windows host via RDP
- Command:
  ```powershell
  New-Item -ItemType Directory -Force D:\WSL\Downloads\Ubuntu2004Bundle | Out-Null
  tar.exe -tf D:\WSL\Downloads\Ubuntu2004.AppxBundle | Tee-Object -FilePath C:\uav-g3b\p1-ubuntu-bundle-tar-list.txt
  tar.exe -xf D:\WSL\Downloads\Ubuntu2004.AppxBundle -C D:\WSL\Downloads\Ubuntu2004Bundle
  Get-ChildItem D:\WSL\Downloads\Ubuntu2004Bundle -Recurse | Select-Object FullName,Length | Tee-Object -FilePath C:\uav-g3b\p1-ubuntu-bundle-list.txt
  ```
- Output:
  ```text
  Ubuntu_2004.2021.825.0_ARM64.appx
  Ubuntu_2004.2021.825.0_scale-100.appx
  Ubuntu_2004.2021.825.0_scale-125.appx
  Ubuntu_2004.2021.825.0_scale-150.appx
  Ubuntu_2004.2021.825.0_scale-400.appx
  Ubuntu_2004.2021.825.0_x64.appx
  AppxMetadata/AppxBundleManifest.xml
  AppxBlockMap.xml
  [Content_Types].xml
  AppxSignature.p7x

  D:\WSL\Downloads\Ubuntu2004Bundle\Ubuntu_2004.2021.825.0_x64.appx Length=488019108
  ```
- Verdict: P1_1_PARTIAL_PASS; AppxBundle extraction succeeded and x64 appx is available.
- Next: extract the x64 appx with `tar.exe`, copy `install.tar.gz`, then import with `wsl --import`.

- Time: 2026-04-29, x64 appx extraction
- Server: remote Windows host via RDP
- Command:
  ```powershell
  Remove-Item -Recurse -Force D:\WSL\Downloads\Ubuntu2004Appx -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Force D:\WSL\Downloads\Ubuntu2004Appx | Out-Null
  tar.exe -tf D:\WSL\Downloads\Ubuntu2004Bundle\Ubuntu_2004.2021.825.0_x64.appx | Tee-Object -FilePath C:\uav-g3b\p1-ubuntu-x64-appx-tar-list.txt
  tar.exe -xf D:\WSL\Downloads\Ubuntu2004Bundle\Ubuntu_2004.2021.825.0_x64.appx -C D:\WSL\Downloads\Ubuntu2004Appx
  Get-ChildItem D:\WSL\Downloads\Ubuntu2004Appx -Recurse | Select-Object FullName,Length | Tee-Object -FilePath C:\uav-g3b\p1-ubuntu-x64-appx-list.txt
  ```
- Output:
  ```text
  tar list included install.tar.gz and ubuntu.exe.
  D:\WSL\Downloads\Ubuntu2004Appx\install.tar.gz Length=487526665
  D:\WSL\Downloads\Ubuntu2004Appx\ubuntu.exe Length=475648
  ```
- Verdict: P1_1_PARTIAL_PASS; Ubuntu 20.04 rootfs tarball extracted.
- Next: copy `install.tar.gz`, run `wsl --import Ubuntu-20.04 D:\WSL\Ubuntu-20.04 ... --version 2`, and verify with `wsl -l -v`.

- Time: 2026-04-29, first WSL2 import attempt
- Server: remote Windows host via RDP
- Command:
  ```powershell
  Copy-Item D:\WSL\Downloads\Ubuntu2004Appx\install.tar.gz D:\WSL\Downloads\ubuntu-20.04-install.tar.gz -Force
  Get-Item D:\WSL\Downloads\ubuntu-20.04-install.tar.gz | Select-Object FullName,Length | Format-List | Tee-Object -FilePath C:\uav-g3b\p1-ubuntu-rootfs-extract.txt
  wsl --import Ubuntu-20.04 D:\WSL\Ubuntu-20.04 D:\WSL\Downloads\ubuntu-20.04-install.tar.gz --version 2 2>&1 | Tee-Object -FilePath C:\uav-g3b\p1-ubuntu-import.txt
  wsl -l -v 2>&1 | Tee-Object -FilePath C:\uav-g3b\p1-wsl-list-after-install.txt
  ```
- Output:
  ```text
  FullName : D:\WSL\Downloads\ubuntu-20.04-install.tar.gz
  Length   : 487526665

  wsl --import output: WSL 2 requires an update to its kernel component; see https://aka.ms/wsl2kernel. (Displayed as mojibake.)
  wsl -l -v output: no installed Linux distributions; points to Microsoft Store installation.
  ```
- Verdict: BLOCKED_WSL2_KERNEL_NOT_INSTALLED; rootfs is valid, but WSL2 kernel component is not installed or not active.
- Root cause: `https://aka.ms/wsl2kernel` is a documentation redirect in this environment, not a stable MSI binary URL. The direct Microsoft blob URL for the x64 kernel MSI must be used.
- Next: download `https://wslstorestorage.blob.core.windows.net/wslblob/wsl_update_x64.msi`, verify file length is about 17MB, run MSI, then retry `wsl --set-default-version 2` and `wsl --import`.

- Time: 2026-04-29, WSL2 kernel MSI direct-link retry
- Server: remote Windows host via RDP
- Command:
  ```powershell
  Get-Item D:\WSL\Downloads\wsl_update_x64.msi | Select-Object FullName,Length | Format-List | Tee-Object -FilePath C:\uav-g3b\p1-bad-wsl-kernel-msi-size.txt
  $WslKernelMsiUrl = "https://wslstorestorage.blob.core.windows.net/wslblob/wsl_update_x64.msi"
  Invoke-WebRequest $WslKernelMsiUrl -UseBasicParsing -OutFile D:\WSL\Downloads\wsl_update_x64.msi
  Get-Item D:\WSL\Downloads\wsl_update_x64.msi | Select-Object FullName,Length | Format-List | Tee-Object -FilePath C:\uav-g3b\p1-wsl-kernel-msi-download.txt
  Start-Process msiexec.exe -ArgumentList '/i "D:\WSL\Downloads\wsl_update_x64.msi" /quiet /norestart' -Wait -PassThru | Select-Object ExitCode | Format-List | Tee-Object -FilePath C:\uav-g3b\p1-wsl-kernel-msi-install.txt
  wsl --set-default-version 2 2>&1 | Tee-Object -FilePath C:\uav-g3b\p1-default-version-retry.txt
  ```
- Output:
  ```text
  Previous D:\WSL\Downloads\wsl_update_x64.msi Length=71190
  Direct-link D:\WSL\Downloads\wsl_update_x64.msi Length=17104896
  msiexec Start-Process returned to the prompt, but ExitCode field was blank.
  wsl --set-default-version 2 printed mojibake Chinese output with https://aka.ms/wsl2 reference.
  ```
- Verdict: P1_1_KERNEL_BINARY_FIXED; previous file was not a valid MSI, direct-link MSI now has the expected 17MB size and set-default-version no longer shows the `wsl2kernel` URL.
- Next: retry `wsl --import Ubuntu-20.04 ... --version 2` and verify with `wsl -l -v`.

- Time: 2026-04-29, WSL2 import retry
- Server: remote Windows host via RDP
- Command:
  ```powershell
  Get-ChildItem D:\WSL\Ubuntu-20.04 -Force | Select-Object FullName,Length | Tee-Object -FilePath C:\uav-g3b\p1-ubuntu-import-dir-before-retry.txt
  wsl --import Ubuntu-20.04 D:\WSL\Ubuntu-20.04 D:\WSL\Downloads\ubuntu-20.04-install.tar.gz --version 2 2>&1 | Tee-Object -FilePath C:\uav-g3b\p1-ubuntu-import-retry.txt
  wsl -l -v 2>&1 | Tee-Object -FilePath C:\uav-g3b\p1-wsl-list-after-import-retry.txt
  ```
- Output:
  ```text
  NAME            STATE           VERSION
  * Ubuntu-20.04    Stopped         2
  ```
- Verdict: P1_1_PASS; Ubuntu-20.04 imported successfully as WSL2 on D:\WSL.
- Next: start Ubuntu, verify `/etc/os-release`, create `uavdev`, and verify user shell.

### P1.2 Ubuntu-20.04 WSL2 Verification
- Time: 2026-04-29
- Server: remote Windows host via RDP
- Command:
  ```powershell
  wsl -d Ubuntu-20.04 -- bash -lc "cat /etc/os-release && uname -a" 2>&1 | Tee-Object -FilePath C:\uav-g3b\p1-ubuntu-version.txt
  wsl -d Ubuntu-20.04 -- bash -lc "id -u uavdev >/dev/null 2>&1 || (useradd -m -s /bin/bash uavdev && usermod -aG sudo uavdev && echo 'uavdev ALL=(ALL) NOPASSWD:ALL' >/etc/sudoers.d/90-uavdev && chmod 440 /etc/sudoers.d/90-uavdev)"
  wsl -d Ubuntu-20.04 --user uavdev -- bash -lc "whoami && pwd && cat /etc/os-release" 2>&1 | Tee-Object -FilePath C:\uav-g3b\p1-ubuntu-user.txt
  ```
- Output:
  ```text
  NAME="Ubuntu"
  VERSION="20.04.3 LTS (Focal Fossa)"
  PRETTY_NAME="Ubuntu 20.04.3 LTS"
  VERSION_ID="20.04"
  VERSION_CODENAME=focal
  UBUNTU_CODENAME=focal
  Linux LAPTOP-JC 5.10.16.3-microsoft-standard-WSL2 #1 SMP Fri Apr 2 22:23:49 UTC 2021 x86_64 x86_64 x86_64 GNU/Linux

  uavdev
  /mnt/c/uav-g3b
  NAME="Ubuntu"
  VERSION="20.04.3 LTS (Focal Fossa)"
  PRETTY_NAME="Ubuntu 20.04.3 LTS"
  VERSION_ID="20.04"
  VERSION_CODENAME=focal
  UBUNTU_CODENAME=focal
  ```
- Verdict: P1_2_PASS; Ubuntu-20.04 runs under WSL2 and the `uavdev` sudo-capable user exists.
- Next: proceed to P1.5 Ubuntu apt/proxy/base-package setup.

## P1.5 Ubuntu Proxy And Base Packages

### P1.5.1 Ubuntu Version And Proxy
- Time: 2026-04-29, first PowerShell-wrapped P1.5 attempt
- Server: remote Windows host via RDP
- Command:
  ```powershell
  wsl -d Ubuntu-20.04 --user uavdev -- bash -lc 'cd ~ && mkdir -p ~/uav-g3b-evidence && sudo rm -f /etc/apt/apt.conf.d/95proxies && { date -Is; cat /etc/os-release; uname -a; env | grep -E "^(http_proxy|https_proxy)=" | sed "s#://.*@#://***:***@#" || true; ls -l /etc/apt/apt.conf.d/95proxies 2>/dev/null || true; } | tee ~/uav-g3b-evidence/p15-ubuntu-network.txt'
  ```
- Output:
  ```text
  /bin/bash: -c: line 0: syntax error near unexpected token `('
  ```
- Verdict: RETRY_REQUIRED_DIRECT_WSL_SHELL; PowerShell quoting broke the Linux command, not a WSL or apt failure.
- Next: launch the existing `Ubuntu-20.04` WSL2 environment directly as `uavdev` and run Linux commands inside bash.

### P1.5.2 apt Update And Base Packages
- Time: 2026-04-29, PowerShell-wrapped apt run
- Server: remote Windows host via RDP
- Command:
  ```powershell
  wsl -d Ubuntu-20.04 --user uavdev -- bash -lc 'cd ~ && sudo apt update 2>&1 | tee ~/uav-g3b-evidence/p15-apt-update.txt'
  wsl -d Ubuntu-20.04 --user uavdev -- bash -lc 'cd ~ && sudo DEBIAN_FRONTEND=noninteractive apt install -y curl gnupg lsb-release build-essential git python3-pip 2>&1 | tee ~/uav-g3b-evidence/p15-base-packages.txt'
  ```
- Output:
  ```text
  tee: /home/uavdev/uav-g3b-evidence/p15-apt-update.txt: No such file or directory
  apt update fetched 35.4 MB from archive.ubuntu.com and security.ubuntu.com.
  apt update completed: 289 packages can be upgraded.

  tee: /home/uavdev/uav-g3b-evidence/p15-base-packages.txt: No such file or directory
  apt install fetched 69.5 MB.
  Installed base packages including curl, gnupg, lsb-release, build-essential, git, and python3-pip.
  ldconfig warning: Can't link /usr/lib/wsl/lib/libnvoptix_loader.so.1 to libnvoptix.so.1.
  ```
- Verdict: P1_5_PARTIAL_PASS_EVIDENCE_RETRY_REQUIRED; apt network and base package installation succeeded, but evidence files were not written because the evidence directory was not created.
- Next: create `~/uav-g3b-evidence` from an interactive WSL shell and run lightweight verification commands to capture P1.5 evidence files.

- Time: 2026-04-29, interactive WSL evidence retry
- Server: remote Windows host, interactive Ubuntu-20.04 WSL2 shell as `uavdev`
- Command:
  ```bash
  mkdir -p ~/uav-g3b-evidence
  cd ~
  {
    date -Is
    cat /etc/os-release
    uname -a
    env | grep -E '^(http_proxy|https_proxy)=' | sed 's#://.*@#://***:***@#' || true
    ls -l /etc/apt/apt.conf.d/95proxies 2>/dev/null || true
  } | tee ~/uav-g3b-evidence/p15-ubuntu-network.txt
  ```
- Output:
  ```text
  2026-04-29T12:49:38+08:00
  NAME="Ubuntu"
  VERSION="20.04.3 LTS (Focal Fossa)"
  PRETTY_NAME="Ubuntu 20.04.3 LTS"
  VERSION_ID="20.04"
  VERSION_CODENAME=focal
  UBUNTU_CODENAME=focal
  Linux LAPTOP-JC 5.10.16.3-microsoft-standard-WSL2 #1 SMP Fri Apr 2 22:23:49 UTC 2021 x86_64 x86_64 x86_64 GNU/Linux
  ```
- Verdict: P1_5_1_PASS; interactive WSL shell is the correct execution environment and no apt proxy is required.
- Next: capture apt update and base package verification evidence.

- Time: 2026-04-29, interactive WSL apt verification
- Server: remote Windows host, interactive Ubuntu-20.04 WSL2 shell as `uavdev`
- Command:
  ```bash
  sudo apt update 2>&1 | tee ~/uav-g3b-evidence/p15-apt-update.txt
  dpkg -l curl gnupg lsb-release build-essential git python3-pip 2>&1 | tee ~/uav-g3b-evidence/p15-base-packages-verify.txt
  ```
- Output:
  ```text
  Hit:1 http://archive.ubuntu.com/ubuntu focal InRelease
  Hit:2 http://archive.ubuntu.com/ubuntu focal-updates InRelease
  Hit:3 http://archive.ubuntu.com/ubuntu focal-backports InRelease
  Hit:4 http://security.ubuntu.com/ubuntu focal-security InRelease
  Reading package lists...
  Building dependency tree...
  Reading state information...
  264 packages can be upgraded. Run 'apt list --upgradable' to see them.

  ii  build-essential 12.8ubuntu1.1        amd64
  ii  curl            7.68.0-1ubuntu2.25   amd64
  ii  git             1:2.25.1-1ubuntu3.14 amd64
  ii  gnupg           2.2.19-3ubuntu2.5    all
  ii  lsb-release     11.1.0ubuntu2        all
  ii  python3-pip     20.0.2-5ubuntu1.11   all
  ```
- Verdict: P1_5_2_PASS; apt direct network works and base build packages are installed.
- Next: proceed to P2 ROS Noetic installation from the interactive WSL shell.

## P2 ROS Noetic

### P2.1 ROS Noetic Install
- Time: 2026-04-30, ROS apt source setup
- Server: remote Windows host, interactive Ubuntu-20.04 WSL2 shell as `uavdev`
- Command:
  ```bash
  cd ~
  source /etc/os-release
  test "$VERSION_ID" = "20.04" && echo "Ubuntu $VERSION_ID / $VERSION_CODENAME"
  sudo rm -f /usr/share/keyrings/ros-archive-keyring.gpg /etc/apt/sources.list.d/ros-latest.list
  curl -fsSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.asc | sudo gpg --dearmor -o /usr/share/keyrings/ros-archive-keyring.gpg
  ls -l /usr/share/keyrings/ros-archive-keyring.gpg | tee ~/uav-g3b-evidence/p2-ros-keyring.txt
  echo "deb [signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros/ubuntu $(lsb_release -sc) main" | sudo tee /etc/apt/sources.list.d/ros-latest.list
  cat /etc/apt/sources.list.d/ros-latest.list | tee ~/uav-g3b-evidence/p2-ros-source.txt
  sudo apt update 2>&1 | tee ~/uav-g3b-evidence/p2-ros-apt-update.txt
  ```
- Output:
  ```text
  Ubuntu 20.04 / focal
  -rw-r--r-- 1 root root 1766 Apr 30 09:54 /usr/share/keyrings/ros-archive-keyring.gpg
  deb [signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros/ubuntu focal main

  Hit:1 http://archive.ubuntu.com/ubuntu focal InRelease
  Hit:2 http://archive.ubuntu.com/ubuntu focal-updates InRelease
  Hit:3 http://archive.ubuntu.com/ubuntu focal-backports InRelease
  Hit:4 http://security.ubuntu.com/ubuntu focal-security InRelease
  Get:5 http://packages.ros.org/ros/ubuntu focal InRelease [4679 B]
  Get:6 http://packages.ros.org/ros/ubuntu focal/main amd64 Packages [842 kB]
  Fetched 847 kB in 12s (68.2 kB/s)
  Reading package lists...
  Building dependency tree...
  Reading state information...
  264 packages can be upgraded. Run 'apt list --upgradable' to see them.
  ```
- Verdict: P2_1_SOURCE_PASS; ROS Noetic apt source and keyring are configured and reachable.
- Next: install ROS Noetic packages and verify core ROS commands.

- Time: 2026-04-30, ROS package install and basic command verification
- Server: remote Windows host, interactive Ubuntu-20.04 WSL2 shell as `uavdev`
- Command:
  ```bash
  df -h / | tee ~/uav-g3b-evidence/p2-disk-before-ros.txt
  sudo DEBIAN_FRONTEND=noninteractive apt install -y ros-noetic-desktop-full python3-rosdep python3-rosinstall python3-rosinstall-generator python3-wstool python3-catkin-tools 2>&1 | tee ~/uav-g3b-evidence/p2-ros-install.txt
  test -f /opt/ros/noetic/setup.bash && echo "setup.bash exists" | tee ~/uav-g3b-evidence/p2-ros-setup-file.txt
  grep -qxF 'source /opt/ros/noetic/setup.bash' ~/.bashrc || echo 'source /opt/ros/noetic/setup.bash' >> ~/.bashrc
  source /opt/ros/noetic/setup.bash
  rosversion -d | tee ~/uav-g3b-evidence/p2-ros-version.txt
  which roscore rosnode rostopic rosmsg | tee ~/uav-g3b-evidence/p2-ros-tools.txt
  ```
- Output:
  ```text
  ROS apt install finished and processed package triggers.
  ldconfig warning: Can't link /usr/lib/wsl/lib/libnvoptix_loader.so.1 to libnvoptix.so.1.

  setup.bash exists
  noetic
  /opt/ros/noetic/bin/roscore
  /opt/ros/noetic/bin/rosnode
  /opt/ros/noetic/bin/rostopic
  /opt/ros/noetic/bin/rosmsg
  ```
- Verdict: P2_1_INSTALL_PASS; ROS Noetic desktop-full and core command-line tools are installed. WSL `libnvoptix` warning is unrelated to ROS CLI availability.
- Next: run a minimal `roscore` and topic-tool smoke test.

### P2.2 ROS Core Verification
- Time: 2026-04-30
- Server: remote Windows host, interactive Ubuntu-20.04 WSL2 shell as `uavdev`
- Command:
  ```bash
  source /opt/ros/noetic/setup.bash
  pkill -f roscore || true
  pkill -f rosmaster || true
  roscore > ~/uav-g3b-evidence/p2-roscore.log 2>&1 &
  echo $! | tee ~/uav-g3b-evidence/p2-roscore.pid
  sleep 5
  rosnode list 2>&1 | tee ~/uav-g3b-evidence/p2-rosnode-list.txt
  rostopic list 2>&1 | tee ~/uav-g3b-evidence/p2-rostopic-list.txt
  rosmsg show std_msgs/String 2>&1 | tee ~/uav-g3b-evidence/p2-rosmsg-std-string.txt
  kill "$(cat ~/uav-g3b-evidence/p2-roscore.pid)" || true
  sleep 2
  pgrep -af 'roscore|rosmaster' | tee ~/uav-g3b-evidence/p2-roscore-after-kill.txt || true
  ```
- Output:
  ```text
  roscore PID: 27441
  rosnode list:
  /rosout

  rostopic list:
  /rosout
  /rosout_agg

  rosmsg show std_msgs/String:
  string data

  roscore exited after kill.
  pgrep after kill only matched the `tee ... p2-roscore-after-kill.txt` command line, not a live roscore/rosmaster process.
  ```
- Verdict: P2_2_PASS; ROS master, node/topic tools, and message introspection work in WSL2.
- Next: proceed to P3 Diff-planner workspace sync and interface verification.

## P3 Diff-planner

### P3.1 Workspace Sync
- Time:
- Server:
- Command:
- Output:
- Verdict:
- Next:

### P3.2 Build And Message Verification
- Time:
- Server:
- Command:
- Output:
- Verdict:
- Next:

### P3.3 Static Interface Verification
- Time:
- Server:
- Command:
- Output:
- Verdict:
- Next:

## G3-B ROS Graph

### G3-B.1 Read-only Topic And Node Observation
- Time:
- Server:
- Command:
- Output:
- Verdict:
- Next:

### G3-B.2 Dry-run Payload Evidence
- Time:
- Server:
- Command:
- Output:
- Verdict:
- Next:

## Final Gate

- P0 Verdict:
- P1 Verdict:
- P1.5 Verdict:
- P2 Verdict:
- P3 Verdict:
- G3-B Verdict:
- G3-C Entry Decision:
