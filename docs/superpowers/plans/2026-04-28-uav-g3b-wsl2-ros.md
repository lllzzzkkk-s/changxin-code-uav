# UAV G3-B WSL2 ROS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify a remote Windows Server + WSL2 Ubuntu 20.04 + ROS Noetic baseline for UAV G3-B ROS graph observation without publishing any real action topics.

**Architecture:** Treat the remote server setup as gated infrastructure work: P0 validates Windows/proxy/virtualization, P1 installs WSL2 Ubuntu, P2 installs ROS Noetic, P3 validates Diff-planner build and message visibility, and G3-B records ROS graph evidence. Every stage writes evidence before moving to the next gate, and action-topic publish commands remain forbidden throughout this plan.

**Tech Stack:** Windows Server, Administrator PowerShell, WSL2, Ubuntu 20.04, ROS Noetic, catkin, Diff-planner, Markdown evidence logs, git.

---

## Scope Check

This plan implements one subsystem: the G3-B remote WSL2 ROS environment and read-only ROS graph validation path. It does not implement G3-C, does not connect a real flight controller, does not publish `/goal`, `/back_trigger`, `/px4ctrl/takeoff_land`, or `/setpoints_cmd`, and does not merge the separate `uav/llm_control` service-layer worktree.

## File Structure

- Create: `docs/superpowers/evidence/2026-04-28-uav-g3b-wsl2-ros-evidence.md`
  - Responsibility: durable execution log for P0/P1/P2/P3/G3-B command outputs, verdicts, and next steps.
- Read: `docs/superpowers/specs/2026-04-28-uav-g3b-wsl2-ros-design.md`
  - Responsibility: approved design and safety boundary for this plan.
- Read: `uav/20-dev-docs/01-developer-guide.md`
  - Responsibility: source of the current UAV environment baseline, ROS topics, and Diff-planner entrypoints.
- Remote Windows path: `C:\uav-g3b`
  - Responsibility: temporary working folder on the Windows Server for text outputs copied from PowerShell.
- Remote WSL path: `~/changxin-code`
  - Responsibility: Ubuntu-side repository or Diff-planner workspace location for P3/G3-B checks.

## Safety Rules For Every Task

- Never run `rostopic pub /px4ctrl/takeoff_land ...`.
- Never run `rostopic pub /back_trigger ...`.
- Never run `rostopic pub /goal ...`.
- Never run `rostopic pub /setpoints_cmd ...`.
- If a command fails, record the exact command, output, verdict, and next branch in the evidence file before retrying or changing approach.
- Do not write proxy usernames, proxy passwords, server passwords, or host-specific secrets into the repository.

### Task 1: Create Evidence Log

**Files:**
- Create: `docs/superpowers/evidence/2026-04-28-uav-g3b-wsl2-ros-evidence.md`

- [ ] **Step 1: Create the evidence directory and file**

Run from repo root:

```bash
mkdir -p docs/superpowers/evidence
cat > docs/superpowers/evidence/2026-04-28-uav-g3b-wsl2-ros-evidence.md <<'EOF'
# UAV G3-B WSL2 ROS Evidence

Date: 2026-04-28
Spec: docs/superpowers/specs/2026-04-28-uav-g3b-wsl2-ros-design.md
Safety boundary: read-only ROS graph observation only. No action-topic publish is allowed in this evidence run.

## P0 Windows/Proxy

### P0.1 Windows Version, Virtualization, Disk, WSL Status
- Time:
- Server:
- Command:
- Output:
- Verdict:
- Next:

### P0.2 PowerShell Proxy Download Check
- Time:
- Server:
- Command:
- Output:
- Verdict:
- Next:

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
EOF
```

- [ ] **Step 2: Verify the evidence sections exist**

Run:

```bash
rg -n "P0 Windows/Proxy|P1 WSL2 Ubuntu|P2 ROS Noetic|P3 Diff-planner|G3-B ROS Graph|Final Gate" docs/superpowers/evidence/2026-04-28-uav-g3b-wsl2-ros-evidence.md
```

Expected: output contains all six section names.

- [ ] **Step 3: Commit the evidence template**

Run:

```bash
git add docs/superpowers/evidence/2026-04-28-uav-g3b-wsl2-ros-evidence.md
git commit -m "docs: add UAV G3-B evidence log"
```

Expected: commit succeeds with one new evidence file.

### Task 2: Run P0 Windows And Proxy Self-check

**Files:**
- Modify: `docs/superpowers/evidence/2026-04-28-uav-g3b-wsl2-ros-evidence.md`

- [ ] **Step 1: Open Administrator PowerShell on the remote server**

Use RDP to log into the Windows Server. Open PowerShell as Administrator.

Run:

```powershell
whoami /groups | findstr /i "S-1-5-32-544"
```

Expected: output includes the local Administrators group SID `S-1-5-32-544`. If it does not, stop and record `权限不足，不能继续 P0` in the evidence file.

- [ ] **Step 2: Create the Windows working directory**

Run:

```powershell
New-Item -ItemType Directory -Force C:\uav-g3b | Out-Null
Set-Location C:\uav-g3b
```

Expected: no error; current directory is `C:\uav-g3b`.

- [ ] **Step 3: Run read-only system checks**

Run:

```powershell
Get-ComputerInfo | Select-Object OsName, OsVersion, WindowsVersion, OsBuildNumber, CsSystemType | Format-List | Tee-Object -FilePath C:\uav-g3b\p0-system.txt
systeminfo | findstr /i "Virtualization Hyper-V" | Tee-Object -FilePath C:\uav-g3b\p0-virtualization.txt
Get-PSDrive C | Format-List | Tee-Object -FilePath C:\uav-g3b\p0-disk.txt
wsl --status 2>&1 | Tee-Object -FilePath C:\uav-g3b\p0-wsl-status.txt
wsl -l -v 2>&1 | Tee-Object -FilePath C:\uav-g3b\p0-wsl-list.txt
netsh winhttp show proxy | Tee-Object -FilePath C:\uav-g3b\p0-winhttp-proxy.txt
```

Expected:
- `p0-system.txt` shows Windows Server version and build.
- `p0-disk.txt` shows at least 80GB free on the target drive.
- `wsl --status` either succeeds or reports WSL is not installed; both are valid P0 evidence.

- [ ] **Step 4: Set temporary proxy variables without writing secrets to disk**

Run:

```powershell
$env:UAV_PROXY_URL = Read-Host "Enter HTTP proxy URL with scheme"
$env:UAV_WINHTTP_PROXY = Read-Host "Enter WinHTTP proxy host and port"
$env:HTTP_PROXY = $env:UAV_PROXY_URL
$env:HTTPS_PROXY = $env:UAV_PROXY_URL
```

Expected: variables are set in the current PowerShell session only.

- [ ] **Step 5: Run proxy download checks**

Run:

```powershell
Invoke-WebRequest https://aka.ms/wslstorepage -UseBasicParsing -TimeoutSec 30 | Select-Object StatusCode, StatusDescription | Tee-Object -FilePath C:\uav-g3b\p0-wsl-download-check.txt
Invoke-WebRequest https://packages.ros.org -UseBasicParsing -TimeoutSec 30 | Select-Object StatusCode, StatusDescription | Tee-Object -FilePath C:\uav-g3b\p0-ros-download-check.txt
```

Expected: both commands return a status code instead of a proxy, DNS, TLS, or timeout error. HTTP `200`, `301`, `302`, or `403` are acceptable P0 evidence because they prove network reachability.

- [ ] **Step 6: Update evidence and commit**

Copy the contents of `C:\uav-g3b\p0-*.txt` into `P0.1` and `P0.2` in the evidence file.

Verdict rules:
- `PASS` if admin rights are present, disk is sufficient, virtualization is available or can be enabled, and both download checks reach the remote hosts.
- `BLOCKED_PROXY` if download checks fail through the configured proxy.
- `BLOCKED_VIRTUALIZATION` if virtualization is unavailable.
- `BLOCKED_PERMISSION` if admin rights are absent.

Run from repo root after updating the evidence file:

```bash
git add docs/superpowers/evidence/2026-04-28-uav-g3b-wsl2-ros-evidence.md
git commit -m "docs: record UAV G3-B P0 evidence"
```

Expected: commit succeeds with only the evidence file changed.

### Task 3: Install And Verify WSL2 Ubuntu 20.04 On D Drive

**Files:**
- Modify: `docs/superpowers/evidence/2026-04-28-uav-g3b-wsl2-ros-evidence.md`

- [ ] **Step 1: Create D-drive WSL directories**

Run in Administrator PowerShell:

```powershell
New-Item -ItemType Directory -Force D:\WSL\Downloads | Out-Null
New-Item -ItemType Directory -Force D:\WSL\Ubuntu-20.04 | Out-Null
Get-CimInstance Win32_LogicalDisk | ForEach-Object { "DeviceID=$($_.DeviceID) SizeGB=$([math]::Round($_.Size/1GB,2)) FreeGB=$([math]::Round($_.FreeSpace/1GB,2))" } | Tee-Object -FilePath C:\uav-g3b\p1-disk-target.txt
```

Expected: `D:` exists and has at least 80GB free. Do not continue if `D:` is missing or below 80GB free.

- [ ] **Step 2: Download or update the WSL2 kernel package**

Run:

```powershell
$WslKernelMsiUrl = "https://wslstorestorage.blob.core.windows.net/wslblob/wsl_update_x64.msi"
Invoke-WebRequest $WslKernelMsiUrl -UseBasicParsing -OutFile D:\WSL\Downloads\wsl_update_x64.msi
Get-Item D:\WSL\Downloads\wsl_update_x64.msi | Select-Object FullName,Length | Format-List | Tee-Object -FilePath C:\uav-g3b\p1-wsl-kernel-msi-download.txt
msiexec.exe /i D:\WSL\Downloads\wsl_update_x64.msi /quiet /norestart
wsl --set-default-version 2 2>&1 | Tee-Object -FilePath C:\uav-g3b\p1-default-version.txt
```

Expected: MSI file length is about 17MB, MSI install returns to the prompt with no fatal error, and `wsl --set-default-version 2` does not fail. If the MSI requests a restart, restart before continuing. Do not use `https://aka.ms/wsl2kernel` as an `-OutFile` MSI target because it can resolve to the Microsoft Learn HTML page rather than the MSI binary.

- [ ] **Step 3: Download Ubuntu 20.04 AppxBundle**

Run:

```powershell
$UbuntuAppxUrl = "https://aka.ms/wslubuntu2004"
Invoke-WebRequest $UbuntuAppxUrl -UseBasicParsing -OutFile D:\WSL\Downloads\Ubuntu2004.AppxBundle
Get-Item D:\WSL\Downloads\Ubuntu2004.AppxBundle | Select-Object FullName,Length | Format-List | Tee-Object -FilePath C:\uav-g3b\p1-ubuntu-appxbundle-download.txt
```

Expected: downloaded file exists and is roughly 900MB. If this URL is blocked, stop and record `BLOCKED_UBUNTU_APPXBUNDLE_DOWNLOAD`.

- [ ] **Step 4: Extract install.tar.gz from the AppxBundle**

Run:

```powershell
Remove-Item -Recurse -Force D:\WSL\Downloads\Ubuntu2004Bundle,D:\WSL\Downloads\Ubuntu2004Appx -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force D:\WSL\Downloads\Ubuntu2004Bundle,D:\WSL\Downloads\Ubuntu2004Appx | Out-Null
tar.exe -xf D:\WSL\Downloads\Ubuntu2004.AppxBundle -C D:\WSL\Downloads\Ubuntu2004Bundle
$Appx = Get-ChildItem D:\WSL\Downloads\Ubuntu2004Bundle -Recurse -Filter "*x64.appx" | Select-Object -First 1
if (-not $Appx) { throw "No x64 appx found in Ubuntu2004.AppxBundle" }
tar.exe -xf $Appx.FullName -C D:\WSL\Downloads\Ubuntu2004Appx
$Rootfs = Get-ChildItem D:\WSL\Downloads\Ubuntu2004Appx -Recurse -Filter "install.tar.gz" | Select-Object -First 1
if (-not $Rootfs) { throw "No install.tar.gz found in Ubuntu2004 x64 appx" }
Copy-Item $Rootfs.FullName D:\WSL\Downloads\ubuntu-20.04-install.tar.gz -Force
Get-Item D:\WSL\Downloads\ubuntu-20.04-install.tar.gz | Select-Object FullName,Length | Format-List | Tee-Object -FilePath C:\uav-g3b\p1-ubuntu-rootfs-extract.txt
```

Expected: `D:\WSL\Downloads\ubuntu-20.04-install.tar.gz` exists and is several hundred MB.

- [ ] **Step 5: Import Ubuntu 20.04 into D:\WSL**

Run:

```powershell
wsl --import Ubuntu-20.04 D:\WSL\Ubuntu-20.04 D:\WSL\Downloads\ubuntu-20.04-install.tar.gz --version 2 2>&1 | Tee-Object -FilePath C:\uav-g3b\p1-ubuntu-import.txt
wsl -l -v 2>&1 | Tee-Object -FilePath C:\uav-g3b\p1-wsl-list-after-install.txt
```

Expected: `wsl -l -v` lists `Ubuntu-20.04` with `VERSION` equal to `2`.

- [ ] **Step 6: Start Ubuntu, create a normal user, and verify release**

Run:

```powershell
wsl -d Ubuntu-20.04 -- bash -lc "cat /etc/os-release && uname -a" 2>&1 | Tee-Object -FilePath C:\uav-g3b\p1-ubuntu-version.txt
wsl -d Ubuntu-20.04 -- bash -lc "id -u uavdev >/dev/null 2>&1 || (useradd -m -s /bin/bash uavdev && usermod -aG sudo uavdev && echo 'uavdev ALL=(ALL) NOPASSWD:ALL' >/etc/sudoers.d/90-uavdev && chmod 440 /etc/sudoers.d/90-uavdev)"
wsl -d Ubuntu-20.04 --user uavdev -- bash -lc "whoami && pwd && cat /etc/os-release" 2>&1 | Tee-Object -FilePath C:\uav-g3b\p1-ubuntu-user.txt
```

Expected: `/etc/os-release` contains `VERSION_ID="20.04"` and `whoami` prints `uavdev`.

- [ ] **Step 7: Update evidence and commit**

Copy `C:\uav-g3b\p1-*.txt` into the `P1` sections in the evidence file.

Verdict rules:
- `PASS` if `Ubuntu-20.04` exists, is WSL2, and reports Ubuntu 20.04.
- `BLOCKED_INSTALL` if Ubuntu cannot be installed after primary and manual paths.
- `BLOCKED_VIRTUALIZATION` if WSL2 conversion fails due to virtualization.

Run:

```bash
git add docs/superpowers/evidence/2026-04-28-uav-g3b-wsl2-ros-evidence.md
git commit -m "docs: record UAV G3-B P1 evidence"
```

Expected: commit succeeds with only the evidence file changed.

### Task 4: Configure Ubuntu Network And Base Packages

**Files:**
- Modify: `docs/superpowers/evidence/2026-04-28-uav-g3b-wsl2-ros-evidence.md`

- [ ] **Step 1: Verify Ubuntu network context and remove stale apt proxy**

Run in Ubuntu as `uavdev`:

```bash
mkdir -p ~/uav-g3b-evidence
sudo rm -f /etc/apt/apt.conf.d/95proxies
{
  date -Is
  cat /etc/os-release
  uname -a
  env | grep -E '^(http_proxy|https_proxy)=' | sed 's#://.*@#://***:***@#' || true
  ls -l /etc/apt/apt.conf.d/95proxies 2>/dev/null || true
} | tee ~/uav-g3b-evidence/p15-ubuntu-network.txt
```

Expected: Ubuntu is 20.04 and no stale apt proxy file remains unless a proxy is intentionally required.

- [ ] **Step 2: Verify apt reachability with direct network**

Run:

```bash
sudo apt update 2>&1 | tee ~/uav-g3b-evidence/p15-apt-update.txt
```

Expected: `apt update` finishes with package index output and no fatal DNS, TLS, or proxy error.

If direct apt fails because a network proxy is required, run this fallback and retry `sudo apt update`:

```bash
read -r -s -p "Proxy URL with scheme: " UAV_PROXY_URL
printf '\n'
export http_proxy="$UAV_PROXY_URL"
export https_proxy="$UAV_PROXY_URL"
sudo tee /etc/apt/apt.conf.d/95proxies >/dev/null <<EOF
Acquire::http::Proxy "$UAV_PROXY_URL";
Acquire::https::Proxy "$UAV_PROXY_URL";
EOF
sudo chmod 600 /etc/apt/apt.conf.d/95proxies
sudo apt update 2>&1 | tee ~/uav-g3b-evidence/p15-apt-update-proxy-retry.txt
```

Expected: retry succeeds. Do not copy proxy credentials into the repo evidence file.

- [ ] **Step 3: Install base packages**

Run:

```bash
sudo apt install -y curl gnupg lsb-release build-essential git python3-pip 2>&1 | tee ~/uav-g3b-evidence/p15-base-packages.txt
```

Expected: package installation completes with no `E: Unable to locate package` or fatal network error.

- [ ] **Step 4: Update evidence and commit**

Copy sanitized outputs from `~/uav-g3b-evidence/p15-*.txt` into `P1.5` in the evidence file.

Verdict rules:
- `PASS` if Ubuntu is 20.04, apt update works, and base packages install.
- `BLOCKED_APT_NETWORK` if apt cannot reach repositories directly or through proxy fallback.
- `BLOCKED_DNS` if name resolution fails inside WSL.

Run:

```bash
git add docs/superpowers/evidence/2026-04-28-uav-g3b-wsl2-ros-evidence.md
git commit -m "docs: record UAV G3-B P1.5 evidence"
```

Expected: commit succeeds with only the evidence file changed.

### Task 5: Install And Verify ROS Noetic

**Files:**
- Modify: `docs/superpowers/evidence/2026-04-28-uav-g3b-wsl2-ros-evidence.md`

- [ ] **Step 1: Add ROS Noetic apt source**

Run in Ubuntu:

```bash
source /etc/os-release
test "$VERSION_ID" = "20.04"
sudo sh -c 'echo "deb http://packages.ros.org/ros/ubuntu $(lsb_release -sc) main" > /etc/apt/sources.list.d/ros-latest.list'
curl -s https://raw.githubusercontent.com/ros/rosdistro/master/ros.asc | sudo apt-key add - 2>&1 | tee ~/uav-g3b-evidence/p2-ros-key.txt
sudo apt update 2>&1 | tee ~/uav-g3b-evidence/p2-ros-apt-update.txt
```

Expected: `test "$VERSION_ID" = "20.04"` succeeds; `apt update` includes ROS package lists.

- [ ] **Step 2: Install ROS Noetic packages**

Run:

```bash
sudo apt install -y ros-noetic-desktop-full python3-rosdep python3-rosinstall python3-rosinstall-generator python3-wstool python3-catkin-tools 2>&1 | tee ~/uav-g3b-evidence/p2-ros-install.txt
```

Expected: installation completes successfully. The command may take a long time; do not interrupt unless it is clearly blocked on proxy authentication.

- [ ] **Step 3: Initialize ROS environment**

Run:

```bash
sudo rosdep init 2>&1 | tee ~/uav-g3b-evidence/p2-rosdep-init.txt || true
rosdep update 2>&1 | tee ~/uav-g3b-evidence/p2-rosdep-update.txt || true
grep -qxF 'source /opt/ros/noetic/setup.bash' ~/.bashrc || echo 'source /opt/ros/noetic/setup.bash' >> ~/.bashrc
source /opt/ros/noetic/setup.bash
test -f /opt/ros/noetic/setup.bash
```

Expected: `/opt/ros/noetic/setup.bash` exists. `rosdep update` failure is recorded as a P3 dependency risk, not as a P2 blocker if ROS core commands work.

- [ ] **Step 4: Verify roscore and message tools**

Terminal A:

```bash
source /opt/ros/noetic/setup.bash
roscore 2>&1 | tee ~/uav-g3b-evidence/p2-roscore.txt
```

Expected: output includes `started core service [/rosout]`.

Terminal B:

```bash
source /opt/ros/noetic/setup.bash
{
  rostopic list
  rosmsg show geometry_msgs/PoseStamped
} 2>&1 | tee ~/uav-g3b-evidence/p2-ros-tools.txt
```

Expected: `rostopic list` includes `/rosout`; `rosmsg show geometry_msgs/PoseStamped` prints header and pose fields.

- [ ] **Step 5: Update evidence and commit**

Copy `~/uav-g3b-evidence/p2-*.txt` into the `P2` sections in the evidence file. Stop `roscore` with `Ctrl-C` after capturing evidence.

Verdict rules:
- `PASS` if ROS Noetic installs and `roscore`, `rostopic`, and `rosmsg` work.
- `PASS_WITH_ROSDEP_RISK` if only `rosdep update` fails.
- `BLOCKED_ROS_APT` if ROS packages cannot install.

Run:

```bash
git add docs/superpowers/evidence/2026-04-28-uav-g3b-wsl2-ros-evidence.md
git commit -m "docs: record UAV G3-B P2 evidence"
```

Expected: commit succeeds with only the evidence file changed.

### Task 6: Sync Diff-planner And Verify Core Interfaces

**Files:**
- Modify: `docs/superpowers/evidence/2026-04-28-uav-g3b-wsl2-ros-evidence.md`

- [ ] **Step 1: Place repository or Diff-planner snapshot in WSL**

Use one of these two fixed layouts:

Preferred full repo layout:

```bash
mkdir -p ~/changxin-code
cd ~/changxin-code
test -d uav/03-drone-code/snapshot_20260421_174511/Diff-planner
```

Standalone Diff-planner layout:

```bash
mkdir -p ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511
test -d ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner
```

Expected: one command path succeeds and points to the Diff-planner root. If neither path exists, copy the repository or Diff-planner snapshot into the preferred full repo layout before continuing.

- [ ] **Step 2: Build Diff-planner workspace**

Run:

```bash
source /opt/ros/noetic/setup.bash
cd ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner
catkin_make 2>&1 | tee ~/uav-g3b-evidence/p3-catkin-make.txt
```

Expected: full build succeeds, or failure output identifies missing sensor/GPU/dependency packages.

- [ ] **Step 3: If full build fails, record and try core message visibility**

Run this step only when `catkin_make` fails:

```bash
source /opt/ros/noetic/setup.bash
cd ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner
find src -maxdepth 4 \( -path '*quadrotor_msgs/package.xml' -o -path '*multipoint/package.xml' -o -path '*plan_manage/package.xml' \) | sort | tee ~/uav-g3b-evidence/p3-core-package-files.txt
```

Expected: output lists `Utils/quadrotor_msgs/package.xml`, `user_command/multipoint/package.xml`, and `diff_planner/plan_manage/package.xml`. If these package files are missing, the workspace snapshot is incomplete and P3 is blocked.

- [ ] **Step 4: Verify custom and standard messages**

Run after a successful build:

```bash
source /opt/ros/noetic/setup.bash
cd ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner
source devel/setup.bash
{
  rosmsg show geometry_msgs/PoseStamped
  rosmsg show quadrotor_msgs/TakeoffLand
} 2>&1 | tee ~/uav-g3b-evidence/p3-rosmsg.txt
```

Expected: `quadrotor_msgs/TakeoffLand` shows a `takeoff_land_cmd` field.

- [ ] **Step 5: Verify `/goal` and `multipoint` static source evidence**

Run:

```bash
cd ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner
{
  rg -n 'nh.subscribe\("/goal"|waypointCallback|planNextWaypoint' src/diff_planner/plan_manage/src/diff_replan_fsm.cpp
  rg -n 'point_pub = nh.advertise<geometry_msgs::PoseStamped>\("/goal"|/move_base_simple/goal|/back_trigger' src/user_command/multipoint/src/multipointplan.cpp
  rg -n 'arg name="flight_type" value="1"' src/diff_planner/plan_manage/launch/exp/run_exp_single_lio.launch src/diff_planner/plan_manage/launch/exp/run_exp_single_vio.launch
} 2>&1 | tee ~/uav-g3b-evidence/p3-static-goal-evidence.txt
```

Expected:
- `diff_replan_fsm.cpp` shows `/goal` subscription and `waypointCallback`.
- `multipointplan.cpp` shows `/goal` publisher and `/move_base_simple/goal` trigger wiring.
- LIO/VIO experiment launch files show `flight_type` value `1`.

- [ ] **Step 6: Update evidence and commit**

Copy `~/uav-g3b-evidence/p3-*.txt` into the `P3` sections in the evidence file.

Verdict rules:
- `PASS` if build succeeds and both `rosmsg` and static `/goal` evidence pass.
- `PASS_STATIC_ONLY` if build is blocked by non-core dependencies but static `/goal` evidence and package files are present.
- `BLOCKED_WORKSPACE` if the Diff-planner snapshot is missing core packages.

Run:

```bash
git add docs/superpowers/evidence/2026-04-28-uav-g3b-wsl2-ros-evidence.md
git commit -m "docs: record UAV G3-B P3 evidence"
```

Expected: commit succeeds with only the evidence file changed.

### Task 7: Run G3-B Read-only ROS Graph Observation

**Files:**
- Modify: `docs/superpowers/evidence/2026-04-28-uav-g3b-wsl2-ros-evidence.md`

- [ ] **Step 1: Start ROS core**

Terminal A:

```bash
source /opt/ros/noetic/setup.bash
roscore 2>&1 | tee ~/uav-g3b-evidence/g3b-roscore.txt
```

Expected: output includes `started core service [/rosout]`.

- [ ] **Step 2: Capture baseline graph without planner nodes**

Terminal B:

```bash
source /opt/ros/noetic/setup.bash
{
  rostopic list
  rostopic info /goal || true
  rostopic type /goal || true
  rosmsg show geometry_msgs/PoseStamped
  rostopic info /move_base_simple/goal || true
  rostopic info /back_trigger || true
  rosnode list
} 2>&1 | tee ~/uav-g3b-evidence/g3b-baseline-graph.txt
```

Expected: baseline may show no `/goal` subscriber because planner is not started. This is valid baseline evidence.

- [ ] **Step 3: Start planner/multipoint only when P3 build supports launch**

Run this step only when P3 verdict is `PASS`:

```bash
source /opt/ros/noetic/setup.bash
cd ~/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner
source devel/setup.bash
export DRONE_ID=0
roslaunch diff_planner run_exp_single_lio.launch 2>&1 | tee ~/uav-g3b-evidence/g3b-run-exp-single-lio.txt
```

Expected: launch starts nodes or fails with missing live sensor topics. If it fails because `/ekf/ekf_odom`, mapping, or hardware streams are missing, record that as expected non-action G3-B evidence and do not bypass by publishing fake action topics.

- [ ] **Step 4: Capture graph after planner launch attempt**

Terminal C:

```bash
source /opt/ros/noetic/setup.bash
{
  rostopic list
  rostopic info /goal || true
  rostopic type /goal || true
  rostopic info /planning/trajectory || true
  rostopic info /setpoints_cmd || true
  rosnode list
  rosnode info /drone_0_diff_planner_node || true
  rosparam list | grep 'fsm/flight_type' || true
  rosparam get /drone_0_diff_planner_node/fsm/flight_type || true
} 2>&1 | tee ~/uav-g3b-evidence/g3b-planner-graph.txt
```

Expected:
- If planner starts, `/goal` has a subscriber.
- If planner does not start due to missing sensor/hardware topics, evidence must show the exact failure.
- No action publish command is used.

- [ ] **Step 5: Capture dry-run payload evidence without publishing**

Use the current local `uav/llm_control` implementation only if it exists in the execution workspace. Check:

```bash
cd ~/changxin-code
test -d uav/llm_control && echo "llm_control present" || echo "llm_control absent"
```

If present, run this exact dry-run command and copy its output into `G3-B.2`:

```bash
python3 - <<'PY' 2>&1 | tee ~/uav-g3b-evidence/g3b-llm-control-dry-run.txt
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

Expected: output contains `needs_confirmation`, `/goal`, and no publish side effect.

If `uav/llm_control` is absent, write this exact verdict in `G3-B.2`:

```text
Verdict: SKIPPED_LLM_CONTROL_NOT_SYNCED
Next: Merge or copy the separate uav/llm_control service-layer worktree before using dry-run payload evidence as a G3-C gate.
```

Expected: dry-run evidence is either present or explicitly marked `SKIPPED_LLM_CONTROL_NOT_SYNCED`. It is not a blocker for ROS environment readiness, but it is a blocker for entering G3-C with LLM-control evidence.

- [ ] **Step 6: Update evidence and commit**

Copy `~/uav-g3b-evidence/g3b-*.txt` into `G3-B` in the evidence file. Stop `roscore` and any `roslaunch` processes with `Ctrl-C`.

Verdict rules:
- `PASS_GRAPH` if ROS graph commands work and `/goal` subscriber evidence is captured.
- `PASS_BASELINE_ONLY` if ROS works but planner cannot launch due to missing non-action sensor/hardware inputs.
- `BLOCKED_ROS_GRAPH` if `rostopic` or `rosnode` cannot talk to ROS master.

Run:

```bash
git add docs/superpowers/evidence/2026-04-28-uav-g3b-wsl2-ros-evidence.md
git commit -m "docs: record UAV G3-B graph evidence"
```

Expected: commit succeeds with only the evidence file changed.

### Task 8: Final Gate Review

**Files:**
- Modify: `docs/superpowers/evidence/2026-04-28-uav-g3b-wsl2-ros-evidence.md`

- [ ] **Step 1: Fill final gate verdicts**

In `docs/superpowers/evidence/2026-04-28-uav-g3b-wsl2-ros-evidence.md`, fill:

```md
## Final Gate

- P0 Verdict: PASS or blocking verdict from Task 2
- P1 Verdict: PASS or blocking verdict from Task 3
- P1.5 Verdict: PASS or blocking verdict from Task 4
- P2 Verdict: PASS, PASS_WITH_ROSDEP_RISK, or blocking verdict from Task 5
- P3 Verdict: PASS, PASS_STATIC_ONLY, or blocking verdict from Task 6
- G3-B Verdict: PASS_GRAPH, PASS_BASELINE_ONLY, or blocking verdict from Task 7
- G3-C Entry Decision: DO_NOT_ENTER_G3C_UNTIL_REVIEWED
```

Expected: every line is filled with a concrete verdict, not a narrative paragraph.

- [ ] **Step 2: Run repository evidence checks**

Run from repo root:

```bash
rg -n "BLOCKED|PASS|SKIPPED_LLM_CONTROL_NOT_SYNCED|DO_NOT_ENTER_G3C_UNTIL_REVIEWED" docs/superpowers/evidence/2026-04-28-uav-g3b-wsl2-ros-evidence.md
rg -n "/px4ctrl/takeoff_land|/back_trigger|/goal|/setpoints_cmd" docs/superpowers/evidence/2026-04-28-uav-g3b-wsl2-ros-evidence.md
```

Expected:
- First command shows concrete verdicts.
- Second command shows safety boundary text and read-only `rostopic info/type` observations only. It must not show `rostopic pub /px4ctrl/takeoff_land`, `rostopic pub /back_trigger`, `rostopic pub /goal`, or `rostopic pub /setpoints_cmd`.

- [ ] **Step 3: Commit final evidence**

Run:

```bash
git add docs/superpowers/evidence/2026-04-28-uav-g3b-wsl2-ros-evidence.md
git commit -m "docs: finalize UAV G3-B gate evidence"
```

Expected: commit succeeds with final evidence updates.

- [ ] **Step 4: Report next decision**

Report one of these outcomes:

```text
Outcome A: G3-B environment baseline is ready. G3-C remains blocked until separate approval.
Outcome B: G3-B is partially ready with PASS_STATIC_ONLY or PASS_BASELINE_ONLY. Next work is to remove the named blocker.
Outcome C: G3-B is blocked. Next work is the first BLOCKED_* verdict in phase order.
```

Expected: the report names the first unresolved blocker and does not recommend any real action publish.
