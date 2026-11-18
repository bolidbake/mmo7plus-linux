# Maintainer: sena
pkgname=mmo7-config
pkgver=1.1.0
pkgrel=3
pkgdesc="Native Linux PyQt6 configurator for the Mad Catz M.M.O. 7+ gaming mouse"
arch=('any')
license=('MIT')
depends=('python' 'python-pyqt6')
makedepends=('python-build' 'python-installer' 'python-setuptools' 'python-wheel')
source=()

build() {
    cd "$startdir"
    rm -rf dist build *.egg-info
    python -m build --wheel --no-isolation
}

package() {
    cd "$startdir"
    python -m installer --destdir="$pkgdir" dist/*.whl

    # Install udev rule for non-root /dev/hidraw access
    install -Dm644 "99-madcatz-mmo7.rules" "$pkgdir/usr/lib/udev/rules.d/99-madcatz-mmo7.rules"

    # Install desktop launcher & application icon
    install -Dm644 "madcatz-mmo7.desktop" "$pkgdir/usr/share/applications/madcatz-mmo7.desktop"
    install -Dm644 "mmo7/assets/device.png" "$pkgdir/usr/share/pixmaps/madcatz-mmo7.png"
}
