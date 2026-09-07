#!/usr/bin/env bash
set -euo pipefail
printf 'EIRA2_TRANSPORT_V5=RETIRED\n'
printf 'REDIRECT=EIRA2_INSTALL_CLEAN_TRANSPORT_V6.sh\n'
exec bash -c "$(curl -fsSL https://raw.githubusercontent.com/domenicleonetti8-dev/ish-broadcast/master/EIRA2_INSTALL_CLEAN_TRANSPORT_V6.sh)"
