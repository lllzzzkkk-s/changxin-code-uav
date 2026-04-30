#!/usr/bin/env bash
set -Eeuo pipefail

MODE="${1:-all}"
EVIDENCE_DIR="${UAV_G3B_EVIDENCE_DIR:-$HOME/uav-g3b-evidence}"
SRC_DIR="${UAV_DEPS_SRC_DIR:-$HOME/uav-deps/src}"
BUILD_DIR="${UAV_DEPS_BUILD_DIR:-$HOME/uav-deps/build}"
OPENCV_VERSION="${UAV_OPENCV_VERSION:-3.4.14}"
OPENCV_PREFIX="${UAV_OPENCV_PREFIX:-/home/nv/Lib/opencv3.4.14/install}"
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
    protobuf-compiler \
    python3-opencv \
    ros-noetic-cv-bridge \
    ros-noetic-ddynamic-reconfigure \
    ros-noetic-diagnostic-updater \
    ros-noetic-eigen-conversions \
    ros-noetic-image-transport \
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
  } | tee "$EVIDENCE_DIR/p3-full-deps-verify.txt"

  if [[ -z "$ceres_config" ]]; then
    echo "CeresConfig.cmake not found after apt dependency install" >&2
    exit 3
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
    opencv)
      build_opencv_314 2>&1 | tee "$EVIDENCE_DIR/p3-full-deps-opencv.txt"
      verify_deps
      ;;
    all)
      install_apt_deps 2>&1 | tee "$EVIDENCE_DIR/p3-full-deps-apt.txt"
      build_opencv_314 2>&1 | tee "$EVIDENCE_DIR/p3-full-deps-opencv.txt"
      install_cuda_toolkit_if_requested 2>&1 | tee "$EVIDENCE_DIR/p3-full-deps-cuda.txt"
      verify_deps
      ;;
    verify)
      verify_deps
      ;;
    *)
      echo "Usage: $0 [apt|opencv|all|verify]" >&2
      exit 64
      ;;
  esac
}

main "$@"
