# UAV G3-B WSL2 ROS 环境设计

日期：2026-04-28

## 1. 目标与边界

本设计服务于 UAV LLM Control A 阶段的 G3-B 前置验证：在远端 Windows Server 上建立一套可重复的 `WSL2 Ubuntu 20.04 + ROS Noetic` 基线环境，用于后续 ROS graph 观测、Diff-planner 构建验证和 `/goal` spike。

本轮不做真实无人机动作，不连接飞控，不接 Qt，不接 LLM 端到端，不修改 Diff-planner 主链，不 publish `/setpoints_cmd`。服务器侧只允许完成环境安装、只读观测、dry-run 输出和证据记录。

首轮验收范围：

1. Windows Server 侧确认 WSL2 前置条件满足。
2. WSL2 内 `Ubuntu-20.04` 可用，且版本为 WSL2。
3. Ubuntu 内 ROS Noetic 可用。
4. Windows 与 Ubuntu 两侧代理配置可复用。
5. 能为后续 Diff-planner 构建、ROS graph 观测、`/goal` spike 提供环境基础。

阶段定位：

`P0 服务器/代理/WSL 自检 -> P1 WSL2 Ubuntu -> P2 ROS Noetic -> P3 Diff-planner 静态/构建验证 -> G3-B ROS graph 观测`

## 2. 已确认前提

- 服务器当前是 Windows Server + WSL2 目标形态。
- 当前还没有安装 WSL。
- 用户可通过 RDP 登录服务器。
- 登录账号具备管理员权限。
- 允许随时重启服务器。
- 服务器访问公网需要公司代理或内网代理。
- 当前推荐路线为在线代理主线，不采用 Docker 作为首轮主路径。

## 3. 阶段门与验收标准

### P0 Windows Server 与代理自检

目标是在不修改系统的前提下确认 Windows、WSL、虚拟化、磁盘、代理是否具备安装条件。

验收标准：

- 能拿到 Windows 版本、构建号、系统架构。
- 能确认虚拟化已开启或可开启。
- PowerShell 能通过代理访问 Microsoft、Ubuntu、ROS 相关下载源。
- 系统盘或目标安装盘至少保留 80GB 可用空间。
- 能确认是否已经存在 WSL 安装。

失败分支：

- Windows Server 版本过旧：切到手动 WSL 安装或升级建议。
- 虚拟化未开：停止安装，要求 BIOS、宿主机或云服务器规格侧启用虚拟化。
- 代理不可用：停止 WSL 安装，切到半离线包方案。
- 权限不足：停止安装，补齐管理员权限后再继续。

### P1 WSL2 + Ubuntu 20.04 基线

目标是安装并固定 `Ubuntu-20.04`，保证其运行在 WSL2。

验收标准：

- `wsl --status` 可用。
- `wsl -l -v` 显示 `Ubuntu-20.04`。
- `Ubuntu-20.04` 的 `VERSION` 是 `2`。
- Ubuntu 内 `/etc/os-release` 显示 20.04。
- Ubuntu 内 `sudo apt update` 能通过代理成功。

失败分支：

- `wsl --install` 不支持：转手动启用 `Microsoft-Windows-Subsystem-Linux` 与 `VirtualMachinePlatform`，再手动安装或导入 Ubuntu。
- Ubuntu 被安装为 WSL1：执行 `wsl --set-version Ubuntu-20.04 2`，失败则回到虚拟化和内核版本检查。
- Ubuntu 不是 20.04：并行安装指定发行版，不在 22.04 上强行作为 Noetic 基线。
- apt 代理不通：先修代理，不继续 ROS 安装。

### P2 ROS Noetic 基线

目标是在 Ubuntu 20.04 内安装 ROS Noetic，并验证基础 ROS 命令可用。

验收标准：

- `/opt/ros/noetic/setup.bash` 存在。
- `roscore` 能启动。
- 新终端 source ROS 后能执行 `rostopic list`。
- `rosmsg show geometry_msgs/PoseStamped` 正常。
- `rosmsg show quadrotor_msgs/TakeoffLand` 不作为 P2 必须项，因为它来自 Diff-planner workspace，放到 P3 验证。

失败分支：

- ROS apt 源不可达：优先修代理；仍不稳定时切可信镜像源。
- `rosdep update` 不通：不阻塞 P2 的 `roscore` 验收，但记录为 P3 构建风险。
- Python 环境混乱：ROS 终端不启用 conda，固定使用 Ubuntu 20.04 系统 Python3。

### P3 Diff-planner 工作区构建与静态验证

目标是同步源码，验证核心消息和 `/goal` 接入关系。首轮不要求传感器、GPU、RViz 全链路跑通。

验收标准：

- 能把仓库或 Diff-planner 快照同步到 WSL。
- `catkin_make` 至少能构建核心消息包和目标相关包。
- `rosmsg show quadrotor_msgs/TakeoffLand` 可用。
- 能确认 planner 在 `flight_type=1` 时订阅 `/goal`。
- 能确认 `multipoint` 会发布 `/goal`，而 `/move_base_simple/goal` 只是启动触发。

失败分支：

- 全量 `catkin_make` 被 Realsense、VINS、Livox、CUDA 等依赖卡住：切到最小验证 workspace，先构建 `Utils/quadrotor_msgs`、`diff_planner/plan_manage`、`user_command/multipoint` 及其必要依赖。
- 图形或 RViz 不通：不阻塞 G3-B，首轮以命令行 `rostopic/rosnode/rosmsg/rosparam` 为证据。
- 自定义消息不可见：优先修 `quadrotor_msgs` 构建与 `devel/setup.bash` source 链。

### G3-B ROS Graph 观测

目标是只读验证 ROS graph，不做实机动作。

验收标准：

- `roscore` 可启动。
- 能用 `rostopic list/info/type` 观察关键 topic。
- 能确认 `/goal` 的 subscriber/publisher 关系。
- 能 dry-run 生成 `move_relative` payload，但不 publish 到真实 ROS topic。
- 能产出 G3-B evidence log：环境版本、命令输出、topic 信息、风险结论。

失败分支：

- `/goal` 没有 subscriber：说明 planner 没按 manual target 启动，检查 `flight_type`。
- `/goal` 只有 `multipoint` publisher 但 planner subscriber 正常：可继续设计受控 single-goal adapter。
- `/goal` 与 `multipoint` 明显抢入口：暂不实机测 `move_relative`，先设计仲裁层。

## 4. 命令骨架

### P0 Windows 只读自检

管理员 PowerShell：

```powershell
Get-ComputerInfo | Select-Object OsName, OsVersion, WindowsVersion, OsBuildNumber, CsSystemType
systeminfo | findstr /i "Virtualization Hyper-V"
Get-PSDrive C
wsl --status
wsl -l -v
netsh winhttp show proxy
```

代理检查：

```powershell
Invoke-WebRequest https://aka.ms/wslstorepage -UseBasicParsing
Invoke-WebRequest https://packages.ros.org -UseBasicParsing
```

如果直连失败，当前 PowerShell 会话先设置代理。实际代理地址只在服务器环境中配置，不写入仓库文档：

```powershell
$env:HTTP_PROXY=$env:UAV_PROXY_URL
$env:HTTPS_PROXY=$env:UAV_PROXY_URL
```

如需系统级 WinHTTP 代理：

```powershell
$env:UAV_WINHTTP_PROXY="proxy.example.internal:8080"
netsh winhttp set proxy proxy-server=$env:UAV_WINHTTP_PROXY
```

`UAV_PROXY_URL` 用于带协议的环境变量形式，例如 `http://proxy.example.internal:8080`。`UAV_WINHTTP_PROXY` 用于 WinHTTP，通常不带协议。实际代理地址、账号、密码只在服务器环境中配置，不写入仓库。

### P1 启用 WSL2 与安装 Ubuntu 20.04

优先主线：

```powershell
wsl --install --web-download -d Ubuntu-20.04
```

如果 `wsl --install` 不支持，手动启用组件：

```powershell
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
shutdown /r /t 0
```

重启后：

```powershell
wsl --set-default-version 2
wsl --install --web-download -d Ubuntu-20.04
wsl -l -v
```

### P1.5 Ubuntu 代理与基础工具

进入 Ubuntu：

```bash
cat /etc/os-release
uname -a
```

设置当前 shell 代理：

```bash
export http_proxy="$UAV_PROXY_URL"
export https_proxy="$UAV_PROXY_URL"
```

如需 apt 持久代理：

```bash
sudo tee /etc/apt/apt.conf.d/95proxies >/dev/null <<EOF
Acquire::http::Proxy "${UAV_PROXY_URL}";
Acquire::https::Proxy "${UAV_PROXY_URL}";
EOF
```

基础包：

```bash
sudo apt update
sudo apt install -y curl gnupg lsb-release build-essential git python3-pip
```

### P2 ROS Noetic

Ubuntu 20.04 对应 ROS Noetic：

```bash
sudo sh -c 'echo "deb http://packages.ros.org/ros/ubuntu $(lsb_release -sc) main" > /etc/apt/sources.list.d/ros-latest.list'
curl -s https://raw.githubusercontent.com/ros/rosdistro/master/ros.asc | sudo apt-key add -
sudo apt update
sudo apt install -y ros-noetic-desktop-full python3-rosdep python3-rosinstall python3-rosinstall-generator python3-wstool python3-catkin-tools
sudo rosdep init || true
rosdep update
echo "source /opt/ros/noetic/setup.bash" >> ~/.bashrc
source /opt/ros/noetic/setup.bash
```

验收终端 A：

```bash
roscore
```

验收终端 B：

```bash
source /opt/ros/noetic/setup.bash
rostopic list
rosmsg show geometry_msgs/PoseStamped
```

### P3 Diff-planner 同步与构建策略

建议路径：

```bash
mkdir -p ~/changxin-code
```

首轮先尝试全量构建；失败后按最小验证 workspace 切分。最小验证优先关注：

- `Utils/quadrotor_msgs`
- `diff_planner/plan_manage`
- `user_command/multipoint`
- 必要的 `traj_utils`
- 必要的 `plan_env`
- 必要的 `path_searching`
- 必要的 `traj_opt`

### G3-B 只读观测命令

允许：

```bash
roscore
rostopic list
rostopic info /goal
rostopic type /goal
rosmsg show geometry_msgs/PoseStamped
rostopic info /move_base_simple/goal
rostopic info /back_trigger
rosnode list
rosnode info /drone_0_diff_planner_node
rosparam get /drone_0_diff_planner_node/fsm/flight_type
rosparam list | grep 'fsm/flight_type'
```

如果 planner/multipoint 能启动，再观察：

```bash
rostopic info /goal
rostopic info /planning/trajectory
rostopic info /setpoints_cmd
```

禁止：

```bash
rostopic pub /px4ctrl/takeoff_land ...
rostopic pub /back_trigger ...
rostopic pub /goal ...
rostopic pub /setpoints_cmd ...
```

## 5. 安全边界

G3-B 期间禁止真实动作 publish，尤其禁止：

- `/px4ctrl/takeoff_land`
- `/back_trigger`
- `/goal`
- `/setpoints_cmd`

允许的操作只有：

- `rostopic list`
- `rostopic info`
- `rostopic type`
- `rosmsg show`
- `rosnode list/info`
- `rosparam get`
- `uav/llm_control` dry-run 输出

所有失败必须结构化记录，不允许用“环境问题”作为最终结论。记录至少包含阶段、命令、原始错误、判定原因、下一步分支。

## 6. 证据日志

建议证据日志路径：

`docs/superpowers/evidence/2026-04-28-uav-g3b-wsl2-ros-evidence.md`

建议格式：

```md
# UAV G3-B WSL2 ROS Evidence

## P0 Windows/Proxy
- Time:
- Server:
- Command:
- Output:
- Verdict:
- Next:

## P1 WSL2 Ubuntu
- Command:
- Output:
- Verdict:
- Next:

## P2 ROS Noetic
- Command:
- Output:
- Verdict:
- Next:

## P3 Diff-planner
- Command:
- Output:
- Verdict:
- Next:

## G3-B ROS Graph
- Command:
- Output:
- Verdict:
- Next:
```

## 7. G3-C 进入条件

只有全部满足以下条件，才允许进入下一轮“受控 publish / 单动作实机”设计：

- `Ubuntu-20.04` 是 WSL2。
- `roscore`、`rostopic`、`rosmsg` 正常。
- ROS Noetic 环境可重复 source。
- 代理不会阻断 apt 和 ROS 依赖。
- 已能构建或至少识别 Diff-planner 核心消息/接口。
- `/goal` 的 planner subscriber 关系有证据。
- 已明确 `multipoint` 与 `/goal` 是否存在入口冲突。
- 已有“不 publish 动作 topic”的 G3-B 证据日志。

即使 G3-B 全部通过，G3-C 仍必须单独确认后才允许设计或执行：

- `/goal` 受控 publish
- `/px4ctrl/takeoff_land`
- `/back_trigger`
- 任何真机动作
- 任何连接飞控或传感器的动作

## 8. 后续计划入口

本 spec 通过后，下一步应使用 writing-plans 技能产出 implementation plan。计划应先覆盖 P0/P1/P2 的服务器安装与验收，再覆盖 P3/G3-B 的 ROS graph 观测与证据日志，不应直接进入 G3-C。
