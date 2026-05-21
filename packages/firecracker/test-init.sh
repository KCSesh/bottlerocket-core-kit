#!/bin/sh
# Minimal init for Firecracker test microVM
# Creates a rootfs with busybox when run with: create-rootfs /path/to/output.ext4
# Or runs as /sbin/init inside the VM

case "$0" in
  */init|*/sbin/init)
    # Running as init inside the VM
    mount -t proc proc /proc
    mount -t sysfs sys /sys
    echo "=== Hello from Firecracker microVM! ==="
    echo "Kernel: $(cat /proc/version)"
    echo "Uptime: $(cat /proc/uptime)"
    exec /bin/sh -l
    ;;
esac
