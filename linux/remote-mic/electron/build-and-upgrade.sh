#!/usr/bin/env bash
set -euo pipefail
here="$(cd -- "$(dirname -- "$0")" && pwd)"
bash "$here/build-deb.sh"
version="$(node -p "require('$here/package.json').version")"
package="$here/dist/xiaomi-remote-control_"$version"_amd64.deb"
test -r "$package"
name="$(dpkg-deb -f "$package" Package)"
arch="$(dpkg-deb -f "$package" Architecture)"
if [[ "$name" != "xiaomi-remote-control" || "$arch" != "amd64" ]]; then
 echo "Package identity mismatch; refused" >&2;exit 2
fi
if command -v pkexec >/dev/null 2>&1; then
 pkexec --disable-internal-agent /usr/bin/dpkg -i "$package"
elif sudo -n true 2>/dev/null; then
 sudo /usr/bin/dpkg -i "$package"
else
 echo "Cannot install automatically without local administrator authorization." >&2;exit 3
fi
installed="$(dpkg-query -W xiaomi-remote-control | awk '{print $2}')"
test "$installed" = "$version"
echo "Upgrade verified: xiaomi-remote-control $installed"
