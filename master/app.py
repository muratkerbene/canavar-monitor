"""
CANAVAR Monitor - Master Server
PC'lerinizi tek panelden izleyin ve yönetin.
"""

import json
import os
import socket
import threading
import time
from datetime import datetime, timedelta

from flask import Flask, jsonify, render_template, request, send_file
from flask_cors import CORS

# ─── Config ──────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "master_config.json")
VERSION_FILE = os.path.join(BASE_DIR, "..", "version.txt")
AGENT_ZIP = os.path.join(BASE_DIR, "..", "agent_update.zip")
BEACON_PORT = 50005
BEACON_INTERVAL = 5  # seconds
OFFLINE_THRESHOLD = 30  # seconds - no heartbeat = offline

# ─── App ─────────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

# In-memory stores
agents = {}       # { pc_name: { ...data, last_seen: datetime } }
commands = {}     # { pc_name: [ {cmd, args, id, status} ] }
command_results = {}  # { command_id: result }

# ─── Config Management ──────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "watched_programs": ["chrome.exe", "discord.exe"],
    "alert_cpu_threshold": 90,
    "alert_ram_threshold": 90,
    "alert_disk_threshold": 90,
    "update_url_version": "",
    "update_url_zip": "",
    "custom_names": {}  # { pc_name: "custom_name" }
}


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            # Ensure new keys exist in old configs
            if "custom_names" not in cfg:
                cfg["custom_names"] = {}
            return cfg
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


config = load_config()


def get_version():
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, "r") as f:
            return f.read().strip()
    return "1.0.0"


# ─── UDP Beacon (Auto-Discovery) ────────────────────────────────────────────
def get_local_ip():
    """Get the local network IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def beacon_thread():
    """Broadcast UDP beacon so agents can auto-discover this server."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    while True:
        try:
            local_ip = get_local_ip()
            message = f"CANAVAR_MASTER:{local_ip}:5000"
            sock.sendto(message.encode(), ("<broadcast>", BEACON_PORT))
        except Exception:
            pass
        time.sleep(BEACON_INTERVAL)


# ─── Helper ──────────────────────────────────────────────────────────────────
def get_agent_status(agent_data):
    """Determine agent status based on last heartbeat."""
    last_seen = agent_data.get("last_seen")
    if not last_seen:
        return "offline"
    diff = (datetime.now() - last_seen).total_seconds()
    if diff <= OFFLINE_THRESHOLD:
        return "online"
    elif diff <= OFFLINE_THRESHOLD * 2:
        return "warning"
    return "offline"


def agents_summary():
    """Get all agents with their current status."""
    result = []
    for name, data in agents.items():
        agent = data.copy()
        agent["status"] = get_agent_status(data)
        agent["display_name"] = config.get("custom_names", {}).get(name, name)
        agent["last_seen_str"] = (
            data["last_seen"].strftime("%H:%M:%S")
            if data.get("last_seen")
            else "Hiç bağlanmadı"
        )
        agent["last_seen_ago"] = ""
        if data.get("last_seen"):
            diff = (datetime.now() - data["last_seen"]).total_seconds()
            if diff < 60:
                agent["last_seen_ago"] = f"{int(diff)} sn önce"
            elif diff < 3600:
                agent["last_seen_ago"] = f"{int(diff // 60)} dk önce"
            else:
                agent["last_seen_ago"] = f"{int(diff // 3600)} saat önce"
        # Remove datetime object for JSON serialization
        agent.pop("last_seen", None)
        result.append(agent)
    return result


# ═══════════════════════════════════════════════════════════════════════════
#  PAGES
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/pc/<pc_name>")
def pc_detail(pc_name):
    # Pass both pc_name and display_name to the template
    display_name = config.get("custom_names", {}).get(pc_name, pc_name)
    return render_template("pc_detail.html", pc_name=pc_name, display_name=display_name)


@app.route("/settings")
def settings():
    return render_template("settings.html")


# ═══════════════════════════════════════════════════════════════════════════
#  API - Agent Communication & Management
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/heartbeat", methods=["POST"])
def heartbeat():
    """Receive heartbeat from an agent."""
    data = request.get_json()
    if not data or "pc_name" not in data:
        return jsonify({"error": "pc_name gerekli"}), 400

    pc_name = data["pc_name"]
    agents[pc_name] = {
        "pc_name": pc_name,
        "ip": data.get("ip", request.remote_addr),
        "cpu": data.get("cpu", 0),
        "ram": data.get("ram", 0),
        "ram_total": data.get("ram_total", 0),
        "ram_used": data.get("ram_used", 0),
        "disk": data.get("disk", 0),
        "disk_total": data.get("disk_total", 0),
        "disk_used": data.get("disk_used", 0),
        "uptime": data.get("uptime", ""),
        "os_info": data.get("os_info", ""),
        "processes": data.get("processes", []),
        "watched_status": data.get("watched_status", {}),
        "agent_version": data.get("agent_version", "?"),
        "last_seen": datetime.now(),
    }
    return jsonify({"status": "ok", "server_version": get_version()})


@app.route("/api/agents", methods=["GET"])
def get_agents():
    """Return all agents and their current status."""
    return jsonify(agents_summary())


@app.route("/api/agent/<pc_name>", methods=["GET"])
def get_agent(pc_name):
    """Return single agent detail."""
    if pc_name not in agents:
        return jsonify({"error": "Agent bulunamadı"}), 404
    data = agents[pc_name].copy()
    data["status"] = get_agent_status(agents[pc_name])
    data["display_name"] = config.get("custom_names", {}).get(pc_name, pc_name)
    data["last_seen_str"] = (
        data["last_seen"].strftime("%H:%M:%S") if data.get("last_seen") else ""
    )
    data.pop("last_seen", None)
    return jsonify(data)

@app.route("/api/agent/<pc_name>/rename", methods=["POST"])
def rename_agent(pc_name):
    """Rename an agent (display name only)."""
    data = request.get_json()
    if not data or "new_name" not in data:
        return jsonify({"error": "new_name gerekli"}), 400
    
    new_name = data["new_name"].strip()
    if not new_name:
        new_name = pc_name  # Reset logic
        
    config.setdefault("custom_names", {})[pc_name] = new_name
    save_config(config)
    return jsonify({"status": "ok", "display_name": new_name})

# ═══════════════════════════════════════════════════════════════════════════
#  API - Command System
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/command/<pc_name>", methods=["POST"])
def send_command(pc_name):
    """Send a command to an agent (from dashboard)."""
    data = request.get_json()
    if not data or "action" not in data:
        return jsonify({"error": "action gerekli"}), 400

    cmd_id = f"{pc_name}_{int(time.time()*1000)}"
    cmd = {
        "id": cmd_id,
        "action": data["action"],          # start_program, stop_program, restart, shutdown, custom
        "target": data.get("target", ""),   # program name or command
        "timestamp": datetime.now().isoformat(),
    }

    if pc_name not in commands:
        commands[pc_name] = []
    commands[pc_name].append(cmd)

    return jsonify({"status": "ok", "command_id": cmd_id})


@app.route("/api/commands/<pc_name>", methods=["GET"])
def get_commands(pc_name):
    """Agent polls this to get pending commands."""
    pending = commands.get(pc_name, [])
    commands[pc_name] = []  # clear after fetching
    return jsonify(pending)


@app.route("/api/command_result", methods=["POST"])
def command_result():
    """Agent reports command execution result."""
    data = request.get_json()
    if data and "command_id" in data:
        command_results[data["command_id"]] = {
            "success": data.get("success", False),
            "message": data.get("message", ""),
            "timestamp": datetime.now().isoformat(),
        }
    return jsonify({"status": "ok"})


# ═══════════════════════════════════════════════════════════════════════════
#  API - Settings
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(config)


@app.route("/api/settings", methods=["POST"])
def update_settings():
    global config
    data = request.get_json()
    if data:
        config.update(data)
        save_config(config)
    return jsonify({"status": "ok"})


# ═══════════════════════════════════════════════════════════════════════════
#  API - Update System
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/update/check", methods=["GET"])
def update_check():
    return jsonify({"version": get_version()})


@app.route("/api/update/download", methods=["GET"])
def update_download():
    if os.path.exists(AGENT_ZIP):
        return send_file(AGENT_ZIP, as_attachment=True, download_name="agent_update.zip")
    return jsonify({"error": "Güncelleme dosyası bulunamadı"}), 404


# ═══════════════════════════════════════════════════════════════════════════
#  STARTUP
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    local_ip = get_local_ip()
    print("=" * 60)
    print("  CANAVAR Monitor - Master Server")
    print("=" * 60)
    print(f"  Yerel IP  : {local_ip}")
    print(f"  Dashboard : http://localhost:5000")
    print(f"  Agdan     : http://{local_ip}:5000")
    print(f"  Beacon    : UDP port {BEACON_PORT}")
    print(f"  Versiyon  : {get_version()}")
    print("=" * 60)

    # Start beacon
    t = threading.Thread(target=beacon_thread, daemon=True)
    t.start()

    app.run(host="0.0.0.0", port=5000, debug=False)
