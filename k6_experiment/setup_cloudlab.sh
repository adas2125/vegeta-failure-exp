#!/usr/bin/env bash
set -Eeuo pipefail

# Setup dependencies needed to reproduce the local k6 burst experiment on a
# fresh Ubuntu/CloudLab bare-metal VM.
#
# This script installs system packages, installs the Go toolchain version used
# by the current k6 binary, and installs the Python packages used by the helper
# scripts.
#
# First, clone the upstream k6 repo at the commit used here, then copy these local
# experiment files on top:
#
#   git clone https://github.com/grafana/k6.git
#   cd k6
#   git checkout 7ee37a814bd89b359b9ad95606dc8706c4e183ac
#
# Then copy in the experiment scripts, run this setup script, and build k6 with:
#
#   go build -o k6
#
# The current local binary reports:
#
#   k6 v2.0.1-0.20260528083733-7ee37a814bd8+dirty
#
# Node architecture observed on the original machine:
#
#   OS: Ubuntu 24.04.4 LTS, linux/amd64
#   CPU: 2 sockets x Intel Xeon E5-2683 v3 at 2.00GHz
#   Topology: 14 physical cores per socket, SMT enabled, 56 logical CPUs online
#   Online CPU IDs: 0-55
#   Memory: about 252 GiB RAM, plus 8 GiB swap
#
# For closest reproduction, use a bare-metal x86-64 node with the same or very
# similar dual-socket topology and SMT enabled. The runner compares k6 pinned to
# CPUs 0-7 against k6 pinned to CPUs 0-55, so CPU numbering, socket layout,
# frequency scaling, and other activity on the node can affect the measured
# latency and CPU-utilization results.

GO_VERSION="${GO_VERSION:-1.25.10}"

need_sudo() {
  if [[ "$(id -u)" -eq 0 ]]; then
    SUDO=""
  else
    SUDO="sudo"
  fi
}

detect_arch() {
  case "$(uname -m)" in
    x86_64 | amd64)
      GO_ARCH="amd64"
      ;;
    aarch64 | arm64)
      GO_ARCH="arm64"
      ;;
    *)
      echo "Unsupported architecture: $(uname -m)" >&2
      exit 1
      ;;
  esac
}

install_apt_packages() {
  $SUDO apt-get update
  $SUDO apt-get install -y \
    bash \
    build-essential \
    ca-certificates \
    coreutils \
    curl \
    git \
    pkg-config \
    python3 \
    python3-matplotlib \
    python3-pip \
    python3-psutil \
    tar \
    util-linux
}

install_go() {
  local wanted="go${GO_VERSION}"
  local current=""
  if command -v go >/dev/null 2>&1; then
    current="$(go version | awk '{print $3}')"
  fi

  if [[ "$current" == "$wanted" ]]; then
    echo "Go ${GO_VERSION} is already installed."
    return
  fi

  local tmpdir
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "$tmpdir"' RETURN

  local tarball="go${GO_VERSION}.linux-${GO_ARCH}.tar.gz"
  local url="https://go.dev/dl/${tarball}"

  echo "Installing Go ${GO_VERSION} for linux/${GO_ARCH} from ${url}"
  curl -fsSL "$url" -o "$tmpdir/$tarball"
  $SUDO rm -rf /usr/local/go
  $SUDO tar -C /usr/local -xzf "$tmpdir/$tarball"
  $SUDO ln -sfn /usr/local/go/bin/go /usr/local/bin/go
  $SUDO ln -sfn /usr/local/go/bin/gofmt /usr/local/bin/gofmt
}

install_python_packages() {
  python3 -c 'import psutil, matplotlib'
}

print_summary() {
  cat <<EOF

CloudLab setup complete.

Installed/verified:
  - Go: $(go version)
  - Python: $(python3 --version)
  - psutil: $(python3 -c 'import psutil; print(psutil.__version__)')
  - matplotlib: $(python3 -c 'import matplotlib; print(matplotlib.__version__)')
  - taskset: $(command -v taskset)

Verify the local k6 binary before running the experiment:

  ./k6 version

Notes:
  - The current experiment uses CPU sets 0-7 and 0-55, so use a VM with at
    least 56 logical CPUs for the full profile.
EOF
}

main() {
  need_sudo
  detect_arch
  install_apt_packages
  install_go
  install_python_packages
  print_summary
}

main "$@"
