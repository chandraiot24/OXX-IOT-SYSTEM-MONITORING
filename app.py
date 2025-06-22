from flask import Flask, render_template_string, request, jsonify, redirect, url_for
import os
import logging
import json
from datetime import datetime, timedelta
from collections import deque
import threading
import time

# Configure logging for debugging
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "raspberry-pi-temp-monitor-secret")

# Configuration settings
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "fan_pin": 14,
    "temp_threshold": 60,
    "temp_threshold_high": 70,
    "temp_critical": 80,
    "data_retention_hours": 24,
    "log_interval": 30,
    "auto_refresh": 5
}

# Load configuration
def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            # Merge with defaults for missing keys
            for key, value in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = value
            return config
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_CONFIG.copy()

def save_config(config):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        logging.error(f"Error saving config: {e}")
        return False

# Global configuration
config = load_config()
FAN_PIN = config["fan_pin"]
TEMP_THRESHOLD = config["temp_threshold"]
TEMP_THRESHOLD_HIGH = config["temp_threshold_high"]
TEMP_CRITICAL = config["temp_critical"]

# Temperature history storage
temp_history = deque(maxlen=int(config["data_retention_hours"] * 3600 / config["log_interval"]))
system_stats = {
    "uptime_start": datetime.now(),
    "fan_cycles": 0,
    "max_temp": 0,
    "min_temp": 100,
    "alerts_triggered": 0
}

# Initialize fan control with error handling
try:
    from gpiozero import OutputDevice
    fan = OutputDevice(FAN_PIN, initial_value=False)
    GPIO_AVAILABLE = True
    logging.info(f"GPIO initialized successfully. Fan connected to pin {FAN_PIN}")
except ImportError:
    GPIO_AVAILABLE = False
    fan = None
    logging.warning("gpiozero not available - running in simulation mode")
except Exception as e:
    GPIO_AVAILABLE = False
    fan = None
    logging.error(f"GPIO initialization failed: {e}")

def get_cpu_temp():
    """Get CPU temperature from Raspberry Pi system command or simulate"""
    try:
        temp_str = os.popen("vcgencmd measure_temp").readline()
        if temp_str and "temp=" in temp_str:
            temp = float(temp_str.replace("temp=", "").replace("'C\n", ""))
            logging.debug(f"CPU temperature: {temp}°C")
            return temp
        else:
            # Simulate temperature for demo purposes
            import random
            simulated_temp = 45 + random.uniform(-10, 25)
            logging.debug(f"Simulated CPU temperature: {simulated_temp}°C")
            return simulated_temp
    except Exception as e:
        logging.error(f"Error reading CPU temperature: {e}")
        # Return simulated temperature as fallback
        import random
        return 45 + random.uniform(-10, 25)

def get_system_info():
    """Get additional system information"""
    info = {}
    
    # Get system uptime
    try:
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = float(f.readline().split()[0])
            uptime_str = str(timedelta(seconds=int(uptime_seconds)))
            info['system_uptime'] = uptime_str
    except:
        info['system_uptime'] = "Unknown"
    
    # Get memory usage
    try:
        with open('/proc/meminfo', 'r') as f:
            meminfo = f.readlines()
            mem_total = int([line for line in meminfo if 'MemTotal' in line][0].split()[1])
            mem_available = int([line for line in meminfo if 'MemAvailable' in line][0].split()[1])
            mem_used_percent = ((mem_total - mem_available) / mem_total) * 100
            info['memory_usage'] = f"{mem_used_percent:.1f}%"
    except:
        info['memory_usage'] = "Unknown"
    
    # Get CPU usage (simplified)
    try:
        load_avg = os.getloadavg()[0]
        info['cpu_load'] = f"{load_avg:.2f}"
    except:
        info['cpu_load'] = "Unknown"
    
    # Calculate app uptime
    app_uptime = datetime.now() - system_stats["uptime_start"]
    info['app_uptime'] = str(app_uptime).split('.')[0]
    
    return info

def log_temperature():
    """Log temperature data for history tracking"""
    temp = get_cpu_temp()
    timestamp = datetime.now()
    
    # Update statistics
    if temp > system_stats["max_temp"]:
        system_stats["max_temp"] = temp
    if temp < system_stats["min_temp"]:
        system_stats["min_temp"] = temp
    
    # Add to history
    temp_history.append({
        "timestamp": timestamp.isoformat(),
        "temperature": temp,
        "fan_active": fan.is_active if GPIO_AVAILABLE and fan else False
    })
    
    # Check for alerts
    if temp > TEMP_CRITICAL:
        system_stats["alerts_triggered"] += 1
        logging.warning(f"CRITICAL TEMPERATURE ALERT: {temp}°C > {TEMP_CRITICAL}°C")
    
    return temp

def fan_status():
    """Get current fan status"""
    if not GPIO_AVAILABLE or fan is None:
        return "UNAVAILABLE"
    return "ON" if fan.is_active else "OFF"

def control_fan(temp):
    """Control fan based on temperature threshold"""
    if not GPIO_AVAILABLE or fan is None:
        logging.debug("Fan control unavailable - GPIO not initialized")
        return
    
    try:
        previous_state = fan.is_active
        if temp > TEMP_THRESHOLD:
            if not fan.is_active:
                fan.on()
                system_stats["fan_cycles"] += 1
                logging.info(f"Fan turned ON - Temperature: {temp}°C > {TEMP_THRESHOLD}°C")
        else:
            if fan.is_active:
                fan.off()
                logging.info(f"Fan turned OFF - Temperature: {temp}°C <= {TEMP_THRESHOLD}°C")
    except Exception as e:
        logging.error(f"Error controlling fan: {e}")

# Background temperature logging
def background_logger():
    """Background thread to log temperature data"""
    while True:
        try:
            log_temperature()
            time.sleep(config["log_interval"])
        except Exception as e:
            logging.error(f"Background logger error: {e}")
            time.sleep(30)

# Start background logging
logging_thread = threading.Thread(target=background_logger, daemon=True)
logging_thread.start()

@app.route("/")
def dashboard():
    """Main dashboard route"""
    temp = get_cpu_temp()
    
    # Control fan automatically based on temperature
    control_fan(temp)
    
    status = fan_status()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    system_info = get_system_info()
    
    # Determine temperature color and status based on thresholds
    if temp > TEMP_CRITICAL:
        temp_color = "#ff0000"
        temp_status = "CRITICAL"
    elif temp > TEMP_THRESHOLD_HIGH:
        temp_color = "#ff6600"
        temp_status = "HIGH"
    elif temp > TEMP_THRESHOLD:
        temp_color = "#ffaa00"
        temp_status = "WARM"
    else:
        temp_color = "#00ff00"
        temp_status = "NORMAL"
    
    # Get recent temperature history for mini chart
    recent_temps = list(temp_history)[-12:] if temp_history else []
    
    html_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>🔥 Advanced Raspberry Pi Monitor</title>
        <meta http-equiv="refresh" content="{{ config.auto_refresh }}">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                background-color: #0f0f0f;
                color: #00ff00;
                font-family: 'Courier New', Courier, monospace;
                padding: 20px;
                min-height: 100vh;
                background-image: 
                    radial-gradient(circle at 1px 1px, #003300 1px, transparent 0);
                background-size: 20px 20px;
            }
            
            .nav {
                display: flex;
                justify-content: center;
                gap: 20px;
                margin-bottom: 30px;
                flex-wrap: wrap;
            }
            
            .nav a {
                color: #00ff00;
                text-decoration: none;
                padding: 10px 20px;
                border: 1px solid #003300;
                border-radius: 5px;
                background-color: rgba(0, 51, 0, 0.2);
                transition: all 0.3s;
            }
            
            .nav a:hover, .nav a.active {
                background-color: rgba(0, 255, 0, 0.1);
                box-shadow: 0 0 10px #00ff00;
            }
            
            .container {
                border: 2px solid #00ff00;
                border-radius: 10px;
                padding: 30px;
                background-color: rgba(0, 0, 0, 0.8);
                box-shadow: 
                    0 0 20px #00ff00,
                    inset 0 0 20px rgba(0, 255, 0, 0.1);
                max-width: 1200px;
                margin: 0 auto;
            }
            
            h1 {
                font-size: 2.5em;
                margin-bottom: 30px;
                text-shadow: 0 0 15px #00ff00;
                animation: glow 2s ease-in-out infinite alternate;
                text-align: center;
            }
            
            @keyframes glow {
                from { text-shadow: 0 0 15px #00ff00; }
                to { text-shadow: 0 0 25px #00ff00, 0 0 35px #00ff00; }
            }
            
            .main-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 30px;
                margin-bottom: 30px;
            }
            
            .metric {
                padding: 25px;
                border: 1px solid #003300;
                border-radius: 10px;
                background-color: rgba(0, 51, 0, 0.2);
                text-align: center;
            }
            
            .temp {
                font-size: 4em;
                font-weight: bold;
                color: {{ temp_color }};
                text-shadow: 0 0 20px {{ temp_color }};
                animation: pulse 1.5s ease-in-out infinite alternate;
                margin: 15px 0;
            }
            
            @keyframes pulse {
                from { transform: scale(1); }
                to { transform: scale(1.05); }
            }
            
            .status {
                font-size: 2.5em;
                font-weight: bold;
                margin: 15px 0;
                {% if status == 'ON' %}
                color: #ff3300;
                text-shadow: 0 0 20px #ff3300;
                {% elif status == 'OFF' %}
                color: #00ff00;
                text-shadow: 0 0 20px #00ff00;
                {% else %}
                color: #ffaa00;
                text-shadow: 0 0 20px #ffaa00;
                {% endif %}
            }
            
            .temp-status {
                font-size: 1.5em;
                color: {{ temp_color }};
                font-weight: bold;
                margin-top: 10px;
            }
            
            .system-info {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                gap: 15px;
                margin: 30px 0;
            }
            
            .info-card {
                border: 1px solid #003300;
                border-radius: 5px;
                padding: 15px;
                background-color: rgba(0, 51, 0, 0.1);
                text-align: center;
            }
            
            .info-label {
                font-size: 0.8em;
                color: #009900;
                margin-bottom: 8px;
                text-transform: uppercase;
            }
            
            .info-value {
                font-size: 1.1em;
                font-weight: bold;
                color: #00ff00;
            }
            
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
                margin: 20px 0;
            }
            
            .chart-container {
                margin: 30px 0;
                padding: 20px;
                border: 1px solid #003300;
                border-radius: 10px;
                background-color: rgba(0, 51, 0, 0.1);
            }
            
            .mini-chart {
                display: flex;
                align-items: end;
                justify-content: space-between;
                height: 60px;
                margin: 15px 0;
                padding: 0 10px;
            }
            
            .chart-bar {
                width: 8px;
                background: linear-gradient(to top, #003300, #00ff00);
                border-radius: 2px;
                margin: 0 1px;
                transition: all 0.3s;
            }
            
            {% if not gpio_available %}
            .warning {
                background-color: rgba(255, 170, 0, 0.1);
                border: 1px solid #ffaa00;
                color: #ffaa00;
                padding: 15px;
                border-radius: 5px;
                margin: 20px 0;
                font-size: 1.1em;
                text-align: center;
            }
            {% endif %}
            
            .footer {
                text-align: center;
                margin-top: 30px;
                color: #006600;
                font-size: 0.9em;
            }
            
            @media (max-width: 768px) {
                .main-grid { grid-template-columns: 1fr; }
                .container { padding: 20px; }
                h1 { font-size: 2em; }
                .temp { font-size: 3em; }
                .status { font-size: 2em; }
                .system-info { grid-template-columns: 1fr; }
                .nav { gap: 10px; }
                .nav a { padding: 8px 15px; font-size: 0.9em; }
            }
        </style>
    </head>
    <body>
        <nav class="nav">
            <a href="/" class="active">Dashboard</a>
            <a href="/history">History</a>
            <a href="/config">Settings</a>
            <a href="/api/status">API</a>
        </nav>
        
        <div class="container">
            <h1>🖥️ RASPBERRY PI SYSTEM MONITOR</h1>
            
            {% if not gpio_available %}
            <div class="warning">
                ⚠️ WARNING: GPIO control unavailable. Running in monitoring mode only.
            </div>
            {% endif %}
            
            <div class="main-grid">
                <div class="metric">
                    <div class="info-label">CPU TEMPERATURE</div>
                    <div class="temp">{{ "%.1f"|format(temp) }}°C</div>
                    <div class="temp-status">{{ temp_status }}</div>
                </div>
                
                <div class="metric">
                    <div class="info-label">FAN STATUS</div>
                    <div class="status">{{ status }}</div>
                    <div class="info-label">Cycles: {{ system_stats.fan_cycles }}</div>
                </div>
            </div>
            
            <div class="chart-container">
                <div class="info-label">TEMPERATURE TREND (Last Hour)</div>
                <div class="mini-chart">
                    {% for reading in recent_temps %}
                    <div class="chart-bar" style="height: {{ ((reading.temperature - 30) / 50 * 100)|int }}%;"></div>
                    {% endfor %}
                </div>
            </div>
            
            <div class="system-info">
                <div class="info-card">
                    <div class="info-label">THRESHOLD</div>
                    <div class="info-value">{{ config.temp_threshold }}°C</div>
                </div>
                <div class="info-card">
                    <div class="info-label">HIGH THRESHOLD</div>
                    <div class="info-value">{{ config.temp_threshold_high }}°C</div>
                </div>
                <div class="info-card">
                    <div class="info-label">CRITICAL</div>
                    <div class="info-value">{{ config.temp_critical }}°C</div>
                </div>
                <div class="info-card">
                    <div class="info-label">FAN PIN</div>
                    <div class="info-value">GPIO {{ config.fan_pin }}</div>
                </div>
            </div>
            
            <div class="stats-grid">
                <div class="info-card">
                    <div class="info-label">MAX TEMP</div>
                    <div class="info-value">{{ "%.1f"|format(system_stats.max_temp) }}°C</div>
                </div>
                <div class="info-card">
                    <div class="info-label">MIN TEMP</div>
                    <div class="info-value">{{ "%.1f"|format(system_stats.min_temp) }}°C</div>
                </div>
                <div class="info-card">
                    <div class="info-label">ALERTS</div>
                    <div class="info-value">{{ system_stats.alerts_triggered }}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">APP UPTIME</div>
                    <div class="info-value">{{ system_info.app_uptime }}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">SYSTEM UPTIME</div>
                    <div class="info-value">{{ system_info.system_uptime }}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">MEMORY USAGE</div>
                    <div class="info-value">{{ system_info.memory_usage }}</div>
                </div>
            </div>
            
            <div class="footer">
                <div class="info-label">LAST UPDATE: {{ time }}</div>
                <div>📡 Auto-refresh every {{ config.auto_refresh }} seconds | 📊 {{ recent_temps|length }} readings stored</div>
            </div>
        </div>
    </body>
    </html>
    """
    
    return render_template_string(
        html_template, 
        temp=temp, 
        status=status, 
        time=current_time,
        temp_color=temp_color,
        temp_status=temp_status,
        config=config,
        system_stats=system_stats,
        system_info=system_info,
        recent_temps=recent_temps,
        gpio_available=GPIO_AVAILABLE
    )

@app.route("/history")
def history():
    """Temperature history page"""
    history_data = list(temp_history)
    
    html_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>📊 Temperature History</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                background-color: #0f0f0f;
                color: #00ff00;
                font-family: 'Courier New', Courier, monospace;
                padding: 20px;
                background-image: radial-gradient(circle at 1px 1px, #003300 1px, transparent 0);
                background-size: 20px 20px;
            }
            .nav {
                display: flex;
                justify-content: center;
                gap: 20px;
                margin-bottom: 30px;
                flex-wrap: wrap;
            }
            .nav a {
                color: #00ff00;
                text-decoration: none;
                padding: 10px 20px;
                border: 1px solid #003300;
                border-radius: 5px;
                background-color: rgba(0, 51, 0, 0.2);
                transition: all 0.3s;
            }
            .nav a:hover { background-color: rgba(0, 255, 0, 0.1); box-shadow: 0 0 10px #00ff00; }
            .nav a.active { background-color: rgba(0, 255, 0, 0.1); box-shadow: 0 0 10px #00ff00; }
            .container {
                border: 2px solid #00ff00;
                border-radius: 10px;
                padding: 30px;
                background-color: rgba(0, 0, 0, 0.8);
                box-shadow: 0 0 20px #00ff00, inset 0 0 20px rgba(0, 255, 0, 0.1);
                max-width: 1200px;
                margin: 0 auto;
            }
            h1 {
                font-size: 2.5em;
                margin-bottom: 30px;
                text-shadow: 0 0 15px #00ff00;
                text-align: center;
            }
            .history-table {
                width: 100%;
                border-collapse: collapse;
                margin: 20px 0;
            }
            .history-table th, .history-table td {
                border: 1px solid #003300;
                padding: 12px;
                text-align: center;
            }
            .history-table th {
                background-color: rgba(0, 51, 0, 0.3);
                color: #00ff00;
                font-weight: bold;
            }
            .history-table td {
                background-color: rgba(0, 51, 0, 0.1);
            }
            .temp-high { color: #ff6600; }
            .temp-critical { color: #ff0000; }
            .temp-normal { color: #00ff00; }
            .fan-on { color: #ff3300; }
            .fan-off { color: #00ff00; }
            .stats-summary {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin: 30px 0;
            }
            .stat-card {
                border: 1px solid #003300;
                border-radius: 5px;
                padding: 20px;
                background-color: rgba(0, 51, 0, 0.2);
                text-align: center;
            }
            .stat-label {
                font-size: 0.9em;
                color: #009900;
                margin-bottom: 10px;
                text-transform: uppercase;
            }
            .stat-value {
                font-size: 1.5em;
                font-weight: bold;
                color: #00ff00;
            }
        </style>
    </head>
    <body>
        <nav class="nav">
            <a href="/">Dashboard</a>
            <a href="/history" class="active">History</a>
            <a href="/config">Settings</a>
            <a href="/api/status">API</a>
        </nav>
        
        <div class="container">
            <h1>📊 TEMPERATURE HISTORY</h1>
            
            <div class="stats-summary">
                <div class="stat-card">
                    <div class="stat-label">Total Records</div>
                    <div class="stat-value">{{ history_data|length }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Data Retention</div>
                    <div class="stat-value">{{ config.data_retention_hours }}h</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Log Interval</div>
                    <div class="stat-value">{{ config.log_interval }}s</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Average Temp</div>
                    <div class="stat-value">
                        {% if history_data %}
                        {{ "%.1f"|format((history_data|map(attribute='temperature')|sum) / (history_data|length)) }}°C
                        {% else %}
                        N/A
                        {% endif %}
                    </div>
                </div>
            </div>
            
            {% if history_data %}
            <table class="history-table">
                <thead>
                    <tr>
                        <th>Timestamp</th>
                        <th>Temperature</th>
                        <th>Fan Status</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {% for reading in history_data[-50:] %}
                    <tr>
                        <td>{{ reading.timestamp[:19].replace('T', ' ') }}</td>
                        <td class="{% if reading.temperature > 80 %}temp-critical{% elif reading.temperature > 70 %}temp-high{% else %}temp-normal{% endif %}">
                            {{ "%.1f"|format(reading.temperature) }}°C
                        </td>
                        <td class="{% if reading.fan_active %}fan-on{% else %}fan-off{% endif %}">
                            {{ "ON" if reading.fan_active else "OFF" }}
                        </td>
                        <td>
                            {% if reading.temperature > 80 %}CRITICAL
                            {% elif reading.temperature > 70 %}HIGH
                            {% elif reading.temperature > 60 %}WARM
                            {% else %}NORMAL{% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <div style="text-align: center; padding: 50px; color: #666;">
                No temperature history available yet. Data will appear as the system runs.
            </div>
            {% endif %}
        </div>
    </body>
    </html>
    """
    
    return render_template_string(
        html_template,
        history_data=history_data,
        config=config
    )

@app.route("/config", methods=["GET", "POST"])
def configuration():
    """Configuration management page"""
    global config, TEMP_THRESHOLD, TEMP_THRESHOLD_HIGH, TEMP_CRITICAL, FAN_PIN
    
    message = ""
    if request.method == "POST":
        try:
            # Update configuration from form
            new_config = {
                "fan_pin": int(request.form.get("fan_pin", config["fan_pin"])),
                "temp_threshold": float(request.form.get("temp_threshold", config["temp_threshold"])),
                "temp_threshold_high": float(request.form.get("temp_threshold_high", config["temp_threshold_high"])),
                "temp_critical": float(request.form.get("temp_critical", config["temp_critical"])),
                "data_retention_hours": int(request.form.get("data_retention_hours", config["data_retention_hours"])),
                "log_interval": int(request.form.get("log_interval", config["log_interval"])),
                "auto_refresh": int(request.form.get("auto_refresh", config["auto_refresh"]))
            }
            
            # Validate configuration
            if new_config["temp_threshold"] >= new_config["temp_threshold_high"]:
                message = "Error: High threshold must be greater than normal threshold"
            elif new_config["temp_threshold_high"] >= new_config["temp_critical"]:
                message = "Error: Critical threshold must be greater than high threshold"
            elif new_config["fan_pin"] < 1 or new_config["fan_pin"] > 40:
                message = "Error: GPIO pin must be between 1 and 40"
            else:
                # Save configuration
                if save_config(new_config):
                    config = new_config
                    TEMP_THRESHOLD = config["temp_threshold"]
                    TEMP_THRESHOLD_HIGH = config["temp_threshold_high"]
                    TEMP_CRITICAL = config["temp_critical"]
                    FAN_PIN = config["fan_pin"]
                    message = "Configuration saved successfully! Restart required for GPIO pin changes."
                else:
                    message = "Error: Failed to save configuration"
        except ValueError as e:
            message = f"Error: Invalid input values - {str(e)}"
        except Exception as e:
            message = f"Error: {str(e)}"
    
    html_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>⚙️ System Configuration</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                background-color: #0f0f0f;
                color: #00ff00;
                font-family: 'Courier New', Courier, monospace;
                padding: 20px;
                background-image: radial-gradient(circle at 1px 1px, #003300 1px, transparent 0);
                background-size: 20px 20px;
            }
            .nav {
                display: flex;
                justify-content: center;
                gap: 20px;
                margin-bottom: 30px;
                flex-wrap: wrap;
            }
            .nav a {
                color: #00ff00;
                text-decoration: none;
                padding: 10px 20px;
                border: 1px solid #003300;
                border-radius: 5px;
                background-color: rgba(0, 51, 0, 0.2);
                transition: all 0.3s;
            }
            .nav a:hover { background-color: rgba(0, 255, 0, 0.1); box-shadow: 0 0 10px #00ff00; }
            .nav a.active { background-color: rgba(0, 255, 0, 0.1); box-shadow: 0 0 10px #00ff00; }
            .container {
                border: 2px solid #00ff00;
                border-radius: 10px;
                padding: 30px;
                background-color: rgba(0, 0, 0, 0.8);
                box-shadow: 0 0 20px #00ff00, inset 0 0 20px rgba(0, 255, 0, 0.1);
                max-width: 800px;
                margin: 0 auto;
            }
            h1 {
                font-size: 2.5em;
                margin-bottom: 30px;
                text-shadow: 0 0 15px #00ff00;
                text-align: center;
            }
            .form-group {
                margin: 25px 0;
                padding: 20px;
                border: 1px solid #003300;
                border-radius: 5px;
                background-color: rgba(0, 51, 0, 0.1);
            }
            .form-group label {
                display: block;
                margin-bottom: 8px;
                color: #00ff00;
                font-weight: bold;
                text-transform: uppercase;
            }
            .form-group input {
                width: 100%;
                padding: 10px;
                border: 1px solid #003300;
                border-radius: 3px;
                background-color: #1a1a1a;
                color: #00ff00;
                font-family: 'Courier New', Courier, monospace;
                font-size: 1em;
            }
            .form-group input:focus {
                outline: none;
                border-color: #00ff00;
                box-shadow: 0 0 5px #00ff00;
            }
            .form-group .description {
                font-size: 0.9em;
                color: #009900;
                margin-top: 5px;
                font-style: italic;
            }
            .button {
                background-color: rgba(0, 255, 0, 0.2);
                border: 2px solid #00ff00;
                color: #00ff00;
                padding: 15px 30px;
                font-size: 1.1em;
                border-radius: 5px;
                cursor: pointer;
                font-family: 'Courier New', Courier, monospace;
                text-transform: uppercase;
                font-weight: bold;
                transition: all 0.3s;
                width: 100%;
                margin: 20px 0;
            }
            .button:hover {
                background-color: rgba(0, 255, 0, 0.3);
                box-shadow: 0 0 15px #00ff00;
            }
            .message {
                padding: 15px;
                border-radius: 5px;
                margin: 20px 0;
                text-align: center;
                font-weight: bold;
            }
            .message.success {
                background-color: rgba(0, 255, 0, 0.1);
                border: 1px solid #00ff00;
                color: #00ff00;
            }
            .message.error {
                background-color: rgba(255, 0, 0, 0.1);
                border: 1px solid #ff3300;
                color: #ff3300;
            }
            .config-section {
                margin: 30px 0;
            }
            .section-title {
                font-size: 1.3em;
                color: #00ff00;
                margin-bottom: 15px;
                text-transform: uppercase;
                border-bottom: 1px solid #003300;
                padding-bottom: 10px;
            }
        </style>
    </head>
    <body>
        <nav class="nav">
            <a href="/">Dashboard</a>
            <a href="/history">History</a>
            <a href="/config" class="active">Settings</a>
            <a href="/api/status">API</a>
        </nav>
        
        <div class="container">
            <h1>⚙️ SYSTEM CONFIGURATION</h1>
            
            {% if message %}
            <div class="message {{ 'success' if 'successfully' in message else 'error' }}">
                {{ message }}
            </div>
            {% endif %}
            
            <form method="POST">
                <div class="config-section">
                    <div class="section-title">Temperature Thresholds</div>
                    
                    <div class="form-group">
                        <label for="temp_threshold">Normal Threshold (°C)</label>
                        <input type="number" id="temp_threshold" name="temp_threshold" 
                               value="{{ config.temp_threshold }}" min="30" max="100" step="0.1" required>
                        <div class="description">Temperature at which the fan turns on</div>
                    </div>
                    
                    <div class="form-group">
                        <label for="temp_threshold_high">High Threshold (°C)</label>
                        <input type="number" id="temp_threshold_high" name="temp_threshold_high" 
                               value="{{ config.temp_threshold_high }}" min="30" max="100" step="0.1" required>
                        <div class="description">Temperature considered high (warning level)</div>
                    </div>
                    
                    <div class="form-group">
                        <label for="temp_critical">Critical Threshold (°C)</label>
                        <input type="number" id="temp_critical" name="temp_critical" 
                               value="{{ config.temp_critical }}" min="30" max="100" step="0.1" required>
                        <div class="description">Critical temperature level (triggers alerts)</div>
                    </div>
                </div>
                
                <div class="config-section">
                    <div class="section-title">Hardware Settings</div>
                    
                    <div class="form-group">
                        <label for="fan_pin">Fan GPIO Pin</label>
                        <input type="number" id="fan_pin" name="fan_pin" 
                               value="{{ config.fan_pin }}" min="1" max="40" required>
                        <div class="description">GPIO pin number for fan control (requires restart)</div>
                    </div>
                </div>
                
                <div class="config-section">
                    <div class="section-title">Data & Display Settings</div>
                    
                    <div class="form-group">
                        <label for="data_retention_hours">Data Retention (hours)</label>
                        <input type="number" id="data_retention_hours" name="data_retention_hours" 
                               value="{{ config.data_retention_hours }}" min="1" max="168" required>
                        <div class="description">How long to keep temperature history</div>
                    </div>
                    
                    <div class="form-group">
                        <label for="log_interval">Log Interval (seconds)</label>
                        <input type="number" id="log_interval" name="log_interval" 
                               value="{{ config.log_interval }}" min="5" max="300" required>
                        <div class="description">How often to record temperature data</div>
                    </div>
                    
                    <div class="form-group">
                        <label for="auto_refresh">Auto Refresh (seconds)</label>
                        <input type="number" id="auto_refresh" name="auto_refresh" 
                               value="{{ config.auto_refresh }}" min="1" max="60" required>
                        <div class="description">Dashboard refresh interval</div>
                    </div>
                </div>
                
                <button type="submit" class="button">Save Configuration</button>
            </form>
        </div>
    </body>
    </html>
    """
    
    return render_template_string(
        html_template,
        config=config,
        message=message
    )

@app.route("/api/status")
def api_status():
    """Enhanced API endpoint for system status"""
    temp = get_cpu_temp()
    control_fan(temp)
    system_info = get_system_info()
    
    # Determine temperature status
    if temp > TEMP_CRITICAL:
        temp_status = "CRITICAL"
    elif temp > TEMP_THRESHOLD_HIGH:
        temp_status = "HIGH"
    elif temp > TEMP_THRESHOLD:
        temp_status = "WARM"
    else:
        temp_status = "NORMAL"
    
    return jsonify({
        "temperature": round(temp, 2),
        "temperature_status": temp_status,
        "fan_status": fan_status(),
        "fan_cycles": system_stats["fan_cycles"],
        "thresholds": {
            "normal": TEMP_THRESHOLD,
            "high": TEMP_THRESHOLD_HIGH,
            "critical": TEMP_CRITICAL
        },
        "statistics": {
            "max_temp": round(system_stats["max_temp"], 2),
            "min_temp": round(system_stats["min_temp"], 2),
            "alerts_triggered": system_stats["alerts_triggered"],
            "uptime_start": system_stats["uptime_start"].isoformat()
        },
        "system_info": system_info,
        "config": {
            "fan_pin": config["fan_pin"],
            "data_retention_hours": config["data_retention_hours"],
            "log_interval": config["log_interval"],
            "auto_refresh": config["auto_refresh"]
        },
        "gpio_available": GPIO_AVAILABLE,
        "history_count": len(temp_history),
        "timestamp": datetime.now().isoformat()
    })

@app.route("/api/history")
def api_history():
    """API endpoint for temperature history"""
    history_data = list(temp_history)
    return jsonify({
        "history": history_data,
        "count": len(history_data),
        "retention_hours": config["data_retention_hours"],
        "log_interval": config["log_interval"]
    })

@app.route("/api/reset-stats", methods=["POST"])
def reset_stats():
    """Reset system statistics"""
    global system_stats
    system_stats = {
        "uptime_start": datetime.now(),
        "fan_cycles": 0,
        "max_temp": 0,
        "min_temp": 100,
        "alerts_triggered": 0
    }
    return jsonify({"message": "Statistics reset successfully", "timestamp": datetime.now().isoformat()})

@app.errorhandler(404)
def not_found(error):
    """Custom 404 error page with hacker theme"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>404 - System Not Found</title>
        <style>
            body {
                background-color: #0f0f0f;
                color: #ff3300;
                font-family: 'Courier New', Courier, monospace;
                text-align: center;
                padding: 50px;
            }
            h1 { font-size: 4em; text-shadow: 0 0 20px #ff3300; }
            a { color: #00ff00; text-decoration: none; }
            a:hover { text-shadow: 0 0 10px #00ff00; }
        </style>
    </head>
    <body>
        <h1>404</h1>
        <h2>SYSTEM NOT FOUND</h2>
        <p><a href="/">Return to Dashboard</a></p>
    </body>
    </html>
    """
    return html, 404

if __name__ == "__main__":
    logging.info("Starting Raspberry Pi Temperature Monitor Dashboard")
    logging.info(f"Temperature threshold: {TEMP_THRESHOLD}°C")
    logging.info(f"Fan GPIO pin: {FAN_PIN}")
    logging.info(f"GPIO available: {GPIO_AVAILABLE}")
    
    try:
        app.run(host="0.0.0.0", port=5000, debug=True)
    except KeyboardInterrupt:
        logging.info("Application stopped by user")
        if GPIO_AVAILABLE and fan:
            fan.off()
            logging.info("Fan turned off during shutdown")
    except Exception as e:
        logging.error(f"Application error: {e}")
        if GPIO_AVAILABLE and fan:
            fan.off()
