# -*- coding: utf-8 -*-
"""
AI Network Monitor - Google & YouTube
Enhanced Ultra-Modern UI with Live Animations & Email Notifications
GITHUB READY - Stores data in CSV files
"""

import streamlit as st
import pandas as pd
import numpy as np
import joblib
import requests
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import hashlib
import os
from pathlib import Path

# -------------------------
# Page Configuration
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
ONLINE_THRESHOLD_SECONDS = 60
STALE_THRESHOLD_SECONDS = 120
OFFLINE_THRESHOLD_SECONDS = 300
REFRESH_INTERVAL = 15
DATABASE_SAVE_INTERVAL = 10  # Save every 10 seconds

# CSV Storage Setup
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

METRICS_CSV = DATA_DIR / "network_metrics.csv"
RECOMMENDATIONS_CSV = DATA_DIR / "recommendations.csv"
LOGS_CSV = DATA_DIR / "system_logs.csv"

# Initialize CSV files with headers if they don't exist
if not METRICS_CSV.exists():
    pd.DataFrame(columns=[
        'timestamp', 'google_latency', 'google_packet_loss', 'google_bandwidth', 'google_quality',
        'youtube_latency', 'youtube_packet_loss', 'youtube_bandwidth', 'youtube_quality',
        'combined_speed', 'network_score', 'network_status', 'congestion_prediction'
    ]).to_csv(METRICS_CSV, index=False)

if not RECOMMENDATIONS_CSV.exists():
    pd.DataFrame(columns=[
        'timestamp', 'service', 'recommendation', 'severity', 'network_score', 'network_status'
    ]).to_csv(RECOMMENDATIONS_CSV, index=False)

if not LOGS_CSV.exists():
    pd.DataFrame(columns=[
        'timestamp', 'log_type', 'message'
    ]).to_csv(LOGS_CSV, index=False)

SERVICE_THRESHOLDS = {
    'google': {'latency_good': 50, 'latency_warning': 100, 'loss_good': 1, 'loss_warning': 2, 'bw_good': 50, 'bw_warning': 20},
    'youtube': {'latency_good': 70, 'latency_warning': 140, 'loss_good': 0.5, 'loss_warning': 1.5, 'bw_good': 75, 'bw_warning': 30}
}

# Email Configuration
EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'sender_email': 'offliqz@gmail.com',
    'sender_password': 'lkid xdce bpls xvtw',
    'recipient_email': 'ndahabonimanadaniel13@gmail.com'
}

# Notification cooldown
NOTIFICATION_COOLDOWN = 300
ALERT_THRESHOLDS = {
    'critical_score': 40,
    'congestion_alert': 50,
    'high_latency': 150,
    'high_packet_loss': 3
}

# -------------------------
# Session State
# -------------------------
for key, val in {
    'last_refresh': datetime.now(),
    'auto_refresh': True,
    'data': None,
    'prev_data': None,
    'time_diff': 0,
    'last_update': None,
    'status': "offline",
    'last_database_save': datetime.now(),
    'pulse_triggered': False,
    'update_count': 0,
    'last_notification_sent': {},
    'email_configured': False,
    'db_write_count': 0
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

# -------------------------
# Quality / Score Helpers
# -------------------------
def score_color(score):
    if score >= 80: return "#00ff88"
    elif score >= 60: return "#00f5ff"
    elif score >= 40: return "#ffe600"
    elif score >= 20: return "#ff6b00"
    else: return "#ff003c"

def score_shadow(score):
    c = score_color(score)
    return f"0 0 20px {c}80, 0 0 40px {c}40"

def get_network_status(score):
    if score >= 80: return "EXCELLENT"
    elif score >= 60: return "GOOD"
    elif score >= 40: return "FAIR"
    elif score >= 20: return "POOR"
    else: return "CRITICAL"

def calculate_quality_score(latency, packet_loss, bandwidth, service):
    t = SERVICE_THRESHOLDS.get(service, SERVICE_THRESHOLDS['google'])
    if latency <= t['latency_good']:       latency_score = 100
    elif latency <= t['latency_warning']:  latency_score = 60 - (latency - t['latency_good']) / (t['latency_warning'] - t['latency_good']) * 40
    else:                                  latency_score = max(0, 20 - (latency - t['latency_warning']) / 10)
    if packet_loss <= t['loss_good']:      loss_score = 100
    elif packet_loss <= t['loss_warning']: loss_score = 70 - (packet_loss - t['loss_good']) / (t['loss_warning'] - t['loss_good']) * 30
    else:                                  loss_score = max(0, 40 - (packet_loss - t['loss_warning']) * 20)
    if bandwidth >= t['bw_good']:          bw_score = 100
    elif bandwidth >= t['bw_warning']:     bw_score = 60 + (bandwidth - t['bw_warning']) / (t['bw_good'] - t['bw_warning']) * 40
    else:                                  bw_score = max(0, (bandwidth / t['bw_warning']) * 60)
    return int(latency_score * 0.4 + loss_score * 0.3 + bw_score * 0.3)

def format_time_diff(s):
    if s < 60: return f"{int(s)}s ago"
    elif s < 3600: return f"{int(s/60)}m ago"
    elif s < 86400: return f"{int(s/3600)}h ago"
    else: return f"{int(s/86400)}d ago"

def generate_recommendations(data):
    recs = []
    for svc, key in [('Google', 'google'), ('YouTube', 'youtube')]:
        q = data[f'{key}_quality']
        if q < 40:
            recs.append({'service': svc, 'message': f"CRITICAL — {svc} severely degraded (Score: {q}/100). Latency: {data[f'{key}_latency']:.1f}ms, Loss: {data[f'{key}_packet_loss']:.1f}%", 'severity': 'critical'})
        elif q < 60:
            recs.append({'service': svc, 'message': f"DEGRADED — {svc} performance below threshold (Score: {q}/100). Check routing.", 'severity': 'warning'})
        elif q >= 80:
            recs.append({'service': svc, 'message': f"OPTIMAL — {svc} all metrics nominal (Score: {q}/100).", 'severity': 'good'})
    if data['network_score'] < 50:
        recs.append({'service': 'Network', 'message': f"SYSTEM ALERT — Network health critical ({data['network_score']:.0f}/100). Immediate investigation required.", 'severity': 'critical'})
    elif data['combined_speed'] < 30:
        recs.append({'service': 'Network', 'message': f"BANDWIDTH LOW — Combined speed {data['combined_speed']:.1f} Mbps. Upgrade plan or check ISP.", 'severity': 'warning'})
    return recs

# -------------------------
# CSV Storage Functions
# -------------------------
def add_log_entry(log_type, message):
    """Add entry to system logs CSV"""
    try:
        new_entry = pd.DataFrame([{
            'timestamp': datetime.now(),
            'log_type': log_type,
            'message': message
        }])
        
        existing = pd.read_csv(LOGS_CSV) if LOGS_CSV.exists() else pd.DataFrame()
        updated = pd.concat([existing, new_entry], ignore_index=True)
        updated.to_csv(LOGS_CSV, index=False)
        
        # Keep only last 1000 logs to prevent file from growing too large
        if len(updated) > 1000:
            updated.tail(1000).to_csv(LOGS_CSV, index=False)
            
    except Exception as e:
        print(f"Log error: {e}")

def save_classified_metrics(data, prediction):
    """Save metrics to CSV file"""
    if not data or data['network_score'] == 0:
        return False
    
    try:
        # Create new metrics record
        new_record = pd.DataFrame([{
            'timestamp': datetime.now(),
            'google_latency': data['google_latency'],
            'google_packet_loss': data['google_packet_loss'],
            'google_bandwidth': data['google_bandwidth'],
            'google_quality': data['google_quality'],
            'youtube_latency': data['youtube_latency'],
            'youtube_packet_loss': data['youtube_packet_loss'],
            'youtube_bandwidth': data['youtube_bandwidth'],
            'youtube_quality': data['youtube_quality'],
            'combined_speed': data['combined_speed'],
            'network_score': data['network_score'],
            'network_status': data['network_status'],
            'congestion_prediction': prediction
        }])
        
        # Append to existing CSV
        if METRICS_CSV.exists():
            existing = pd.read_csv(METRICS_CSV)
            # Check for duplicate within last 30 seconds
            if not existing.empty:
                last_record = existing.iloc[-1]
                time_diff = (datetime.now() - pd.to_datetime(last_record['timestamp'])).total_seconds()
                if time_diff < 30 and abs(last_record['network_score'] - data['network_score']) < 5:
                    return False  # Duplicate, don't save
        
        updated = pd.concat([existing, new_record], ignore_index=True) if METRICS_CSV.exists() else new_record
        updated.to_csv(METRICS_CSV, index=False)
        
        # Save recommendations
        for rec in generate_recommendations(data):
            rec_record = pd.DataFrame([{
                'timestamp': datetime.now(),
                'service': rec['service'],
                'recommendation': rec['message'],
                'severity': rec['severity'],
                'network_score': data['network_score'],
                'network_status': data['network_status']
            }])
            
            existing_recs = pd.read_csv(RECOMMENDATIONS_CSV) if RECOMMENDATIONS_CSV.exists() else pd.DataFrame()
            updated_recs = pd.concat([existing_recs, rec_record], ignore_index=True)
            updated_recs.to_csv(RECOMMENDATIONS_CSV, index=False)
        
        st.session_state.db_write_count += 1
        st.session_state.last_database_save = datetime.now()
        add_log_entry("INFO", f"Data saved to CSV (Record #{st.session_state.db_write_count}): Score={data['network_score']:.1f}")
        return True
        
    except Exception as e:
        add_log_entry("ERROR", f"Failed to save metrics: {str(e)}")
        return False

def load_historical_data(limit=100):
    """Load historical metrics from CSV"""
    try:
        if METRICS_CSV.exists():
            df = pd.read_csv(METRICS_CSV)
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df = df.sort_values('timestamp', ascending=False)
                return df.head(limit)
        return pd.DataFrame()
    except Exception as e:
        add_log_entry("ERROR", f"Failed to load historical data: {str(e)}")
        return pd.DataFrame()

def load_recommendations_history(limit=50):
    """Load recommendations from CSV"""
    try:
        if RECOMMENDATIONS_CSV.exists():
            df = pd.read_csv(RECOMMENDATIONS_CSV)
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df = df.sort_values('timestamp', ascending=False)
                return df.head(limit)
        return pd.DataFrame()
    except Exception as e:
        add_log_entry("ERROR", f"Failed to load recommendations: {str(e)}")
        return pd.DataFrame()

def load_system_logs(limit=100):
    """Load system logs from CSV"""
    try:
        if LOGS_CSV.exists():
            df = pd.read_csv(LOGS_CSV)
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df = df.sort_values('timestamp', ascending=False)
                return df.head(limit)
        return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

def get_data_stats():
    """Get statistics about stored data"""
    stats = {
        'total_records': 0,
        'date_range': None,
        'avg_score': 0,
        'last_update': None
    }
    
    if METRICS_CSV.exists():
        df = pd.read_csv(METRICS_CSV)
        if not df.empty:
            stats['total_records'] = len(df)
            stats['avg_score'] = df['network_score'].mean()
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            stats['date_range'] = f"{df['timestamp'].min().strftime('%Y-%m-%d')} to {df['timestamp'].max().strftime('%Y-%m-%d')}"
            stats['last_update'] = df['timestamp'].max()
    
    return stats

# -------------------------
# Email Functions
# -------------------------
def test_email_connection():
    if not EMAIL_CONFIG['sender_email'] or not EMAIL_CONFIG['sender_password']:
        return False, "Email credentials not configured. Please add your Gmail credentials in the sidebar."
    try:
        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        server.starttls()
        server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
        server.quit()
        return True, "Email configured successfully!"
    except Exception as e:
        return False, f"Email configuration error: {str(e)}"

def send_email_notification(subject, body, alert_type="general"):
    last_sent = st.session_state.last_notification_sent.get(alert_type, datetime.min)
    cooldown_remaining = NOTIFICATION_COOLDOWN - (datetime.now() - last_sent).total_seconds()
    if cooldown_remaining > 0:
        return False, f"Notification on cooldown. Next allowed in {int(cooldown_remaining)} seconds"
    if not EMAIL_CONFIG['sender_email'] or not EMAIL_CONFIG['sender_password']:
        return False, "Email credentials not configured"
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_CONFIG['sender_email']
        msg['To'] = EMAIL_CONFIG['recipient_email']
        msg['Subject'] = f"[NetPulse Monitor] {subject}"
        html_body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Courier New', monospace; background-color: #0a0a0a; color: #00ff88; }}
                .container {{ padding: 20px; border: 1px solid #00ff88; border-radius: 5px; }}
                .header {{ color: #00f5ff; font-size: 18px; font-weight: bold; }}
                .critical {{ color: #ff003c; }}
                .warning {{ color: #ff6b00; }}
                .good {{ color: #00ff88; }}
                .info {{ color: #5a7a9a; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">🛰 NETPULSE AI ALERT</div>
                <hr>
                {body}
                <hr>
                <div class="info">Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
                <div class="info">Monitor: Google & YouTube Service Classification</div>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html_body, 'html'))
        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        server.starttls()
        server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
        server.send_message(msg)
        server.quit()
        st.session_state.last_notification_sent[alert_type] = datetime.now()
        return True, "Notification sent successfully"
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"

def check_and_send_alerts(data):
    if not data or data['network_score'] == 0:
        return
    alerts_sent = []
    if data['network_score'] < ALERT_THRESHOLDS['critical_score']:
        subject = "🚨 CRITICAL: Network Health Degraded"
        body = f"""
        <div class="critical">
        <strong>CRITICAL ALERT - Immediate Attention Required</strong><br><br>
        Network Health Score: <strong>{data['network_score']:.1f}/100</strong><br>
        Status: {data['network_status']}<br><br>
        <strong>Service Metrics:</strong><br>
        • Google: {data['google_quality']}/100 (Latency: {data['google_latency']:.1f}ms, Loss: {data['google_packet_loss']:.2f}%)<br>
        • YouTube: {data['youtube_quality']}/100 (Latency: {data['youtube_latency']:.1f}ms, Loss: {data['youtube_packet_loss']:.2f}%)<br>
        • Combined Speed: {data['combined_speed']:.1f} Mbps<br><br>
        <strong>Recommended Actions:</strong><br>
        1. Check your internet connection and router<br>
        2. Contact your ISP if issue persists<br>
        3. Review historical data for patterns<br>
        </div>
        """
        success, msg = send_email_notification(subject, body, "critical_score")
        if success:
            alerts_sent.append("Critical Score Alert")
            add_log_entry("ALERT", f"Critical score alert sent - Score: {data['network_score']:.1f}")
    elif data['network_score'] < ALERT_THRESHOLDS['congestion_alert']:
        subject = "⚠️ Congestion Detected on Network"
        body = f"""
        <div class="warning">
        <strong>Congestion Warning - Network Performance Degraded</strong><br><br>
        Network Score: {data['network_score']:.1f}/100<br>
        Combined Speed: {data['combined_speed']:.1f} Mbps<br><br>
        <strong>Service Impact:</strong><br>
        • Google Quality: {data['google_quality']}/100<br>
        • YouTube Quality: {data['youtube_quality']}/100<br><br>
        <strong>Recommendation:</strong> Monitor your network usage and consider bandwidth optimization.
        </div>
        """
        success, msg = send_email_notification(subject, body, "congestion")
        if success:
            alerts_sent.append("Congestion Alert")
            add_log_entry("WARNING", f"Congestion alert sent - Score: {data['network_score']:.1f}")
    if data['google_latency'] > ALERT_THRESHOLDS['high_latency'] or data['youtube_latency'] > ALERT_THRESHOLDS['high_latency']:
        subject = "📡 High Latency Detected"
        body = f"""
        <div class="warning">
        <strong>High Latency Alert</strong><br><br>
        Google Latency: {data['google_latency']:.1f}ms<br>
        YouTube Latency: {data['youtube_latency']:.1f}ms<br>
        Threshold: {ALERT_THRESHOLDS['high_latency']}ms<br><br>
        High latency can cause buffering and slow page loads.
        </div>
        """
        success, msg = send_email_notification(subject, body, "high_latency")
        if success:
            alerts_sent.append("High Latency Alert")
            add_log_entry("WARNING", f"High latency alert - Google: {data['google_latency']:.1f}ms, YouTube: {data['youtube_latency']:.1f}ms")
    if data['google_packet_loss'] > ALERT_THRESHOLDS['high_packet_loss'] or data['youtube_packet_loss'] > ALERT_THRESHOLDS['high_packet_loss']:
        subject = "📡 High Packet Loss Detected"
        body = f"""
        <div class="warning">
        <strong>High Packet Loss Alert</strong><br><br>
        Google Packet Loss: {data['google_packet_loss']:.2f}%<br>
        YouTube Packet Loss: {data['youtube_packet_loss']:.2f}%<br>
        Threshold: {ALERT_THRESHOLDS['high_packet_loss']}%<br><br>
        High packet loss indicates network instability.
        </div>
        """
        success, msg = send_email_notification(subject, body, "high_loss")
        if success:
            alerts_sent.append("High Packet Loss Alert")
            add_log_entry("WARNING", f"High packet loss - Google: {data['google_packet_loss']:.2f}%, YouTube: {data['youtube_packet_loss']:.2f}%")
    if st.session_state.prev_data:
        prev_score = st.session_state.prev_data.get('network_score', 0)
        if prev_score < 50 and data['network_score'] >= 70:
            subject = "✅ Network Recovery Detected"
            body = f"""
            <div class="good">
            <strong>Network Recovery - Service Restored</strong><br><br>
            Previous Score: {prev_score:.1f}/100<br>
            Current Score: {data['network_score']:.1f}/100<br>
            Status: {data['network_status']}<br><br>
            Network is now operating normally.
            </div>
            """
            success, msg = send_email_notification(subject, body, "recovery")
            if success:
                alerts_sent.append("Recovery Alert")
                add_log_entry("INFO", f"Recovery alert sent - Score improved from {prev_score:.1f} to {data['network_score']:.1f}")
    if st.session_state.status in ['stale', 'offline']:
        subject = f"⚠️ ThingSpeak Feed {st.session_state.status.upper()}"
        body = f"""
        <div class="warning">
        <strong>ThingSpeak Connection Issue</strong><br><br>
        Feed Status: {st.session_state.status.upper()}<br>
        Last Update: {format_time_diff(st.session_state.time_diff) if st.session_state.time_diff else 'Unknown'}<br>
        Time Since Last Update: {st.session_state.time_diff:.0f} seconds<br><br>
        Check ThingSpeak channel configuration and network connectivity.
        </div>
        """
        success, msg = send_email_notification(subject, body, "thingspeak_status")
        if success:
            alerts_sent.append("ThingSpeak Status Alert")
    return alerts_sent

# -------------------------
# ThingSpeak Fetch
# -------------------------
def fetch_thingspeak_data():
    try:
        CHANNEL_ID = "3381959"
        READ_API_KEY = "8F8XKE0PABJFF6GG"
        url = f"http://api.thingspeak.com/channels/{CHANNEL_ID}/feeds.json?api_key={READ_API_KEY}&results=1"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        feed_data = response.json()
        
        if 'feeds' in feed_data and feed_data['feeds']:
            latest = feed_data['feeds'][0]
            last_update_str = latest.get('created_at')
            
            if last_update_str:
                last_update = datetime.strptime(last_update_str, '%Y-%m-%dT%H:%M:%SZ')
                time_diff = (datetime.utcnow() - last_update).total_seconds()
                
                if time_diff > OFFLINE_THRESHOLD_SECONDS:
                    return None, time_diff, last_update, "offline"
                if time_diff > STALE_THRESHOLD_SECONDS:
                    return None, time_diff, last_update, "stale"
            else:
                time_diff = OFFLINE_THRESHOLD_SECONDS
                last_update = None
            
            def fv(f): return float(latest.get(f, 0) or 0)
            g_lat, g_loss, g_bw = fv('field1'), fv('field2'), fv('field3')
            y_lat, y_loss, y_bw = fv('field4'), fv('field5'), fv('field6')
            combined_speed = fv('field7')
            network_score  = fv('field8')
            
            # If all zeros, return None
            if g_lat == 0 and y_lat == 0 and network_score == 0:
                return None, time_diff, last_update, "offline"
            
            # Calculate quality scores
            google_quality = calculate_quality_score(g_lat, g_loss, g_bw, 'google')
            youtube_quality = calculate_quality_score(y_lat, y_loss, y_bw, 'youtube')
            
            # Use ThingSpeak network_score if valid, otherwise calculate
            if network_score <= 0 or network_score > 100:
                network_score = (google_quality + youtube_quality) / 2
            
            status = get_network_status(network_score)
            
            d = {
                'google_latency': g_lat,
                'google_packet_loss': g_loss,
                'google_bandwidth': g_bw,
                'google_quality': google_quality,
                'youtube_latency': y_lat,
                'youtube_packet_loss': y_loss,
                'youtube_bandwidth': y_bw,
                'youtube_quality': youtube_quality,
                'combined_speed': combined_speed,
                'network_score': network_score,
                'network_status': status
            }
            
            status_flag = "online" if time_diff <= ONLINE_THRESHOLD_SECONDS else "recent"
            return d, time_diff, last_update, status_flag
            
        return None, OFFLINE_THRESHOLD_SECONDS, None, "offline"
    except Exception as e:
        add_log_entry("ERROR", f"ThingSpeak fetch error: {str(e)}")
        return None, OFFLINE_THRESHOLD_SECONDS, None, "offline"

# -------------------------
# Refresh Function
# -------------------------
def refresh_data():
    data, td, lu, status = fetch_thingspeak_data()
    
    if data and data['network_score'] > 0:
        prev = st.session_state.data
        changed = prev is None or any(
            abs(data.get(k, 0) - prev.get(k, 0)) > 0.01
            for k in ['network_score', 'google_latency', 'youtube_latency']
        )
        
        st.session_state.prev_data = st.session_state.data
        st.session_state.data = data
        st.session_state.time_diff = td
        st.session_state.last_update = lu
        st.session_state.status = status
        st.session_state.last_refresh = datetime.now()
        
        # Save to CSV immediately
        prediction = 1 if data['network_score'] < 50 else 0
        saved = save_classified_metrics(data, prediction)
        
        if changed:
            st.session_state.update_count += 1
            st.session_state.pulse_triggered = True
            check_and_send_alerts(data)
        
        return True
    return False

# -------------------------
# Model + Init
# -------------------------
@st.cache_resource
def load_model():
    try: 
        return joblib.load("network_congestion_model.pkl")
    except: 
        return None

model = load_model()
add_log_entry("INFO", "Application started - GitHub CSV version")

# Initial data load
if st.session_state.data is None:
    refresh_data()

# -------------------------
# Auto Refresh
# -------------------------
now = datetime.now()
since_refresh = (now - st.session_state.last_refresh).total_seconds()
next_refresh = max(0, REFRESH_INTERVAL - since_refresh)

if since_refresh >= REFRESH_INTERVAL and st.session_state.auto_refresh:
    refresh_data()
    st.rerun()

# -------------------------
# CSS Styling
# -------------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;600;700;800;900&family=Share+Tech+Mono&family=Rajdhani:wght@300;400;500;600;700&display=swap');
    
    .stApp {
        background: linear-gradient(135deg, #0a0a0f 0%, #0d0d15 50%, #0a0a0f 100%);
        background-attachment: fixed;
    }
    
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    
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
    
    .cyber-divider {
        margin: 1.2rem 0;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(0, 245, 255, 0.3), rgba(0, 255, 136, 0.3), rgba(0, 245, 255, 0.3), transparent);
    }
    
    .score-ring-wrap {
        background: linear-gradient(135deg, rgba(0, 245, 255, 0.05) 0%, rgba(0, 0, 0, 0.2) 100%);
        border-radius: 16px;
        padding: 1.2rem;
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
        font-size: 4.5rem;
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
    
    .pred-congestion, .pred-normal {
        background: linear-gradient(135deg, rgba(0, 0, 0, 0.4) 0%, rgba(0, 0, 0, 0.2) 100%);
        border-radius: 12px;
        padding: 1.2rem;
        border: 1px solid rgba(255, 0, 60, 0.3);
        backdrop-filter: blur(10px);
        height: 100%;
    }
    .pred-normal {
        border-color: rgba(0, 255, 136, 0.3);
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
    
    .svc-panel {
        background: linear-gradient(135deg, rgba(0, 0, 0, 0.3) 0%, rgba(0, 0, 0, 0.15) 100%);
        border-radius: 12px;
        padding: 1.2rem;
        margin-bottom: 0.5rem;
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
    
    .stButton button {
        font-family: 'Orbitron', monospace;
        background: linear-gradient(135deg, rgba(0, 245, 255, 0.15) 0%, rgba(0, 0, 0, 0.3) 100%);
        border: 1px solid rgba(0, 245, 255, 0.3);
        color: #00f5ff;
        transition: all 0.3s ease;
    }
    .stButton button:hover {
        border-color: #00f5ff;
        box-shadow: 0 0 15px rgba(0, 245, 255, 0.2);
        transform: translateY(-1px);
    }
</style>
""", unsafe_allow_html=True)

# -------------------------
# MAIN APP
# -------------------------
def main():
    pulse_class = "data-updated" if st.session_state.pulse_triggered else ""
    st.session_state.pulse_triggered = False
    
    # Get data stats
    stats = get_data_stats()

    # Header
    st.markdown(f"""
    <div class="netpulse-header {pulse_class}">
        <div class="header-title">🛰 NETPULSE AI MONITOR</div>
        <div class="header-sub">GOOGLE &amp; YOUTUBE SERVICE CLASSIFICATION SYSTEM · THINGSPEAK LIVE FEED</div>
        <div class="header-badge">
            <span class="pulse-dot"></span>
            LIVE · AUTO-REFRESH {REFRESH_INTERVAL}S · UPDATE #{st.session_state.update_count}
            <span style="margin-left: 12px;">💾 RECORDS: {stats['total_records']}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Sidebar
    with st.sidebar:
        st.markdown("""
        <div style="font-family:'Orbitron',monospace; font-size:0.7rem; letter-spacing:0.2rem;
             color:#00f5ff; margin-bottom:1rem; padding-bottom:6px;
             border-bottom:1px solid rgba(0,245,255,0.15);">
            ⬡ SYSTEM CONTROLS
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns([3, 1])
        with col1:
            auto_refresh = st.toggle("AUTO REFRESH", value=st.session_state.auto_refresh)
            if auto_refresh != st.session_state.auto_refresh:
                st.session_state.auto_refresh = auto_refresh
                st.rerun()
        with col2:
            if st.button("⟳", help="Refresh Now", use_container_width=True):
                refresh_data()
                st.rerun()

        st.markdown('<div class="cyber-divider"></div>', unsafe_allow_html=True)

        # Email Configuration
        st.markdown("""
        <div style="font-family:'Orbitron',monospace; font-size:0.7rem; letter-spacing:0.15rem;
             color:#00f5ff; margin-bottom:8px;">
            ✉ ALERT CONFIGURATION
        </div>
        """, unsafe_allow_html=True)
        
        with st.expander("📧 Email Settings", expanded=False):
            email_sender = st.text_input("Gmail Address", value=EMAIL_CONFIG['sender_email'], 
                                          placeholder="your.email@gmail.com", type="default")
            email_password = st.text_input("App Password", value=EMAIL_CONFIG['sender_password'],
                                            placeholder="16-character app password", type="password")
            
            if email_sender != EMAIL_CONFIG['sender_email'] or email_password != EMAIL_CONFIG['sender_password']:
                EMAIL_CONFIG['sender_email'] = email_sender
                EMAIL_CONFIG['sender_password'] = email_password
                st.session_state.email_configured = False
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📧 TEST", use_container_width=True):
                    success, msg = test_email_connection()
                    if success:
                        st.success("✅ Connected!")
                        test_subject = "NetPulse Monitor - Test"
                        test_body = """
                        <div class="good">
                        <strong>✅ Email Configuration Test Successful!</strong><br><br>
                        You will receive real-time alerts for network issues.
                        </div>
                        """
                        send_email_notification(test_subject, test_body, "test")
                        st.session_state.email_configured = True
                        add_log_entry("INFO", "Email notification test sent")
                    else:
                        st.error(f"❌ {msg}")
            with col2:
                if EMAIL_CONFIG['sender_email'] and EMAIL_CONFIG['sender_password']:
                    st.markdown('<span style="color:#00ff88;">● ACTIVE</span>', unsafe_allow_html=True)
                else:
                    st.markdown('<span style="color:#ff6b00;">● NOT CONFIGURED</span>', unsafe_allow_html=True)

        st.markdown('<div class="cyber-divider"></div>', unsafe_allow_html=True)

        # Connection Status
        if st.session_state.auto_refresh:
            st.markdown(f"""
            <div class="sidebar-stat">
                <span class="sidebar-stat-label">⏱ NEXT UPDATE</span>
                <span class="sidebar-stat-value">{int(next_refresh)}s</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown('<div class="cyber-divider"></div>', unsafe_allow_html=True)

        # ThingSpeak Status
        status = st.session_state.status
        td = st.session_state.time_diff

        status_map = {
            'online': ('status-online', '◉ ONLINE', '#00ff88'),
            'recent': ('status-online', '◎ RECENT', '#00f5ff'),
            'stale':  ('status-stale',  '◌ STALE', '#ffaa00'),
            'offline':('status-offline','✕ OFFLINE', '#ff003c'),
        }
        sc, sl, scolor = status_map.get(status, ('status-offline', '✕ OFFLINE', '#ff003c'))
        st.markdown(f"""
        <div class="sidebar-stat">
            <span class="{sc}" style="font-family:'Share Tech Mono',monospace; font-size:0.7rem;">{sl}</span>
            <span class="sidebar-stat-label" style="color:{scolor};">{format_time_diff(td) if td else "—"}</span>
        </div>
        """, unsafe_allow_html=True)

        # Storage Status
        storage_status = "✅ ACTIVE" if METRICS_CSV.exists() else "⚠ NOT READY"
        storage_color = "#00ff88" if METRICS_CSV.exists() else "#ffaa00"
        st.markdown(f"""
        <div class="sidebar-stat">
            <span style="font-family:'Share Tech Mono',monospace; font-size:0.7rem;">💾 CSV STORAGE</span>
            <span style="color:{storage_color};">{storage_status}</span>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="cyber-divider"></div>', unsafe_allow_html=True)

        # Analytics Summary
        if stats['total_records'] > 0:
            st.markdown("""<div style="font-family:'Orbitron',monospace; font-size:0.65rem;
                letter-spacing:0.15rem; color:#5a7a9a; margin-bottom:8px;">⬡ ANALYTICS</div>""", unsafe_allow_html=True)
            
            a1, a2 = st.columns(2)
            with a1:
                st.metric("TOTAL RECORDS", stats['total_records'], delta=None)
            with a2:
                st.metric("AVG SCORE", f"{stats['avg_score']:.0f}", delta=None)
            
            if stats['date_range']:
                st.caption(f"📅 {stats['date_range']}")

        st.markdown('<div class="cyber-divider"></div>', unsafe_allow_html=True)
        st.caption(f"🕒 LAST REFRESH\n{st.session_state.last_refresh.strftime('%Y-%m-%d %H:%M:%S')}")

    # Main Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["🛰 LIVE DASHBOARD", "📊 HISTORICAL CHARTS", "💡 DIAGNOSTICS", "📝 SYSTEM LOGS"])

    # TAB 1 — LIVE DASHBOARD
    with tab1:
        data = st.session_state.data

        if data and data['network_score'] > 0:
            if st.session_state.email_configured:
                st.success(f"📧 Email alerts active → {EMAIL_CONFIG['recipient_email']}")
            
            ns = data['network_score']
            nc = score_color(ns)
            ns_shadow = score_shadow(ns)
            network_status = data['network_status']
            status_border = {"EXCELLENT": "#00ff88", "GOOD": "#00f5ff", "FAIR": "#ffe600", "POOR": "#ff6b00", "CRITICAL": "#ff003c"}
            sb = status_border.get(network_status, "#00f5ff")

            col_score, col_pred = st.columns([1, 1.2], gap="large")

            with col_score:
                st.markdown(f"""
                <div class="score-ring-wrap" style="border-color: {sb}40;">
                    <div class="score-label">NETWORK HEALTH SCORE</div>
                    <div class="score-number" style="color:{nc}; text-shadow:{ns_shadow};">{ns:.0f}</div>
                    <div class="score-label">/ 100</div>
                    <div class="score-status" style="color:{nc}; background:{nc}15; border:1px solid {nc}40;">{network_status}</div>
                    <div style="margin-top:12px; font-family:'Share Tech Mono',monospace; font-size:0.75rem; color:#5a7a9a;">
                        <span style="color:#00f5ff;">⇄</span> {data['combined_speed']:.1f} MBPS COMBINED
                    </div>
                </div>
                """, unsafe_allow_html=True)

            with col_pred:
                prediction = 1 if ns < 50 else 0
                if prediction == 1:
                    st.markdown(f"""
                    <div class="pred-congestion">
                        <div class="pred-title" style="color:#ff003c;">⚠ CONGESTION RISK DETECTED</div>
                        <div class="pred-sub">Multiple services show degraded performance below 50/100 threshold.
                        Network score: {ns:.0f}/100. Immediate action recommended.</div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="pred-normal">
                        <div class="pred-title" style="color:#00ff88;">✓ NORMAL OPERATION</div>
                        <div class="pred-sub">All monitored services within acceptable parameters.
                        Network score: {ns:.0f}/100. No congestion predicted.</div>
                    </div>
                    """, unsafe_allow_html=True)

                m1, m2, m3 = st.columns(3)
                with m1:
                    st.metric("GOOGLE Q", f"{data['google_quality']}/100", 
                             delta=f"{data['google_quality'] - st.session_state.prev_data['google_quality'] if st.session_state.prev_data else 0:+.0f}")
                with m2:
                    st.metric("YOUTUBE Q", f"{data['youtube_quality']}/100",
                             delta=f"{data['youtube_quality'] - st.session_state.prev_data['youtube_quality'] if st.session_state.prev_data else 0:+.0f}")
                with m3:
                    st.metric("SPEED", f"{data['combined_speed']:.0f} Mbps",
                             delta=f"{data['combined_speed'] - st.session_state.prev_data['combined_speed'] if st.session_state.prev_data else 0:+.1f}")

            st.markdown('<div class="cyber-divider"></div>', unsafe_allow_html=True)

            # Service Panels
            col_g, col_y = st.columns(2, gap="medium")

            def svc_panel(col, name, icon, quality, latency, packet_loss, bandwidth, accent):
                qc = score_color(quality)
                bar_pct = quality
                with col:
                    st.markdown(f"""
                    <div class="svc-panel" style="border-top: 3px solid {accent}80;">
                        <div class="svc-title" style="color:{accent};">
                            <span>{icon}</span> {name}
                        </div>
                        <div class="quality-bar-wrap">
                            <div class="quality-bar-top">
                                <span class="quality-bar-name">QUALITY SCORE</span>
                                <span class="quality-bar-score" style="color:{qc};">{quality}</span>
                            </div>
                            <div class="quality-bar-track">
                                <div class="quality-bar-fill" style="width:{bar_pct}%; background:linear-gradient(90deg,{qc}80,{qc});"></div>
                            </div>
                        </div>
                        <div class="metric-row">
                            <div class="metric-cell">
                                <div class="metric-cell-label">LATENCY</div>
                                <div class="metric-cell-value">{latency:.1f}<span class="metric-cell-unit">ms</span></div>
                            </div>
                            <div class="metric-cell">
                                <div class="metric-cell-label">PACKET LOSS</div>
                                <div class="metric-cell-value">{packet_loss:.2f}<span class="metric-cell-unit">%</span></div>
                            </div>
                            <div class="metric-cell">
                                <div class="metric-cell-label">BANDWIDTH</div>
                                <div class="metric-cell-value">{bandwidth:.1f}<span class="metric-cell-unit">Mbps</span></div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

            svc_panel(col_g, "GOOGLE", "🔍",
                      data['google_quality'], data['google_latency'], data['google_packet_loss'], data['google_bandwidth'], "#4285f4")
            svc_panel(col_y, "YOUTUBE", "▶",
                      data['youtube_quality'], data['youtube_latency'], data['youtube_packet_loss'], data['youtube_bandwidth'], "#ff4444")

            st.markdown('<div class="cyber-divider"></div>', unsafe_allow_html=True)

            # Recommendations
            st.markdown("### 💡 REAL-TIME DIAGNOSTICS")
            recs = generate_recommendations(data)
            for rec in recs:
                cls = {'critical': 'alert-critical', 'warning': 'alert-warning', 'good': 'alert-good'}.get(rec['severity'], 'alert-good')
                prefix = {'critical': '⚠', 'warning': '◈', 'good': '✓'}.get(rec['severity'], '◎')
                st.markdown(f'<div class="{cls}"><strong>[{rec["service"].upper()}]</strong> {prefix} {rec["message"]}</div>', unsafe_allow_html=True)

        else:
            st.warning("⚠ Waiting for valid data from ThingSpeak...")
            with st.expander("📡 THINGSPEAK CHANNEL CONFIGURATION", expanded=True):
                st.code("""Channel ID : 3381959
API Key    : 8F8XKE0PABJFF6GG

field1 → Google Latency (ms)
field2 → Google Packet Loss (%)
field3 → Google Bandwidth (Mbps)
field4 → YouTube Latency (ms)
field5 → YouTube Packet Loss (%)
field6 → YouTube Bandwidth (Mbps)
field7 → Combined Speed (Mbps)
field8 → Network Score (0-100)""", language="text")

    # TAB 2 — HISTORICAL CHARTS
    with tab2:
        st.markdown("### 📊 HISTORICAL SERVICE ANALYTICS")
        hist = load_historical_data(200)

        if not hist.empty:
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                date_range = st.selectbox("Time Range", ["Last 50 Records", "Last 100 Records", "Last 200 Records", "All Records"], index=1)
                limit_map = {"Last 50 Records": 50, "Last 100 Records": 100, "Last 200 Records": 200, "All Records": 1000}
                hist = load_historical_data(limit_map[date_range])
            
            with col_f2:
                show_metrics = st.multiselect("Show Metrics", ["Network Score", "Google Latency", "YouTube Latency", "Combined Speed"],
                                              default=["Network Score", "Google Latency", "YouTube Latency"])
            
            fig = go.Figure()
            
            if "Network Score" in show_metrics:
                fig.add_trace(go.Scatter(
                    x=hist['timestamp'], y=hist['network_score'],
                    mode='lines+markers', name='Network Score',
                    line=dict(color='#00f5ff', width=2),
                    marker=dict(size=4, color='#00f5ff'),
                    fill='tozeroy', fillcolor='rgba(0,245,255,0.05)'
                ))
            
            if "Google Latency" in show_metrics and 'google_latency' in hist.columns:
                fig.add_trace(go.Scatter(
                    x=hist['timestamp'], y=hist['google_latency'],
                    mode='lines', name='Google Latency (ms)',
                    yaxis='y2', line=dict(color='#4285f4', width=1.5)
                ))
            
            if "YouTube Latency" in show_metrics and 'youtube_latency' in hist.columns:
                fig.add_trace(go.Scatter(
                    x=hist['timestamp'], y=hist['youtube_latency'],
                    mode='lines', name='YouTube Latency (ms)',
                    yaxis='y2', line=dict(color='#ff4444', width=1.5)
                ))
            
            if "Combined Speed" in show_metrics and 'combined_speed' in hist.columns:
                fig.add_trace(go.Scatter(
                    x=hist['timestamp'], y=hist['combined_speed'],
                    mode='lines', name='Combined Speed (Mbps)',
                    yaxis='y3', line=dict(color='#00ff88', width=1.5, dash='dot')
                ))
            
            fig.update_layout(
                title=dict(text='NETWORK METRICS OVER TIME', font=dict(family='Orbitron', size=13, color='#00f5ff')),
                xaxis=dict(gridcolor='rgba(0,245,255,0.05)', color='#5a7a9a', tickfont=dict(family='Share Tech Mono', size=10)),
                yaxis=dict(title='Network Score', gridcolor='rgba(0,245,255,0.05)', color='#5a7a9a', tickfont=dict(family='Share Tech Mono', size=10), range=[0, 100]),
                yaxis2=dict(title='Latency (ms)', overlaying='y', side='right', color='#5a7a9a', tickfont=dict(family='Share Tech Mono', size=10)),
                yaxis3=dict(title='Speed (Mbps)', overlaying='y', side='right', position=0.95, color='#5a7a9a', tickfont=dict(family='Share Tech Mono', size=10)),
                template='plotly_dark',
                height=450,
                hovermode='x unified',
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                legend=dict(font=dict(family='Share Tech Mono', size=10, color='#5a7a9a'), bgcolor='rgba(0,0,0,0)'),
                margin=dict(l=50, r=80, t=50, b=40)
            )
            st.plotly_chart(fig, use_container_width=True)

            col_d1, col_d2 = st.columns([1, 1.5])
            
            with col_d1:
                if 'network_status' in hist.columns:
                    status_counts = hist['network_status'].value_counts()
                    color_map = {'EXCELLENT':'#00ff88','GOOD':'#00f5ff','FAIR':'#ffe600','POOR':'#ff6b00','CRITICAL':'#ff003c'}
                    fig2 = go.Figure(go.Pie(
                        labels=status_counts.index,
                        values=status_counts.values,
                        hole=0.6,
                        marker=dict(colors=[color_map.get(s,'#5a7a9a') for s in status_counts.index]),
                        textfont=dict(family='Share Tech Mono', size=10),
                        pull=[0.05 if s == 'CRITICAL' else 0 for s in status_counts.index]
                    ))
                    fig2.update_layout(
                        title=dict(text='STATUS DISTRIBUTION', font=dict(family='Orbitron', size=12, color='#00f5ff')),
                        template='plotly_dark',
                        height=300,
                        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                        legend=dict(font=dict(family='Share Tech Mono', size=9, color='#5a7a9a'), bgcolor='rgba(0,0,0,0)', orientation='h', yanchor='bottom', y=-0.2),
                        margin=dict(l=20, r=20, t=50, b=20)
                    )
                    st.plotly_chart(fig2, use_container_width=True)
            
            with col_d2:
                st.markdown("#### 📋 RECENT RECORDS")
                cols = [c for c in ['timestamp', 'network_score', 'network_status', 'combined_speed', 'google_latency', 'youtube_latency'] if c in hist.columns]
                if cols:
                    st.dataframe(hist[cols].head(20), use_container_width=True, height=300)

            st.markdown("---")
            col_e1, col_e2, col_e3 = st.columns([1, 1, 2])
            with col_e1:
                csv = hist.to_csv(index=False)
                st.download_button("📥 EXPORT CSV", csv, "netpulse_metrics.csv", "text/csv", use_container_width=True)
            with col_e2:
                if st.button("🔄 REFRESH DATA", use_container_width=True):
                    st.cache_data.clear()
                    st.rerun()
            with col_e3:
                st.info(f"💾 Data stored in: `{METRICS_CSV}`")
        else:
            st.info("◌ No historical data yet. Data will start saving immediately when ThingSpeak provides valid readings.")

    # TAB 3 — DIAGNOSTICS
    with tab3:
        st.markdown("### 💡 DIAGNOSTICS HISTORY")
        recs_df = load_recommendations_history(50)
        if not recs_df.empty:
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                severity_filter = st.multiselect("Filter by Severity", ["critical", "warning", "good"], default=["critical", "warning", "good"])
            with col_f2:
                service_filter = st.multiselect("Filter by Service", recs_df['service'].unique(), default=recs_df['service'].unique())
            
            filtered_df = recs_df[recs_df['severity'].isin(severity_filter) & recs_df['service'].isin(service_filter)]
            
            if not filtered_df.empty:
                for _, row in filtered_df.iterrows():
                    sev_map = {'critical':('#ff003c','⚠'), 'warning':('#ff6b00','◈'), 'good':('#00ff88','✓')}
                    c, sym = sev_map.get(row.get('severity','good'), ('#00f5ff','◎'))
                    ts = row['timestamp'].strftime('%Y-%m-%d %H:%M:%S') if pd.notna(row.get('timestamp')) else '—'
                    score_val = row.get('network_score', 0)
                    score_c = score_color(score_val)
                    with st.expander(f"{sym} {ts} · {row['service']} · Score: {score_val:.0f}"):
                        st.markdown(f"""
                        <div style="background:rgba(0,0,0,0.3); border-left:3px solid {c}; padding:14px 18px; border-radius:0 3px 3px 0;">
                            <div style="font-family:'Rajdhani',sans-serif; color:#e8f4fd; font-size:0.95rem;">{row['recommendation']}</div>
                            <div style="font-family:'Share Tech Mono',monospace; font-size:0.7rem; color:#5a7a9a; margin-top:10px;">
                                NETWORK SCORE: <span style="color:{score_c};">{score_val:.0f}/100</span> · STATUS: {row.get('network_status', '—')}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
            else:
                st.info("◌ No recommendations match the selected filters.")
        else:
            st.info("◌ No recommendations logged yet.")

    # TAB 4 — SYSTEM LOGS
    with tab4:
        st.markdown("### 📝 SYSTEM LOGS")
        
        col_c1, col_c2, col_c3 = st.columns([1, 1, 2])
        with col_c1:
            log_filter = st.selectbox("Filter by Type", ["All", "INFO", "WARNING", "ERROR", "ALERT"], index=0)
        with col_c2:
            if st.button("🗑 CLEAR VIEW", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
        
        logs_df = load_system_logs(200)
        
        if not logs_df.empty:
            if log_filter != "All":
                logs_df = logs_df[logs_df['log_type'] == log_filter]
            
            for _, row in logs_df.iterrows():
                lc = {'ERROR':'#ff003c','WARNING':'#ff6b00','INFO':'#00ff88', 'ALERT':'#ff6b00'}.get(row['log_type'], '#00f5ff')
                ts = row['timestamp'].strftime('%Y-%m-%d %H:%M:%S') if pd.notna(row.get('timestamp')) else '—'
                st.markdown(f"""
                <div style="background:rgba(0,0,0,0.2); border-left:2px solid {lc}; border-radius:0 4px 4px 0;
                     padding:8px 14px; margin:6px 0; display:flex; gap:14px; align-items:baseline;">
                    <span style="font-family:'Share Tech Mono',monospace; font-size:0.7rem; color:#3a5a7a; white-space:nowrap;">{ts}</span>
                    <span style="font-family:'Orbitron',monospace; font-size:0.65rem; color:{lc}; min-width:75px; font-weight:600;">[{row['log_type']}]</span>
                    <span style="font-family:'Rajdhani',sans-serif; font-size:0.85rem; color:#a0b8cc;">{row['message']}</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("◌ No system logs yet.")

if __name__ == "__main__":
    main()
