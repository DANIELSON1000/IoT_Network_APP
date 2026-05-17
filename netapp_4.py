# -*- coding: utf-8 -*-
"""
NetPulse AI Monitor - Complete Production Version
Cyberpunk UI + Real-time ThingSpeak Monitoring + Email Alerts
"""

import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
import plotly.graph_objects as go
import plotly.express as px

# -------------------------
# Page Config
# -------------------------
st.set_page_config(
    page_title="NetPulse AI Monitor",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------
# Constants
# -------------------------
REFRESH_INTERVAL = 30
ONLINE_THRESHOLD_SECONDS = 60
STALE_THRESHOLD_SECONDS = 120

THINGSPEAK_CHANNEL = "3381959"
THINGSPEAK_KEY = "8F8XKE0PABJFF6GG"

# Email config (for Streamlit Cloud secrets)
try:
    EMAIL_SENDER = st.secrets.get("EMAIL_SENDER", "")
    EMAIL_PASSWORD = st.secrets.get("EMAIL_PASSWORD", "")
    EMAIL_TO = st.secrets.get("EMAIL_TO", "ndahabonimanadaniel13@gmail.com")
except:
    EMAIL_SENDER = ""
    EMAIL_PASSWORD = ""
    EMAIL_TO = "ndahabonimanadaniel13@gmail.com"

# Alert thresholds
ALERT_THRESHOLDS = {
    'critical_score': 40,
    'warning_score': 60,
    'high_latency': 150,
    'high_packet_loss': 3
}

# -------------------------
# Session State
# -------------------------
if 'data' not in st.session_state:
    st.session_state.data = None
if 'prev_data' not in st.session_state:
    st.session_state.prev_data = None
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = datetime.now()
if 'history' not in st.session_state:
    st.session_state.history = []
if 'update_count' not in st.session_state:
    st.session_state.update_count = 0
if 'auto_refresh' not in st.session_state:
    st.session_state.auto_refresh = True
if 'last_alert_sent' not in st.session_state:
    st.session_state.last_alert_sent = {}
if 'status' not in st.session_state:
    st.session_state.status = "offline"
if 'time_diff' not in st.session_state:
    st.session_state.time_diff = 0
if 'pulse_triggered' not in st.session_state:
    st.session_state.pulse_triggered = False

# -------------------------
# CSS Styling (Cyberpunk Theme - Same as Local)
# -------------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;600;700;800;900&family=Share+Tech+Mono&family=Rajdhani:wght@300;400;500;600;700&display=swap');
    
    /* Main container */
    .stApp {
        background: linear-gradient(135deg, #0a0a0f 0%, #0d0d15 50%, #0a0a0f 100%);
        background-attachment: fixed;
    }
    
    /* Hide default Streamlit elements */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Custom scrollbar */
    ::-webkit-scrollbar {
        width: 6px;
        height: 6px;
    }
    ::-webkit-scrollbar-track {
        background: rgba(0, 245, 255, 0.05);
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb {
        background: rgba(0, 245, 255, 0.3);
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: rgba(0, 245, 255, 0.5);
    }
    
    /* Header Section */
    .netpulse-header {
        text-align: center;
        padding: 1.5rem 0.5rem 1rem;
        margin-bottom: 1.5rem;
        position: relative;
        border-bottom: 1px solid rgba(0, 245, 255, 0.15);
        background: linear-gradient(180deg, rgba(0, 245, 255, 0.02) 0%, transparent 100%);
    }
    .netpulse-header::before {
        content: '';
        position: absolute;
        top: 0;
        left: 20%;
        right: 20%;
        height: 1px;
        background: linear-gradient(90deg, transparent, #00f5ff, #00ff88, #00f5ff, transparent);
    }
    .header-title {
        font-family: 'Orbitron', monospace;
        font-size: 2.4rem;
        font-weight: 800;
        letter-spacing: 0.3rem;
        background: linear-gradient(135deg, #00f5ff 0%, #00ff88 50%, #00f5ff 100%);
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
        text-shadow: 0 0 30px rgba(0, 245, 255, 0.3);
    }
    .header-sub {
        font-family: 'Rajdhani', sans-serif;
        font-size: 0.8rem;
        letter-spacing: 0.15rem;
        color: #5a7a9a;
        margin-top: 0.5rem;
        text-transform: uppercase;
    }
    .header-badge {
        display: inline-block;
        margin-top: 0.8rem;
        padding: 0.3rem 1rem;
        background: rgba(0, 245, 255, 0.08);
        border: 1px solid rgba(0, 245, 255, 0.2);
        border-radius: 20px;
        font-family: 'Share Tech Mono', monospace;
        font-size: 0.7rem;
        color: #00f5ff;
        backdrop-filter: blur(5px);
    }
    .pulse-dot {
        display: inline-block;
        width: 8px;
        height: 8px;
        background: #00ff88;
        border-radius: 50%;
        margin-right: 6px;
        box-shadow: 0 0 8px #00ff88;
        animation: pulse-green 1.5s infinite;
    }
    @keyframes pulse-green {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.5; transform: scale(1.2); }
    }
    .data-updated {
        animation: flash 0.5s ease-out;
    }
    @keyframes flash {
        0% { background: rgba(0, 255, 136, 0.15); }
        100% { background: transparent; }
    }
    
    /* Cyber divider */
    .cyber-divider {
        margin: 1.2rem 0;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(0, 245, 255, 0.3), rgba(0, 255, 136, 0.3), rgba(0, 245, 255, 0.3), transparent);
    }
    
    /* Score Ring Container */
    .score-ring-wrap {
        background: linear-gradient(135deg, rgba(0, 245, 255, 0.05) 0%, rgba(0, 0, 0, 0.2) 100%);
        border-radius: 16px;
        padding: 1.5rem;
        text-align: center;
        border: 1px solid rgba(0, 245, 255, 0.15);
        backdrop-filter: blur(10px);
        transition: all 0.3s ease;
    }
    .score-ring-wrap:hover {
        border-color: rgba(0, 245, 255, 0.4);
        box-shadow: 0 0 25px rgba(0, 245, 255, 0.1);
    }
    .score-label {
        font-family: 'Share Tech Mono', monospace;
        font-size: 0.7rem;
        letter-spacing: 0.2rem;
        color: #7a9abc;
        text-transform: uppercase;
    }
    .score-number {
        font-family: 'Orbitron', monospace;
        font-size: 5rem;
        font-weight: 800;
        margin: 0.2rem 0;
        line-height: 1;
    }
    .score-status {
        display: inline-block;
        margin-top: 0.8rem;
        padding: 0.3rem 1rem;
        border-radius: 20px;
        font-family: 'Orbitron', monospace;
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 0.1rem;
        background: rgba(0, 0, 0, 0.3);
    }
    
    /* Prediction Cards */
    .pred-critical, .pred-warning, .pred-normal {
        background: linear-gradient(135deg, rgba(0, 0, 0, 0.4) 0%, rgba(0, 0, 0, 0.2) 100%);
        border-radius: 12px;
        padding: 1.2rem;
        backdrop-filter: blur(10px);
        height: 100%;
    }
    .pred-critical {
        border: 1px solid rgba(255, 0, 60, 0.3);
    }
    .pred-warning {
        border: 1px solid rgba(255, 107, 0, 0.3);
    }
    .pred-normal {
        border: 1px solid rgba(0, 255, 136, 0.3);
    }
    .pred-title {
        font-family: 'Orbitron', monospace;
        font-size: 1rem;
        font-weight: 700;
        letter-spacing: 0.1rem;
        margin-bottom: 0.5rem;
    }
    .pred-sub {
        font-family: 'Rajdhani', sans-serif;
        font-size: 0.85rem;
        color: #a0b8cc;
        line-height: 1.4;
    }
    
    /* Service Panels */
    .svc-panel {
        background: linear-gradient(135deg, rgba(0, 0, 0, 0.3) 0%, rgba(0, 0, 0, 0.15) 100%);
        border-radius: 12px;
        padding: 1.2rem;
        backdrop-filter: blur(10px);
        transition: all 0.3s ease;
    }
    .svc-panel:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(0, 0, 0, 0.3);
    }
    .svc-title {
        font-family: 'Orbitron', monospace;
        font-size: 1.1rem;
        font-weight: 600;
        letter-spacing: 0.1rem;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    .quality-bar-wrap {
        margin-bottom: 1rem;
    }
    .quality-bar-top {
        display: flex;
        justify-content: space-between;
        margin-bottom: 0.4rem;
    }
    .quality-bar-name {
        font-family: 'Share Tech Mono', monospace;
        font-size: 0.7rem;
        color: #7a9abc;
    }
    .quality-bar-score {
        font-family: 'Orbitron', monospace;
        font-size: 1rem;
        font-weight: 700;
    }
    .quality-bar-track {
        background: rgba(255, 255, 255, 0.08);
        border-radius: 4px;
        height: 6px;
        overflow: hidden;
    }
    .quality-bar-fill {
        height: 100%;
        border-radius: 4px;
        transition: width 0.5s ease;
    }
    .metric-row {
        display: grid;
        grid-template-columns: 1fr 1fr 1fr;
        gap: 0.8rem;
        margin-top: 1rem;
    }
    .metric-cell {
        background: rgba(0, 0, 0, 0.3);
        border-radius: 8px;
        padding: 0.5rem;
        text-align: center;
    }
    .metric-cell-label {
        font-family: 'Share Tech Mono', monospace;
        font-size: 0.6rem;
        color: #5a7a9a;
        text-transform: uppercase;
        letter-spacing: 0.05rem;
    }
    .metric-cell-value {
        font-family: 'Orbitron', monospace;
        font-size: 1rem;
        font-weight: 600;
        color: #e8f4fd;
    }
    .metric-cell-unit {
        font-family: 'Share Tech Mono', monospace;
        font-size: 0.6rem;
        color: #5a7a9a;
        margin-left: 2px;
    }
    
    /* Alert messages */
    .alert-critical, .alert-warning, .alert-good {
        padding: 0.8rem 1rem;
        margin: 0.5rem 0;
        border-radius: 6px;
        font-family: 'Rajdhani', sans-serif;
        font-size: 0.85rem;
        border-left: 4px solid;
    }
    .alert-critical {
        background: rgba(255, 0, 60, 0.08);
        border-left-color: #ff003c;
        color: #ff6b8a;
    }
    .alert-warning {
        background: rgba(255, 107, 0, 0.08);
        border-left-color: #ff6b00;
        color: #ffaa66;
    }
    .alert-good {
        background: rgba(0, 255, 136, 0.05);
        border-left-color: #00ff88;
        color: #88ffcc;
    }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(8, 8, 12, 0.95) 0%, rgba(5, 5, 8, 0.98) 100%);
        border-right: 1px solid rgba(0, 245, 255, 0.1);
        backdrop-filter: blur(10px);
    }
    .sidebar-stat {
        display: flex;
        justify-content: space-between;
        margin: 0.8rem 0;
        padding: 0.3rem 0;
        border-bottom: 1px dashed rgba(0, 245, 255, 0.1);
    }
    .sidebar-stat-label {
        font-family: 'Share Tech Mono', monospace;
        font-size: 0.7rem;
        color: #5a7a9a;
        text-transform: uppercase;
    }
    .sidebar-stat-value {
        font-family: 'Orbitron', monospace;
        font-size: 0.8rem;
        color: #00f5ff;
        font-weight: 600;
    }
    .status-online {
        color: #00ff88;
        text-shadow: 0 0 5px #00ff88;
    }
    .status-stale {
        color: #ffaa00;
    }
    .status-offline {
        color: #ff003c;
    }
    
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 1rem;
        background: rgba(0, 0, 0, 0.2);
        border-radius: 8px;
        padding: 0.3rem;
    }
    .stTabs [data-baseweb="tab"] {
        font-family: 'Orbitron', monospace;
        font-size: 0.8rem;
        letter-spacing: 0.1rem;
        border-radius: 6px;
        padding: 0.4rem 1.2rem;
        background: transparent;
        color: #7a9abc;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(0, 245, 255, 0.12);
        color: #00f5ff;
        border-bottom: 2px solid #00f5ff;
    }
    
    /* Metrics styling */
    [data-testid="stMetric"] {
        background: rgba(0, 0, 0, 0.25);
        border-radius: 8px;
        padding: 0.5rem;
    }
    [data-testid="stMetricLabel"] {
        font-family: 'Share Tech Mono', monospace;
        font-size: 0.7rem;
        color: #7a9abc;
    }
    [data-testid="stMetricValue"] {
        font-family: 'Orbitron', monospace;
        font-size: 1.2rem;
        color: #00f5ff;
    }
    
    /* Button styling */
    .stButton button {
        font-family: 'Orbitron', monospace;
        background: linear-gradient(135deg, rgba(0, 245, 255, 0.15) 0%, rgba(0, 0, 0, 0.3) 100%);
        border: 1px solid rgba(0, 245, 255, 0.3);
        color: #00f5ff;
        transition: all 0.3s ease;
        width: 100%;
    }
    .stButton button:hover {
        border-color: #00f5ff;
        box-shadow: 0 0 15px rgba(0, 245, 255, 0.2);
        transform: translateY(-1px);
    }
    
    /* Expander styling */
    .streamlit-expanderHeader {
        font-family: 'Rajdhani', sans-serif;
        background: rgba(0, 0, 0, 0.2);
        border-radius: 6px;
    }
    
    /* Dataframe styling */
    .dataframe {
        font-family: 'Share Tech Mono', monospace;
        font-size: 0.75rem;
    }
</style>
""", unsafe_allow_html=True)

# -------------------------
# Helper Functions
# -------------------------
def get_score_color(score):
    if score >= 80: return "#00ff88"
    if score >= 60: return "#00f5ff"
    if score >= 40: return "#ffe600"
    if score >= 20: return "#ff6b00"
    return "#ff003c"

def get_network_status(score):
    if score >= 80: return "EXCELLENT"
    if score >= 60: return "GOOD"
    if score >= 40: return "FAIR"
    if score >= 20: return "POOR"
    return "CRITICAL"

def format_time_diff(seconds):
    if seconds < 60: return f"{int(seconds)}s ago"
    if seconds < 3600: return f"{int(seconds/60)}m ago"
    if seconds < 86400: return f"{int(seconds/3600)}h ago"
    return f"{int(seconds/86400)}d ago"

def calculate_score(latency, loss, bandwidth, service):
    """Calculate quality score (0-100)"""
    if service == 'google':
        if latency <= 50: latency_score = 100
        elif latency <= 100: latency_score = 60 - (latency - 50) / 50 * 40
        else: latency_score = max(0, 20 - (latency - 100) / 10)
        
        if loss <= 1: loss_score = 100
        elif loss <= 2: loss_score = 70 - (loss - 1) / 1 * 30
        else: loss_score = max(0, 40 - (loss - 2) * 20)
        
        if bandwidth >= 50: bw_score = 100
        elif bandwidth >= 20: bw_score = 60 + (bandwidth - 20) / 30 * 40
        else: bw_score = (bandwidth / 20) * 60
    else:  # YouTube
        if latency <= 70: latency_score = 100
        elif latency <= 140: latency_score = 60 - (latency - 70) / 70 * 40
        else: latency_score = max(0, 20 - (latency - 140) / 10)
        
        if loss <= 0.5: loss_score = 100
        elif loss <= 1.5: loss_score = 70 - (loss - 0.5) / 1 * 30
        else: loss_score = max(0, 40 - (loss - 1.5) * 20)
        
        if bandwidth >= 75: bw_score = 100
        elif bandwidth >= 30: bw_score = 60 + (bandwidth - 30) / 45 * 40
        else: bw_score = (bandwidth / 30) * 60
    
    return int(latency_score * 0.4 + loss_score * 0.3 + bw_score * 0.3)

def fetch_data():
    """Fetch data from ThingSpeak"""
    try:
        url = f"https://api.thingspeak.com/channels/{THINGSPEAK_CHANNEL}/feeds/last.json?api_key={THINGSPEAK_KEY}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Parse fields
            g_lat = float(data.get('field1', 0) or 0)
            g_loss = float(data.get('field2', 0) or 0)
            g_bw = float(data.get('field3', 0) or 0)
            y_lat = float(data.get('field4', 0) or 0)
            y_loss = float(data.get('field5', 0) or 0)
            y_bw = float(data.get('field6', 0) or 0)
            combined_speed = float(data.get('field7', 0) or 0)
            raw_score = float(data.get('field8', 0) or 0)
            
            # Get timestamp from ThingSpeak
            last_update_str = data.get('created_at')
            if last_update_str:
                last_update = datetime.strptime(last_update_str, '%Y-%m-%dT%H:%M:%SZ')
                time_diff = (datetime.utcnow() - last_update).total_seconds()
                if time_diff > STALE_THRESHOLD_SECONDS:
                    st.session_state.status = "stale"
                else:
                    st.session_state.status = "online"
                st.session_state.time_diff = time_diff
            
            result = {
                'timestamp': datetime.now(),
                'google_latency': g_lat,
                'google_loss': g_loss,
                'google_bw': g_bw,
                'youtube_latency': y_lat,
                'youtube_loss': y_loss,
                'youtube_bw': y_bw,
                'combined_speed': combined_speed,
                'raw_score': raw_score,
                'google_score': calculate_score(g_lat, g_loss, g_bw, 'google'),
                'youtube_score': calculate_score(y_lat, y_loss, y_bw, 'youtube')
            }
            
            # Final network score
            if raw_score > 0:
                result['network_score'] = raw_score
            else:
                result['network_score'] = (result['google_score'] + result['youtube_score']) / 2
            
            result['status'] = get_network_status(result['network_score'])
            result['status_color'] = get_score_color(result['network_score'])
            
            return result
        return None
    except Exception as e:
        st.session_state.status = "offline"
        return None

def send_alert(subject, message, alert_type="general"):
    """Send email alert with cooldown"""
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        return False
    
    # Check cooldown (5 minutes)
    last_sent = st.session_state.last_alert_sent.get(alert_type, datetime.min)
    if (datetime.now() - last_sent).total_seconds() < 300:
        return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_TO
        msg['Subject'] = f"[NetPulse] {subject}"
        
        body = f"""
<html>
<head>
    <style>
        body {{ font-family: 'Courier New', monospace; background-color: #0a0a0a; color: #00ff88; }}
        .container {{ padding: 20px; border: 1px solid #00ff88; border-radius: 5px; }}
        .critical {{ color: #ff003c; }}
        .warning {{ color: #ff6b00; }}
        .good {{ color: #00ff88; }}
    </style>
</head>
<body>
    <div class="container">
        <h2>🛰 NetPulse Monitor Alert</h2>
        <hr>
        <div class="{alert_type}">{message}</div>
        <hr>
        <div>Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        <div>Monitor: Google & YouTube Service Classification</div>
    </div>
</body>
</html>
"""
        msg.attach(MIMEText(body, 'html'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        st.session_state.last_alert_sent[alert_type] = datetime.now()
        return True
    except:
        return False

def check_and_send_alerts(data):
    """Check conditions and send alerts"""
    if not data:
        return
    
    alerts_sent = []
    
    # Critical score alert
    if data['network_score'] < ALERT_THRESHOLDS['critical_score']:
        subject = "🚨 CRITICAL: Network Health Degraded"
        message = f"""
        <div class="critical">
        <strong>CRITICAL ALERT - Immediate Attention Required</strong><br><br>
        Network Health Score: <strong>{data['network_score']:.1f}/100</strong><br>
        Status: {data['status']}<br><br>
        Google: {data['google_score']}/100 (Latency: {data['google_latency']:.1f}ms)<br>
        YouTube: {data['youtube_score']}/100 (Latency: {data['youtube_latency']:.1f}ms)<br>
        Combined Speed: {data['combined_speed']:.1f} Mbps
        </div>
        """
        if send_alert(subject, message, "critical"):
            alerts_sent.append("Critical Alert")
    
    # Warning score alert
    elif data['network_score'] < ALERT_THRESHOLDS['warning_score']:
        subject = "⚠️ Network Performance Degraded"
        message = f"""
        <div class="warning">
        <strong>Network Performance Below Optimal Levels</strong><br><br>
        Network Score: {data['network_score']:.1f}/100<br>
        Combined Speed: {data['combined_speed']:.1f} Mbps
        </div>
        """
        if send_alert(subject, message, "warning"):
            alerts_sent.append("Warning Alert")
    
    # High latency alert
    if data['google_latency'] > ALERT_THRESHOLDS['high_latency'] or data['youtube_latency'] > ALERT_THRESHOLDS['high_latency']:
        subject = "📡 High Latency Detected"
        message = f"""
        <div class="warning">
        Google Latency: {data['google_latency']:.1f}ms<br>
        YouTube Latency: {data['youtube_latency']:.1f}ms<br>
        Threshold: {ALERT_THRESHOLDS['high_latency']}ms
        </div>
        """
        send_alert(subject, message, "latency")
    
    # Recovery alert
    if st.session_state.prev_data:
        prev_score = st.session_state.prev_data.get('network_score', 0)
        if prev_score < 50 and data['network_score'] >= 70:
            subject = "✅ Network Recovery Detected"
            message = f"""
            <div class="good">
            Previous Score: {prev_score:.1f}/100<br>
            Current Score: {data['network_score']:.1f}/100<br>
            Network is now operating normally.
            </div>
            """
            send_alert(subject, message, "recovery")
    
    return alerts_sent

def generate_recommendations(data):
    """Generate recommendations based on current data"""
    recs = []
    
    if data['network_score'] < 40:
        recs.append({
            'service': 'Network',
            'message': 'CRITICAL — Network severely degraded! Immediate investigation required.',
            'severity': 'critical'
        })
    elif data['network_score'] < 60:
        recs.append({
            'service': 'Network',
            'message': 'WARNING — Network performance below optimal levels. Monitor for patterns.',
            'severity': 'warning'
        })
    else:
        recs.append({
            'service': 'Network',
            'message': 'OPTIMAL — All services operating within normal parameters.',
            'severity': 'good'
        })
    
    if data['google_score'] < 60:
        recs.append({
            'service': 'Google',
            'message': f'Google performance degraded (Score: {data["google_score"]}/100). Latency: {data["google_latency"]:.1f}ms',
            'severity': 'warning' if data['google_score'] >= 40 else 'critical'
        })
    
    if data['youtube_score'] < 60:
        recs.append({
            'service': 'YouTube',
            'message': f'YouTube performance degraded (Score: {data["youtube_score"]}/100). Latency: {data["youtube_latency"]:.1f}ms',
            'severity': 'warning' if data['youtube_score'] >= 40 else 'critical'
        })
    
    if data['combined_speed'] < 30:
        recs.append({
            'service': 'Bandwidth',
            'message': f'Low bandwidth detected ({data["combined_speed"]:.1f} Mbps). May affect streaming quality.',
            'severity': 'warning'
        })
    
    return recs

# -------------------------
# Auto Refresh Logic
# -------------------------
now = datetime.now()
since_refresh = (now - st.session_state.last_refresh).total_seconds()
next_refresh = max(0, REFRESH_INTERVAL - since_refresh)

if since_refresh >= REFRESH_INTERVAL and st.session_state.auto_refresh and st.session_state.data:
    new_data = fetch_data()
    if new_data:
        st.session_state.prev_data = st.session_state.data
        st.session_state.data = new_data
        st.session_state.history.insert(0, new_data)
        if len(st.session_state.history) > 100:
            st.session_state.history = st.session_state.history[:100]
        st.session_state.update_count += 1
        st.session_state.last_refresh = datetime.now()
        st.session_state.pulse_triggered = True
        check_and_send_alerts(new_data)
        st.rerun()

# -------------------------
# Main App
# -------------------------
def main():
    pulse_class = "data-updated" if st.session_state.pulse_triggered else ""
    st.session_state.pulse_triggered = False
    
    # Header
    st.markdown(f"""
    <div class="netpulse-header {pulse_class}">
        <div class="header-title">🛰 NETPULSE AI MONITOR</div>
        <div class="header-sub">GOOGLE &amp; YOUTUBE SERVICE CLASSIFICATION · THINGSPEAK LIVE FEED</div>
        <div class="header-badge">
            <span class="pulse-dot"></span>
            LIVE · AUTO-REFRESH {REFRESH_INTERVAL}S · UPDATE #{st.session_state.update_count}
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.markdown("### ⚡ SYSTEM CONTROLS")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            auto_refresh = st.toggle("AUTO REFRESH", value=st.session_state.auto_refresh)
            if auto_refresh != st.session_state.auto_refresh:
                st.session_state.auto_refresh = auto_refresh
                st.rerun()
        with col2:
            if st.button("⟳", help="Refresh Now"):
                with st.spinner("Fetching data..."):
                    new_data = fetch_data()
                    if new_data:
                        st.session_state.prev_data = st.session_state.data
                        st.session_state.data = new_data
                        st.session_state.history.insert(0, new_data)
                        if len(st.session_state.history) > 100:
                            st.session_state.history = st.session_state.history[:100]
                        st.session_state.update_count += 1
                        st.session_state.last_refresh = datetime.now()
                        st.session_state.pulse_triggered = True
                        check_and_send_alerts(new_data)
                        st.success("✅ Data updated!")
                        st.rerun()
                    else:
                        st.error("❌ Failed to fetch data")
        
        st.markdown('<div class="cyber-divider"></div>', unsafe_allow_html=True)
        
        # Connection Status
        st.markdown("### 🔗 CONNECTION STATUS")
        
        status_map = {
            'online': ('◉ ONLINE', '#00ff88'),
            'stale': ('◌ STALE', '#ffaa00'),
            'offline': ('✕ OFFLINE', '#ff003c'),
        }
        status_text, status_color = status_map.get(st.session_state.status, ('✕ UNKNOWN', '#ff003c'))
        st.markdown(f"""
        <div class="sidebar-stat">
            <span class="sidebar-stat-label">THINGSPEAK</span>
            <span style="color:{status_color};">{status_text}</span>
        </div>
        """, unsafe_allow_html=True)
        
        if st.session_state.time_diff > 0:
            st.markdown(f"""
            <div class="sidebar-stat">
                <span class="sidebar-stat-label">LAST UPDATE</span>
                <span>{format_time_diff(st.session_state.time_diff)}</span>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown('<div class="cyber-divider"></div>', unsafe_allow_html=True)
        
        # Statistics
        st.markdown("### 📊 STATISTICS")
        
        if st.session_state.data:
            st.metric("Current Score", f"{st.session_state.data['network_score']:.0f}/100")
            st.metric("Combined Speed", f"{st.session_state.data['combined_speed']:.1f} Mbps")
            st.metric("Total Updates", st.session_state.update_count)
            st.metric("History Records", len(st.session_state.history))
        
        st.markdown('<div class="cyber-divider"></div>', unsafe_allow_html=True)
        
        # Email Configuration
        st.markdown("### ✉️ ALERTS")
        
        if EMAIL_SENDER and EMAIL_PASSWORD:
            st.success("✅ Email configured")
            st.caption(f"📧 Sending to: {EMAIL_TO}")
            st.caption("⏱️ Cooldown: 5 minutes per alert type")
        else:
            st.warning("⚠️ Email not configured")
            with st.expander("How to configure email alerts"):
                st.markdown("""
                To enable email alerts, add to Streamlit secrets:
                
                ```toml
                EMAIL_SENDER = "your.email@gmail.com"
                EMAIL_PASSWORD = "your_app_password"
                EMAIL_TO = "recipient@email.com"
