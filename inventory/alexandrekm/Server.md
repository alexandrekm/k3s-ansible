**Version 10.2 - Updated on September 14, 2025**

This document covers the setup of the k3s Kubernetes cluster using Ansible playbooks from the `k3s-home-lab` repository. All configuration examples reference actual files in the repository rather than expanded code blocks. It assumes the Proxmox host, ZFS storage, and Ubuntu cloud image template are already configured.

### Infrastructure Prerequisites Summary

**Required Setup Before Cluster Deployment:**

1. **Proxmox Host and ZFS Storage**: Configured as detailed below
2. **Ubuntu Cloud Image Template**: Must be created before VM provisioning (see [Cloud Image Setup Guide](https://github.com/alexandrekm/k3s-home-lab/blob/main/alexandrekm-guides/cloud-image-setup.md))
3. **Network Configuration**: VLAN and IP addressing as specified
4. **SSH Keys**: Generated and configured for automation

**Server Hardware Specifications:**

- **CPU:** AMD EPYC (24 Cores, 48 Threads)
    
- **RAM:** 256 GB
    
- **GPU:** NVIDIA RTX 3060 (Available for GPU Passthrough to VMs)
    
- **Motherboard:** ASRock ROMED8-2T
    
- **Management:** IPMI available at `192.168.99.3`
    
- **Primary Network:** 2 x 10-Gigabit Ethernet (Intel X550-AT2)
    

**ZFS Storage Pool Overview:**

- **`rpool`:** 128GB SSD (Boot drive for Proxmox OS).
    
- **`vm-storage-mirrored`:** 2 x 1TB SSDs in a mirror (RAID-1). Intended for critical, redundant VMs like the k3s control plane.
    
- **`vm-storage-large`:** 1 x 4TB NVMe as a single drive. Intended for high-performance, non-redundant VMs like k3s workers, which will provide storage for Longhorn.
    
- **`bulk-storage`:** Mirrored 14TB HDDs. Intended for large data storage and as the target for VM backups.
    
- **`archive-storage`:** 2 x 8TB HDDs in a mirror (RAID-1). Intended for infrequently accessed data.
    

### 1. Unified Infrastructure as Code (IaC) Strategy

This plan centralizes all infrastructure tasks into a single private Git repository (`k3s-home-lab`), created by mirroring the official Axivo k3s-cluster project.

**1.1. Core Principles**

- **Single Source of Truth:** Your private `k3s-home-lab` repository contains all configuration.
    
- **Role-Based Architecture:** Ansible roles manage each component independently with a unified playbook structure.
    
- **GitOps Integration:** Argo CD manages applications deployed _on_ the cluster.
    
- **No Manual `kubectl`:** All changes are managed through Git and Ansible.
    

**1.2. Repository Structure**

The repository is organized with the following key directories:

- **`collections/`**: Contains [`requirements.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/collections/requirements.yaml) for required Ansible collections
- **`inventories/homelab/`**: Custom inventory structure with [`hosts.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/inventories/homelab/hosts.yaml) and group variables
- **`playbooks/`**: Custom Proxmox integration playbooks
- **`roles/`**: Ansible roles for each component (argo-cd, cert-manager, cilium, etc.)
- **`apps/`**: Application manifests organized by category (media, system)

**1.3. Ansible Playbook Workflow**

The repository uses a unified playbook structure with role-based execution:

1. **[`provisioning.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/provisioning.yaml):** Main deployment playbook with tag-based execution
   - `cluster` tag: Base system configuration (cluster role)
   - `kubernetes` tag: K3s installation with HAProxy/Keepalived (k3s and helm roles)  
   - `charts` tag: All application deployments (cilium, coredns, cert-manager, external-dns, argo-cd, kured, longhorn, metrics-server, victoria-logs, victoria-metrics)

2. **Supporting Playbooks:**
   - [`reset.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/reset.yaml): Complete cluster teardown and cleanup
   - [`upgrade.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/upgrade.yaml): Component-specific upgrade automation
   - [`validation.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/validation.yaml): Cluster configuration validation
   - [`vault.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/vault.yaml): Interactive vault management utility

3. **Custom Playbooks for Proxmox Integration:**
    - [`playbooks/provision-vms.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/playbooks/provision-vms.yaml): Creates the Proxmox VMs
    - [`playbooks/configure-bind-mounts.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/playbooks/configure-bind-mounts.yaml): Configures ZFS bind mounts
    - [`playbooks/configure-gpu-passthrough.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/playbooks/configure-gpu-passthrough.yaml): Configures GPU passthrough
    - [`playbooks/install-nvidia-drivers.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/playbooks/install-nvidia-drivers.yaml): Installs NVIDIA drivers on GPU workers
    - [`playbooks/configure-hostnames.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/playbooks/configure-hostnames.yaml): Sets proper hostnames for k3s VMs
    - [`playbooks/cluster-config.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/playbooks/cluster-config.yaml): Additional cluster configuration
    

**1.4. Initial Setup**

**1.4.1. Syncing Upstream Changes**

Keep your repository updated using the included sync script:

```bash
./sync_repo.sh
```

**1.4.2. Local Ansible Prerequisites**

Install required Ansible collections:

```bash
# Run this from the root of your k3s-home-lab repository
ansible-galaxy collection install -r collections/requirements.yaml
```

**1.4.3. Proxmox User and API Token**

Create a dedicated user and API token on Proxmox for Ansible to use.

1. **Create the Ansible User**
    
    - In the Proxmox UI, go to **Datacenter -> Permissions -> Users** and click **Add**.
        
    - User name: `ansible-user`, Realm: `Proxmox VE authentication server`. Add a strong password.
        
2. **Grant Permissions**
    
    - Go to **Datacenter -> Permissions** and click **Add -> User Permission**.
        
    - Path: `/`, User: `ansible-user@pve`, Role: `Administrator`.
        
3. **Create the API Token**
    
    - Go to **Datacenter -> Permissions -> API Tokens** and click **Add**.
        
    - User: `ansible-user@pve`, Token ID: `ansible-automation`.
        
    - **Important:** Uncheck the _Privilege Separation_ box.
        
    - Securely store the generated **Secret**.


**1.5. Playbook Execution Order**

The following is the recommended execution order for all playbooks during initial cluster setup:

**Phase 1: Infrastructure Setup (Proxmox Host Operations):**

1. **[`playbooks/provision-vms.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/playbooks/provision-vms.yaml)**: Creates all k3s VMs on Proxmox with proper resource allocation and network configuration
   ```bash
   ansible-playbook -v -i inventories/homelab/hosts.yaml playbooks/provision-vms.yaml --vault-password-file ./.vault-password
   ```

2. **[`playbooks/configure-bind-mounts.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/playbooks/configure-bind-mounts.yaml)**: Configures ZFS storage bind mounts to make bulk and archive storage available in VMs
   ```bash
   ansible-playbook -v -i inventories/homelab/hosts.yaml playbooks/configure-bind-mounts.yaml --vault-password-file ./.vault-password
   ```

3. **[`playbooks/configure-gpu-passthrough.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/playbooks/configure-gpu-passthrough.yaml)**: Configures GPU passthrough for CUDA workloads (run only if using GPU workers)
   ```bash
   ansible-playbook -v -i inventories/homelab/hosts.yaml playbooks/configure-gpu-passthrough.yaml --vault-password-file ./.vault-password
   ```

4. **[`playbooks/install-nvidia-drivers.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/playbooks/install-nvidia-drivers.yaml)**: Installs NVIDIA drivers and CUDA toolkit on GPU worker nodes
   ```bash
   ansible-playbook -v -i inventories/homelab/hosts.yaml playbooks/install-nvidia-drivers.yaml --vault-password-file ./.vault-password
   ```

5. **[`playbooks/configure-hostnames.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/playbooks/configure-hostnames.yaml)**: Sets proper hostnames and FQDNs for all k3s VMs
   ```bash
   ansible-playbook -v -i inventories/homelab/hosts.yaml playbooks/configure-hostnames.yaml --vault-password-file ./.vault-password
   ```

**Phase 2: Cluster Deployment (VM Operations):**

6. **Base System Configuration** - Configure all VMs with base system settings:
   ```bash
   ansible-playbook -v -i inventories/homelab/hosts.yaml provisioning.yaml --tags cluster --vault-password-file ./.vault-password
   ```

7. **Deploy Kubernetes Cluster** - Install k3s with HAProxy/Keepalived:
   ```bash
   ansible-playbook -v -i inventories/homelab/hosts.yaml provisioning.yaml --tags kubernetes --vault-password-file ./.vault-password
   ```

8. **Deploy Applications** - Install all cluster applications:
   ```bash
   ansible-playbook -v -i inventories/homelab/hosts.yaml provisioning.yaml --tags charts --vault-password-file ./.vault-password
   ```

**Phase 3: Post-Deployment Configuration:**

9. **[`playbooks/cluster-config.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/playbooks/cluster-config.yaml)**: Applies cluster-wide configurations including GPU device plugins, node taints, and labels (must run after cluster is deployed)
   ```bash
   ansible-playbook -v -i inventories/homelab/hosts.yaml playbooks/cluster-config.yaml --vault-password-file ./.vault-password
   ```

**Maintenance & Utility Playbooks:**

- **[`playbooks/resize-vm-disks.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/playbooks/resize-vm-disks.yaml)**: Resizes VM disks and expands filesystems (for capacity expansion)
- **[`playbooks/remove-vms.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/playbooks/remove-vms.yaml)**: Safely removes all k3s VMs with confirmation prompts (destructive operation)


### 2. Ansible Configuration & Execution

**2.1. Authentication Setup**

**Authentication Patterns Explained:**

1. **Proxmox Host Operations**:
   - Operations that run directly on the Proxmox host (10.10.10.10)
   - Examples: VM creation, ZFS bind mounts, disk resizing
   - Requires root access to manage hypervisor resources

2. **VM Operations** (uses `ansible-user` from inventory):
   - Operations that run on the created VMs (10.10.10.50+)
   - Examples: K3s installation, application deployment, cluster management
   - Uses the `ansible-user` configured in group variables and cloud-init

**Why This Distinction Matters:**
- **Cloud image template** sets up `ansible-user` with sudo privileges via cloud-init
- **Proxmox host** needs direct root access for hypervisor operations
- **VM operations** use the secure, non-root `ansible-user` with controlled sudo access

**2.2. Ansible Configuration Details**

You will modify the files within your cloned `k3s-home-lab` repository.

**2.2.1. Custom Inventory Structure**

The homelab inventory is configured in [`inventories/homelab/hosts.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/inventories/homelab/hosts.yaml). This file defines:

- **Proxmox host** configuration for VM provisioning
- **Control plane nodes** (k3s-master-1, k3s-master-2, k3s-master-3)
- **Worker nodes** (k3s-worker-1, k3s-worker-2, k3s-worker-3)
- **VPN workers** (k3s-worker-vpn-general, k3s-worker-vpn-brazil) for VPN-routed traffic
  - General VPN worker: 8 cores, 16GB RAM for standard VPN workloads
  - Brazil VPN worker: 2 cores, 4GB RAM for lightweight Brazil-specific VPN traffic
- **GPU workers** with flexible multi-GPU support:
  - NVIDIA GPU workers (currently k3s-worker-gpu-1)
  - Provisions for Intel and AMD GPU workers
  - Inventory GPU PCI binding: set gpu_pci_id per GPU worker in [hosts.yaml](inventories/homelab/hosts.yaml). This value is used by GPU passthrough tasks and driver installation. Example:
    - k3s-worker-gpu-1: gpu_pci_id: "47:00.0"
- **Group mappings** for repository compatibility

The inventory includes VM IDs for Proxmox integration and GPU PCI IDs for passthrough configuration.

**2.2.2. Group Variables**

The homelab configuration is defined in [`inventories/homelab/group_vars/all.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/inventories/homelab/group_vars/all.yaml), which includes:

- **Authentication** configuration with ansible user and encrypted passwords
- **K3s cluster** settings including API server configuration
- **Network configuration** with Cilium load balancer IP pools (10.10.10.100-254)
- **Application settings** for cert-manager, Longhorn, ArgoCD
- **External service credentials** (referenced from vault file)

**Key Differences from Upstream:**
- Uses `ansible-user` instead of `floren` for authentication
- Custom network scheme (10.10.10.x) instead of default ranges
- Homelab-specific inventory structure for Proxmox integration

**Network Configuration:**
- **Static Infrastructure Range**: 10.10.10.1-99
  - Gateway: 10.10.10.1
  - Proxmox Host: 10.10.10.10  
  - K3s Masters: 10.10.10.50-52
  - K3s Workers: 10.10.10.60-62, 65-66, 70-81
- **Dynamic Load Balancer Range**: 10.10.10.100-254
  - Cilium Load Balancer Pool: 10.10.10.100-254
  - First Ingress IP: 10.10.10.100
- **API Server**: 10.10.10.50:6443 (first master node)

**2.2.3. Encrypted Secrets**

Sensitive variables are stored in [`inventories/homelab/group_vars/all/vault.yml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/inventories/homelab/group_vars/all/vault.yml) and encrypted with ansible-vault. This includes:

- K3s cluster token
- Ansible user password
- Cloudflare API token for External DNS
- Other service credentials

Use ansible-vault to manage encrypted values:

```bash
# Encrypt a new secret
ansible-vault encrypt_string 'your-secret-value' --name 'variable_name'

# Edit vault file
ansible-vault edit inventories/homelab/group_vars/all/vault.yml

# Alternative: Use the interactive vault.yaml playbook for easier management
ansible-playbook vault.yaml --vault-password-file ./.vault-password
```

**2.3. Available Roles**

The [`roles/`](https://github.com/alexandrekm/k3s-home-lab/tree/main/roles) directory contains Ansible roles for each component:

- **Core Infrastructure**: `cluster`, `k3s`, `helm`
- **Networking**: `cilium`, `coredns`, `external-dns`
- **Security**: `cert-manager`
- **Storage**: `longhorn`
- **GitOps**: `argo-cd`
- **Monitoring**: `victoria-metrics`, `victoria-logs`, `metrics-server`
- **Maintenance**: `kured`

Each role includes documentation, defaults, tasks, templates, and validation.

**2.4. Custom Playbooks**

The [`playbooks/`](https://github.com/alexandrekm/k3s-home-lab/tree/main/playbooks) directory contains Proxmox-specific automation:

**VM Management:**
- [`provision-vms.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/playbooks/provision-vms.yaml): Creates Proxmox VMs with proper resource allocation and network configuration
- [`remove-vms.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/playbooks/remove-vms.yaml): Safely removes all k3s VMs with confirmation prompts (destructive operation)
- [`resize-vm-disks.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/playbooks/resize-vm-disks.yaml): Resizes VM disks and expands filesystems (for capacity expansion)

**System Configuration:**
- [`configure-bind-mounts.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/playbooks/configure-bind-mounts.yaml): Configures ZFS storage bind mounts to make bulk and archive storage available in VMs
- [`configure-gpu-passthrough.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/playbooks/configure-gpu-passthrough.yaml): Configures GPU passthrough for CUDA workloads (run only if using GPU workers)
- [`install-nvidia-drivers.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/playbooks/install-nvidia-drivers.yaml): Installs NVIDIA drivers and CUDA toolkit on GPU worker nodes
- [`configure-hostnames.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/playbooks/configure-hostnames.yaml): Sets proper hostnames and FQDNs for all k3s VMs
- [`cluster-config.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/playbooks/cluster-config.yaml): Applies cluster-wide configurations including GPU device plugins, node taints, and labels



### 3. Deployment Process

**⚠️ Prerequisites**: Before starting, ensure you have:
1. **Created the Ubuntu cloud image template** using the [Cloud Image Setup Guide](https://github.com/alexandrekm/k3s-home-lab/blob/main/alexandrekm-guides/cloud-image-setup.md)
2. **Configured Proxmox API access** with `ansible-user` and API token
3. **Generated SSH keys** and updated the inventory with your network settings

**🔑 Authentication Quick Reference:**
- **Vault password file**: All operations use `--vault-password-file ./.vault-password` for authentication
- **User selection**: Proxmox host operations use root (defined in inventory), VM operations use `ansible-user` from inventory
- **Why this approach**: Inventory defines the appropriate user for each target, vault password file provides secure credential access

**🔧 Proxmox Host Operations**

**3.1. VM Provisioning**

Create the VMs on Proxmox host:
```bash
ansible-playbook -v -i inventories/homelab/hosts.yaml playbooks/provision-vms.yaml --vault-password-file ./.vault-password
```

**3.2. Configure Storage Bind Mounts**

Set up ZFS storage access on Proxmox host:
```bash
ansible-playbook -v -i inventories/homelab/hosts.yaml playbooks/configure-bind-mounts.yaml --vault-password-file ./.vault-password
```

Note: The bind-mounts playbook now builds its VM target list dynamically from inventory groups [k3s_workers](inventories/homelab/hosts.yaml), [k3s_vpn_workers](inventories/homelab/hosts.yaml), and [k3s_nvidia_gpu_workers](inventories/homelab/hosts.yaml). Ensure all VMs that require bind mounts are present in these groups with their vmid defined.

**3.3. Configure GPU Passthrough**

Configure GPU passthrough for CUDA workloads (run only if using GPU workers):
```bash
ansible-playbook -v -i inventories/homelab/hosts.yaml playbooks/configure-gpu-passthrough.yaml --vault-password-file ./.vault-password
```

Note: GPU passthrough uses PCI addresses from inventory via gpu_pci_id on each GPU worker in [hosts.yaml](inventories/homelab/hosts.yaml). The playbooks iterate over [k3s_nvidia_gpu_workers](inventories/homelab/hosts.yaml). For multi-GPU environments, set gpu_pci_id per host accordingly.

**3.4. Remove All VMs (destructive)**

⚠️ **WARNING**: This permanently destroys all k3s VMs and their data:
```bash
ansible-playbook -v -i inventories/homelab/hosts.yaml playbooks/remove-vms.yaml --vault-password-file ./.vault-password
# You must type 'DELETE' when prompted to confirm
```

**🚀 VM/Cluster Operations**

**3.4. Base System Configuration**

Configure all VMs with base system settings:
```bash
ansible-playbook -v -i inventories/homelab/hosts.yaml provisioning.yaml --tags cluster --vault-password-file ./.vault-password
```

**⚠️ QEMU VM Compatibility:** When deploying on Proxmox QEMU VMs, use extra-vars to override hardware validation:
```bash
ansible-playbook -v -i inventories/homelab/hosts.yaml provisioning.yaml --tags cluster --vault-password-file ./.vault-password --extra-vars '{
  "cluster_vars": {
    "device": {"enabled": false, "id": "2:2", "name": "ASMedia Technology"},
    "hardware": {"architecture": "x86_64", "product": "QEMU"},
    "ssh": {"key": "id_ed25519.pub", "path": "/Users/alexandre/.ssh"}
  }
}'
```

**3.5. Configure Hostnames**

Set proper hostnames and FQDNs for all k3s VMs:
```bash
ansible-playbook -v -i inventories/homelab/hosts.yaml playbooks/configure-hostnames.yaml --vault-password-file ./.vault-password
```

**3.6. Install NVIDIA Drivers**

Install GPU drivers on GPU worker nodes:
```bash
ansible-playbook -v -i inventories/homelab/hosts.yaml playbooks/install-nvidia-drivers.yaml --vault-password-file ./.vault-password
```

Note: The NVIDIA driver tasks target [k3s_nvidia_gpu_workers](inventories/homelab/hosts.yaml). Verify your GPU workers are children of k3s_nvidia_gpu_workers.

**3.7. Deploy Kubernetes Cluster**

Install k3s with HAProxy/Keepalived:
```bash
ansible-playbook -v -i inventories/homelab/hosts.yaml provisioning.yaml --tags kubernetes --vault-password-file ./.vault-password
```

**3.7. Deploy Applications**

Install all cluster applications:
```bash
ansible-playbook -v -i inventories/homelab/hosts.yaml provisioning.yaml --tags charts --vault-password-file ./.vault-password
```

**3.8. Apply Cluster Configuration**

Apply cluster-wide configurations including GPU device plugins, node taints, and labels:
```bash
ansible-playbook -v -i inventories/homelab/hosts.yaml playbooks/cluster-config.yaml --vault-password-file ./.vault-password
```

**3.9. Complete Deployment (All Steps)**

Deploy everything at once (excludes Proxmox host operations):
```bash
ansible-playbook -v -i inventories/homelab/hosts.yaml provisioning.yaml --vault-password-file ./.vault-password
```

**3.10. Reset Cluster (if needed)**

Complete cluster teardown:
```bash
ansible-playbook -v -i inventories/homelab/hosts.yaml reset.yaml --vault-password-file ./.vault-password
```

**3.11. Additional Maintenance Commands**

**Component Upgrades:**
```bash
# Upgrade specific component (requires component name as tag)
ansible-playbook -v -i inventories/homelab/hosts.yaml upgrade.yaml --tags cilium --vault-password-file ./.vault-password

# Available component tags: argo-cd, cert-manager, cilium, cluster, coredns, external-dns, helm, k3s, kured, longhorn, metrics-server, victoria-logs, victoria-metrics
```

**Configuration Validation:**
```bash
# Validate entire cluster configuration (validation tag is required)
ansible-playbook -v -i inventories/homelab/hosts.yaml validation.yaml --tags validation --vault-password-file ./.vault-password

# Validate specific component
ansible-playbook -v -i inventories/homelab/hosts.yaml validation.yaml --tags validation,longhorn --vault-password-file ./.vault-password
```

**Vault Management:**
```bash
# Interactive utility for managing encrypted variables
ansible-playbook vault.yaml --vault-password-file ./.vault-password
# Options: 1) List encrypted variables, 2) Encrypt new variable, 3) Update global password
```

### 2.5. Variable Override Techniques

**2.5.1. QEMU VM Hardware Validation Override**

When deploying on QEMU VMs (Proxmox), the default cluster role expects Raspberry Pi hardware, causing device validation failures. Use `--extra-vars` to override these role defaults:

**Problem:** The `cluster` role defaults in [`roles/cluster/defaults/main.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/roles/cluster/defaults/main.yaml) define:
```yaml
cluster_vars:
  device:
    enabled: true      # Looks for USB hardware
    name: "Raspberry Pi"
  hardware:
    architecture: aarch64  # ARM architecture
    product: "Raspberry Pi"
```

**Solution:** Override with QEMU-compatible settings using `--extra-vars`:
```bash
# Working extra-vars for QEMU VMs
ansible-playbook provisioning.yaml --tags cluster --vault-password-file ./.vault-password --extra-vars '{
  "cluster_vars": {
    "device": {
      "enabled": false,
      "id": "2:2", 
      "name": "ASMedia Technology"
    },
    "hardware": {
      "architecture": "x86_64",
      "product": "QEMU"
    },
    "ssh": {
      "key": "id_ed25519.pub",
      "path": "/Users/alexandre/.ssh"
    }
  }
}'
```

**2.5.2. Variable Precedence in Ansible**

Understanding Ansible variable precedence is crucial for successful overrides:

1. **Role defaults** (lowest precedence) - `roles/*/defaults/main.yaml`
2. **Group variables** - `inventories/homelab/group_vars/all.yaml`
3. **Host variables** - `inventories/homelab/host_vars/hostname.yaml`
4. **Extra variables** (highest precedence) - `--extra-vars`

**Key Insight:** Role defaults with complex nested structures (like `cluster_vars`) cannot be reliably overridden by group variables. The `--extra-vars` approach provides the highest precedence and ensures complete variable replacement.

**2.5.3. When to Use Extra Variables**

Use `--extra-vars` for:
- **Hardware compatibility**: Overriding role defaults for different hardware platforms
- **Environment-specific overrides**: Development vs production configurations  
- **Troubleshooting**: Temporarily testing different variable values
- **Complex nested variables**: When group_vars partial overrides don't work

**Example scenarios:**
```bash
# Override for Intel/AMD hardware instead of Raspberry Pi
--extra-vars '{"cluster_vars": {"hardware": {"architecture": "x86_64", "product": "QEMU"}}}'

# Disable device validation entirely
--extra-vars '{"cluster_vars": {"device": {"enabled": false}}}'

# Test different SSH key configurations
--extra-vars '{"cluster_vars": {"ssh": {"key": "id_rsa.pub", "path": "/custom/path"}}}'
```

**2.5.4. Best Practices for Variable Overrides**

1. **Document overrides**: Always document why extra-vars are needed in comments
2. **Test incrementally**: Use `--check` mode to validate before applying
3. **Consistent JSON format**: Use valid JSON syntax for complex structures
4. **Version control**: Consider creating override files for reusable configurations
5. **Minimal overrides**: Only override necessary values, inherit defaults where possible

    

### 3. Cluster Foundation Architecture

**3.1. Key Components**

The Axivo k3s-cluster includes these components:

- **K3s:** Lightweight Kubernetes with embedded etcd for HA
- **HAProxy + Keepalived:** Built into k3s role for API server load balancing
- **Cilium:** Advanced CNI with eBPF and Gateway API (replaces default networking)
- **CoreDNS:** Internal DNS resolution
- **External DNS:** Automatic external DNS record management with Cloudflare
- **Cert-Manager:** TLS certificate automation with Let's Encrypt
- **Longhorn:** Distributed storage for persistent volumes
- **Argo CD:** GitOps application deployment
- **VictoriaMetrics/VictoriaLogs:** Observability stack for metrics and logs
- **Kured:** Coordinated node reboots for maintenance

**3.2. Networking Architecture**

- **CNI:** Cilium with eBPF data plane (replaces kube-proxy)
- **Ingress:** Cilium Gateway API (not traditional Ingress controllers)
- **Load Balancer:** Cilium L2 announcements with configurable IP pool
- **DNS:** External DNS with Cloudflare integration for automatic subdomain management
    

**3.3. Longhorn Storage**

- **Installation:** Deployed via the longhorn role in the charts phase
- **How it Works:** Longhorn pools local storage from worker VMs to create a distributed block storage layer, providing replicated, persistent volumes for stateful applications
- **Features:** Volume replication, backup/restore, disaster recovery with web UI
    

**3.4. Accessing Bulk Storage with Bind Mounts**

To make ZFS pools available inside Kubernetes, we pass them from the Proxmox host into all worker VMs. Pods scheduled on these workers can then access the storage using a `hostPath` volume.

1. **Proxmox Host: Verify ZFS Permissions (Manual Check)** This is a one-time manual check to ensure containers can write to the storage.
    
    ```
    # Assign ownership to nobody:nogroup (UID/GID 65534)
    chown -R nobody:nogroup /bulk-storage /archive-storage
    chmod -R 777 /bulk-storage /archive-storage
    ```
    
2. **Proxmox Host: Configure Bind Mounts (Automated)** The `configure-bind-mounts.yaml` playbook safely stops all worker VMs, adds the mount points to their configs, and restarts them.
    

**3.5. Backup and Recovery Strategy**

- **VM Backups:** A daily Proxmox `vzdump` job backs up all VM disks to the `bulk-storage` ZFS pool for disaster recovery.
    
- **Configuration Backup:** The `k3s-home-lab` Git repository is a complete, version-controlled backup of all cluster and application configurations.
    

### 4. GitOps and CI/CD Strategy

**4.1. The GitOps Workflow**

1. **Infrastructure Change:** A change to an Ansible playbook triggers the GitHub Actions workflow to update the cluster.
    
2. **Application Change:** A change to a manifest in the `apps/` directory is pushed to Git.
    
3. **Automatic Sync:** Argo CD detects the change and automatically syncs the application in the cluster to match the new state in Git.
    

**4.2. GitHub Actions Workflow**

The repository includes a sophisticated release workflow that provides:

- **Automatic Documentation:** Updates README files when role configurations change
- **Version Management:** Handles semantic versioning for components  
- **Issue Tracking:** Creates issues for failed workflows
- **Template Processing:** Uses Handlebars for dynamic content generation

The workflow is triggered by changes to role configurations and automatically maintains documentation consistency.

**4.3. Automated Dependency Updates with Renovate**

Renovate Bot monitors the repository for new Docker image versions and creates Pull Requests. The configuration is defined in [`renovate.json`](https://github.com/alexandrekm/k3s-home-lab/blob/main/renovate.json) and includes:

- Monitoring of Kubernetes manifests in the `apps/` directory
- Grouping of Docker dependency updates
- Automatic detection of outdated container images

**Note:** Use specific image tags (e.g., `:4.3.2`), not `:latest` for proper version tracking.

**4.4. Managing Secrets in a GitOps World**

**You must never commit plain-text secrets to Git.** Manifests in Git should reference Kubernetes `Secret` objects that are created and managed in the cluster separately, outside of the GitOps workflow.

### 5. Exposing Applications with Gateway API and TLS

With Cilium Gateway API and Cert-Manager, you can securely expose applications with automatic HTTPS.

- **How it Works:** You point a DNS record to the Cilium load balancer IP. A Kubernetes `HTTPRoute` manifest tells Cilium how to route traffic for that domain. Cert-Manager automatically obtains TLS certificates from Let's Encrypt and integrates with External DNS for DNS-01 challenges.

- **Architecture Difference:** Uses Gateway API (successor to Ingress) with Cilium's eBPF-based load balancing instead of traditional ingress controllers.
    

### 6. Application Structure

Applications are organized in the [`apps/`](https://github.com/alexandrekm/k3s-home-lab/tree/main/apps) directory using a structured approach:

**Media Stack:** [`apps/media/`](https://github.com/alexandrekm/k3s-home-lab/tree/main/apps/media)
- **[`namespace.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/apps/media/namespace.yaml):** Media namespace definition
- **[`plex/`](https://github.com/alexandrekm/k3s-home-lab/tree/main/apps/media/plex):** Complete Plex media server setup with:
  - [`deployment.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/apps/media/plex/deployment.yaml): Application deployment with GPU transcoding support
  - [`service.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/apps/media/plex/service.yaml): Service definition
  - [`pvc.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/apps/media/plex/pvc.yaml): Persistent volume claims for media storage
  - [`httproute.yaml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/apps/media/plex/httproute.yaml): Gateway API routing configuration
- **[`sonarr/`](https://github.com/alexandrekm/k3s-home-lab/tree/main/apps/media/sonarr):** TV series management with same structure
- **[`sabnzbd/`](https://github.com/alexandrekm/k3s-home-lab/tree/main/apps/media/sabnzbd):** Usenet downloader with VPN routing

**System Components:** [`apps/system/`](https://github.com/alexandrekm/k3s-home-lab/tree/main/apps/system)
- **[`amd-gpu-plugin-config.yml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/apps/system/amd-gpu-plugin-config.yml):** AMD GPU plugin configuration
- **[`intel-gpu-plugin-config.yml`](https://github.com/alexandrekm/k3s-home-lab/blob/main/apps/system/intel-gpu-plugin-config.yml):** Intel GPU plugin configuration

All applications use the same structure with deployment, service, storage, and routing manifests. Deploy using ArgoCD for GitOps automation.

### 7. Verification and Health Checks

**Check Cluster Status:**
```bash
ssh root@10.10.10.50 "kubectl get nodes -o wide"
```

**Check Application Pods:**
```bash
ssh root@10.10.10.50 "kubectl get pods -A"
```

**Check GPU Resources:**
```bash
ssh root@10.10.10.70 "nvidia-smi"
ssh root@10.10.10.50 "kubectl describe node k3s-worker-gpu-1"
```

**Check Storage:**
```bash
ssh root@10.10.10.60 "df -h /data /archive"
```

**VM Management:**
```bash
# List all VMs on Proxmox
ssh root@10.10.10.10 "qm list"

# Check VM status by group
ssh root@10.10.10.10 "qm list | grep -E '(101|102|103|201|202|203|205|301)'"

# Verify template exists
ssh root@10.10.10.10 "qm config 9000"
```

### 8. Key Components

The cluster includes these components deployed via Ansible roles:

- **[`k3s`](https://github.com/alexandrekm/k3s-home-lab/tree/main/roles/k3s):** Lightweight Kubernetes with embedded etcd for HA
- **[`cilium`](https://github.com/alexandrekm/k3s-home-lab/tree/main/roles/cilium):** Advanced CNI with eBPF and Gateway API (replaces kube-proxy)
- **[`coredns`](https://github.com/alexandrekm/k3s-home-lab/tree/main/roles/coredns):** Internal DNS resolution
- **[`external-dns`](https://github.com/alexandrekm/k3s-home-lab/tree/main/roles/external-dns):** Automatic DNS record management with Cloudflare
- **[`cert-manager`](https://github.com/alexandrekm/k3s-home-lab/tree/main/roles/cert-manager):** TLS certificate automation with Let's Encrypt
- **[`longhorn`](https://github.com/alexandrekm/k3s-home-lab/tree/main/roles/longhorn):** Distributed storage for persistent volumes
- **[`argo-cd`](https://github.com/alexandrekm/k3s-home-lab/tree/main/roles/argo-cd):** GitOps application deployment
- **[`victoria-metrics`](https://github.com/alexandrekm/k3s-home-lab/tree/main/roles/victoria-metrics):** Metrics collection and storage
- **[`victoria-logs`](https://github.com/alexandrekm/k3s-home-lab/tree/main/roles/victoria-logs):** Log aggregation and analysis
- **[`metrics-server`](https://github.com/alexandrekm/k3s-home-lab/tree/main/roles/metrics-server):** Resource metrics for HPA/VPA
- **[`kured`](https://github.com/alexandrekm/k3s-home-lab/tree/main/roles/kured):** Coordinated node reboots for maintenance
- **[`helm`](https://github.com/alexandrekm/k3s-home-lab/tree/main/roles/helm):** Package manager for Kubernetes

### 9. Network Configuration

- **Load Balancer IP Pool:** 10.10.10.100 - 10.10.10.254
- **Ingress IP:** 10.10.10.100
- **API Server:** 10.10.10.50:6443
- **Domain:** `lab.alexkm.me` (managed by External DNS)

### 10. Storage Configuration

- **Longhorn:** Distributed block storage from worker node local disks
- **Bind Mounts:** ZFS pools mounted as `/data` and `/archive` in worker VMs
- **Backup Target:** `bulk-storage` ZFS pool for VM backups

## Architecture Summary & Key Differences

### 🚀 **Implementation Notes**

1. **Separate Inventory:** Uses `inventories/homelab/` to avoid upstream conflicts
2. **Original Network Scheme:** Maintains your original 10.10.10.x IP addresses  
3. **Enhanced Worker Configuration:** 3 general workers + 1 VPN worker + 1 GPU worker (5 total workers)
4. **Complete Playbook Set:** Includes all essential playbooks (VM provisioning, bind mounts, NVIDIA drivers, cluster config)
5. **Dual Group Structure:** Maps your custom groups to repository structure for compatibility
6. **Universal Bind Mounts:** All worker VMs get access to bulk and archive storage
7. **Domain Structure:** All services use `lab.alexkm.me` subdomains with automatic DNS/TLS
8. **Complete Application Examples:** Full Helm-style manifests with deployment, service, routing, and storage
9. **DNS Integration:** Configure Cloudflare API token for External DNS automation
10. **Storage:** Longhorn provides distributed storage; bind mounts for bulk storage access
11. **Applications:** Use `apps/` directory structure for GitOps with Argo CD
12. **Certificates:** Automatic TLS with cert-manager and Let's Encrypt integration

**Directory Structure:**
```
k3s-home-lab/
├── apps/                           # Application manifests
│   ├── media/                      # Media applications (Plex, Sonarr, SABnzbd)
│   └── system/                     # System configurations (GPU plugins)
├── collections/
│   └── requirements.yaml           # Ansible collection dependencies
├── alexandrekm-guides/              # Personal homelab guides
│   ├── Server.md                   # Complete homelab setup documentation
│   └── cloud-image-setup.md        # Ubuntu cloud image preparation guide
├── inventories/
│   └── homelab/                    # Custom homelab inventory
│       ├── hosts.yaml              # Host definitions and VM IDs
│       └── group_vars/
│           ├── all.yaml            # Main configuration variables
│           └── all/
│               └── vault.yml       # Encrypted secrets
├── inventory/
│   └── cluster/                    # Default cluster inventory
├── playbooks/                      # Custom Proxmox integration playbooks
│   ├── provision-vms.yaml          # VM creation and configuration
│   ├── remove-vms.yaml             # VM removal with safety checks
│   ├── configure-bind-mounts.yaml  # ZFS storage bind mounts
│   ├── install-nvidia-drivers.yaml # GPU driver installation
│   ├── configure-gpu-passthrough.yaml
│   ├── cluster-config.yaml
│   └── resize-vm-disks.yaml
├── roles/                          # Ansible roles for each component
│   ├── argo-cd/                    # GitOps application deployment
│   ├── cert-manager/               # TLS certificate automation
│   ├── cilium/                     # Advanced CNI with eBPF
│   ├── cluster/                    # Base system configuration
│   ├── coredns/                    # Internal DNS resolution
│   ├── external-dns/               # External DNS management
│   ├── helm/                       # Helm package manager
│   ├── k3s/                        # Kubernetes cluster
│   ├── kured/                      # Node reboot coordination
│   ├── longhorn/                   # Distributed storage
│   ├── metrics-server/             # Resource metrics
│   ├── victoria-logs/              # Log aggregation
│   └── victoria-metrics/           # Metrics collection
├── provisioning.yaml               # Main deployment playbook
├── reset.yaml                      # Cluster teardown
├── upgrade.yaml                    # Cluster upgrade automation
├── validation.yaml                 # Cluster validation
├── vault.yaml                      # Vault management
└── sync_repo.sh                    # Upstream sync script
```

This configuration combines sophisticated k3s cluster automation with Proxmox integration, GPU support, and network configuration while maintaining separation from the upstream repository. All examples reference actual repository files for accurate implementation.
