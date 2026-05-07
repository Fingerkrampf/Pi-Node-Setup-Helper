#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pi Node Setup Helper - Web Application v13.0
Supports Windows
Copyright by Fingerkrampf 2026
"""

import subprocess, os, sys, platform, threading, time, json, re, uuid, webbrowser
import requests as req_lib

CURRENT_VERSION = "13.0"
GH_REPO = "Fingerkrampf/Pi-Node-Setup-Helper" # GitHub Repository

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

try:
    from tkinter import filedialog, Tk, Toplevel, Label, Button
    import tkinter.font as tkFont
except ImportError:
    filedialog = None

try:
    import paramiko
except ImportError:
    paramiko = None

# ── OS Detection ──
CURRENT_OS = platform.system()
IS_WINDOWS = CURRENT_OS == "Windows"
ARCH = platform.machine()

if IS_WINDOWS:
    import ctypes
    import winreg

from flask import Flask, render_template, jsonify, request, Response

# ── Constants ──
DEFAULT_PORTS_TCP = "31400-31409"
DEFAULT_PORTS_UDP = "51820"
URLS = {
    "wsl_kernel": "https://wslstorestorage.blob.core.windows.net/wslblob/wsl_update_x64.msi",
    "wireguard_installer": "https://download.wireguard.com/windows-client/wireguard-installer.exe",
    "docker_releases_page": "https://docs.docker.com/desktop/release-notes/",
    "pi_node_api_latest_release": "https://api.github.com/repos/pi-node/pi-node/releases/latest",
}
WIREGUARD_CLIENT_NAME = "pivpnclient"

def get_default_download_dir():
    # Primary choice: User's Downloads folder
    home_downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    if os.path.isdir(home_downloads):
        return home_downloads
    # Fallback: Current working directory
    return os.getcwd()

# ── Config Persistence ──
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "download_dir": get_default_download_dir(),
    "ssh_ip": "",
    "ssh_port": "22",
    "ssh_user": "root",
    "telemetry_url": "http://217.154.250.218:8080",
    "node_id": "unknown"
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        cfg = DEFAULT_CONFIG.copy()
        cfg["node_id"] = str(uuid.uuid4()) # Fresh ID for this machine
        save_config(cfg)
        return cfg
    
    cfg = DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, 'r') as f:
            loaded = json.load(f)
            cfg.update(loaded)
    except: pass
    
    # Validation: Ensure download_dir exists, otherwise reset to default
    if not os.path.isdir(cfg.get("download_dir", "")):
        cfg["download_dir"] = get_default_download_dir()
    
    return cfg

def save_config(cfg):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(cfg, f, indent=4)
    except: pass

config = load_config()
if config.get("node_id") in [None, "", "unknown"]:
    config["node_id"] = str(uuid.uuid4())
    save_config(config)

INSTALLER_FILENAMES = {
    "wsl_setup": "wsl_update_x64.msi",
    "docker": "DockerDesktopInstaller.exe",
    "pi_node": "PiNetworkSetup.exe",
    "wireguard_client": "wireguard-installer.exe",
}

COMPONENTS_DOWNLOAD_URLS = {
    "wsl_setup": URLS["wsl_kernel"],
    "docker": "https://www.docker.com/products/docker-desktop/",
    "pi_node": "https://minepi.com/pi-node/",
    "wireguard_client": "https://www.wireguard.com/install/",
}

# ── Translations ──
def load_translations():
    try:
        # Fixed path for bundled file
        with open(resource_path("translations.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[!] Error loading translations: {e}")
        return {}

LANGUAGES = load_translations()

# ── System Helpers ──
def is_admin():
    if IS_WINDOWS:
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False
    else:
        return False

def run_cmd(command, shell=True):
    try:
        kwargs = dict(shell=shell, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        if IS_WINDOWS:
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(command, **kwargs)
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return -1, "", "Command not found"
    except Exception as e:
        report_telemetry_error({"type": "cmd_error", "command": str(command), "error": str(e)})
        return -1, "", str(e)

try:
    import psutil
except ImportError:
    psutil = None

def get_system_specs():
    """ Collects anonymized hardware specifications for telemetry. """
    specs = {
        "cpu_count": "unknown",
        "ram_gb": "unknown",
        "is_vm": "no",
        "os_version": platform.version()
    }
    if psutil:
        try:
            specs["cpu_count"] = psutil.cpu_count(logical=True)
            specs["ram_gb"] = round(psutil.virtual_memory().total / (1024**3), 2)
        except: pass
    
    # Simple VM detection
    try:
        vm_indicators = ['hyper-v', 'vmware', 'virtualbox', 'kvm', 'xen']
        uname = platform.uname().version.lower() + " " + platform.uname().release.lower()
        if any(x in uname for x in vm_indicators):
            specs["is_vm"] = "yes"
    except: pass
    return specs

def _send_telemetry_async(url, payload):
    """ Helper to send telemetry in a background thread without crashing if the server is down. """
    def worker():
        try:
            req_lib.post(url, json=payload, timeout=5)
        except:
            pass
    threading.Thread(target=worker, daemon=True).start()

def report_telemetry_error(error_data):
    """ Sends an error report from the Python backend to the telemetry server. """
    try:
        url = config.get("telemetry_url", "http://217.154.250.218:8080") + "/api/telemetry/error"
        payload = {
            **error_data,
            "version": CURRENT_VERSION,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "nodeId": config.get("node_id", "unknown"),
            "os": platform.system(),
            "arch": platform.machine(),
            "source": "python_backend",
            "metadata": get_system_specs()
        }
        # Non-blocking safe send
        _send_telemetry_async(url, payload)
    except:
        pass

def report_telemetry_event(event_name, event_data=None):
    """ Sends an event report from the Python backend to the telemetry server. """
    try:
        url = config.get("telemetry_url", "http://217.154.250.218:8080") + "/api/telemetry/event"
        payload = {
            "event": event_name,
            "version": CURRENT_VERSION,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "nodeId": config.get("node_id", "unknown"),
            "os": platform.system(),
            "arch": platform.machine(),
            "source": "python_backend",
            "metadata": {
                **(event_data or {}),
                **get_system_specs()
            }
        }
        if event_data:
            payload.update(event_data)
        # Non-blocking safe send
        _send_telemetry_async(url, payload)
    except:
        pass

def download_file(url, save_path):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        with req_lib.get(url, stream=True, headers=headers) as r:
            r.raise_for_status()
            with open(save_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return True
    except Exception:
        return False

def version_to_tuple(v):
    """ Converts a version string like '10.0.1' into a tuple (10, 0, 1) for safe comparison. """
    try:
        # Regex to find all numbers in the version string
        nums = re.findall(r'\d+', str(v))
        return tuple(int(n) for n in nums)
    except:
        return (0,)
class TaskManager:

    # ═══ CHECK FUNCTIONS ═══

    def check_wsl(self):
        _, out1, _ = run_cmd("dism.exe /online /Get-FeatureInfo /FeatureName:Microsoft-Windows-Subsystem-Linux")
        wsl_ok = "State : Enabled" in out1 or "Status : Aktiviert" in out1
        _, out2, _ = run_cmd("dism.exe /online /Get-FeatureInfo /FeatureName:VirtualMachinePlatform")
        vm_ok = "State : Enabled" in out2 or "Status : Aktiviert" in out2
        return wsl_ok and vm_ok

    def check_hibernate(self):
        _, out, _ = run_cmd("powercfg /a")
        is_disabled = "Hibernation" in out and ("not been enabled" in out or "nicht aktiviert" in out or "not available" in out)
        return not is_disabled

    def check_program_installed(self, name_sub):
        return self._find_uninstaller_win(name_sub) is not None

    def check_firewall(self):
        # Check if BOTH TCP and UDP rules exist
        c1, _, _ = run_cmd('netsh advfirewall firewall show rule name="PiNodePorts-TCP"')
        c2, _, _ = run_cmd('netsh advfirewall firewall show rule name="PiNodePorts-UDP"')
        return c1 == 0 and c2 == 0

    def check_wireguard_keys(self):
        return os.path.exists(os.path.join(os.path.expanduser("~"), "wireguard_client_keys.json"))

    def check_wireguard_server(self):
        wg_path = self._get_wg_path_win()
        if not wg_path:
            return False
        wg_exe = os.path.join(wg_path, "wg.exe")
        if not os.path.exists(wg_exe):
            return False
        code, out, _ = run_cmd(f'"{wg_exe}" show')
        return code == 0 and "latest handshake" in out

    def check_pi_node_container(self):
        # We check for running containers with specific names
        # Patterns: Testnet1, Testnet2, Community, Mainnet
        code, out, _ = run_cmd('docker ps --format "{{.Names}}" --filter "status=running"')
        if code != 0:
            return False
        
        running_names = out.lower().splitlines()
        patterns = ["testnet1", "testnet2", "community", "mainnet"]
        
        for name in running_names:
            name = name.strip()
            if not name:
                continue
            for p in patterns:
                if p in name:
                    return True
        return False

    def _get_installer_path(self, task_name):
        fname = INSTALLER_FILENAMES.get(task_name)
        if not fname: return None
        
        d_dir = config.get('download_dir', '')
        if not d_dir or not os.path.isdir(d_dir):
             return None

        def is_ready(p):
            if not os.path.exists(p): return False
            try:
                # Try to open for appending (will fail on Windows if locked)
                with open(p, 'ab'):
                    pass
                # Check for reasonable minimum size (50KB for tiny installers)
                if os.path.getsize(p) < 50 * 1024:
                     return False
                return True
            except:
                return False

        # Try exact filename first
        exact_path = os.path.join(d_dir, fname)
        if is_ready(exact_path):
            return exact_path

        # Fuzzy matching for common installers
        try:
            files = os.listdir(d_dir)
            potential_path = None
            if task_name == "pi_node":
                for f in files:
                    fl = f.lower()
                    if (("pi" in fl and "network" in fl) or fl.startswith("pinode")) and fl.endswith(('.exe', '.dmg')):
                         potential_path = os.path.join(d_dir, f)
                         break
            elif task_name == "docker":
                 for f in files:
                    fl = f.lower()
                    if "docker" in fl and "desktop" in fl and fl.endswith(('.exe', '.dmg')):
                        potential_path = os.path.join(d_dir, f)
                        break
            elif task_name == "wireguard_client":
                 for f in files:
                    fl = f.lower()
                    if "wireguard" in fl and fl.endswith(('.exe', '.msi')):
                        potential_path = os.path.join(d_dir, f)
                        break
            elif task_name == "wsl_setup":
                 for f in files:
                    fl = f.lower()
                    if "wsl" in fl and "update" in fl and fl.endswith('.msi'):
                        potential_path = os.path.join(d_dir, f)
                        break
            
            if potential_path and is_ready(potential_path):
                return potential_path
        except: pass

        return None

    # ═══ ACTION FUNCTIONS ═══

    def _normalize_ports(self, p_str, platform="linux"):
        if not p_str: return ""
        # Support space or comma as delimiters. Normalize to comma.
        p_str = p_str.replace(" ", ",").replace(";", ",")
        parts = [p.strip() for p in p_str.split(",") if p.strip()]
        if platform == "linux":
             # iptables uses : for ranges
             return ",".join([p.replace("-", ":") for p in parts])
        else:
             # windows uses - for ranges
             return ",".join([p.replace(":", "-") for p in parts])


    def setup_wsl(self, log_fn=None):
        log = log_fn or (lambda m: None)
            
        # PHASE 2: After reboot
        if config.get("wsl_phase") == 2:
            msi = self._get_installer_path("wsl_setup")
            if msi:
                log(f"Installing {os.path.basename(msi)} (WSL2-Kernel)...")
                import tempfile
                with tempfile.NamedTemporaryFile("w", suffix=".bat", delete=False) as bat:
                    bat.write('@echo off\n')
                    bat.write('title Phase 2 - Linux Kernel Update\n')
                    bat.write('color 0b\n')
                    bat.write('echo ========================================================\n')
                    bat.write('echo Phase 2: Linux Kernel Update Installation\n')
                    bat.write('echo ========================================================\n')
                    bat.write('echo.\n')
                    bat.write('echo Please press ENTER to confirm and install the update...\n')
                    bat.write('pause >nul\n')
                    bat.write('echo.\n')
                    bat.write('echo Installing...\n')
                    bat.write(f'msiexec.exe /i "{msi}" /qn\n')
                    bat.write('echo.\n')
                    bat.write('echo Installation complete. Closing...\n')
                    bat.write('ping 127.0.0.1 -n 3 >nul\n')
                    bat_path = bat.name
                
                subprocess.run(f'cmd.exe /c "{bat_path}"', creationflags=subprocess.CREATE_NEW_CONSOLE)
                try:
                    os.remove(bat_path)
                except:
                    pass
                time.sleep(1)
            
            log("Updating WSL...")
            # Running this multiple times for safety
            run_cmd("wsl --update")
            
            log("Cleaning up Phase 2 flag...")
            config.pop("wsl_phase", None)
            save_config(config)
            
            log("WSL Setup Phase 2 completed. You can continue with Step 2.")
            return
            
        # PHASE 1: Enable Features
        for feat in ["Microsoft-Windows-Subsystem-Linux", "VirtualMachinePlatform"]:
            log(f"Activating {feat}...")
            run_cmd(f"dism.exe /online /enable-feature /featurename:{feat} /all /norestart")
        
        log("Preparing for Step 1 Phase 2...")
        config["wsl_phase"] = 2
        save_config(config)
        
        log("WSL features enabled. A system restart is REQUIRED now.")
        log("Please start this program manually after the restart to finish Step 1.")

    def deactivate_wsl(self, log_fn=None):
        log = log_fn or (lambda m: None)
        log("Deactivating WSL features...")
        run_cmd("dism.exe /online /disable-feature /featurename:Microsoft-Windows-Subsystem-Linux /norestart")
        run_cmd("dism.exe /online /disable-feature /featurename:VirtualMachinePlatform /norestart")
        run_cmd("wsl --uninstall")
        log("WSL features deactivated. A restart is required.")

    def deactivate_hibernate(self, log_fn=None):
        log = log_fn or (lambda m: None)
        log("Deactivating hibernation...")
        run_cmd("powercfg /hibernate off")
        log("Hibernation deactivated.")

    def activate_hibernate(self, log_fn=None):
        log = log_fn or (lambda m: None)
        log("Activating hibernation...")
        run_cmd("powercfg /hibernate on")
        log("Hibernation activated.")

    def install_docker(self, log_fn=None):
        log = log_fn or (lambda m: None)
        exe = self._get_installer_path("docker")
        if exe:
            log("Installing Docker Desktop...")
            run_cmd(f'"{exe}" install --quiet')
            dpath = os.path.join(os.environ.get("ProgramW6432", r"C:\Program Files"), "Docker", "Docker", "Docker Desktop.exe")
            self._set_autostart_win("Docker Desktop", dpath)
            if os.path.exists(dpath):
                run_cmd(f'start "" "{dpath}"')
            log("Docker Desktop installed successfully.")
        else:
            log("DockerDesktopInstaller.exe not found in download folder.")

    def uninstall_docker(self, log_fn=None):
        log = log_fn or (lambda m: None)
        cmd = self._find_uninstaller_win("docker desktop")
        if cmd:
            log("Uninstalling Docker Desktop...")
            run_cmd(cmd)
            log("Docker Desktop uninstalled.")
        else:
            log("Docker Desktop uninstaller not found.")

    def install_pi_node(self, log_fn=None):
        log = log_fn or (lambda m: None)
        path = self._get_installer_path("pi_node")
        if path:
            log("Installing Pi Node...")
            run_cmd(f'"{path}" /S')
            log("Pi Node installed successfully.")
        else:
            log("PiNetworkSetup.exe not found in download folder.")

    def uninstall_pi_node(self, log_fn=None):
        log = log_fn or (lambda m: None)
        cmd = self._find_uninstaller_win("pi network")
        if cmd:
            log("Uninstalling Pi Node...")
            run_cmd(cmd)
            log("Pi Node uninstalled.")
        else:
            log("Pi Node uninstaller not found.")

    def activate_firewall(self, log_fn=None):
        log = log_fn or (lambda m: None)
        tcp_ports = config.get("tcp_ports", DEFAULT_PORTS_TCP)
        udp_ports = config.get("udp_ports", DEFAULT_PORTS_UDP)
        
        rule_tcp = "PiNodePorts-TCP"
        rule_udp = "PiNodePorts-UDP"
        
        win_tcp = self._normalize_ports(tcp_ports, "windows")
        win_udp = self._normalize_ports(udp_ports, "windows")

        log(f"Creating firewall rules for TCP {win_tcp}...")
        run_cmd(f'netsh advfirewall firewall add rule name="{rule_tcp}" dir=in action=allow protocol=TCP localport={win_tcp}')
        run_cmd(f'netsh advfirewall firewall add rule name="{rule_tcp}" dir=out action=allow protocol=TCP localport={win_tcp}')
        log(f"Creating firewall rules for UDP {win_udp}...")
        run_cmd(f'netsh advfirewall firewall add rule name="{rule_udp}" dir=in action=allow protocol=UDP localport={win_udp}')
        run_cmd(f'netsh advfirewall firewall add rule name="{rule_udp}" dir=out action=allow protocol=UDP localport={win_udp}')
        log("Firewall rules created. Don't forget port forwarding on your router!")

    def delete_firewall(self, log_fn=None):
        log = log_fn or (lambda m: None)
        log("Deleting firewall rules...")
        run_cmd('netsh advfirewall firewall delete rule name="PiNodePorts-TCP"')
        run_cmd('netsh advfirewall firewall delete rule name="PiNodePorts-UDP"')
        log("Firewall rules deleted.")

    def install_wireguard(self, log_fn=None):
        log = log_fn or (lambda m: None)
        exe = self._get_installer_path("wireguard_client")
        if exe:
            log("Installing WireGuard...")
            run_cmd(f'"{exe}" /S')
            wg_dir = self._get_wg_path_win()
            if wg_dir:
                self._set_autostart_win("WireGuard", os.path.join(wg_dir, "wireguard.exe"))
            log("WireGuard installed successfully.")
        else:
            log("wireguard-installer.exe not found in download folder.")

    def uninstall_wireguard(self, log_fn=None):
        log = log_fn or (lambda m: None)
        cmd = self._find_uninstaller_win("wireguard")
        if cmd:
            log("Uninstalling WireGuard...")
            run_cmd(cmd)
            log("WireGuard uninstalled.")
        else:
            log("WireGuard uninstaller not found.")

    def generate_keys(self, log_fn=None):
        log = log_fn or (lambda m: None)
        kf = os.path.join(os.path.expanduser("~"), "wireguard_client_keys.json")
        if os.path.exists(kf):
            log("Keys already exist.")
            return
        keys = self._generate_wg_keys()
        if keys:
            with open(kf, 'w') as f:
                json.dump(keys, f)
            log("WireGuard keys generated successfully.")
        else:
            log("Failed to generate keys. Is WireGuard installed?")

    def delete_keys(self, log_fn=None):
        log = log_fn or (lambda m: None)
        kf = os.path.join(os.path.expanduser("~"), "wireguard_client_keys.json")
        if os.path.exists(kf):
            os.remove(kf)
            log("WireGuard keys deleted.")
        else:
            log("No keys to delete.")

    def configure_server(self, ssh_ip, ssh_user, ssh_pass, ssh_port=22, mode='auto', log_fn=None):
        log = log_fn or (lambda m: None)
        if not paramiko:
            log("paramiko module not available.")
            return
        
        do_wipe = (mode == 'wipe')
        tcp_ports = config.get("tcp_ports", DEFAULT_PORTS_TCP)
        udp_ports = config.get("udp_ports", DEFAULT_PORTS_UDP)
        
        fw_tcp = self._normalize_ports(tcp_ports, "linux")
        fw_udp = self._normalize_ports(udp_ports, "linux")

        kf = os.path.join(os.path.expanduser("~"), "wireguard_client_keys.json")
        if not os.path.exists(kf):
            log("Local WireGuard keys not found. Please generate first.")
            return
        with open(kf, 'r') as f:
            client_keys = json.load(f)

        client_name = WIREGUARD_CLIENT_NAME
        cpk = client_keys['public']

        script = f"""#!/usr/bin/env bash
# Pi Node Setup Helper v13.0 - Server Script
set -e
exec 2>&1
echo "--- WireGuard Peer Setup Start ---"

if [[ $EUID -ne 0 ]]; then echo "ERROR: Must be root." >&2; exit 1; fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -y || true
apt-get install -y wireguard iptables-persistent curl
update-alternatives --set iptables /usr/sbin/iptables-legacy 2>/dev/null || true

DO_WIPE={str(do_wipe).lower()}
SERVER_CONFIG_FILE="/etc/wireguard/wg0.conf"
CLIENT_NAME="{client_name}"
CLIENT_PUBLIC_KEY="{cpk}"
FW_TCP="{fw_tcp}"
FW_UDP="{fw_udp}"
SSH_PORT="{ssh_port}"

if [[ "$DO_WIPE" == "true" ]]; then
    echo "WIPING existing configuration..."
    wg-quick down wg0 2>/dev/null || true
    rm -f /etc/wireguard/wg0.conf /etc/wireguard/server_private.key /etc/wireguard/server_public.key /etc/wireguard/*.conf
    iptables -F; iptables -t nat -F; iptables -X; iptables -t nat -X || true
fi

# Ensure basic dirs and keys
mkdir -p /etc/wireguard; chmod 700 /etc/wireguard; umask 077
if [ ! -f /etc/wireguard/server_private.key ]; then
    wg genkey | tee /etc/wireguard/server_private.key | wg pubkey > /etc/wireguard/server_public.key
fi

DEFAULT_INTERFACE=$(ip -4 route get 8.8.8.8 | awk '{{print $5; exit}}')
SIP=$(curl -4 -s https://ifconfig.me || hostname -I | awk '{{print $1}}')
SPK=$(cat /etc/wireguard/server_private.key)

if [ ! -f "$SERVER_CONFIG_FILE" ]; then
    echo "Creating new wg0.conf..."
    cat <<EOF > "$SERVER_CONFIG_FILE"
[Interface]
Address = 192.168.200.1/24
ListenPort = 51820
PrivateKey = $SPK
PostUp = iptables -A FORWARD -i %i -j ACCEPT; iptables -t nat -A POSTROUTING -o $DEFAULT_INTERFACE -j MASQUERADE; iptables -A INPUT -i %i -j ACCEPT; iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu
PostDown = iptables -D FORWARD -i %i -j ACCEPT 2>/dev/null || true; iptables -t nat -D POSTROUTING -o $DEFAULT_INTERFACE -j MASQUERADE 2>/dev/null || true; iptables -D INPUT -i %i -j ACCEPT 2>/dev/null || true; iptables -t mangle -D FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu 2>/dev/null || true
MTU = 1390
EOF
    wg-quick up wg0 || true
    systemctl enable wg-quick@wg0 || true
fi

# Ensure interface is up
if ! ip link show wg0 >/dev/null 2>&1; then wg-quick up wg0 || true; fi

# Peer addition
if ! grep -q "$CLIENT_PUBLIC_KEY" "$SERVER_CONFIG_FILE"; then
    echo "Adding new peer to config..."
    LAST_IP=$(grep "AllowedIPs" "$SERVER_CONFIG_FILE" | cut -d. -f4 | cut -d/ -f1 | sort -n | tail -1)
    NEXT_IP=$((LAST_IP > 1 ? LAST_IP + 1 : 2))
    CVIP="192.168.200.$NEXT_IP"
    cat <<EOF >> "$SERVER_CONFIG_FILE"

[Peer]
# Name = $CLIENT_NAME
PublicKey = $CLIENT_PUBLIC_KEY
AllowedIPs = $CVIP/32
EOF
    wg set wg0 peer "$CLIENT_PUBLIC_KEY" allowed-ips "$CVIP/32"
else
    # If peer already exists, retrieve its assigned IP
    CVIP=$(grep -A 5 "$CLIENT_PUBLIC_KEY" "$SERVER_CONFIG_FILE" | grep "AllowedIPs" | head -1 | awk '{{print $3}}' | cut -d/ -f1)
fi

CLIENT_VPN_IP=$CVIP
CVIP_TARGET=$CLIENT_VPN_IP
echo "Assigned Client IP: $CVIP_TARGET"

# Setting up advanced firewall rules
iptables -P INPUT ACCEPT
iptables -P FORWARD ACCEPT
iptables -P OUTPUT ACCEPT
iptables -F
iptables -t nat -F
iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -i "$DEFAULT_INTERFACE" -p udp --dport 51820 -j ACCEPT
iptables -A INPUT -p icmp -j ACCEPT
iptables -A INPUT -p tcp --dport $SSH_PORT -j ACCEPT
iptables -A INPUT -i wg0 -j ACCEPT
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -P INPUT DROP
iptables -A FORWARD -i wg0 -o "$DEFAULT_INTERFACE" -j ACCEPT 
iptables -A FORWARD -i "$DEFAULT_INTERFACE" -o wg0 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
# Port Forwarding for Pi Node (TCP)
iptables -t nat -A PREROUTING -i "$DEFAULT_INTERFACE" -p tcp -m multiport --dports $FW_TCP -j DNAT --to-destination $CLIENT_VPN_IP
# NOTE: UDP forwarding of 51820 removed in v13.0 to prevent server-side conflict
iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu
iptables -P FORWARD ACCEPT

sysctl -w net.ipv4.ip_forward=1 > /dev/null
sysctl -w net.ipv4.conf.all.rp_filter=2 > /dev/null
sysctl -w net.ipv4.conf.default.rp_filter=2 > /dev/null
[ ! -f /etc/sysctl.d/99-pivpn.conf ] && echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-pivpn.conf
echo "net.ipv4.conf.all.rp_filter=2" >> /etc/sysctl.d/99-pivpn.conf
echo "net.ipv4.conf.default.rp_filter=2" >> /etc/sysctl.d/99-pivpn.conf
echo "iptables-persistent iptables-persistent/autosave_v4 boolean true" | debconf-set-selections
echo "iptables-persistent iptables-persistent/autosave_v6 boolean true" | debconf-set-selections
netfilter-persistent save || true

# Generate Client Config for download
SPUB=$(cat /etc/wireguard/server_public.key)
CCF="/etc/wireguard/$CLIENT_NAME.conf"
cat <<EOF > "$CCF"
[Interface]
PrivateKey = CLIENT_PRIVATE_KEY_PLACEHOLDER
Address = $CVIP_TARGET/24
DNS = 1.1.1.1, 8.8.8.8
MTU = 1390

[Peer]
PublicKey = $SPUB
Endpoint = $SIP:51820
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
EOF

wg-quick down wg0 2>/dev/null || true; wg-quick up wg0
echo "CLIENT_CONFIG_PATH:$CCF"
echo "--- WireGuard Peer Setup Complete ---"
"""
        rsp = f"/tmp/setup_{client_name}.sh"
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            log(f"Connecting to server {ssh_ip}:{ssh_port}...")
            client.connect(ssh_ip, port=ssh_port, username=ssh_user, password=ssh_pass, timeout=15)
            log("Uploading setup script...")
            with client.open_sftp() as sftp:
                with sftp.file(rsp, 'w') as f:
                    f.write(script)
                sftp.chmod(rsp, 0o755)
            log("Executing setup script (this may take several minutes)...")
            stdin, stdout, stderr = client.exec_command(f"sudo -S bash {rsp}", get_pty=True)
            stdin.write(ssh_pass + '\n')
            stdin.flush()
            full_output = ""
            for line in iter(stdout.readline, ""):
                log(line.rstrip())
                full_output += line
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                err = stderr.read().decode('utf-8', errors='ignore')
                log(f"STDERR: {err}")
                raise Exception(f"Script failed (exit code {exit_status}).")
            conf_match = [l for l in full_output.splitlines() if l.startswith("CLIENT_CONFIG_PATH:")]
            if not conf_match:
                raise Exception("Could not find config path in output.")
            remote_conf = conf_match[0].split(":", 1)[1].strip()
            log("Downloading client configuration...")
            wg_path = self._get_wg_path_win()
            if not wg_path:
                raise Exception("Local WireGuard installation not found.")
            local_tmp = os.path.join(wg_path, "Data", "Configurations", f"{client_name}.conf.tmp")
            
            # Ensure local directory exists
            os.makedirs(os.path.dirname(local_tmp), exist_ok=True)
            
            with client.open_sftp() as sftp:
                sftp.get(remote_conf, local_tmp)
            log("Customizing local configuration...")
            with open(local_tmp, 'r') as f:
                content = f.read()
            updated = content.replace("CLIENT_PRIVATE_KEY_PLACEHOLDER", client_keys['private'])
            final = os.path.join(wg_path, "Data", "Configurations", f"{client_name}.conf")
            with open(final, 'w') as f:
                f.write(updated)
            os.remove(local_tmp)
            log("Restarting WireGuard service...")
            wg_exe = os.path.join(wg_path, "wireguard.exe")
            run_cmd('taskkill /f /im wireguard.exe')
            time.sleep(1)
            run_cmd(f'"{wg_exe}" /uninstallservice {client_name}')
            time.sleep(1)
            run_cmd(f'"{wg_exe}" /installservice "{final}"')
            time.sleep(1)
            run_cmd(f'start "" "{wg_exe}"')


            log("Cleaning up remote files...")
            s2, _, _ = client.exec_command(f"sudo -S rm {rsp} {remote_conf}", get_pty=True)
            s2.write(ssh_pass + '\n')
            s2.flush()
            
            # Connection Verification
            self._show_activation_popup()
            log("Verifying connection (waiting for handshake)...")
            connection_ok = False
            for _ in range(15):
                if self.check_wireguard_server():
                    connection_ok = True
                    break
                time.sleep(1)
            
            if connection_ok:
                log("\nWireGuard setup completed successfully!")
                log("The tunnel is ACTIVE and a handshake has been established.")
            else:
                log("\nError: WireGuard setup finished, but NO HANDSHAKE detected.")
                log("Please check if UDP Port 51820 is open on your server firewall.")
        except Exception as e:
            log(f"\nAn error occurred: {e}")
        finally:
            client.close()

    def _show_activation_popup(self):
        """ Shows a modal popup with large text to remind the user to activate WireGuard. """
        try:
            root = Tk()
            root.withdraw()
            
            top = Toplevel(root)
            top.title("WireGuard Aktivierung")
            top.attributes('-topmost', True)
            
            # Popup size and style
            top.geometry("650x400")
            top.configure(bg='#ffffff')

            # Center window on screen
            top.update_idletasks()
            width = top.winfo_width()
            height = top.winfo_height()
            x = (top.winfo_screenwidth() // 2) - (width // 2)
            y = (top.winfo_screenheight() // 2) - (height // 2)
            top.geometry(f'+{x}+{y}')

            title_font = tkFont.Font(family="Helvetica", size=22, weight="bold")
            msg_font = tkFont.Font(family="Helvetica", size=16)
            btn_font = tkFont.Font(family="Helvetica", size=14, weight="bold")

            # Header
            Label(top, text="FAST GESCHAFFT!", font=title_font, bg='#ffffff', fg='#1a73e8', pady=25).pack()
            
            # Content
            msg = ("Bitte klicken Sie jetzt im WireGuard Client auf 'Aktivieren',\n\n"
                   "damit sich der Client mit dem Server verbindet und\n"
                   "so einen IPv4 Tunnel aufbauen kann.")
            
            Label(top, text=msg, font=msg_font, bg='#ffffff', justify="center", padx=40).pack(expand=True)
            
            def on_ok():
                top.destroy()
                root.destroy()
            
            # Button
            btn = Button(top, text="OK - Ich habe auf Aktivieren geklickt", command=on_ok, 
                         font=btn_font, bg='#1a73e8', fg='white', padx=30, pady=15, 
                         relief="flat", cursor="hand2")
            btn.pack(pady=40)
            
            # UI focus and blocking
            top.protocol("WM_DELETE_WINDOW", on_ok)
            top.focus_force()
            top.mainloop()
        except Exception as e:
            print(f"[!] Warning: Could not show activation popup: {e}")

    # ═══ PRIVATE HELPERS ═══

    def _generate_wg_keys(self):
        wg_path = self._get_wg_path_win()
        if not wg_path:
            return None
        wg_exe = os.path.join(wg_path, "wg.exe")
        if not os.path.exists(wg_exe):
            return None
        try:
            priv = subprocess.check_output(f'"{wg_exe}" genkey', shell=True, creationflags=subprocess.CREATE_NO_WINDOW).decode('utf-8').strip()
            pub = subprocess.check_output(f'echo {priv} | "{wg_exe}" pubkey', shell=True, creationflags=subprocess.CREATE_NO_WINDOW).decode('utf-8').strip()
            return {"private": priv, "public": pub}
        except Exception:
            return None

    def _set_autostart_win(self, name, path):
        if not IS_WINDOWS:
            return
        
        def set_run_key(hive, subkey):
            try:
                with winreg.OpenKey(hive, subkey, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, path)
                return True
            except Exception:
                return False

        # Try HKEY_LOCAL_MACHINE first since we probably have admin rights
        if set_run_key(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"):
            return
        
        # Fallback to HKEY_CURRENT_USER
        set_run_key(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run")

    def _remove_autostart_win(self, name):
        if not IS_WINDOWS:
            return
        
        def del_run_key(hive, subkey):
            try:
                with winreg.OpenKey(hive, subkey, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, name)
            except Exception:
                pass
        
        del_run_key(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run")
        del_run_key(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run")

    def _find_uninstaller_win(self, name_sub):
        if not IS_WINDOWS:
            return None
        name_sub = name_sub.lower()
        keys = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]
        for hive, kp in keys:
            try:
                with winreg.OpenKey(hive, kp) as key:
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            sn = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, sn) as sk:
                                dn = winreg.QueryValueEx(sk, "DisplayName")[0]
                                if name_sub in dn.lower():
                                    us = winreg.QueryValueEx(sk, "UninstallString")[0]
                                    if "msiexec" in us.lower():
                                        us = re.sub(r'/I', '/X', us, flags=re.IGNORECASE)
                                        if "/quiet" not in us and "/qn" not in us:
                                            us += " /quiet /norestart"
                                    elif "/S" not in us.upper() and "/SILENT" not in us.upper():
                                        us += " /S"
                                    return us
                        except OSError:
                            continue
            except FileNotFoundError:
                continue
        return None

    def _get_wg_path_win(self):
        if not IS_WINDOWS:
            return ""
        keys = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]
        for hive, kp in keys:
            try:
                with winreg.OpenKey(hive, kp) as key:
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            sn = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, sn) as sk:
                                dn = winreg.QueryValueEx(sk, "DisplayName")[0]
                                if "wireguard" in dn.lower():
                                    ip = winreg.QueryValueEx(sk, "InstallLocation")[0]
                                    if ip and os.path.isdir(ip) and os.path.exists(os.path.join(ip, "wireguard.exe")):
                                        return ip
                        except OSError:
                            continue
            except FileNotFoundError:
                continue
        for pf in ["ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"]:
            pp = os.environ.get(pf)
            if pp:
                p = os.path.join(pp, "WireGuard")
                if os.path.isdir(p) and os.path.exists(os.path.join(p, "wireguard.exe")):
                    return p
        return ""

    def _get_latest_docker_url_win(self):
        try:
            r = req_lib.get(URLS["docker_releases_page"])
            r.raise_for_status()
            m = re.search(r'(https://desktop\.docker\.com/win/main/amd64/[\d\.]+/Docker%20Desktop%20Installer\.exe)', r.text)
            return m.group(1) if m else None
        except Exception:
            return None

    def _get_latest_pi_node_url(self):
        try:
            r = req_lib.get(URLS["pi_node_api_latest_release"])
            r.raise_for_status()
            data = r.json()
            for asset in data.get('assets', []):
                name = asset.get('name', '').lower()
                if IS_WINDOWS and name.endswith('.exe'):
                    return asset.get('browser_download_url')
            return None
        except Exception:
            return None


# ── Flask App ──
app = Flask(__name__, 
            template_folder=resource_path("templates"),
            static_folder=resource_path("static"))
tm = TaskManager()
operation_logs = {}
operation_lock = threading.Lock()

TASKS_ORDER = [
    "wsl_setup", "hibernate", "firewall", "docker",
    "pi_node", "wireguard_client", "wireguard_keys", "wireguard_server"
]

TASK_DEFINITIONS = {
    "wsl_setup":        {"type": "activate", "check": tm.check_wsl,
                         "action": tm.setup_wsl, "uninstall": tm.deactivate_wsl},
    "hibernate":        {"type": "activate", "check": tm.check_hibernate,
                         "action": tm.deactivate_hibernate, "uninstall": None},
    "firewall":         {"type": "activate", "check": tm.check_firewall,
                         "action": tm.activate_firewall, "uninstall": tm.delete_firewall},
    "docker":           {"type": "install",  "check": lambda: tm.check_program_installed("docker desktop"),
                         "action": tm.install_docker, "uninstall": tm.uninstall_docker},
    "pi_node":          {"type": "install",  "check": lambda: tm.check_program_installed("pi network"),
                         "action": tm.install_pi_node, "uninstall": tm.uninstall_pi_node},
    "wireguard_client": {"type": "install",  "check": lambda: tm.check_program_installed("wireguard"),
                         "action": tm.install_wireguard, "uninstall": tm.uninstall_wireguard},
    "wireguard_keys":   {"type": "generate", "check": tm.check_wireguard_keys,
                         "action": tm.generate_keys, "uninstall": tm.delete_keys},
    "wireguard_server": {"type": "configure","check": tm.check_wireguard_server,
                         "action": None, "uninstall": None},
}


def get_system_lang():
    try:
        import locale
        lang, _ = locale.getlocale()
        if lang and lang.lower().startswith('de'):
            return 'de'
    except:
        pass
    return 'en'

@app.route('/')
def index():
    return render_template('index.html', 
                          version=CURRENT_VERSION, 
                          system_lang=get_system_lang(),
                          node_id=config.get('node_id', 'unknown'),
                          telemetry_url=config.get('telemetry_url', 'http://217.154.250.218:8080'))


@app.route('/api/status')
def get_status():
    statuses = {}
    for name in TASKS_ORDER:
        try:
            active = TASK_DEFINITIONS[name]["check"]()
        except Exception:
            active = False
        
        # Check if installer is present
        installer_ready = tm._get_installer_path(name) is not None
        
        statuses[name] = {
            "active": active,
            "type": TASK_DEFINITIONS[name]["type"],
            "has_uninstall": TASK_DEFINITIONS[name].get("uninstall") is not None,
            "installer_ready": installer_ready,
            "download_url": COMPONENTS_DOWNLOAD_URLS.get(name)
        }
    return jsonify({
        "admin": is_admin(), 
        "os": CURRENT_OS, 
        "arch": ARCH, 
        "tasks": statuses, 
        "config": config,
        "wsl_phase": config.get("wsl_phase"),
        "pi_node_container_running": tm.check_pi_node_container()
    })


@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    global config
    if request.method == 'POST':
        data = request.json
        changed = False
        if 'download_dir' in data:
            config['download_dir'] = data['download_dir']
            changed = True
        if 'tcp_ports' in data:
            config['tcp_ports'] = data['tcp_ports']
            changed = True
        if 'udp_ports' in data:
            config['udp_ports'] = data['udp_ports']
            changed = True
        if 'ssh_ip' in data:
            config['ssh_ip'] = data['ssh_ip']
            changed = True
        if 'ssh_port' in data:
            config['ssh_port'] = data['ssh_port']
            changed = True
        if 'ssh_user' in data:
            config['ssh_user'] = data['ssh_user']
            changed = True
        
        if changed:
            save_config(config)
            return jsonify({"ok": True, "config": config})
    return jsonify(config)


@app.route('/api/config/pick_dir', methods=['POST'])
def pick_directory():
    global config
    if not filedialog:
        return jsonify({"error": "Tkinter not available"}), 500
    
    try:
        # Create a hidden root window for the dialog
        root = Tk()
        root.withdraw()
        root.attributes('-topmost', True) # Bring to front
        root.lift()
        root.focus_force()
        
        selected_dir = filedialog.askdirectory(initialdir=config['download_dir'], title="Select Download Folder")
        root.destroy()
        
        if selected_dir:
            selected_dir = os.path.normpath(selected_dir)
            config['download_dir'] = selected_dir
            save_config(config)
            return jsonify({"ok": True, "config": config})
        else:
            return jsonify({"ok": False, "message": "No directory selected"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/config/open_dir', methods=['POST'])
def open_directory():
    global config
    try:
        d = config.get('download_dir')
        if d and os.path.isdir(d):
            if IS_WINDOWS:
                subprocess.Popen(f'explorer "{os.path.normpath(d)}"', shell=True)
                return jsonify({"ok": True})
            else:
                return jsonify({"error": "Only supported on Windows"}), 400
        else:
            return jsonify({"error": "Directory does not exist"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/tasks/check_wg', methods=['POST'])
def check_wg_exists():
    data = request.json
    ip = data.get('ip')
    user = data.get('user')
    pw = data.get('pass')
    port = int(data.get('port', 22))
    # Save credentials (except password) to config
    config['ssh_ip'] = ip
    config['ssh_user'] = user
    config['ssh_port'] = str(port)
    save_config(config)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(ip, port=port, username=user, password=pw, timeout=10)
        stdin, stdout, stderr = client.exec_command("[ -f /etc/wireguard/wg0.conf ] && echo EXISTS")
        out = stdout.read().decode().strip()
        return jsonify({"exists": out == "EXISTS"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        client.close()


@app.route('/api/update_check')
def check_for_updates():
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/releases/latest"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = req_lib.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            latest_tag = data.get('tag_name', '').lower().strip()
            latest_version_str = latest_tag.replace('v', '').strip()
            assets = data.get('assets', [])
            has_installer = any(a.get('name', '').lower().endswith(('.exe', '.dmg')) for a in assets)
            latest_tuple = version_to_tuple(latest_version_str)
            current_tuple = version_to_tuple(CURRENT_VERSION)
            if latest_tuple > current_tuple and has_installer:
                return jsonify({
                    "update_available": True,
                    "latest_version": latest_version_str,
                    "url": data.get('html_url')
                })
        return jsonify({"update_available": False})
    except Exception as e:
        return jsonify({"update_available": False})


@app.route('/api/action/<task_name>', methods=['POST'])
def handle_action(task_name):
    try:
        if task_name not in TASK_DEFINITIONS:
            return jsonify({"error": "Task not found"}), 404
        
        data = request.json or {}
        action_type = data.get("action_type", "action")
        
        if action_type == "action" and task_name == "wireguard_server":
            ip = data.get('ip')
            user = data.get('user')
            port = data.get('port', 22)
            if ip and user:
                config['ssh_ip'] = ip
                config['ssh_user'] = user
                config['ssh_port'] = str(port)
                save_config(config)

        op_id = str(uuid.uuid4())
        with operation_lock:
            operation_logs[op_id] = {"messages": [], "done": False}

        def log_fn(msg):
            with operation_lock:
                if op_id in operation_logs:
                    operation_logs[op_id]["messages"].append(msg)

        def worker():
            report_telemetry_event("task_started", {"task": task_name, "action": action_type})
            has_failed = False
            last_err = ""

            def intercept_log(msg):
                nonlocal has_failed, last_err
                log_fn(msg)
                if "error" in msg.lower() or "failed" in msg.lower():
                    has_failed = True
                    last_err = msg

            try:
                if task_name == "wireguard_server" and action_type == "action":
                    ip = data.get('ip')
                    user = data.get('user')
                    pw = data.get('pass')
                    port = int(data.get('port', 22))
                    mode = data.get('mode', 'auto')
                    tm.configure_server(ip, user, pw, ssh_port=port, mode=mode, log_fn=intercept_log)
                else:
                    task_def = TASK_DEFINITIONS[task_name]
                    action_fn = task_def.get("uninstall") if action_type == "uninstall" else task_def.get("action")
                    if action_fn:
                        action_fn(log_fn=intercept_log)
                    else:
                        intercept_log(f"Error: Action '{action_type}' not implemented for {task_name}.")
                
                if has_failed:
                    report_telemetry_event("task_failed", {"task": task_name, "action": action_type, "error": last_err})
                else:
                    report_telemetry_event("task_completed", {"task": task_name, "action": action_type})
            except Exception as e:
                intercept_log(f"Critical error in worker thread: {e}")
                report_telemetry_event("task_failed", {"task": task_name, "action": action_type, "error": str(e)})
            finally:
                with operation_lock:
                    if op_id in operation_logs:
                        operation_logs[op_id]["done"] = True

        threading.Thread(target=worker, daemon=True).start()
        return jsonify({"op_id": op_id})
    except Exception as e:
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


@app.route('/api/logs/<op_id>')
def stream_logs(op_id):
    def generate():
        idx = 0
        while True:
            with operation_lock:
                op = operation_logs.get(op_id)
                if not op:
                    yield f"data: {json.dumps({'error': 'Not found'})}\n\n"
                    break
                msgs = op["messages"][idx:]
                idx = len(op["messages"])
                done = op["done"]
            for m in msgs:
                yield f"data: {json.dumps({'log': m})}\n\n"
            if done:
                yield f"data: {json.dumps({'done': True})}\n\n"
                time.sleep(5)
                with operation_lock:
                    operation_logs.pop(op_id, None)
                break
            time.sleep(0.3)
    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/api/translations/<lang_code>')
def get_translations(lang_code):
    if lang_code not in LANGUAGES:
        lang_code = "en"
    return jsonify(LANGUAGES[lang_code])


@app.route('/api/qr_code')
def get_qr_code():
    try:
        local_path = os.path.join(os.path.dirname(sys.executable), "qr_code.txt")
        if not os.path.exists(local_path):
            local_path = resource_path("qr_code.txt")
            if not os.path.exists(local_path):
                local_path = "qr_code.txt"

        with open(local_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content or "[PLEASE_INSERT_BASE64_QR_CODE_HERE]" in content:
                 return jsonify({"ok": False, "message": "No QR code set"}), 404
            if not content.startswith("data:image"):
                 content = f"data:image/png;base64,{content}"
            return jsonify({"ok": True, "base64": content})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/restart', methods=['POST'])
def restart_system():
    run_cmd("shutdown /r /t 5")
    return jsonify({"ok": True})

last_heartbeat = time.time()

@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    global last_heartbeat
    last_heartbeat = time.time()
    return jsonify({"ok": True})

@app.route('/api/shutdown', methods=['POST'])
def shutdown_app():
    threading.Thread(target=lambda: (time.sleep(1), os._exit(0))).start()
    return jsonify({"ok": True})

def shutdown_checker():
    while True:
        time.sleep(5)
        if time.time() - last_heartbeat > 15:
            os._exit(0)

if __name__ == '__main__':
    if not is_admin():
        print(f"[!] WARNING: Running without admin privileges.")
    
    print(f"[*] Pi Node Setup Helper v{CURRENT_VERSION} - Windows ({ARCH})")
    print("    Open http://localhost:5000 in your browser")

    report_telemetry_event("app_started_backend")
    threading.Thread(target=shutdown_checker, daemon=True).start()

    try:
        def open_browser():
            time.sleep(1.5)
            webbrowser.open("http://localhost:5000")
        threading.Thread(target=open_browser, daemon=True).start()
    except: pass

    try:
        from waitress import serve
        print("    [!] Running production WSGI server (Waitress)")
        serve(app, host='127.0.0.1', port=5000, threads=8)
    except ImportError:
        app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)
