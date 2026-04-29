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
- Time:
- Server:
- Command:
- Output:
- Verdict:
- Next:

### P1.2 Ubuntu-20.04 WSL2 Verification
- Time:
- Server:
- Command:
- Output:
- Verdict:
- Next:

## P1.5 Ubuntu Proxy And Base Packages

### P1.5.1 Ubuntu Version And Proxy
- Time:
- Server:
- Command:
- Output:
- Verdict:
- Next:

### P1.5.2 apt Update And Base Packages
- Time:
- Server:
- Command:
- Output:
- Verdict:
- Next:

## P2 ROS Noetic

### P2.1 ROS Noetic Install
- Time:
- Server:
- Command:
- Output:
- Verdict:
- Next:

### P2.2 ROS Core Verification
- Time:
- Server:
- Command:
- Output:
- Verdict:
- Next:

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
