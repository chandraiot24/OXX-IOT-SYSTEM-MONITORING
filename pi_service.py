#!/usr/bin/env python3
"""
Simple temperature service for Raspberry Pi
Run this on your Pi at 192.168.205.83 to provide real temperature data
"""

from flask import Flask, jsonify
import os
import logging
from datetime import datetime
from gpiozero import OutputDevice

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# GPIO configuration
FAN_PIN = 14
try:
    fan = OutputDevice(FAN_PIN, initial_value=False)
    GPIO_AVAILABLE = True
    logging.info(f"GPIO initialized on pin {FAN_PIN}")
except Exception as e:
    fan = None
    GPIO_AVAILABLE = False
    logging.error(f"GPIO initialization failed: {e}")

def get_cpu_temp():
    """Get actual CPU temperature from Raspberry Pi"""
    try:
        temp_str = os.popen("vcgencmd measure_temp").readline()
        if temp_str and "temp=" in temp_str:
            temp = float(temp_str.replace("temp=", "").replace("'C\n", ""))
            return temp
        return 0.0
    except Exception as e:
        logging.error(f"Temperature read error: {e}")
        return 0.0

def get_system_info():
    """Get system information"""
    info = {}
    
    # System uptime
    try:
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = float(f.readline().split()[0])
            info['uptime'] = int(uptime_seconds)
    except:
        info['uptime'] = 0
    
    # Memory usage
    try:
        with open('/proc/meminfo', 'r') as f:
            meminfo = f.readlines()
            mem_total = int([line for line in meminfo if 'MemTotal' in line][0].split()[1])
            mem_available = int([line for line in meminfo if 'MemAvailable' in line][0].split()[1])
            mem_used_percent = ((mem_total - mem_available) / mem_total) * 100
            info['memory_usage'] = round(mem_used_percent, 1)
    except:
        info['memory_usage'] = 0
    
    # CPU load
    try:
        load_avg = os.getloadavg()[0]
        info['cpu_load'] = round(load_avg, 2)
    except:
        info['cpu_load'] = 0
    
    return info

@app.route('/api/temperature')
def get_temperature():
    """Return current CPU temperature"""
    temp = get_cpu_temp()
    return jsonify({
        'temperature': temp,
        'timestamp': datetime.now().isoformat(),
        'unit': 'celsius'
    })

@app.route('/api/status')
def get_status():
    """Return full system status"""
    temp = get_cpu_temp()
    system_info = get_system_info()
    
    return jsonify({
        'temperature': temp,
        'fan_available': GPIO_AVAILABLE,
        'fan_status': 'ON' if GPIO_AVAILABLE and fan and fan.is_active else 'OFF',
        'system_info': system_info,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/fan/<action>')
def control_fan(action):
    """Control fan via API"""
    if not GPIO_AVAILABLE or not fan:
        return jsonify({'error': 'Fan control not available'}), 400
    
    try:
        if action.lower() == 'on':
            fan.on()
            status = 'ON'
        elif action.lower() == 'off':
            fan.off()
            status = 'OFF'
        else:
            return jsonify({'error': 'Invalid action. Use on or off'}), 400
        
        return jsonify({
            'fan_status': status,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'gpio_available': GPIO_AVAILABLE,
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    logging.info("Starting Raspberry Pi Temperature Service")
    logging.info(f"GPIO available: {GPIO_AVAILABLE}")
    app.run(host='0.0.0.0', port=5001, debug=False)