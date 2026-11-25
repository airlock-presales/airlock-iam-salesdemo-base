provider "libvirt" {
  uri = "qemu+sshcmd://${var.platform_kvm.user}@${var.platform_kvm.host}/system"
}
