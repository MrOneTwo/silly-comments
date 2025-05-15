#!/usr/bin/env bash

#set -o errexit
set -o nounset
set -o pipefail

cd "$(dirname "$0")"

RED=`tput setaf 1`
GREEN=`tput setaf 2`
BOLD=`tput bold`
RESET=`tput sgr0`

run() {
  flask --app frontend.py run -p 32168
}

deploy() {
  local HOST_INFO_FILE=remote.txt

  # Expect a certain data to be on a specific line.
  local REMOTE_PASSWORD=$(sed -n 1p $HOST_INFO_FILE)
  local REMOTE_SERVER=$(sed -n 2p $HOST_INFO_FILE)
  local REMOTE_USER=$(sed -n 3p $HOST_INFO_FILE)

  rsync -v \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude 'venv' \
    -- * "$REMOTE_USER"@"$REMOTE_SERVER":~/silly-comments/
}

kill() {
  local HOST_INFO_FILE=remote.txt

  # Expect a certain data to be on a specific line.
  local REMOTE_PASSWORD=$(sed -n 1p $HOST_INFO_FILE)
  local REMOTE_SERVER=$(sed -n 2p $HOST_INFO_FILE)
  local REMOTE_USER=$(sed -n 3p $HOST_INFO_FILE)

  printf "Killing frontend.py...\n"

  pid=$(ssh "$REMOTE_USER"@"$REMOTE_SERVER" ps ax | grep frontend.py | awk '{print $1}')
  printf "frontend.py PID: %d\n" "$pid"
}

run_tests() {
  pytest -rA --setup-show
}

"$@"
