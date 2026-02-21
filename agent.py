"""
CANAVAR Monitor - Agent
Diğer PC'lerde çalışır, sistem bilgisi toplar ve Master'a rapor eder.
"""

import json
import os
import platform
import socket
import subprocess
import sys
import threading
import time
import zipfile
from datetime import datetime, timedelta

import psutil
import requests

# ─── Config ──────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "agent_config.json")
VERSION_FILE = os.path.join(BASE_DIR, "..", "version.txt")
BEACON_PORT = 50005
HEARTBEAT_INTERVAL = 10  # seconds
COMMAND_POLL_INTERVAL = 5  # seconds

DEFAULT_CONFIG = {
    "pc_name": platform.node(),
    "server_url": "",
    "watched_programs": ["chrome.exe", "discord.exe"],
    "version": "1.0.0",
    "auto_update": True,
    # GitHub repo raw URL (örnek: https://raw.githubusercontent.com/KULLANICI/REPO/main)
    "github_raw_url": "",
}


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


config = load_config()


def get_version():
    """Version bilgisini oku. Git merge conflict marker’larını temizle."""
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, "r") as f:
            content = f.read()
        # Merge conflict marker’larını temizle, ilk geçerli satırı al
        import re
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith(('<', '>', '=', '#')):
                if re.match(r'^\d+\.\d+', line):  # x.y ile başlamalı
                    return line
    return config.get("version", "1.0.0")



# ─── System Info Collection ──────────────────────────────────────────────────
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_uptime():
    try:
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        delta = datetime.now() - boot_time
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes = remainder // 60
        parts = []
        if days > 0:
            parts.append(f"{days}g")
        if hours > 0:
            parts.append(f"{hours}s")
        parts.append(f"{minutes}dk")
        return " ".join(parts)
    except Exception:
        return "?"


def get_os_info():
    try:
        return f"{platform.system()} {platform.release()} ({platform.architecture()[0]})"
    except Exception:
        return platform.system()


def get_running_processes():
    """Get list of unique running process names."""
    try:
        procs = set()
        for proc in psutil.process_iter(["name"]):
            try:
                name = proc.info["name"]
                if name:
                    procs.add(name)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return sorted(procs)
    except Exception:
        return []


def get_watched_status(processes):
    """Check which watched programs are running."""
    watched = config.get("watched_programs", [])
    running_lower = {p.lower() for p in processes}
    return {prog: prog.lower() in running_lower for prog in watched}


def collect_system_info():
    """Collect all system information for heartbeat."""
    processes = get_running_processes()
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("C:\\")

    return {
        "pc_name": config.get("pc_name", platform.node()),
        "ip": get_local_ip(),
        "cpu": psutil.cpu_percent(interval=1),
        "ram": ram.percent,
        "ram_total": round(ram.total / (1024 ** 3), 1),
        "ram_used": round(ram.used / (1024 ** 3), 1),
        "disk": disk.percent,
        "disk_total": round(disk.total / (1024 ** 3), 1),
        "disk_used": round(disk.used / (1024 ** 3), 1),
        "uptime": get_uptime(),
        "os_info": get_os_info(),
        "processes": processes,
        "watched_status": get_watched_status(processes),
        "agent_version": get_version(),
    }


# ─── UDP Auto-Discovery ──────────────────────────────────────────────────────
def discover_server():
    """Listen for UDP beacon from Master server."""
    print("[*] Master sunucu araniyor...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(30)  # 30 second timeout

    try:
        sock.bind(("", BEACON_PORT))
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                message = data.decode()
                if message.startswith("CANAVAR_MASTER:"):
                    parts = message.split(":")
                    if len(parts) >= 3:
                        server_ip = parts[1]
                        server_port = parts[2]
                        server_url = f"http://{server_ip}:{server_port}"
                        print(f"[+] Master bulundu: {server_url}")
                        sock.close()
                        return server_url
            except socket.timeout:
                print("[.] Beacon bekleniyor... (30sn)")
                continue
    except Exception as e:
        print(f"[!] Discovery hatasi: {e}")
    finally:
        try:
            sock.close()
        except Exception:
            pass
    return None


def discovery_loop():
    """Continuously try to discover server if not configured."""
    global config
    while True:
        if not config.get("server_url"):
            url = discover_server()
            if url:
                config["server_url"] = url
                save_config(config)
                print(f"[+] Server URL kaydedildi: {url}")
        else:
            # Test connection
            try:
                r = requests.get(f"{config['server_url']}/api/update/check", timeout=5)
                if r.status_code == 200:
                    time.sleep(60)  # Check every minute
                    continue
            except Exception:
                print("[!] Master baglantisi kesildi, yeniden araniyor...")
                config["server_url"] = ""

        time.sleep(5)

# ─── Heartbeat ────────────────────────────────────────────────────────────────
_update_triggered = False  # aynı anda birden fazla güncelleme tetiklenmesi

def heartbeat_loop():
    """Send heartbeat to master periodically."""
    global _update_triggered
    while True:
        server_url = config.get("server_url")
        if server_url:
            try:
                info = collect_system_info()
                r = requests.post(
                    f"{server_url}/api/heartbeat",
                    json=info,
                    timeout=10,
                )
                if r.status_code == 200:
                    data = r.json()
                    server_ver = data.get("server_version", "")
                    local_ver = get_version()
                    if server_ver and server_ver != local_ver and config.get("auto_update") and not _update_triggered:
                        _update_triggered = True
                        print(f"[*] Yeni versiyon mevcut: {local_ver} -> {server_ver}")
                        check_github_update()
            except requests.exceptions.ConnectionError:
                print("[!] Master'a baglanamadi")
            except Exception as e:
                print(f"[!] Heartbeat hatasi: {e}")

        time.sleep(HEARTBEAT_INTERVAL)


# ─── Command Execution ────────────────────────────────────────────────────────
def execute_command(cmd):
    """Execute a command received from master."""
    action = cmd.get("action", "")
    target = cmd.get("target", "")
    cmd_id = cmd.get("id", "")

    print(f"[>] Komut alindi: {action} {target}")

    result = {"command_id": cmd_id, "success": False, "message": ""}

    try:
        if action == "start_program":
            subprocess.Popen(target, shell=True)
            result["success"] = True
            result["message"] = f"{target} baslatildi"

        elif action == "stop_program":
            os.system(f"taskkill /f /im {target}")
            result["success"] = True
            result["message"] = f"{target} durduruldu"

        elif action == "restart":
            os.system("shutdown /r /t 5 /f")
            result["success"] = True
            result["message"] = "PC yeniden başlatılıyor..."

        elif action == "shutdown":
            os.system("shutdown /s /t 5 /f")
            result["success"] = True
            result["message"] = "PC kapatılıyor..."

        elif action == "custom":
            output = subprocess.run(
                target, shell=True, capture_output=True, text=True, timeout=30
            )
            result["success"] = output.returncode == 0
            result["message"] = output.stdout[:500] or output.stderr[:500] or "Komut çalıştırıldı"

        elif action == "screenshot":
            result["success"] = False
            result["message"] = "Ekran görüntüsü henüz desteklenmiyor"

        else:
            result["message"] = f"Bilinmeyen komut: {action}"

    except Exception as e:
        result["message"] = str(e)

    # Report result back
    server_url = config.get("server_url")
    if server_url:
        try:
            requests.post(f"{server_url}/api/command_result", json=result, timeout=5)
        except Exception:
            pass

    return result


def command_poll_loop():
    """Poll master for pending commands."""
    pc_name = config.get("pc_name", platform.node())
    while True:
        server_url = config.get("server_url")
        if server_url:
            try:
                r = requests.get(
                    f"{server_url}/api/commands/{pc_name}",
                    timeout=5,
                )
                if r.status_code == 200:
                    commands = r.json()
                    for cmd in commands:
                        execute_command(cmd)
            except Exception:
                pass

        time.sleep(COMMAND_POLL_INTERVAL)


# ─── Auto Update (GitHub) ─────────────────────────────────────────────────────
def check_github_update():
    """
    GitHub raw URL'den versiyon kontrol eder ve
    yeni sürüm varsa agent.py'yi indirip kendini yeniden başlatır.
    Config'deki github_raw_url örneği:
      https://raw.githubusercontent.com/KULLANICI/REPO/main
    """
    github_raw_url = config.get("github_raw_url", "").rstrip("/")
    if not github_raw_url or not config.get("auto_update", True):
        return

    try:
        # 1) Uzaktaki version.txt'i oku
        ver_url = f"{github_raw_url}/version.txt"
        r = requests.get(ver_url, timeout=10)
        if r.status_code != 200:
            print(f"[!] GitHub version.txt alinamadi (HTTP {r.status_code})")
            return

        remote_ver = r.text.strip()
        local_ver = get_version()

        if remote_ver == local_ver:
            print(f"[✓] Guncelleme yok. Versiyon: {local_ver}")
            return

        print(f"[*] Yeni versiyon bulundu: {local_ver} -> {remote_ver}")
        print("[*] agent.py indiriliyor...")

        # 2) Yeni agent.py'yi indir
        agent_url = f"{github_raw_url}/agent/agent.py"
        r2 = requests.get(agent_url, timeout=30)
        if r2.status_code != 200:
            print(f"[!] agent.py indirilemedi (HTTP {r2.status_code})")
            return

        # 3) Mevcut dosyayı yedekle, yenisini yaz
        agent_path = os.path.join(BASE_DIR, "agent.py")
        backup_path = os.path.join(BASE_DIR, "agent.py.bak")
        if os.path.exists(agent_path):
            os.replace(agent_path, backup_path)

        with open(agent_path, "w", encoding="utf-8") as f:
            f.write(r2.text)

        # 4) version.txt'i güncelle
        ver_file = os.path.join(BASE_DIR, "..", "version.txt")
        with open(ver_file, "w") as f:
            f.write(remote_ver)

        print(f"[+] Guncelleme tamamlandi ({remote_ver}). Yeniden baslatiliyor...")
        time.sleep(1)

        # 5) Kendini yeniden başlat
        os.execv(sys.executable, [sys.executable] + sys.argv)

    except Exception as e:
        print(f"[!] GitHub guncelleme hatasi: {e}")


def update_check_loop():
    """Her saat başı GitHub'dan güncelleme kontrol eder."""
    # İlk kontrol başlangıçta yapılıyor (main'de), sonra saatlik
    while True:
        time.sleep(3600)  # 1 saat bekle
        check_github_update()


# Eski Master tabanlı güncelleme (aynı ağdaki PC'ler için yedek)
def check_update():
    """Check for updates from master (local network fallback)."""
    server_url = config.get("server_url")
    if not server_url or config.get("github_raw_url"):
        return  # GitHub varsa master'ı kullanma

    try:
        r = requests.get(f"{server_url}/api/update/check", timeout=5)
        if r.status_code == 200:
            remote_ver = r.json().get("version", "")
            local_ver = get_version()
            if remote_ver and remote_ver != local_ver:
                print(f"[*] Guncelleme indiriliyor: {local_ver} -> {remote_ver}")
    except Exception as e:
        print(f"Guncelleme kontrol hatasi: {e}")


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def _get_launch_command():
    """Agent'ı başlatmak için kullanılacak Python ve script yollarını döndürür."""
    script_path = os.path.abspath(sys.argv[0])
    # pythonw.exe kullan → pencere açmaz (arka planda çalışır)
    python_exe = sys.executable.replace("python.exe", "pythonw.exe")
    if not os.path.exists(python_exe):
        python_exe = sys.executable
    return python_exe, script_path


def _add_to_startup_registry():
    """
    HKCU Registry'ye ekler — admin gerektirmez.
    Returns: True başarılı, False başarısız
    """
    try:
        import winreg
        python_exe, script_path = _get_launch_command()
        run_value = f'"{python_exe}" "{script_path}"'
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "CanavarAgent", 0, winreg.REG_SZ, run_value)
        winreg.CloseKey(key)

        # Doğrula
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
        val, _ = winreg.QueryValueEx(key, "CanavarAgent")
        winreg.CloseKey(key)

        if val == run_value:
            print("[OK] Registry'ye eklendi (HKCU\\...\\Run)")
            return True
        return False
    except Exception as e:
        print(f"[!] Registry eklemede hata: {e}")
        return False


def _add_to_startup_folder():
    """
    Startup klasörüne .bat dosyası ekler — yedek yöntem.
    Returns: True başarılı, False başarısız
    """
    try:
        startup_dir = os.path.join(
            os.environ["APPDATA"],
            "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
        )
        os.makedirs(startup_dir, exist_ok=True)
        bat_path = os.path.join(startup_dir, "CanavarAgent.bat")

        python_exe, script_path = _get_launch_command()

        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(f'@echo off\nstart "" "{python_exe}" "{script_path}"\n')

        # Doğrula
        if os.path.exists(bat_path) and os.path.getsize(bat_path) > 0:
            print(f"[OK] Startup klasörüne eklendi: {bat_path}")
            return True
        return False
    except Exception as e:
        print(f"[!] Startup klasörü eklemede hata: {e}")
        return False


def _add_to_startup_taskscheduler():
    """
    Windows Görev Zamanlayıcısı'na ekler — son çare.
    Returns: True başarılı, False başarısız
    """
    try:
        python_exe, script_path = _get_launch_command()
        cmd = (
            f'schtasks /create /tn "CanavarAgent" /tr '
            f'"{python_exe} {script_path}" '
            f'/sc ONLOGON /rl HIGHEST /f'
        )
        ret = os.system(cmd)
        if ret == 0:
            print("[OK] Task Scheduler'a eklendi (ONLOGON)")
            return True
        print(f"[!] Task Scheduler dönüş kodu: {ret}")
        return False
    except Exception as e:
        print(f"[!] Task Scheduler eklemede hata: {e}")
        return False


def add_to_startup():
    """
    Agent'ı Windows başlangıcına zorla ekler.
    Sırasıyla 3 yöntem dener: Registry → Startup klasörü → Task Scheduler.
    En az biri başarılı olursa yeterli sayılır.
    """
    print("[*] Başlangıca ekleniyor...")
    success = False

    # Yöntem 1: Registry (HKCU) — en güvenilir, admin gerektirmez
    if _add_to_startup_registry():
        success = True

    # Yöntem 2: Startup klasörü — yedek
    if not success:
        if _add_to_startup_folder():
            success = True

    # Yöntem 3: Task Scheduler — son çare
    if not success:
        if _add_to_startup_taskscheduler():
            success = True

    if success:
        print("[✓] Başlangıca başarıyla eklendi.")
    else:
        print("[✗] Başlangıca eklenemedi! Tüm yöntemler başarısız.")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    add_to_startup()

    pc_name = config.get("pc_name", platform.node())
    print("=" * 60)
    print("  CANAVAR Monitor - Agent")
    print("=" * 60)
    print(f"  PC Adi     : {pc_name}")
    print(f"  IP         : {get_local_ip()}")
    print(f"  Versiyon   : {get_version()}")
    print(f"  Server     : {config.get('server_url') or 'Otomatik aranacak...'}")
    print(f"  Izlenen    : {', '.join(config.get('watched_programs', []))}")
    print("=" * 60)

    # Başlangıçta güncelleme kontrolü yap
    if config.get("github_raw_url") and config.get("auto_update", True):
        print("[*] GitHub'dan guncelleme kontrol ediliyor...")
        check_github_update()

    # Start threads
    threads = [
        threading.Thread(target=discovery_loop, daemon=True, name="Discovery"),
        threading.Thread(target=heartbeat_loop, daemon=True, name="Heartbeat"),
        threading.Thread(target=command_poll_loop, daemon=True, name="Commands"),
        threading.Thread(target=update_check_loop, daemon=True, name="AutoUpdate"),
    ]

    for t in threads:
        t.start()
        print(f"  > {t.name} thread baslatildi")

    print("\n[OK] Agent calisiyor. Kapatmak icin Ctrl+C basin.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[X] Agent kapatiliyor...")
        sys.exit(0)


if __name__ == "__main__":
    main()
