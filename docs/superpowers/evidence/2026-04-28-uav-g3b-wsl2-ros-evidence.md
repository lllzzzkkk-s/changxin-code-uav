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
- Time: 2026-04-30, initial WSL workspace check
- Server: remote Windows host, interactive Ubuntu-20.04 WSL2 shell as `uavdev`
- Command:
  ```bash
  mkdir -p ~/changxin-code
  cd ~/changxin-code
  pwd
  test -d ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner && echo "FOUND_FULL_REPO" || echo "MISSING_FULL_REPO"
  test -d ~/changxin-code/Diff-planner && echo "FOUND_STANDALONE_DIFF_PLANNER" || echo "MISSING_STANDALONE_DIFF_PLANNER"
  find ~ -maxdepth 5 -type d -name Diff-planner 2>/dev/null | tee ~/uav-g3b-evidence/p3-find-diff-planner.txt
  ```
- Output:
  ```text
  /home/uavdev/changxin-code
  MISSING_FULL_REPO
  MISSING_STANDALONE_DIFF_PLANNER
  find output: empty
  ```
- Verdict: BLOCKED_WORKSPACE_SYNC; WSL2 environment is ready, but the Diff-planner snapshot is not present in WSL.
- Local source note: Mac local workspace has `uav/03-drone-code/snapshot_20260421_174511/Diff-planner` at about 140MB, but `uav/03-drone-code` is not tracked in the current git remote.
- Next: transfer the local Diff-planner snapshot into WSL at `~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner`, then rerun P3 build/static checks.

- Time: 2026-04-30, copied snapshot with nested directory
- Server: remote Windows host, interactive Ubuntu-20.04 WSL2 shell as `uavdev`
- Command:
  ```bash
  mkdir -p ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511
  rm -rf ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner
  cp -a /mnt/d/WSL/Downloads/Diff-planner ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/
  test -d ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner && echo FOUND
  find ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner/src -maxdepth 4 -name package.xml | sort | tee ~/uav-g3b-evidence/p3-package-files-after-copy.txt
  ```
- Output:
  ```text
  FOUND
  find: '/home/uavdev/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner/src': No such file or directory
  ```
- Verdict: RETRY_REQUIRED_PATH_NORMALIZATION; snapshot copied, but archive extraction introduced a nested `Diff-planner/Diff-planner` directory and `__MACOSX`.
- Next: inspect root, normalize directory layout, and verify core packages.

- Time: 2026-04-30, normalized copied snapshot
- Server: remote Windows host, interactive Ubuntu-20.04 WSL2 shell as `uavdev`
- Command:
  ```bash
  ls -la ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner | tee ~/uav-g3b-evidence/p3-diff-planner-root-list.txt
  find ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner -maxdepth 3 -type d | sort | tee ~/uav-g3b-evidence/p3-diff-planner-dirs.txt
  find ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner -maxdepth 6 -name package.xml | sort | tee ~/uav-g3b-evidence/p3-package-files-after-copy-deep.txt
  cd ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511
  mv Diff-planner Diff-planner.outer
  mv Diff-planner.outer/Diff-planner Diff-planner
  rm -rf Diff-planner.outer
  test -d ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner/src && echo SRC_FOUND
  find ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner/src -maxdepth 4 \( -path '*quadrotor_msgs/package.xml' -o -path '*multipoint/package.xml' -o -path '*plan_manage/package.xml' \) | sort | tee ~/uav-g3b-evidence/p3-core-package-files.txt
  ```
- Output:
  ```text
  root listing showed:
  Diff-planner
  __MACOSX

  nested directories included:
  .../Diff-planner/Diff-planner/src
  .../Diff-planner/__MACOSX

  SRC_FOUND
  /home/uavdev/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner/src/Utils/quadrotor_msgs/package.xml
  /home/uavdev/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner/src/diff_planner/plan_manage/package.xml
  /home/uavdev/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner/src/user_command/multipoint/package.xml
  ```
- Verdict: P3_1_PASS; Diff-planner snapshot is now present at the fixed WSL path and core package files exist.
- Next: run full `catkin_make`; if blocked by non-core dependencies, proceed with whitelisted core message build and static interface checks.

### P3.2 Build And Message Verification
- Time: 2026-04-30, full workspace build attempt
- Server: remote Windows host, interactive Ubuntu-20.04 WSL2 shell as `uavdev`
- Command:
  ```bash
  source /opt/ros/noetic/setup.bash
  cd ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner
  catkin_make 2>&1 | tee ~/uav-g3b-evidence/p3-catkin-make.txt
  ```
- Output:
  ```text
  catkin traversed 34 packages.
  quadrotor_msgs: 24 messages, 0 services

  CMake Error at realflight_modules/VINS-Fusion-gpu/camera_models/CMakeLists.txt:16 (include):
    include could not find load file:
      /home/nv/Lib/opencv3.4.14/install/OpenCVConfig.cmake

  CMake Error at realflight_modules/VINS-Fusion-gpu/camera_models/CMakeLists.txt:20 (find_package):
    Could not find a package configuration file provided by "Ceres"

  Invoking "cmake" failed
  ```
- Verdict: P3_2_FULL_BUILD_BLOCKED_BY_NONCORE_DEPS; full build is blocked by VINS camera_models OpenCV/Ceres dependencies, not by ROS Noetic or missing core packages.
- Next: build `quadrotor_msgs` with `CATKIN_WHITELIST_PACKAGES`, verify custom message visibility, and collect static `/goal` evidence.

- Time: 2026-04-30, whitelisted core message build
- Server: remote Windows host, interactive Ubuntu-20.04 WSL2 shell as `uavdev`
- Command:
  ```bash
  source /opt/ros/noetic/setup.bash
  cd ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner
  rm -rf build devel
  catkin_make -DCATKIN_WHITELIST_PACKAGES="quadrotor_msgs" 2>&1 | tee ~/uav-g3b-evidence/p3-catkin-make-quadrotor-msgs.txt
  source devel/setup.bash
  rosmsg show quadrotor_msgs/TakeoffLand 2>&1 | tee ~/uav-g3b-evidence/p3-rosmsg-takeoffland.txt
  rosmsg show geometry_msgs/PoseStamped 2>&1 | tee ~/uav-g3b-evidence/p3-rosmsg-posestamped.txt
  ```
- Output:
  ```text
  Using CATKIN_WHITELIST_PACKAGES: quadrotor_msgs
  quadrotor_msgs: 24 messages, 0 services
  [100%] Built target encode_msgs
  [100%] Built target decode_msgs

  rosmsg show quadrotor_msgs/TakeoffLand:
  uint8 TAKEOFF=1
  uint8 LAND=2
  uint8 takeoff_land_cmd

  rosmsg show geometry_msgs/PoseStamped:
  std_msgs/Header header
    uint32 seq
    time stamp
    string frame_id
  geometry_msgs/Pose pose
    geometry_msgs/Point position
      float64 x
      float64 y
      float64 z
    geometry_msgs/Quaternion orientation
      float64 x
      float64 y
      float64 z
      float64 w
  ```
- Verdict: P3_2_CORE_MSG_PASS; core custom command message and standard planning goal message are visible after a minimal build.
- Next: collect static `/goal`, `/move_base_simple/goal`, `/back_trigger`, and launch `flight_type=1` evidence.

### P3.3 Static Interface Verification
- Time: 2026-04-30
- Server: remote Windows host, interactive Ubuntu-20.04 WSL2 shell as `uavdev`
- Command:
  ```bash
  {
    grep -nE 'nh\.subscribe\("/goal"|waypointCallback|planNextWaypoint' src/diff_planner/plan_manage/src/diff_replan_fsm.cpp
    grep -nE 'point_pub = nh\.advertise<geometry_msgs::PoseStamped>\("/goal"|/move_base_simple/goal|/back_trigger' src/user_command/multipoint/src/multipointplan.cpp
    grep -n 'arg name="flight_type" value="1"' src/diff_planner/plan_manage/launch/exp/run_exp_single_lio.launch src/diff_planner/plan_manage/launch/exp/run_exp_single_vio.launch
  } 2>&1 | tee ~/uav-g3b-evidence/p3-static-goal-evidence.txt
  ```
- Output:
  ```text
  72:      waypoint_sub_ = nh.subscribe("/goal", 1, &DiffReplanFSM::waypointCallback, this);
  235:        planNextWaypoint(wps_[wpt_id_], true);
  245:          planNextWaypoint(wps_[wpt_id_], true);
  634:    bool DiffReplanFSM::planNextWaypoint(const Eigen::Vector3d next_wp, bool flag_2replan)
  710:          if (planNextWaypoint(pt, false)) // final_goal_=pt inside if success
  728:  void DiffReplanFSM::waypointCallback(const geometry_msgs::PoseStampedPtr &msg)
  737:    if (planNextWaypoint(end_wp, true))
  768:    planNextWaypoint(wps_[wpt_id_], true);
  387:        startcommand_sub = nh.subscribe("/move_base_simple/goal", 10, startplan_cb);
  390:        backcommand_sub = nh.subscribe("/back_trigger", 10, backplan_cb);
  394:    startcommand_pub = nh.advertise<geometry_msgs::PoseStamped>("/move_base_simple/goal", 10);
  395:    backcommand_pub = nh.advertise<geometry_msgs::PoseStamped>("/back_trigger", 10);
  396:    point_pub = nh.advertise<geometry_msgs::PoseStamped>("/goal", 10);
  src/diff_planner/plan_manage/launch/exp/run_exp_single_lio.launch:37:        <arg name="flight_type" value="1" />
  src/diff_planner/plan_manage/launch/exp/run_exp_single_vio.launch:37:        <arg name="flight_type" value="1" />
  ```
- Verdict: P3_3_PASS_STATIC_ONLY_WITH_CORE_MSGS; `/goal` is the planner goal subscriber/publisher path, `/move_base_simple/goal` and `/back_trigger` are multipoint triggers, and both single LIO/VIO experiment launches use `flight_type=1`.
- Next: proceed to G3-B baseline read-only ROS graph observation. Do not launch planner nodes because full workspace build is blocked by non-core VINS/OpenCV/Ceres dependencies.

### P3.4 Full Diff-planner Dependency Completion
- Time: 2026-04-30, local implementation of remote WSL dependency installer
- Server: local Codex worktree; script is intended to run inside Ubuntu-20.04 WSL2 as `uavdev`
- Root cause:
  ```text
  Full catkin_make stopped inside realflight_modules/VINS-Fusion-gpu/camera_models.
  The first hard blocker is a hard-coded include path:
    /home/nv/Lib/opencv3.4.14/install/OpenCVConfig.cmake
  The second hard blocker is a missing Ceres package config:
    CeresConfig.cmake or ceres-config.cmake
  ```
- Added script:
  ```text
  uav/01-scripts/install_diff_planner_deps_focal.sh
  ```
- Remote command to run after syncing this commit into WSL:
  ```bash
  cd ~/changxin-code
  chmod +x uav/01-scripts/install_diff_planner_deps_focal.sh
  UAV_DEPS_JOBS=8 uav/01-scripts/install_diff_planner_deps_focal.sh all

  source /opt/ros/noetic/setup.bash
  cd ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner
  rm -rf build devel
  catkin_make 2>&1 | tee ~/uav-g3b-evidence/p3-catkin-make-after-full-deps.txt
  ```
- Script coverage:
  ```text
  Required apt deps: Ceres, Eigen3, SuiteSparse, glog/gflags, Boost, PCL, cv_bridge,
  image_transport, tf/tf2, diagnostic_updater, ddynamic_reconfigure, librealsense
  binary package candidates, OpenCV build prerequisites, protobuf/yaml/glfw.

  Source-built dep: OpenCV 3.4.14 installed to the exact VINS hard-coded prefix:
  /home/nv/Lib/opencv3.4.14/install

  GPU/CUDA handling: detect and log nvidia-smi, nvcc, and /usr/local/cuda/version.txt.
  It does not install CUDA by default because WSL CUDA must match the Windows host
  NVIDIA driver. Ubuntu nvidia-cuda-toolkit install is gated behind
  UAV_ALLOW_UBUNTU_CUDA_TOOLKIT=1.
  ```
- Local verification:
  ```text
  bash -n uav/01-scripts/install_diff_planner_deps_focal.sh
  OK
  ```
- Verdict: P3_4_DEP_INSTALLER_READY_NOT_EXECUTED_REMOTE; the missing VINS/OpenCV/Ceres path now has a reproducible installer, but the remote WSL full-build verdict remains pending until the script is run on the Windows server.
- Next: sync this script to WSL, run it, retry full `catkin_make`, and capture the next concrete blocker if CUDA/Realsense/Livox surfaces after OpenCV/Ceres.

## G3-B ROS Graph

### G3-B.1 Read-only Topic And Node Observation
- Time: 2026-04-30
- Server: remote Windows host, interactive Ubuntu-20.04 WSL2 shell as `uavdev`
- Command:
  ```bash
  source /opt/ros/noetic/setup.bash
  pkill -f roscore || true
  pkill -f rosmaster || true
  roscore > ~/uav-g3b-evidence/g3b-roscore.log 2>&1 &
  echo $! | tee ~/uav-g3b-evidence/g3b-roscore.pid
  sleep 5
  {
    date -Is
    rosnode list
    rostopic list
    rostopic info /goal || true
    rostopic type /goal || true
    rosmsg show geometry_msgs/PoseStamped
    rostopic info /move_base_simple/goal || true
    rostopic info /back_trigger || true
    rostopic info /px4ctrl/takeoff_land || true
  } 2>&1 | tee ~/uav-g3b-evidence/g3b-baseline-graph.txt
  kill "$(cat ~/uav-g3b-evidence/g3b-roscore.pid)" || true
  sleep 2
  pgrep -af 'roscore|rosmaster' | tee ~/uav-g3b-evidence/g3b-roscore-after-kill.txt || true
  ```
- Output:
  ```text
  roscore PID: 29617

  2026-04-30T10:32:15+08:00
  rosnode list:
  /rosout

  rostopic list:
  /rosout
  /rosout_agg

  rostopic info /goal:
  ERROR: Unknown topic /goal
  rostopic type /goal:
  unknown topic type [/goal]

  rosmsg show geometry_msgs/PoseStamped:
  std_msgs/Header header
    uint32 seq
    time stamp
    string frame_id
  geometry_msgs/Pose pose
    geometry_msgs/Point position
      float64 x
      float64 y
      float64 z
    geometry_msgs/Quaternion orientation
      float64 x
      float64 y
      float64 z
      float64 w

  rostopic info /move_base_simple/goal:
  ERROR: Unknown topic /move_base_simple/goal
  rostopic info /back_trigger:
  ERROR: Unknown topic /back_trigger
  rostopic info /px4ctrl/takeoff_land:
  ERROR: Unknown topic /px4ctrl/takeoff_land

  roscore exited after kill.
  pgrep after kill only matched the `tee ... g3b-roscore-after-kill.txt` command line, not a live roscore/rosmaster process.
  ```
- Verdict: G3_B_1_PASS_BASELINE_READ_ONLY; with only `roscore` running, no planner/action topics exist, no action topic is published, and standard goal message type introspection works.
- Next: complete final gate review. Do not attempt planner launch in this environment because P3 full build is blocked by non-core VINS/OpenCV/Ceres dependencies.

### G3-B.2 Dry-run Payload Evidence
- Time: 2026-04-30, local worktree dry-run after A-stage service implementation
- Server: local Codex worktree, pure Python dry-run; no ROS master required and no topic publish attempted
- Command:
  ```bash
  python3 - <<'PY'
  from uav.llm_control.core.pipeline import process_command
  from uav.llm_control.schemas.models import BatterySnapshot, FcuSnapshot, LocalizationSnapshot, RcSnapshot, StateSnapshot

  snapshot = StateSnapshot(
      captured_at=100.0,
      fcu=FcuSnapshot(connected=True, armed=True, mode="OFFBOARD", updated_at=100.0),
      battery=BatterySnapshot(voltage=24.1, percentage=0.75, updated_at=100.0),
      rc=RcSnapshot(channels=[1000, 1500, 1500, 1500, 1000, 1000, 1800, 1500], updated_at=100.0),
      localization=LocalizationSnapshot(
          source="lio",
          position={"x": 1.0, "y": 2.0, "z": 1.0},
          velocity={"x": 0.0, "y": 0.0, "z": 0.0},
          yaw=0.0,
          updated_at=100.0,
      ),
  )
  envelope = {
      "meta": {"request_id": "g3b-dry-run"},
      "intent": {"name": "move_relative"},
      "arguments": {"frame": "world", "direction": "forward", "distance_m": 1.0},
      "resolution": {},
      "safety": {},
      "execution": {},
  }
  result = process_command(envelope, snapshot, now=100.0)
  print(result.as_dict())
  PY
  ```
- Output:
  ```text
  status: needs_confirmation
  resolution.target_position: {"x": 2.0, "y": 2.0, "z": 1.0}
  safety.confirmation_policy: always
  safety.reasons: ["confirmation_required"]
  execution.dry_run: True
  execution.publish_attempted: False
  execution.ros_payload.topic: /goal
  execution.ros_payload.message_type: geometry_msgs/PoseStamped
  ```
- Verdict: G3_B_2_PASS_LOCAL_DRY_RUN; `move_relative` compiles into a `/goal` `PoseStamped` dry-run payload and stops at `needs_confirmation` with no publish side effect.
- Next: sync the `uav/llm_control` implementation into the WSL workspace and repeat this same dry-run there before using it as a remote G3-C gate.

- Time: 2026-04-30, WSL sync and dry-run verification
- Server: remote Windows host, interactive Ubuntu-20.04 WSL2 shell as `uavdev`
- Command:
  ```bash
  cd ~/changxin-code
  cp /mnt/d/WSL/Downloads/uav-llm-control-g0.zip .
  python3 -m zipfile -e uav-llm-control-g0.zip .
  find uav/llm_control tests/uav_llm_control -maxdepth 3 -type f | sort
  python3 -m unittest tests.uav_llm_control.test_pipeline
  python3 - <<'PY'
  from uav.llm_control.core.pipeline import process_command
  from uav.llm_control.schemas.models import BatterySnapshot, FcuSnapshot, LocalizationSnapshot, RcSnapshot, StateSnapshot

  snapshot = StateSnapshot(
      captured_at=100.0,
      fcu=FcuSnapshot(connected=True, armed=True, mode="OFFBOARD", updated_at=100.0),
      battery=BatterySnapshot(voltage=24.1, percentage=0.75, updated_at=100.0),
      rc=RcSnapshot(channels=[1000, 1500, 1500, 1500, 1000, 1000, 1800, 1500], updated_at=100.0),
      localization=LocalizationSnapshot(source="lio", position={"x": 1.0, "y": 2.0, "z": 1.0}, velocity={"x": 0.0, "y": 0.0, "z": 0.0}, yaw=0.0, updated_at=100.0),
  )
  result = process_command({
      "meta": {"request_id": "g3b-dry-run-wsl"},
      "intent": {"name": "move_relative"},
      "arguments": {"frame": "world", "direction": "forward", "distance_m": 1.0},
  }, snapshot, now=100.0)
  print(result.as_dict())
  PY
  ```
- Output:
  ```text
  tests/uav_llm_control/__init__.py
  tests/uav_llm_control/test_pipeline.py
  uav/llm_control/__init__.py
  uav/llm_control/api/__init__.py
  uav/llm_control/core/__init__.py
  uav/llm_control/core/pipeline.py
  uav/llm_control/llm/__init__.py
  uav/llm_control/ros_adapters/__init__.py
  uav/llm_control/schemas/__init__.py
  uav/llm_control/schemas/models.py
  uav/llm_control/tools/__init__.py
  uav/llm_control/tools/catalog.py

  Ran 8 tests in 0.001s
  OK

  status: needs_confirmation
  resolution.target_position: {"x": 2.0, "y": 2.0, "z": 1.0}
  safety.confirmation_policy: always
  safety.reasons: ["confirmation_required"]
  execution.dry_run: True
  execution.publish_attempted: False
  execution.ros_payload.topic: /goal
  execution.ros_payload.message_type: geometry_msgs/PoseStamped
  ```
- Verdict: G3_B_2_PASS_WSL_DRY_RUN; the A-stage service layer is synced into WSL and the same `move_relative` dry-run passes there with no publish side effect.
- Next: use this WSL dry-run as the A-stage evidence baseline before adding ROS adapter code.

- Time: 2026-04-30, local ROS adapter dry-run trace
- Server: local Codex worktree, pure Python adapter report; no ROS master required and no topic publish attempted
- Command:
  ```bash
  python -m unittest tests.uav_llm_control.test_pipeline tests.uav_llm_control.test_ros_adapter_dry_run
  python - <<'PY'
  from uav.llm_control.ros_adapters.dry_run import build_dry_run_report
  from uav.llm_control.schemas.models import BatterySnapshot, FcuSnapshot, LocalizationSnapshot, RcSnapshot, StateSnapshot

  snapshot = StateSnapshot(
      captured_at=100.0,
      fcu=FcuSnapshot(connected=True, armed=True, mode='OFFBOARD', updated_at=100.0),
      battery=BatterySnapshot(voltage=24.1, percentage=0.75, updated_at=100.0),
      rc=RcSnapshot(channels=[1000,1500,1500,1500,1000,1000,1800,1500], updated_at=100.0),
      localization=LocalizationSnapshot(source='lio', position={'x': 1.0, 'y': 2.0, 'z': 1.0}, velocity={'x': 0.0, 'y': 0.0, 'z': 0.0}, yaw=0.0, updated_at=100.0),
  )
  report = build_dry_run_report({
      'meta': {'request_id': 'g3b-a-adapter-local'},
      'intent': {'name': 'move_relative'},
      'arguments': {'frame': 'world', 'direction': 'forward', 'distance_m': 1.0},
  }, snapshot, now=100.0).as_dict()
  print('status:', report['status'])
  print('publish_attempted:', report['publish_attempted'])
  print('trace_stages:', [entry['stage'] for entry in report['trace']])
  print('target_position:', report['trace'][4]['target_position'])
  print('ros_payload_topic:', report['trace'][5]['topic'])
  print('confirmation_gate:', report['trace'][6]['status'])
  PY
  ```
- Output:
  ```text
  Ran 11 tests in 0.002s
  OK

  status: needs_confirmation
  publish_attempted: False
  trace_stages: ['input', 'schema_validation', 'state_snapshot', 'safety_policy', 'target_point', 'ros_payload', 'confirmation_gate']
  target_position: {'x': 2.0, 'y': 2.0, 'z': 1.0}
  ros_payload_topic: /goal
  confirmation_gate: blocked_for_confirmation
  ```
- Verdict: G3_B_2_PASS_LOCAL_ADAPTER_TRACE; A-stage adapter trace includes input, schema validation, state snapshot, safety policy, target point, ROS payload, and confirmation gate, while still refusing to publish.
- Next: sync adapter and dependency installer to WSL; rerun the 11-test suite and adapter trace there before marking A closed.

- Time: 2026-04-30, WSL full Diff-planner build and A-stage post-build tests
- Server: remote Windows host, interactive Ubuntu-20.04 WSL2 shell as `uavdev`
- Command:
  ```bash
  cd ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner
  source /opt/ros/noetic/setup.bash
  rm -rf build devel
  catkin_make -j8 -l8 2>&1 | tee ~/uav-g3b-evidence/p3-catkin-make-after-full-deps-7.txt

  cd ~/changxin-code
  source /opt/ros/noetic/setup.bash
  source ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner/devel/setup.bash
  PYTHONPATH="$PWD:${PYTHONPATH:-}" \
    python3 -m unittest tests.uav_llm_control.test_pipeline tests.uav_llm_control.test_ros_adapter_dry_run \
    2>&1 | tee ~/uav-g3b-evidence/a-stage-python-tests-after-full-catkin.txt

  cd ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner
  source /opt/ros/noetic/setup.bash
  source devel/setup.bash
  {
    echo "ROSPACK:"
    for p in quadrotor_msgs diff_planner multipoint px4ctrl vins faster_lio; do
      rospack find "$p"
    done

    echo
    echo "NODES:"
    test -x devel/lib/diff_planner/diff_planner_node && echo DIFF_PLANNER_NODE_OK
    test -x devel/lib/vins/vins_node && echo VINS_NODE_OK
    test -x devel/lib/faster_lio/run_mapping_online && echo FASTER_LIO_ONLINE_OK
    test -x devel/lib/px4ctrl/px4ctrl_node && echo PX4CTRL_NODE_OK || true
  } | tee ~/uav-g3b-evidence/p3-ros-package-node-checks.txt
  ```
- Output:
  ```text
  [100%] Built target vins_node
  [100%] Built target run_mapping_online
  [100%] Built target run_mapping_offline

  Ran 11 tests in 0.002s
  OK

  ROSPACK:
  /home/uavdev/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner/src/Utils/quadrotor_msgs
  /home/uavdev/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner/src/diff_planner/plan_manage
  /home/uavdev/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner/src/user_command/multipoint
  /home/uavdev/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner/src/realflight_modules/px4ctrl
  /home/uavdev/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner/src/realflight_modules/VINS-Fusion-gpu/vins_estimator
  /home/uavdev/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner/src/realflight_modules/faster-lio

  NODES:
  DIFF_PLANNER_NODE_OK
  VINS_NODE_OK
  FASTER_LIO_ONLINE_OK
  PX4CTRL_NODE_OK
  ```
- Notes:
  ```text
  The WSL build links both OpenCV 3.4 and ROS/apt OpenCV 4.2 libraries in VINS-related targets, producing linker conflict warnings. The build still completes. For real-aircraft CUDA deployment, use one consistent CUDA OpenCV/contrib stack and a matching cv_bridge build.
  ```
- Verdict: P3_PASS_FULL_CATKIN_BUILD_AND_NODE_VISIBILITY; the full Diff-planner workspace builds in WSL, the A-stage Python suite passes after sourcing the built workspace, and the main planner/VINS/Faster-LIO/PX4 control packages and node executables are visible.
- Next: capture a standalone WSL adapter trace output from `build_dry_run_report` before marking A closed.

- Time: 2026-04-30, WSL standalone adapter trace after full catkin build
- Server: remote Windows host, interactive Ubuntu-20.04 WSL2 shell as `uavdev`
- Command:
  ```bash
  cd ~/changxin-code
  source /opt/ros/noetic/setup.bash
  source ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner/devel/setup.bash

  PYTHONPATH="$PWD:${PYTHONPATH:-}" python3 - <<'PY' | tee ~/uav-g3b-evidence/a-stage-wsl-adapter-trace-after-full-catkin.txt
  from uav.llm_control.ros_adapters.dry_run import build_dry_run_report
  from uav.llm_control.schemas.models import BatterySnapshot, FcuSnapshot, LocalizationSnapshot, RcSnapshot, StateSnapshot

  snapshot = StateSnapshot(
      captured_at=100.0,
      fcu=FcuSnapshot(connected=True, armed=True, mode="OFFBOARD", updated_at=100.0),
      battery=BatterySnapshot(voltage=24.1, percentage=0.75, updated_at=100.0),
      rc=RcSnapshot(channels=[1000,1500,1500,1500,1000,1000,1800,1500], updated_at=100.0),
      localization=LocalizationSnapshot(
          source="lio",
          position={"x": 1.0, "y": 2.0, "z": 1.0},
          velocity={"x": 0.0, "y": 0.0, "z": 0.0},
          yaw=0.0,
          updated_at=100.0,
      ),
  )
  report = build_dry_run_report({
      "meta": {"request_id": "a-stage-wsl-after-full-catkin"},
      "intent": {"name": "move_relative"},
      "arguments": {"frame": "world", "direction": "forward", "distance_m": 1.0},
  }, snapshot, now=100.0).as_dict()

  print("status:", report["status"])
  print("publish_attempted:", report["publish_attempted"])
  print("trace_stages:", [entry["stage"] for entry in report["trace"]])
  print("target_position:", report["trace"][4]["target_position"])
  print("ros_payload_topic:", report["trace"][5]["topic"])
  print("ros_payload_type:", report["trace"][5]["message_type"])
  print("confirmation_gate:", report["trace"][6]["status"])
  PY
  ```
- Output:
  ```text
  status: needs_confirmation
  publish_attempted: False
  trace_stages: ['input', 'schema_validation', 'state_snapshot', 'safety_policy', 'target_point', 'ros_payload', 'confirmation_gate']
  target_position: {'x': 2.0, 'y': 2.0, 'z': 1.0}
  ros_payload_topic: /goal
  ros_payload_type: geometry_msgs/PoseStamped
  confirmation_gate: blocked_for_confirmation
  ```
- Verdict: G3_B_2_PASS_WSL_ADAPTER_TRACE_AFTER_FULL_CATKIN; after sourcing the full WSL catkin workspace, the A-stage adapter still produces a `/goal` `PoseStamped` dry-run payload, blocks at the confirmation gate, and records `publish_attempted=False`.
- Next: A-stage dry-run scope can close. Any B/G3-C work must start with read-only runtime prechecks and must not publish motion/takeoff/land commands until a separate action-safety gate is approved.

## G3-C Read-Only Planner Runtime Prechecks

- Time: 2026-04-30, WSL launch/topic inventory
- Server: remote Windows host, interactive Ubuntu-20.04 WSL2 shell as `uavdev`
- Command:
  ```bash
  cd ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner
  source /opt/ros/noetic/setup.bash
  source devel/setup.bash
  mkdir -p ~/uav-g3c-evidence

  {
    date -Is
    echo "ROS_PACKAGE_PATH=$ROS_PACKAGE_PATH"
    echo
    for p in quadrotor_msgs diff_planner multipoint px4ctrl vins faster_lio; do
      echo "### $p"
      rospack find "$p"
    done
  } | tee ~/uav-g3c-evidence/g3c-00-env-packages.txt

  find src -path '*/launch/*.launch' | sort \
    | tee ~/uav-g3c-evidence/g3c-01-launch-files.txt

  rg -n "/goal|/move_base_simple/goal|/back_trigger|/px4ctrl/takeoff_land|mavros|arming|set_mode|setpoint|advertise|publish|subscribe" \
    src/diff_planner src/user_command src/realflight_modules/px4ctrl src/realflight_modules/VINS-Fusion-gpu src/realflight_modules/faster-lio \
    | tee ~/uav-g3c-evidence/g3c-02-topic-control-static-scan.txt

  while read -r f; do
    echo "===== $f ====="
    roslaunch --nodes "$f" || true
  done < ~/uav-g3c-evidence/g3c-01-launch-files.txt \
    | tee ~/uav-g3c-evidence/g3c-03-launch-node-inventory.txt
  ```
- Output:
  ```text
  ROS_PACKAGE_PATH=/home/uavdev/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner/src:/opt/ros/noetic/share

  rospack resolved:
  quadrotor_msgs, diff_planner, multipoint, px4ctrl, vins, faster_lio

  Key launch files:
  src/diff_planner/plan_manage/launch/exp/run_exp_single_lio.launch
  src/diff_planner/plan_manage/launch/exp/run_exp_single_vio.launch
  src/diff_planner/plan_manage/launch/sim/run_sim_single.launch
  src/user_command/multipoint/launch/multipointplan_exp_lio.launch
  src/user_command/multipoint/launch/multipointplan_exp_vio.launch
  src/realflight_modules/px4ctrl/launch/run_ctrl_lio.launch
  src/realflight_modules/px4ctrl/launch/run_ctrl_vio.launch
  src/realflight_modules/faster-lio/launch/mapping_mid360.launch
  src/realflight_modules/VINS-Fusion-gpu/vins_estimator/launch/vins_d435.launch

  run_sim_single.launch nodes:
  /random_forest
  /drone_0_diff_planner_node
  /drone_0_traj_server
  /drone_0_poscmd_2_odom
  /drone_0_odom_visualization
  /drone_0_pcl_render_node
  /drone_0_manual_take_over
  /multipointplan
  /rviz

  run_exp_single_lio.launch and run_exp_single_vio.launch require DRONE_ID.
  mapping_mid360.launch requires BD_LIST.
  px4ctrl/run_ctrl_lio.launch and run_ctrl_vio.launch resolve /px4ctrl.
  vins_d435.launch resolves /vins.
  Faster-LIO mapping launches resolve /laserMapping, except mapping_mid360 until BD_LIST is set.
  ```
- Action-surface findings:
  ```text
  px4ctrl subscribes FCU/MAVROS state, odometry, IMU, battery, RC, and takeoff_land; it publishes /mavros/setpoint_raw/attitude and owns /mavros/set_mode, /mavros/cmd/arming, and /mavros/cmd/command service clients.
  diff_planner subscribes /goal when flight_type=1 and /traj_start_trigger; traj_server publishes /position_cmd, remapped to /setpoints_cmd in exp launch files.
  multipointplan publishes /goal, /move_base_simple/goal, /back_trigger, /px4ctrl/takeoff_land, and /planning/yaw.
  faster_lio publishes /laserMapping/odometry and point cloud topics; mid360 config uses /mavros/imu/data.
  VINS publishes odometry/path/point cloud topics and uses /mavros/imu/data in the D435 config.
  ```
- Non-blocking launch inventory notes:
  ```text
  Some Realsense examples require rtabmap_ros or rgbd_launch; these are not on the core Diff-planner/PX4/VINS/Faster-LIO path identified for G3-C.
  ```
- Verdict: G3_C_0_PASS_READ_ONLY_INVENTORY_WITH_ACTION_SURFACE_IDENTIFIED. Package resolution, launch-file inventory, static topic/control scan, and launch node inventory are complete enough to choose the next precheck path.
- Next: run target launch parsing with explicit environment variables, dump sim launch parameters, and capture a roscore-only baseline. Do not start px4ctrl or publish `/goal`, `/move_base_simple/goal`, `/back_trigger`, `/px4ctrl/takeoff_land`, `/setpoints_cmd`, or MAVROS arming/set_mode/setpoint traffic.

- Time: 2026-04-30, WSL target launch parsing, parameter dump, and roscore baseline
- Server: remote Windows host, interactive Ubuntu-20.04 WSL2 shell as `uavdev`
- Command:
  ```bash
  cd ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner
  source /opt/ros/noetic/setup.bash
  source devel/setup.bash
  mkdir -p ~/uav-g3c-evidence

  DRONE_ID=0 BD_LIST='' bash -lc '
  for f in \
    src/diff_planner/plan_manage/launch/exp/run_exp_single_lio.launch \
    src/diff_planner/plan_manage/launch/exp/run_exp_single_vio.launch \
    src/realflight_modules/faster-lio/launch/mapping_mid360.launch \
    src/user_command/multipoint/launch/multipointplan_exp_lio.launch \
    src/user_command/multipoint/launch/multipointplan_exp_vio.launch \
    src/diff_planner/plan_manage/launch/sim/run_sim_single.launch; do
      echo "===== $f ====="
      roslaunch --nodes "$f" || true
    done
  ' | tee ~/uav-g3c-evidence/g3c-04-target-launch-node-inventory-with-env.txt

  DRONE_ID=0 roslaunch --dump-params src/diff_planner/plan_manage/launch/sim/run_sim_single.launch \
    | tee ~/uav-g3c-evidence/g3c-05-run-sim-single-dump-params.txt

  DRONE_ID=0 roslaunch --dump-params src/diff_planner/plan_manage/launch/exp/run_exp_single_lio.launch \
    | tee ~/uav-g3c-evidence/g3c-05-run-exp-single-lio-dump-params.txt

  roscore > ~/uav-g3c-evidence/g3c-06-roscore.log 2>&1 &
  ROSCORE_PID=$!
  sleep 3
  {
    date -Is
    rosnode list
    rostopic list -v
  } | tee ~/uav-g3c-evidence/g3c-06-roscore-baseline.txt
  kill "$ROSCORE_PID"
  wait "$ROSCORE_PID" 2>/dev/null || true
  ```
- Output:
  ```text
  run_exp_single_lio.launch:
  /drone_0_diff_planner_node
  /drone_0_traj_server

  run_exp_single_vio.launch:
  /drone_0_diff_planner_node
  /drone_0_traj_server

  mapping_mid360.launch:
  /livox_lidar_publisher2
  /laserMapping

  multipointplan_exp_lio.launch and multipointplan_exp_vio.launch:
  /multipointplan

  run_sim_single.launch:
  /random_forest
  /drone_0_diff_planner_node
  /drone_0_traj_server
  /drone_0_poscmd_2_odom
  /drone_0_odom_visualization
  /drone_0_pcl_render_node
  /drone_0_manual_take_over
  /multipointplan
  /rviz

  roscore baseline at 2026-04-30T12:09:03+08:00:
  /rosout

  Published topics:
   * /rosout_agg [rosgraph_msgs/Log] 1 publisher

  Subscribed topics:
   * /rosout [rosgraph_msgs/Log] 1 subscriber
  ```
- Parameter findings:
  ```text
  run_sim_single.launch sets /drone_0_diff_planner_node/fsm/flight_type=1, realworld_experiment=true, manager/max_vel=1.5, manager/max_acc=6.0, grid_map/pose_type=1, grid_map/resolution=0.1, and /multipointplan/start_plan=1, back_plan=1.
  run_exp_single_lio.launch sets /drone_0_diff_planner_node/fsm/flight_type=1, realworld_experiment=true, manager/max_vel=0.5, manager/max_acc=3.0, grid_map/pose_type=2, grid_map/resolution=0.15, waypoint0=(8.0,0.0,1.0), waypoint1=(0.0,0.0,1.0), and traj_server/time_forward=1.0.
  ```
- Verdict: G3_C_1_PASS_TARGET_PARSE_PARAM_AND_ROSCORE_BASELINE. The target launch files parse with explicit environment variables, sim and LIO parameter dumps were captured, and the roscore-only baseline contains no action topics.
- Next: a sim-only observe run may be started for runtime graph inspection. Keep it bounded and do not publish `/goal`, `/move_base_simple/goal`, `/back_trigger`, `/px4ctrl/takeoff_land`, `/setpoints_cmd`, or MAVROS arming/set_mode/setpoint traffic.

- Time: 2026-04-30, first bounded sim-only observe startup attempt
- Server: remote Windows host, interactive Ubuntu-20.04 WSL2 shell as `uavdev`
- Command:
  ```bash
  cd ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner
  source /opt/ros/noetic/setup.bash
  source devel/setup.bash
  mkdir -p ~/uav-g3c-evidence

  ROS_LOG_DIR=~/uav-g3c-evidence/roslogs-g3c-07 \
  timeout --signal=INT --kill-after=8s 35s \
    roslaunch src/diff_planner/plan_manage/launch/sim/run_sim_single.launch \
    2>&1 | tee ~/uav-g3c-evidence/g3c-07-run-sim-single-observe.log || true

  {
    date -Is
    echo "NODES:"
    rosnode list || true
    echo
    echo "TOPICS:"
    rostopic list -v || true
  } | tee ~/uav-g3c-evidence/g3c-08-run-sim-single-graph-after-timeout.txt

  for t in /goal /move_base_simple/goal /back_trigger /px4ctrl/takeoff_land /setpoints_cmd; do
    echo "===== $t ====="
    timeout 3s rostopic echo -n 1 "$t" || echo "NO_MESSAGE_OR_TOPIC_WITHIN_3S"
  done | tee ~/uav-g3c-evidence/g3c-09-action-topic-passive-echo-check.txt
  ```
- Output:
  ```text
  run_sim_single.launch started:
  /random_forest
  /drone_0_diff_planner_node
  /drone_0_traj_server
  /drone_0_poscmd_2_odom
  /drone_0_odom_visualization
  /drone_0_pcl_render_node
  /drone_0_manual_take_over
  /multipointplan
  /rviz

  rviz failed in the headless WSL session:
  qt.qpa.xcb: could not connect to display
  qt.qpa.plugin: Could not load the Qt platform plugin "xcb" in "" even though it was found.
  This application failed to start because no Qt platform plugin could be initialized.

  roslaunch then shut down the launch because required process [rviz-10] died.

  Follow-up graph checks after shutdown:
  ERROR: Unable to communicate with master!

  Passive action-topic checks after shutdown:
  /goal: ERROR: Unable to communicate with master! NO_MESSAGE_OR_TOPIC_WITHIN_3S
  /move_base_simple/goal: ERROR: Unable to communicate with master! NO_MESSAGE_OR_TOPIC_WITHIN_3S
  /back_trigger: ERROR: Unable to communicate with master! NO_MESSAGE_OR_TOPIC_WITHIN_3S
  /px4ctrl/takeoff_land: ERROR: Unable to communicate with master! NO_MESSAGE_OR_TOPIC_WITHIN_3S
  /setpoints_cmd: ERROR: Unable to communicate with master! NO_MESSAGE_OR_TOPIC_WITHIN_3S
  ```
- Verdict: G3_C_2_PARTIAL_SIM_START_BLOCKED_BY_REQUIRED_RVIZ_HEADLESS_FAILURE. The sim launch reached process startup, but WSL has no GUI display and `rviz` is required, so the launch shut down before a useful runtime graph or passive action-topic observation could be captured.
- Next: create a temporary headless copy of the sim launch that removes only the RViz node, run the same bounded observation, then inspect the live graph and passive action topics while the ROS master is still up.

- Time: 2026-04-30, headless sim-only observe run with live passive action-topic checks
- Server: remote Windows host, interactive Ubuntu-20.04 WSL2 shell as `uavdev`
- Command:
  ```bash
  cd ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner
  source /opt/ros/noetic/setup.bash
  source devel/setup.bash
  mkdir -p ~/uav-g3c-evidence

  python3 - <<'PY'
  import xml.etree.ElementTree as ET
  from pathlib import Path

  src = Path("src/diff_planner/plan_manage/launch/sim/run_sim_single.launch")
  dst = Path.home() / "uav-g3c-evidence/run_sim_single_headless.launch"

  tree = ET.parse(src)
  root = tree.getroot()

  removed = []
  for parent in root.iter():
      for child in list(parent):
          if child.tag == "node" and child.get("pkg") == "rviz":
              parent.remove(child)
              removed.append(child.get("name", "?"))

  tree.write(dst, encoding="utf-8", xml_declaration=False)
  print("removed nodes:", removed)
  print("written to:", dst)
  PY

  roslaunch --nodes ~/uav-g3c-evidence/run_sim_single_headless.launch \
    | tee ~/uav-g3c-evidence/g3c-10-headless-launch-nodes.txt

  ROS_LOG_DIR=~/uav-g3c-evidence/roslogs-g3c-11 \
  QT_QPA_PLATFORM=offscreen \
  roslaunch ~/uav-g3c-evidence/run_sim_single_headless.launch \
    > ~/uav-g3c-evidence/g3c-11-headless-sim.log 2>&1 &
  LAUNCH_PID=$!

  sleep 15

  {
    date -Is
    if kill -0 "$LAUNCH_PID" 2>/dev/null; then
      echo "LAUNCH_ALIVE pid=$LAUNCH_PID"
    else
      echo "LAUNCH_ALREADY_DEAD pid=$LAUNCH_PID"
    fi
  } | tee ~/uav-g3c-evidence/g3c-11b-launch-liveness.txt

  {
    date -Is
    echo "NODES:"
    rosnode list || true
    echo
    echo "TOPICS:"
    rostopic list -v || true
  } | tee ~/uav-g3c-evidence/g3c-12-headless-sim-live-graph.txt

  for t in /goal /move_base_simple/goal /back_trigger /px4ctrl/takeoff_land /setpoints_cmd; do
    echo "===== $t ====="
    timeout 3s rostopic echo -n 1 "$t" || echo "NO_MESSAGE_WITHIN_3S"
  done | tee ~/uav-g3c-evidence/g3c-13-headless-action-topic-passive-echo.txt

  kill -INT "$LAUNCH_PID" 2>/dev/null || echo "already dead at cleanup"
  wait "$LAUNCH_PID" 2>/dev/null || true
  ```
- Output:
  ```text
  removed nodes: ['rviz']
  written to: /home/uavdev/uav-g3c-evidence/run_sim_single_headless.launch

  g3c-10 nodes:
  /random_forest
  /drone_0_diff_planner_node
  /drone_0_traj_server
  /drone_0_poscmd_2_odom
  /drone_0_odom_visualization
  /drone_0_pcl_render_node
  /drone_0_manual_take_over
  /multipointplan

  g3c-11b at 2026-04-30T13:57:20+08:00:
  LAUNCH_ALIVE pid=31765

  g3c-12 live graph nodes:
  /drone_0_diff_planner_node
  /drone_0_manual_take_over
  /drone_0_odom_visualization
  /drone_0_pcl_render_node
  /drone_0_poscmd_2_odom
  /drone_0_traj_server
  /multipointplan
  /random_forest
  /rosout

  g3c-12 action-surface topic registration:
  /px4ctrl/takeoff_land [quadrotor_msgs/TakeoffLand] 1 publisher
  /move_base_simple/goal [geometry_msgs/PoseStamped] 1 publisher, 1 subscriber
  /back_trigger [geometry_msgs/PoseStamped] 1 publisher, 1 subscriber
  /goal [geometry_msgs/PoseStamped] 1 publisher, 1 subscriber
  /planning/yaw [quadrotor_msgs/PositionCommand] 1 publisher, 1 subscriber
  /setpoints_cmd was not advertised.

  g3c-13 passive action-topic echo while launch was alive:
  /goal: NO_MESSAGE_WITHIN_3S
  /move_base_simple/goal: NO_MESSAGE_WITHIN_3S
  /back_trigger: NO_MESSAGE_WITHIN_3S
  /px4ctrl/takeoff_land: NO_MESSAGE_WITHIN_3S
  /setpoints_cmd: WARNING: topic [/setpoints_cmd] does not appear to be published yet; NO_MESSAGE_WITHIN_3S
  ```
- Notes:
  ```text
  The first temporary launch generation attempt used line-oriented skipping and was invalid for a self-closing RViz node. The accepted evidence uses XML parsing to remove only pkg="rviz" nodes.
  `QT_QPA_PLATFORM=offscreen` is required in this headless WSL session so Qt-based nodes can start without an X display.
  The passive no-message check is valid because g3c-11b proves the launch was alive and g3c-12 proves the ROS master was responding when g3c-13 was captured.
  multipointplan advertises /goal, /move_base_simple/goal, /back_trigger, /px4ctrl/takeoff_land, and /planning/yaw, so it remains an action-surface node even though no passive-observation message was emitted in this 15-second window.
  ```
- Verdict: G3_C_3_PASS_HEADLESS_SIM_PASSIVE_ECHO_15S. A headless sim launch copy without RViz starts and remains alive after 15 seconds; all eight expected business nodes plus `/rosout` are visible under a live master; `/goal`, `/move_base_simple/goal`, `/back_trigger`, `/px4ctrl/takeoff_land`, and `/setpoints_cmd` emit no messages during passive observation.
- Next: either extend the passive observation window to 60-120 seconds for a stricter idle guarantee, or proceed to a sim dry-run wiring stage that still blocks publishing and only observes state and planned payloads.

- Time: 2026-04-30, extended 120-second headless sim passive observation
- Server: remote Windows host, interactive Ubuntu-20.04 WSL2 shell as `uavdev`
- Command:
  ```bash
  cd ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner
  source /opt/ros/noetic/setup.bash
  source devel/setup.bash

  ROS_LOG_DIR=~/uav-g3c-evidence/roslogs-g3c-14 \
  QT_QPA_PLATFORM=offscreen \
  roslaunch ~/uav-g3c-evidence/run_sim_single_headless.launch \
    > ~/uav-g3c-evidence/g3c-14-headless-sim-120s.log 2>&1 &
  LAUNCH_PID=$!

  sleep 120

  {
    date -Is
    echo "LAUNCH_PID=$LAUNCH_PID alive=$(kill -0 $LAUNCH_PID 2>/dev/null && echo yes || echo no)"
    echo
    echo "NODES:"
    rosnode list || true
    echo
    echo "TOPICS:"
    rostopic list -v || true
  } | tee ~/uav-g3c-evidence/g3c-15-headless-sim-120s-live-graph.txt

  for t in /goal /move_base_simple/goal /back_trigger /px4ctrl/takeoff_land /setpoints_cmd; do
    echo "===== $t ====="
    timeout 5s rostopic echo -n 1 "$t" || echo "NO_MESSAGE_WITHIN_5S"
  done | tee ~/uav-g3c-evidence/g3c-16-headless-action-topic-120s-passive-echo.txt

  tail -n 120 ~/uav-g3c-evidence/g3c-14-headless-sim-120s.log \
    | tee ~/uav-g3c-evidence/g3c-17-headless-sim-120s-log-tail.txt

  kill -INT "$LAUNCH_PID" 2>/dev/null || echo "already dead"
  wait "$LAUNCH_PID" 2>/dev/null || true
  ```
- Output:
  ```text
  g3c-15 at 2026-04-30T16:06:56+08:00:
  LAUNCH_PID=32098 alive=yes

  g3c-15 live graph nodes:
  /drone_0_diff_planner_node
  /drone_0_manual_take_over
  /drone_0_odom_visualization
  /drone_0_pcl_render_node
  /drone_0_poscmd_2_odom
  /drone_0_traj_server
  /multipointplan
  /random_forest
  /rosout

  g3c-15 action-surface topic registration:
  /px4ctrl/takeoff_land [quadrotor_msgs/TakeoffLand] 1 publisher
  /move_base_simple/goal [geometry_msgs/PoseStamped] 1 publisher, 1 subscriber
  /back_trigger [geometry_msgs/PoseStamped] 1 publisher, 1 subscriber
  /goal [geometry_msgs/PoseStamped] 1 publisher, 1 subscriber
  /planning/yaw [quadrotor_msgs/PositionCommand] 1 publisher, 1 subscriber
  /setpoints_cmd was not advertised.

  g3c-16 passive action-topic echo after 120 seconds:
  /goal: NO_MESSAGE_WITHIN_5S
  /move_base_simple/goal: NO_MESSAGE_WITHIN_5S
  /back_trigger: NO_MESSAGE_WITHIN_5S
  /px4ctrl/takeoff_land: NO_MESSAGE_WITHIN_5S
  /setpoints_cmd: WARNING: topic [/setpoints_cmd] does not appear to be published yet; NO_MESSAGE_WITHIN_5S

  g3c-17 log tail:
  [FSM]Drone:0, from INIT to WAIT_TARGET
  [WARN] Finished generate random map
  [WARN] Global Pointcloud received..
  [FSM]: state: WAIT_TARGET, Drone:0. Waiting for target,trigger,
  [FSM]: state: WAIT_TARGET, Drone:0. Waiting for target,trigger,
  ...
  [FSM]: state: WAIT_TARGET, Drone:0. Waiting for target,trigger,
  ```
- Verdict: G3_C_4_PASS_HEADLESS_SIM_PASSIVE_ECHO_120S. The headless sim launch remains alive after 120 seconds with all eight expected business nodes visible under a live master; the planner FSM stays in `WAIT_TARGET`; `/goal`, `/move_base_simple/goal`, `/back_trigger`, `/px4ctrl/takeoff_land`, and `/setpoints_cmd` emit no messages during the extended passive observation.
- Next: proceed to sim dry-run wiring. The next stage may run the A-stage report generator while the sim graph is alive and verify it still records `publish_attempted=False` and does not emit action-topic messages.

- Time: 2026-04-30, first sim dry-run wiring attempt
- Server: remote Windows host, interactive Ubuntu-20.04 WSL2 shell as `uavdev`
- Command:
  ```bash
  cd ~/changxin-code
  source /opt/ros/noetic/setup.bash
  source ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner/devel/setup.bash

  PYTHONPATH="$PWD:${PYTHONPATH:-}" python3 - <<'PY' \
    | tee ~/uav-g3c-evidence/g3c-18-sim-live-a-stage-dry-run-report.txt
  from uav.llm_control.ros_adapters.dry_run import build_dry_run_report
  from uav.llm_control.schemas.models import BatterySnapshot, FcuSnapshot, LocalizationSnapshot, RcSnapshot, StateSnapshot

  snapshot = StateSnapshot(
      captured_at=100.0,
      fcu=FcuSnapshot(connected=True, armed=True, mode="OFFBOARD", updated_at=100.0),
      battery=BatterySnapshot(voltage=24.1, percentage=0.75, updated_at=100.0),
      rc=RcSnapshot(channels=[1000,1500,1500,1500,1000,1000,1800,1500], updated_at=100.0),
      localization=LocalizationSnapshot(
          source="sim",
          position={"x": -15.0, "y": 0.0, "z": 1.0},
          velocity={"x": 0.0, "y": 0.0, "z": 0.0},
          yaw=0.0,
          updated_at=100.0,
      ),
  )
  report = build_dry_run_report({
      "meta": {"request_id": "g3c-sim-live-dry-run"},
      "intent": {"name": "move_relative"},
      "arguments": {"frame": "world", "direction": "forward", "distance_m": 1.0},
  }, snapshot, now=100.0).as_dict()

  print("status:", report["status"])
  print("publish_attempted:", report["publish_attempted"])
  print("trace_stages:", [entry["stage"] for entry in report["trace"]])
  print("target_position:", report["trace"][4]["target_position"])
  print("ros_payload_topic:", report["trace"][5]["topic"])
  print("ros_payload_type:", report["trace"][5]["message_type"])
  print("confirmation_gate:", report["trace"][6]["status"])
  PY

  for t in /goal /move_base_simple/goal /back_trigger /px4ctrl/takeoff_land /setpoints_cmd; do
    echo "===== $t ====="
    timeout 5s rostopic echo -n 1 "$t" || echo "NO_MESSAGE_WITHIN_5S"
  done | tee ~/uav-g3c-evidence/g3c-19-post-dry-run-action-topic-passive-echo.txt
  ```
- Output:
  ```text
  status: failed
  publish_attempted: False
  trace_stages: ['input', 'schema_validation', 'state_snapshot', 'safety_policy', 'target_point', 'ros_payload', 'confirmation_gate']
  target_position: None
  ros_payload_topic: None
  ros_payload_type: None
  confirmation_gate: not_reached

  /goal: ERROR: Unable to communicate with master! NO_MESSAGE_WITHIN_5S
  /move_base_simple/goal: ERROR: Unable to communicate with master! NO_MESSAGE_WITHIN_5S
  /back_trigger: ERROR: Unable to communicate with master! NO_MESSAGE_WITHIN_5S
  /px4ctrl/takeoff_land: ERROR: Unable to communicate with master! NO_MESSAGE_WITHIN_5S
  /setpoints_cmd: ERROR: Unable to communicate with master! NO_MESSAGE_WITHIN_5S
  ```
- Diagnosis:
  ```text
  The dry-run failure is caused by the A-stage precondition that only accepts localization.source in {"lio", "vio"}. The test snapshot used source="sim", so process_command fails before target resolution with unsupported_localization_source.
  The passive topic checks are not valid for publish/no-publish evidence because the prior 120-second headless sim launch had already been cleaned up, so ROS master was no longer reachable.
  ```
- Local reproduction:
  ```text
  source=sim -> failed, precheck_failure, unsupported_localization_source, target=None, topic=None, confirmation=not_reached
  source=lio -> needs_confirmation, target={'x': -14.0, 'y': 0.0, 'z': 1.0}, topic=/goal, confirmation=blocked_for_confirmation
  ```
- Verdict: G3_C_5_SIM_DRY_RUN_WIRING_RETRY_REQUIRED. The report generator still refused to publish, but this attempt does not prove sim-live wiring because it used an unsupported localization source and the ROS master was not live for passive topic checks.
- Next: rerun sim dry-run wiring with a live headless sim launch and a `localization.source` value of `lio` while keeping the simulated position coordinates. Confirm `publish_attempted=False`, `/goal` payload generation, and no action-topic messages under a live master.

- Time: 2026-04-30, sim dry-run wiring retry with live headless graph
- Server: remote Windows host, interactive Ubuntu-20.04 WSL2 shell as `uavdev`
- Command:
  ```bash
  cd ~/changxin-code
  source /opt/ros/noetic/setup.bash
  source ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner/devel/setup.bash

  ROS_LOG_DIR=~/uav-g3c-evidence/roslogs-g3c-20 \
  QT_QPA_PLATFORM=offscreen \
  roslaunch ~/uav-g3c-evidence/run_sim_single_headless.launch \
    > ~/uav-g3c-evidence/g3c-20-sim-dry-run-live-launch.log 2>&1 &
  LAUNCH_PID=$!

  sleep 15

  {
    date -Is
    echo "LAUNCH_PID=$LAUNCH_PID alive=$(kill -0 $LAUNCH_PID 2>/dev/null && echo yes || echo no)"
    rosnode list || true
  } | tee ~/uav-g3c-evidence/g3c-20b-sim-dry-run-live-launch-check.txt

  PYTHONPATH="$PWD:${PYTHONPATH:-}" python3 - <<'PY' \
    | tee ~/uav-g3c-evidence/g3c-21-sim-live-a-stage-dry-run-report-lio.txt
  from uav.llm_control.ros_adapters.dry_run import build_dry_run_report
  from uav.llm_control.schemas.models import BatterySnapshot, FcuSnapshot, LocalizationSnapshot, RcSnapshot, StateSnapshot

  snapshot = StateSnapshot(
      captured_at=100.0,
      fcu=FcuSnapshot(connected=True, armed=True, mode="OFFBOARD", updated_at=100.0),
      battery=BatterySnapshot(voltage=24.1, percentage=0.75, updated_at=100.0),
      rc=RcSnapshot(channels=[1000,1500,1500,1500,1000,1000,1800,1500], updated_at=100.0),
      localization=LocalizationSnapshot(
          source="lio",
          position={"x": -15.0, "y": 0.0, "z": 1.0},
          velocity={"x": 0.0, "y": 0.0, "z": 0.0},
          yaw=0.0,
          updated_at=100.0,
      ),
  )
  report = build_dry_run_report({
      "meta": {"request_id": "g3c-sim-live-dry-run-lio"},
      "intent": {"name": "move_relative"},
      "arguments": {"frame": "world", "direction": "forward", "distance_m": 1.0},
  }, snapshot, now=100.0).as_dict()

  print("status:", report["status"])
  print("publish_attempted:", report["publish_attempted"])
  print("target_position:", report["trace"][4]["target_position"])
  print("ros_payload_topic:", report["trace"][5]["topic"])
  print("ros_payload_type:", report["trace"][5]["message_type"])
  print("confirmation_gate:", report["trace"][6]["status"])
  PY

  for t in /goal /move_base_simple/goal /back_trigger /px4ctrl/takeoff_land /setpoints_cmd; do
    echo "===== $t ====="
    timeout 5s rostopic echo -n 1 "$t" || echo "NO_MESSAGE_WITHIN_5S"
  done | tee ~/uav-g3c-evidence/g3c-22-post-dry-run-action-topic-passive-echo-live.txt

  kill -INT "$LAUNCH_PID" 2>/dev/null || echo "already dead"
  wait "$LAUNCH_PID" 2>/dev/null || true
  ```
- Output:
  ```text
  g3c-20b at 2026-04-30T16:19:33+08:00:
  LAUNCH_PID=32600 alive=yes
  /drone_0_diff_planner_node
  /drone_0_manual_take_over
  /drone_0_odom_visualization
  /drone_0_pcl_render_node
  /drone_0_poscmd_2_odom
  /drone_0_traj_server
  /multipointplan
  /random_forest
  /rosout

  g3c-21:
  status: needs_confirmation
  publish_attempted: False
  target_position: {'x': -14.0, 'y': 0.0, 'z': 1.0}
  ros_payload_topic: /goal
  ros_payload_type: geometry_msgs/PoseStamped
  confirmation_gate: blocked_for_confirmation

  g3c-22 passive action-topic echo after dry-run report:
  /goal: NO_MESSAGE_WITHIN_5S
  /move_base_simple/goal: NO_MESSAGE_WITHIN_5S
  /back_trigger: NO_MESSAGE_WITHIN_5S
  /px4ctrl/takeoff_land: NO_MESSAGE_WITHIN_5S
  /setpoints_cmd: WARNING: topic [/setpoints_cmd] does not appear to be published yet; NO_MESSAGE_WITHIN_5S
  ```
- Verdict: G3_C_6_PASS_SIM_DRY_RUN_WIRING_NO_PUBLISH. While the headless sim graph was alive, the A-stage dry-run report generated a `/goal` `geometry_msgs/PoseStamped` payload for target `(-14.0, 0.0, 1.0)`, stopped at the confirmation gate, recorded `publish_attempted=False`, and emitted no messages on the action topics during passive observation.
- Next: close G3-C dry-run wiring. Any subsequent stage that would publish to `/goal`, `/move_base_simple/goal`, `/back_trigger`, `/px4ctrl/takeoff_land`, `/setpoints_cmd`, or MAVROS services must begin with a separately defined action-safety gate.

## Final Gate

- P0 Verdict: PASS_WITH_D_DRIVE_TARGET_AND_ROS_TLS_RISK. Windows 11, WSL and VirtualMachinePlatform are enabled, HypervisorPresent is true, D: has enough space, and ROS apt HTTP/key URLs are reachable. C: is too small for default WSL storage.
- P1 Verdict: PASS. Ubuntu-20.04 was imported on D:\WSL as WSL2 and verified as `Ubuntu 20.04.3 LTS` under `5.10.16.3-microsoft-standard-WSL2`; `uavdev` exists.
- P1.5 Verdict: PASS. Interactive WSL shell works, direct apt network works, and base packages `curl`, `gnupg`, `lsb-release`, `build-essential`, `git`, and `python3-pip` are installed.
- P2 Verdict: PASS. ROS Noetic desktop-full is installed; `roscore`, `rosnode`, `rostopic`, `rosmsg`, and standard message introspection work.
- P3 Verdict: PASS_FULL_CATKIN_BUILD_AND_NODE_VISIBILITY. Diff-planner snapshot is present in WSL; full `catkin_make -j8 -l8` completes; `quadrotor_msgs`, `diff_planner`, `multipoint`, `px4ctrl`, `vins`, and `faster_lio` resolve through `rospack`; `diff_planner_node`, `vins_node`, `run_mapping_online`, and `px4ctrl_node` executables are present.
- G3-B Verdict: PASS_BASELINE_READ_ONLY_WSL_DRY_RUN_LOCAL_AND_WSL_ADAPTER_TRACES. With only `roscore` running, baseline graph has `/rosout` and `/rosout_agg`; `/goal`, `/move_base_simple/goal`, `/back_trigger`, and `/px4ctrl/takeoff_land` are absent as expected; no action-topic publish occurred. WSL pure-Python `move_relative` dry-run produces a `/goal` payload with `publish_attempted=False`; local and WSL adapter traces record schema validation, state snapshot, safety policy, target point, ROS payload, and confirmation gate; the WSL 11-test A-stage suite passes after the full catkin build.
- G3-C Verdict: PASS_SIM_DRY_RUN_WIRING_NO_PUBLISH. The WSL package environment, launch files, static topic/control scan, target launch parsing, parameter dumps, roscore-only baseline, headless sim startup, 120-second passive observation, and A-stage dry-run wiring under a live sim graph all pass; the report produces a `/goal` payload while `publish_attempted=False`, and no action-topic messages are observed.
- A-stage Closure Decision: CLOSED_DRY_RUN_ONLY. Full WSL build, package/node visibility, WSL A-stage tests, and standalone WSL adapter trace all pass. The closed scope is dry-run only and does not authorize publishing motion/takeoff/land commands.
- G3-C Closure Decision: CLOSED_SIM_DRY_RUN_NO_PUBLISH. The closed scope covers build visibility, read-only launch analysis, headless sim observation, extended passive no-message checks, and dry-run report generation only. It does not authorize publishing movement, takeoff, land, return-home, MAVROS arming, MAVROS set_mode, or MAVROS setpoint commands.
- Next Stage Gate: READY_FOR_ACTION_SAFETY_GATE_DESIGN. Before any publish-capable work, define and verify an explicit action-safety gate with operator confirmation, mode/state checks, topic allowlists, timeout bounds, and sim-first rollback evidence.

## Action Safety Gate Design

- Time: 2026-04-30, local pure-Python action gate TDD implementation
- Server: local Codex worktree
- Files:
  ```text
  tests/uav_llm_control/test_action_safety_gate.py
  tests/uav_llm_control/test_pipeline.py
  uav/llm_control/safety/__init__.py
  uav/llm_control/safety/action_gate.py
  uav/llm_control/safety/profiles.py
  uav/llm_control/schemas/models.py
  uav/llm_control/core/pipeline.py
  docs/superpowers/specs/2026-04-30-uav-action-safety-gate-design.md
  ```
- Red test:
  ```bash
  python -m unittest tests.uav_llm_control.test_action_safety_gate
  ```
- Red output:
  ```text
  ModuleNotFoundError: No module named 'uav.llm_control.safety'
  FAILED (errors=1)
  ```
- Second red expansion:
  ```text
  ModuleNotFoundError: No module named 'uav.llm_control.safety.profiles'
  failed != needs_confirmation for sim localization before the A-to-B/C transition support was added
  ```
- Green commands:
  ```bash
  python -m unittest tests.uav_llm_control.test_action_safety_gate
  python -m unittest tests.uav_llm_control.test_pipeline tests.uav_llm_control.test_ros_adapter_dry_run tests.uav_llm_control.test_action_safety_gate
  ```
- Green output:
  ```text
  Ran 12 tests in 0.002s
  OK

  Ran 24 tests in 0.003s
  OK
  ```
- Gate design:
  ```text
  The action gate is side-effect free and never publishes. It evaluates an existing dry-run CommandResult plus StateSnapshot, ActionApproval, and requested timeout.
  It is profile-driven so A-stage can use sim evidence while B/C tighten the same API instead of replacing it.
  A-stage sim dry-run profile allows /goal, /move_base_simple/goal, /back_trigger, /px4ctrl/takeoff_land with sim/lio/vio localization, 1.0 m relative-goal limit, and 3.0 s timeout.
  B-stage bench profile allows /goal and /back_trigger with lio/vio only, 0.5 m relative-goal limit, and 2.0 s timeout.
  C-stage real profile allows only /goal with lio/vio only, 0.3 m relative-goal limit, and 1.0 s timeout.
  Tests cover the migration behavior directly: B accepts a return-home /back_trigger candidate while C rejects it, and C rejects the takeoff/land /px4ctrl/takeoff_land surface.
  It rejects /setpoints_cmd and MAVROS service-level actions by allowlist exclusion.
  It requires command status needs_confirmation, no prior publish attempt, a ROS payload, fresh FCU/battery/RC/localization snapshots, FCU connected, FCU mode OFFBOARD, a profile-allowed localization source, a non-expired exact confirmation phrase, operator id, sim evidence id, rollback plan id, action summary, bounded execution timeout, target Z within [0.5, 3.0] meters, and relative goal distance within the profile bound.
  It returns allowed/reasons/topic/message_type/audit and publish_attempted=False.
  ```
- Verdict: ACTION_GATE_DESIGN_PASS_LOCAL_TDD_PROFILED. The first publish-capable boundary now has a tested pure-Python evaluator and explicit A/B/C stage profiles. A-stage can be exercised with sim localization, while B/C reject sim and shrink the command surface. There is still no publisher implementation and no authorization to emit ROS action messages.
- Next: sync this module into WSL, run the same unit tests there after sourcing the Diff-planner workspace, and run a sim-live A-profile gate evaluation that proves an allowed decision still does not publish. B/C work must switch to the stricter profiles before bench or real-aircraft use.

## G3-D Live-Sim Action Gate Preparation

- Time: 2026-04-30, local pure-Python G3-D adapter and WSL evidence script preparation
- Server: local Codex worktree
- Files:
  ```text
  tests/uav_llm_control/test_action_gate_dry_run_adapter.py
  tests/uav_llm_control/test_python38_compat.py
  uav/llm_control/ros_adapters/action_gate_dry_run.py
  uav/01-scripts/g3d_live_action_gate_check.py
  docs/superpowers/specs/2026-04-30-uav-action-safety-gate-design.md
  ```
- Red test:
  ```bash
  python -m unittest tests.uav_llm_control.test_action_gate_dry_run_adapter
  ```
- Red output:
  ```text
  ModuleNotFoundError: No module named 'uav.llm_control.ros_adapters.action_gate_dry_run'
  FAILED (errors=1)
  ```
- WSL compatibility red expansion:
  ```bash
  python -m unittest tests.uav_llm_control.test_python38_compat
  ```
- Compatibility red output:
  ```text
  Python 3.10-only type union syntax detected in WSL runtime files.
  ```
- Green commands:
  ```bash
  python -m unittest tests.uav_llm_control.test_python38_compat tests.uav_llm_control.test_action_gate_dry_run_adapter
  python -m unittest tests.uav_llm_control.test_pipeline tests.uav_llm_control.test_ros_adapter_dry_run tests.uav_llm_control.test_action_safety_gate tests.uav_llm_control.test_action_gate_dry_run_adapter tests.uav_llm_control.test_python38_compat
  python -m py_compile uav/01-scripts/g3d_live_action_gate_check.py uav/llm_control/ros_adapters/action_gate_dry_run.py uav/llm_control/safety/action_gate.py
  python uav/01-scripts/g3d_live_action_gate_check.py --help
  python -m unittest discover
  ```
- Green output:
  ```text
  Ran 4 tests in 0.007s
  OK

  Ran 28 tests in 0.010s
  OK

  Ran 36 tests in 10.617s
  OK

  g3d_live_action_gate_check.py --help prints usage and confirms: This script never publishes ROS topics.
  ```
- G3-D design:
  ```text
  action_gate_dry_run builds a stable JSON report from the existing dry-run compiler plus the profiled safety gate.
  g3d_live_action_gate_check.py is intended to run while the headless sim launch is alive. It captures rosnode list, rostopic list -v, an A-profile gate report, and passive rostopic echo checks for /goal, /move_base_simple/goal, /back_trigger, /px4ctrl/takeoff_land, and /setpoints_cmd.
  It exits nonzero if ROS master is unavailable, if the A-profile gate does not allow the dry-run candidate, or if passive echo receives any action-topic message.
  It never calls rospy.Publisher, rostopic pub, MAVROS services, arming, set_mode, or setpoints.
  ```
- Verdict: G3D_SCRIPT_READY_LOCAL_TDD_NO_PUBLISH. The next WSL action is a live-sim evidence run, not a publisher implementation.

## G3-D Live-Sim Action Gate Evidence

- Time: 2026-05-06T15:57:42+08:00, WSL2 Ubuntu 20.04 / ROS Noetic live headless sim
- Server: `LAPTOP-JC`
- Workspace:
  ```text
  ~/changxin-code
  ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner
  ```
- Sync evidence:
  ```text
  g3d-sync-postcheck.txt:
  all 15 target files OK

  g3d-sync-python-tests.txt:
  Ran 28 tests in 0.009s
  OK
  ```
- Launch check:
  ```text
  2026-05-06T15:57:42+08:00
  LAUNCH_PID=127 alive=yes
  /drone_0_diff_planner_node
  /drone_0_manual_take_over
  /drone_0_odom_visualization
  /drone_0_pcl_render_node
  /drone_0_poscmd_2_odom
  /drone_0_traj_server
  /multipointplan
  /random_forest
  /rosout
  ```
- Gate summary:
  ```text
  profile: a-stage-sim-dry-run
  request_id: g3d-live-a-profile-gate
  ros_graph_ok: True
  gate_status: gate_allowed
  gate_allowed: True
  publish_attempted: False
  topic: /goal
  message_type: geometry_msgs/PoseStamped
  reasons: []
  target_position: {'x': -14.0, 'y': 0.0, 'z': 1.0}
  action_topic_message_received: False
  ```
- Passive action-topic echo:
  ```text
  ===== /goal =====
  NO_MESSAGE_WITHIN_5S
  ===== /move_base_simple/goal =====
  NO_MESSAGE_WITHIN_5S
  ===== /back_trigger =====
  NO_MESSAGE_WITHIN_5S
  ===== /px4ctrl/takeoff_land =====
  NO_MESSAGE_WITHIN_5S
  ===== /setpoints_cmd =====
  NO_MESSAGE_WITHIN_5S
  ```
- Verdict: G3D_PASS_LIVE_SIM_ACTION_GATE_NO_PUBLISH. Under a live headless sim graph, the A-stage profile action gate allowed a dry-run `/goal` candidate for target `(-14.0, 0.0, 1.0)` while `publish_attempted=False`; no messages were observed on `/goal`, `/move_base_simple/goal`, `/back_trigger`, `/px4ctrl/takeoff_land`, or `/setpoints_cmd`.
- Closure Decision: CLOSED_G3D_LIVE_SIM_GATE_NO_PUBLISH. This closes the gate-evaluation stage only. It does not authorize a publisher, motion execution, takeoff, land, return-home, MAVROS arming, MAVROS set_mode, or MAVROS setpoint commands.
- Next Stage Gate: READY_FOR_B_STAGE_PROFILE_BENCH_PRECHECK. Before any publisher implementation, run B-profile bench prechecks with real `lio` or `vio` localization inputs, explicit rollback plan, topic graph verification, and operator approval path still side-effect free.

## B-Stage Bench Profile Precheck Preparation

- Time: 2026-05-06, local pure-Python B-stage precheck adapter and WSL evidence script preparation
- Server: local Codex worktree
- Files:
  ```text
  tests/uav_llm_control/test_bench_precheck.py
  tests/uav_llm_control/test_python38_compat.py
  uav/llm_control/ros_adapters/bench_precheck.py
  uav/01-scripts/g3e_bench_profile_precheck.py
  docs/superpowers/specs/2026-04-30-uav-action-safety-gate-design.md
  ```
- Red tests:
  ```bash
  python -m unittest tests.uav_llm_control.test_bench_precheck
  python -m unittest tests.uav_llm_control.test_python38_compat
  ```
- Red output:
  ```text
  ModuleNotFoundError: No module named 'uav.llm_control.ros_adapters.bench_precheck'
  ImportError: cannot import name 'graph_snapshot_from_ros_cli'
  FileNotFoundError: uav/01-scripts/g3e_bench_profile_precheck.py
  ```
- Green commands:
  ```bash
  python -m unittest tests.uav_llm_control.test_python38_compat tests.uav_llm_control.test_bench_precheck
  python -m unittest tests.uav_llm_control.test_pipeline tests.uav_llm_control.test_ros_adapter_dry_run tests.uav_llm_control.test_action_safety_gate tests.uav_llm_control.test_action_gate_dry_run_adapter tests.uav_llm_control.test_bench_precheck tests.uav_llm_control.test_python38_compat
  python -m py_compile uav/01-scripts/g3e_bench_profile_precheck.py uav/llm_control/ros_adapters/bench_precheck.py
  python uav/01-scripts/g3e_bench_profile_precheck.py --help
  python -m unittest discover
  ```
- Green output:
  ```text
  Ran 5 tests in 0.009s
  OK

  Ran 31 tests in 0.019s
  OK

  Ran 39 tests in 11.168s
  OK

  g3e_bench_profile_precheck.py --help prints usage and confirms: This script never publishes ROS topics.
  ```
- B-stage design:
  ```text
  bench_precheck builds a B-profile report from an existing dry-run candidate, lio/vio StateSnapshot, required ROS graph nodes/subscribers, and passive action-topic echo status.
  It requires /drone_0_diff_planner_node, /drone_0_traj_server, /rosout, and subscribers on /goal and /back_trigger by default.
  It uses b-stage-bench limits: lio/vio only, /goal and /back_trigger only, 0.5 m max relative goal, and 2.0 s max timeout.
  g3e_bench_profile_precheck.py captures rosnode list, rostopic list -v, passively echoes /goal, /move_base_simple/goal, /back_trigger, /px4ctrl/takeoff_land, and /setpoints_cmd, then writes a JSON precheck report and summary.
  It never calls rospy.Publisher, rostopic pub, MAVROS services, arming, set_mode, or setpoints.
  ```
- Verdict: B_STAGE_BENCH_PRECHECK_SCRIPT_READY_LOCAL_TDD_NO_PUBLISH. The next WSL action is a B-profile bench precheck run against an already alive LIO/VIO graph, not a publisher implementation.

## G3-E B-Stage Profile Sim Rehearsal Evidence

- Time: 2026-05-06T16:49:08+08:00, WSL2 Ubuntu 20.04 / ROS Noetic live headless sim
- Server: `LAPTOP-JC`
- Scope: B-stage profile rehearsal on the already validated headless sim graph. This is not a real bench clearance and does not authorize a publisher. It proves that the B-stage script path can evaluate a stricter `lio` profile, inspect the live ROS graph, and remain side-effect free.
- Workspace:
  ```text
  ~/changxin-code
  ~/changxin-code-sync
  ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner
  ```
- GitHub sync check:
  ```text
  cd ~/changxin-code-sync
  git pull --ff-only
  Already up to date.

  rsync -avnc ~/changxin-code-sync/uav/llm_control/ ~/changxin-code/uav/llm_control/
  rsync -avnc ~/changxin-code-sync/tests/uav_llm_control/ ~/changxin-code/tests/uav_llm_control/
  rsync -avnc ~/changxin-code-sync/uav/01-scripts/ ~/changxin-code/uav/01-scripts/
  rsync -avnc ~/changxin-code-sync/docs/superpowers/ ~/changxin-code/docs/superpowers/

  All four dry-run rsync checks listed no file changes.
  ```
- Launch check:
  ```text
  2026-05-06T16:49:08+08:00
  LAUNCH_PID=652 alive=yes

  /drone_0_diff_planner_node
  /drone_0_manual_take_over
  /drone_0_odom_visualization
  /drone_0_pcl_render_node
  /drone_0_poscmd_2_odom
  /drone_0_traj_server
  /multipointplan
  /random_forest
  /rosout
  ```
- Command:
  ```bash
  PYTHONPATH="$PWD:${PYTHONPATH:-}" \
  python3 uav/01-scripts/g3e_bench_profile_precheck.py \
    --evidence-dir ~/uav-g3e-evidence \
    --request-id g3e-b-stage-sim-rehearsal \
    --source lio \
    --x -15.0 \
    --y 0.0 \
    --z 1.0 \
    --distance-m 0.3 \
    --requested-timeout-s 1.5 \
    --echo-timeout-s 5
  ```
- Summary:
  ```text
  profile: b-stage-bench
  request_id: g3e-b-stage-sim-rehearsal
  ros_graph_ok: True
  bench_status: bench_precheck_passed
  graph_ok: True
  gate_allowed: True
  publish_attempted: False
  action_topic_message_received: False
  missing_nodes: []
  missing_subscribed_topics: []
  topic: /goal
  message_type: geometry_msgs/PoseStamped
  reasons: []
  target_position: {'x': -14.7, 'y': 0.0, 'z': 1.0}
  localization_source: lio
  ```
- Passive action-topic echo:
  ```text
  ===== /goal =====
  NO_MESSAGE_WITHIN_5S
  ===== /move_base_simple/goal =====
  NO_MESSAGE_WITHIN_5S
  ===== /back_trigger =====
  NO_MESSAGE_WITHIN_5S
  ===== /px4ctrl/takeoff_land =====
  NO_MESSAGE_WITHIN_5S
  ===== /setpoints_cmd =====
  NO_MESSAGE_WITHIN_5S
  ```
- Verdict: G3E_PASS_B_STAGE_PROFILE_SIM_REHEARSAL_NO_PUBLISH. The B-stage precheck path passed against a live headless sim graph with a `lio` localization source, required planner nodes present, `/goal` and `/back_trigger` subscribed, gate allowed for a 0.3 m `/goal` candidate, `publish_attempted=False`, and no observed action-topic messages.
- Boundary: This rehearsal does not prove real LIO/VIO sensor health, PX4/MAVROS bench readiness, actuator safety, or radio/RC interlock behavior. Real B-stage entry still requires the same script against an already alive bench graph with actual `lio` or `vio` localization inputs and an operator-approved rollback path.
- Next Stage Gate: READY_FOR_REAL_BENCH_READ_ONLY_PRECHECK. The next permitted work is still read-only: launch the bench LIO/VIO graph, run `g3e_bench_profile_precheck.py` with the real localization source, and capture graph/echo evidence. Publisher implementation remains blocked.
