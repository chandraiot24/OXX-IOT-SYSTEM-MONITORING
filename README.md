# Advanced Raspberry Pi Temperature Monitoring System

A comprehensive IoT monitoring system with voice control, real-time alerts, and advanced analytics.

## Features

### Core Monitoring
- Real-time CPU temperature monitoring
- Multi-level fan control (Normal/High/Critical)
- Automatic cooling system management
- Temperature history tracking and analytics

### Voice Control Integration
- Speech recognition with wake word detection
- Text-to-speech responses
- Comprehensive command set for system control
- Voice command history tracking

### Alert Systems
- Email alerts via SendGrid
- Telegram notifications
- Multi-level temperature thresholds
- Cooldown periods to prevent spam

### Dashboard & Analytics
- Hacker-style dark theme with light mode option
- Real-time temperature charts
- Live system logs viewer
- Comprehensive statistics tracking

### Data Export & Reports
- CSV export of temperature history
- PDF report generation with charts
- MQTT integration for IoT platforms
- RESTful API for external integrations

### Advanced Features
- WiFi signal strength monitoring
- System performance metrics
- Configurable thresholds and settings
- Remote Raspberry Pi connection support

## Quick Setup

### 1. Clone and Install Dependencies
```bash
git clone <repository>
cd raspberry-pi-monitor
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Set up your API keys:
- `SENDGRID_API_KEY` - for email alerts
- `TELEGRAM_BOT_TOKEN` - for Telegram notifications
- `TELEGRAM_CHAT_ID` - your Telegram chat ID

### 3. Run the Application
```bash
python main.py
```

Access the dashboard at `http://localhost:5000`

## Connecting to Your Raspberry Pi

### For Remote Monitoring (Recommended)

1. **Copy the service file to your Raspberry Pi:**
```bash
scp pi_service.py pi@192.168.205.83:~/
```

2. **Install dependencies on your Pi:**
```bash
ssh pi@192.168.205.83
pip install flask gpiozero
```

3. **Run the temperature service on your Pi:**
```bash
python3 pi_service.py
```

4. **Configure the monitoring system:**
   - Go to Settings page
   - Enable "Use Remote Raspberry Pi"
   - Set IP address to `192.168.205.83`
   - Save configuration

### Voice Commands

Use the wake phrase "Raspberry Pi" followed by:
- "What is the temperature?"
- "How is the fan?"
- "System status"
- "Show statistics"
- "Help"

### API Endpoints

- `GET /api/status` - Complete system status
- `GET /api/history` - Temperature history
- `POST /api/voice/toggle` - Enable/disable voice control
- `POST /api/voice/test` - Test voice commands
- `GET /export/csv` - Download CSV data
- `GET /export/pdf` - Generate PDF report

### Configuration

All settings can be configured through the web interface:
- Temperature thresholds
- Alert preferences
- MQTT settings
- Remote Pi connection
- Theme preferences

## System Requirements

- Python 3.8+
- Audio device for voice control (optional)
- Network access for alerts and remote monitoring

## Troubleshooting

### Voice Control Issues
- Ensure microphone permissions are granted
- Check audio device availability
- Use the test command feature for debugging

### Remote Pi Connection
- Verify Pi is accessible on the network
- Ensure the service is running on port 5001
- Check firewall settings

### Alert Configuration
- Verify API keys are correctly set
- Test email/Telegram settings individually
- Check network connectivity

## Contributing

Feel free to submit issues and enhancement requests.

## License

MIT License - see LICENSE file for details.