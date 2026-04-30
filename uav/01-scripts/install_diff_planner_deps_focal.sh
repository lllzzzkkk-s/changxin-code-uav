#!/usr/bin/env bash
set -Eeuo pipefail

MODE="${1:-all}"
EVIDENCE_DIR="${UAV_G3B_EVIDENCE_DIR:-$HOME/uav-g3b-evidence}"
SRC_DIR="${UAV_DEPS_SRC_DIR:-$HOME/uav-deps/src}"
BUILD_DIR="${UAV_DEPS_BUILD_DIR:-$HOME/uav-deps/build}"
OPENCV_VERSION="${UAV_OPENCV_VERSION:-3.4.14}"
OPENCV_PREFIX="${UAV_OPENCV_PREFIX:-/home/nv/Lib/opencv3.4.14/install}"
DIFF_PLANNER_DIR="${UAV_DIFF_PLANNER_DIR:-$HOME/changxin-code/uav/03-drone-code/snapshot_20260421_174511/Diff-planner}"
LIVOX_SDK2_REPO="${UAV_LIVOX_SDK2_REPO:-https://github.com/Livox-SDK/Livox-SDK2.git}"
JOBS="${UAV_DEPS_JOBS:-$(nproc)}"

mkdir -p "$EVIDENCE_DIR" "$SRC_DIR" "$BUILD_DIR"

log() {
  printf '[%s] %s\n' "$(date -Is)" "$*"
}

require_focal() {
  # shellcheck disable=SC1091
  source /etc/os-release
  if [[ "${ID:-}" != "ubuntu" || "${VERSION_ID:-}" != "20.04" ]]; then
    echo "This script is pinned to Ubuntu 20.04/focal. Found: ${PRETTY_NAME:-unknown}" >&2
    exit 2
  fi
}

install_apt_deps() {
  log "Installing Diff-planner/VINS base dependencies with apt"
  sudo apt update
  sudo DEBIAN_FRONTEND=noninteractive apt install -y \
    build-essential \
    ca-certificates \
    cmake \
    curl \
    git \
    pkg-config \
    unzip \
    libatlas-base-dev \
    libavcodec-dev \
    libavformat-dev \
    libboost-all-dev \
    libceres-dev \
    libdc1394-22-dev \
    libeigen3-dev \
    libgflags-dev \
    libglfw3-dev \
    libgoogle-glog-dev \
    libgtk2.0-dev \
    libjpeg-dev \
    liblapack-dev \
    libopencv-dev \
    libpcl-dev \
    libpng-dev \
    libprotobuf-dev \
    libsuitesparse-dev \
    libswscale-dev \
    libtiff-dev \
    libv4l-dev \
    libyaml-cpp-dev \
    geographiclib-tools \
    protobuf-compiler \
    python3-opencv \
    ros-noetic-cv-bridge \
    ros-noetic-ddynamic-reconfigure \
    ros-noetic-diagnostic-updater \
    ros-noetic-eigen-conversions \
    ros-noetic-image-transport \
    ros-noetic-mavros \
    ros-noetic-mavros-extras \
    ros-noetic-pcl-conversions \
    ros-noetic-pcl-ros \
    ros-noetic-tf \
    ros-noetic-tf2-ros \
    ros-noetic-vision-opencv

  # These binary packages are useful when the workspace source packages are disabled.
  # They may be absent on some mirrors, so do not make the whole dependency pass fail.
  for optional_pkg in ros-noetic-realsense2-camera ros-noetic-realsense2-description; do
    sudo DEBIAN_FRONTEND=noninteractive apt install -y "$optional_pkg" || true
  done

  if [[ -x /opt/ros/noetic/lib/mavros/install_geographiclib_datasets.sh ]]; then
    sudo /opt/ros/noetic/lib/mavros/install_geographiclib_datasets.sh || true
  fi
}

download_tarball() {
  local url="$1"
  local out="$2"
  if [[ ! -s "$out" ]]; then
    log "Downloading $url"
    curl -L "$url" -o "$out"
  fi
}

build_opencv_314() {
  local config_file="$OPENCV_PREFIX/OpenCVConfig.cmake"
  if [[ -f "$config_file" ]]; then
    log "OpenCV ${OPENCV_VERSION} already present at $config_file"
    return
  fi

  local tarball="$SRC_DIR/opencv-${OPENCV_VERSION}.tar.gz"
  local src_root="$SRC_DIR/opencv-${OPENCV_VERSION}"
  local build_root="$BUILD_DIR/opencv-${OPENCV_VERSION}"

  download_tarball \
    "https://github.com/opencv/opencv/archive/${OPENCV_VERSION}.tar.gz" \
    "$tarball"

  if [[ ! -d "$src_root" ]]; then
    log "Extracting OpenCV ${OPENCV_VERSION}"
    tar -xzf "$tarball" -C "$SRC_DIR"
  fi

  log "Configuring OpenCV ${OPENCV_VERSION} for the path hard-coded by VINS-Fusion-gpu"
  cmake -S "$src_root" -B "$build_root" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$OPENCV_PREFIX" \
    -DBUILD_EXAMPLES=OFF \
    -DBUILD_opencv_python2=OFF \
    -DBUILD_opencv_python3=OFF \
    -DBUILD_PERF_TESTS=OFF \
    -DBUILD_TESTS=OFF \
    -DWITH_CUDA=OFF

  log "Building OpenCV ${OPENCV_VERSION} with ${JOBS} jobs"
  cmake --build "$build_root" -- -j"$JOBS"
  log "Installing OpenCV ${OPENCV_VERSION} to $OPENCV_PREFIX"
  sudo cmake --install "$build_root"
  ensure_opencv_compat_config
}

ensure_opencv_compat_config() {
  local config_file="$OPENCV_PREFIX/OpenCVConfig.cmake"
  local installed_config="$OPENCV_PREFIX/share/OpenCV/OpenCVConfig.cmake"
  if [[ -f "$config_file" ]]; then
    return
  fi
  if [[ ! -f "$installed_config" ]]; then
    echo "OpenCV installed config not found at $installed_config" >&2
    exit 4
  fi

  log "Creating compatibility OpenCVConfig.cmake for VINS-Fusion-gpu hard-coded include path"
  sudo tee "$config_file" >/dev/null <<'EOF'
# Compatibility shim for VINS-Fusion-gpu, which includes this exact path.
include("${CMAKE_CURRENT_LIST_DIR}/share/OpenCV/OpenCVConfig.cmake")
EOF
}

patch_vins_cv_bridge() {
  python3 - "$DIFF_PLANNER_DIR" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
files = [
    root / "src/realflight_modules/VINS-Fusion-gpu/loop_fusion/CMakeLists.txt",
    root / "src/realflight_modules/VINS-Fusion-gpu/vins_estimator/CMakeLists.txt",
]
hardcoded = 'include("~/Lib/cv_bridge_pkgs/devel/share/cv_bridge/cmake/cv_bridgeConfig.cmake")'
replacement = '''if(EXISTS "$ENV{HOME}/Lib/cv_bridge_pkgs/devel/share/cv_bridge/cmake/cv_bridgeConfig.cmake")
  include("$ENV{HOME}/Lib/cv_bridge_pkgs/devel/share/cv_bridge/cmake/cv_bridgeConfig.cmake")
else()
  find_package(cv_bridge REQUIRED)
endif()'''

guard = '''if(DEFINED OpenCV_LIBRARIES)
  list(LENGTH OpenCV_LIBRARIES _uavdeps_opencv_lib_count)
  if(_uavdeps_opencv_lib_count GREATER 0)
    list(REMOVE_ITEM cv_bridge_LIBRARIES ${OpenCV_LIBRARIES})
  endif()
endif()'''

for path in files:
    if not path.exists():
        print(f"skip missing {path}")
        continue

    text = path.read_text()
    original = text
    text = text.replace(hardcoded, replacement)

    lines = text.splitlines()
    patched = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("list(REMOVE_ITEM cv_bridge_LIBRARIES") and "OpenCV_LIBRARIES" in stripped:
            indent = line[: len(line) - len(line.lstrip())]
            for guard_line in guard.splitlines():
                patched.append(f"{indent}{guard_line}")
            continue
        patched.append(line)
    text = "\n".join(patched) + "\n"

    if text != original:
        backup = path.with_suffix(path.suffix + ".uavdeps.bak")
        if not backup.exists():
            backup.write_text(original)
        path.write_text(text)
        print(f"patched {path}")
    else:
        print(f"no patch needed {path}")
PY
}

build_livox_sdk2() {
  if ldconfig -p 2>/dev/null | grep -q 'liblivox_lidar_sdk'; then
    log "Livox-SDK2 runtime library already visible to ldconfig"
    return
  fi

  local sdk_src="$SRC_DIR/Livox-SDK2"
  local sdk_build="$BUILD_DIR/Livox-SDK2"
  if [[ ! -d "$sdk_src/.git" ]]; then
    log "Cloning Livox-SDK2"
    rm -rf "$sdk_src"
    git clone "$LIVOX_SDK2_REPO" "$sdk_src"
  fi

  log "Configuring Livox-SDK2"
  cmake -S "$sdk_src" -B "$sdk_build" -DCMAKE_BUILD_TYPE=Release
  log "Building Livox-SDK2 with ${JOBS} jobs"
  cmake --build "$sdk_build" -- -j"$JOBS"
  log "Installing Livox-SDK2"
  sudo cmake --install "$sdk_build"
  sudo ldconfig
}

verify_deps() {
  local ceres_config
  ceres_config="$(find /usr /opt -name CeresConfig.cmake -print -quit 2>/dev/null || true)"

  {
    date -Is
    echo "MODE=$MODE"
    echo "Ubuntu:"
    cat /etc/os-release
    echo
    echo "CeresConfig=$ceres_config"
    echo "OpenCVConfig=$OPENCV_PREFIX/OpenCVConfig.cmake"
    test -f "$OPENCV_PREFIX/OpenCVConfig.cmake" && echo "OpenCVConfigPresent=yes" || echo "OpenCVConfigPresent=no"
    echo
    echo "CUDA/NVIDIA:"
    command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi || echo "nvidia-smi not found"
    command -v nvcc >/dev/null 2>&1 && nvcc --version || echo "nvcc not found"
    test -f /usr/local/cuda/version.txt && cat /usr/local/cuda/version.txt || true
    echo
    echo "MAVROS:"
    test -f /opt/ros/noetic/share/mavros/cmake/mavrosConfig.cmake && echo "mavrosConfigPresent=yes" || echo "mavrosConfigPresent=no"
    echo
    echo "Livox-SDK2:"
    ldconfig -p 2>/dev/null | grep 'liblivox_lidar_sdk' || true
    find /usr/local/lib /usr/lib -name 'liblivox_lidar_sdk*' -print 2>/dev/null || true
  } | tee "$EVIDENCE_DIR/p3-full-deps-verify.txt"

  if [[ -z "$ceres_config" ]]; then
    echo "CeresConfig.cmake not found after apt dependency install" >&2
    exit 3
  fi
  if [[ -f "$OPENCV_PREFIX/share/OpenCV/OpenCVConfig.cmake" && ! -f "$OPENCV_PREFIX/OpenCVConfig.cmake" ]]; then
    ensure_opencv_compat_config
  fi
  if [[ "$MODE" == "all" || "$MODE" == "opencv" ]]; then
    test -f "$OPENCV_PREFIX/OpenCVConfig.cmake"
  fi
}

install_cuda_toolkit_if_requested() {
  if [[ "${UAV_ALLOW_UBUNTU_CUDA_TOOLKIT:-0}" != "1" ]]; then
    log "Skipping Ubuntu CUDA toolkit install. Set UAV_ALLOW_UBUNTU_CUDA_TOOLKIT=1 only after confirming WSL NVIDIA driver support."
    return
  fi

  sudo DEBIAN_FRONTEND=noninteractive apt install -y nvidia-cuda-toolkit
}

main() {
  require_focal
  case "$MODE" in
    apt)
      install_apt_deps 2>&1 | tee "$EVIDENCE_DIR/p3-full-deps-apt.txt"
      verify_deps
      ;;
    patch)
      ensure_opencv_compat_config 2>&1 | tee "$EVIDENCE_DIR/p3-full-deps-patch.txt"
      patch_vins_cv_bridge 2>&1 | tee -a "$EVIDENCE_DIR/p3-full-deps-patch.txt"
      verify_deps
      ;;
    livox)
      build_livox_sdk2 2>&1 | tee "$EVIDENCE_DIR/p3-full-deps-livox.txt"
      verify_deps
      ;;
    opencv)
      build_opencv_314 2>&1 | tee "$EVIDENCE_DIR/p3-full-deps-opencv.txt"
      verify_deps
      ;;
    all)
      install_apt_deps 2>&1 | tee "$EVIDENCE_DIR/p3-full-deps-apt.txt"
      build_opencv_314 2>&1 | tee "$EVIDENCE_DIR/p3-full-deps-opencv.txt"
      patch_vins_cv_bridge 2>&1 | tee "$EVIDENCE_DIR/p3-full-deps-patch.txt"
      build_livox_sdk2 2>&1 | tee "$EVIDENCE_DIR/p3-full-deps-livox.txt"
      install_cuda_toolkit_if_requested 2>&1 | tee "$EVIDENCE_DIR/p3-full-deps-cuda.txt"
      verify_deps
      ;;
    verify)
      verify_deps
      ;;
    *)
      echo "Usage: $0 [apt|opencv|patch|livox|all|verify]" >&2
      exit 64
      ;;
  esac
}

main "$@"
