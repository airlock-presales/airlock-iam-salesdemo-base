locals {
    # --- Fixed by release, not configurable per instance ---
    talos_version               = "1.14.1"
    k8s_version                 = "1.35.4"

    # disk sizes in GB
    disk_size_system            = 40
    disk_size_data              = 10

    # --- Defaults for optional settings ---
    vm_timezone                 = "Europe/Zurich"
    vm_ntp_servers              = ["pool.ntp.org", "time.cloudflare.com"]
}
