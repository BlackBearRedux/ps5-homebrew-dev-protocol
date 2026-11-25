#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
kit=$(cd "${PS5_BOILERPLATE:-$here/../../../ps5-native-app-boilerplate}" && pwd)
stage=build/protocol-example
mkdir -p "$kit/$stage/src"
cp "$here/main.cpp" "$kit/$stage/src/main.cpp"
cp "$kit/src/"{asset_text.cpp,demo_renderer.cpp,demo_renderer.hpp,frame_submission.hpp} "$kit/$stage/src/"
cp "$kit/sce_sys/param.json" "$kit/$stage/param.json"
TITLE_ID=PPSA99871 APP_NAME='Protocol Check' bash "$kit/tools/init-project.sh" "$kit/$stage/param.json"
make -C "$kit" app APP_SOURCE_DIR="$stage/src" APP_PARAM="$stage/param.json" APP_ASSETS= APP_ROOT_FILES=
bash "$here/../../scripts/freeze-candidate.sh" "$kit/dist/PPSA99871" "${1:?provide a new candidate directory}"
