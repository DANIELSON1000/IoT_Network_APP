# -*- coding: utf-8 -*-
"""
AI Network Monitor - Google & YouTube
Ultra-Modern UI with Live ThingSpeak Animations & Email Notifications
"""

import streamlit as st
import pandas as pd
import numpy as np
import joblib
import requests
from datetime import datetime, timedelta
import mysql.connector
from mysql.connector import Error
import plotly.graph_objects as go
import plotly.express as px
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import hashlib

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
DATABASE_SAVE_INTERVAL = 60

SERVICE_THRESHOLDS = {
    'google': {'latency_good': 50, 'latency_warning': 100, 'loss_good': 1, 'loss_warning': 2, 'bw_good': 50, 'bw_warning': 20},
    'youtube': {'latency_good': 70, 'latency_warning': 140, 'loss_good': 0.5, 'loss_warning': 1.5, 'bw_good': 75, 'bw_warning': 30}
}

# Email Configuration
EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'sender_email': 'offliqz@gmail.com',  # Enter your Gmail address
    'sender_password': 'lkid xdce bpls xvtw',  # Enter your Gmail app password
    'recipient_email': 'ndahabonimanadaniel13@gmail.com'
}

# Notification cooldown (seconds) - to avoid spam
NOTIFICATION_COOLDOWN = 300  # 5 minutes between same type notifications
ALERT_THRESHOLDS = {
    'critical_score': 40,  # Send alert when network score drops below 40
    'congestion_alert': 50,  # Send alert when score below 50 (congestion)
    'high_latency': 150,  # ms
    'high_packet_loss': 3  # %
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
    'email_configured': False
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

# -------------------------
# Email Notification Functions
# -------------------------
def test_email_connection():
    """Test email configuration"""
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
    """
    Send email notification with cooldown to prevent spam
    Returns: (success, message)
    """
    # Check cooldown
    last_sent = st.session_state.last_notification_sent.get(alert_type, datetime.min)
    cooldown_remaining = NOTIFICATION_COOLDOWN - (datetime.now() - last_sent).total_seconds()
    
    if cooldown_remaining > 0:
        return False, f"Notification on cooldown. Next allowed in {int(cooldown_remaining)} seconds"
    
    if not EMAIL_CONFIG['sender_email'] or not EMAIL_CONFIG['sender_password']:
        return False, "Email credentials not configured"
    
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = EMAIL_CONFIG['sender_email']
        msg['To'] = EMAIL_CONFIG['recipient_email']
        msg['Subject'] = f"[NetPulse Monitor] {subject}"
        
        # HTML formatted body
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
        
        # Send email
        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        server.starttls()
        server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
        server.send_message(msg)
        server.quit()
        
        # Update last sent time
        st.session_state.last_notification_sent[alert_type] = datetime.now()
        
        return True, "Notification sent successfully"
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"

def check_and_send_alerts(data):
    """
    Check network conditions and send alerts if thresholds are exceeded
    """
    if not data or data['network_score'] == 0:
        return
    
    alerts_sent = []
    
    # 1. Critical Network Score Alert
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
    
    # 2. Congestion Detection Alert
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
    
    # 3. High Latency Alert
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
    
    # 4. High Packet Loss Alert
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
    
    # 5. Service Recovery Alert (when score improves significantly)
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
    
    # 6. ThingSpeak Feed Status Alert
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
# Database Connection (rest remains same)
# -------------------------
def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host='localhost', database='network_monitor',
            user='root', password='',
            connection_timeout=5, autocommit=True
        )
        return connection
    except Error:
        return None

def initialize_database():
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("SHOW TABLES LIKE 'network_metrics'")
            table_exists = cursor.fetchone()
            if table_exists:
                cursor.execute("SHOW COLUMNS FROM network_metrics LIKE 'network_score'")
                if not cursor.fetchone():
                    for t in ["recommendations", "network_metrics", "system_logs"]:
                        cursor.execute(f"DROP TABLE IF EXISTS {t}")
                    table_exists = False
            if not table_exists:
                cursor.execute("""
                    CREATE TABLE network_metrics (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        timestamp DATETIME NOT NULL,
                        google_latency FLOAT, google_packet_loss FLOAT, google_bandwidth FLOAT, google_quality_score INT,
                        youtube_latency FLOAT, youtube_packet_loss FLOAT, youtube_bandwidth FLOAT, youtube_quality_score INT,
                        combined_speed FLOAT, network_score FLOAT, network_status VARCHAR(20),
                        congestion_prediction INT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_timestamp (timestamp)
                    )""")
                cursor.execute("""
                    CREATE TABLE recommendations (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        metric_id INT, service VARCHAR(20), recommendation TEXT, severity VARCHAR(20),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (metric_id) REFERENCES network_metrics(id) ON DELETE CASCADE
                    )""")
                cursor.execute("""
                    CREATE TABLE system_logs (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        log_type VARCHAR(20), message TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )""")
                connection.commit()
            cursor.close(); connection.close()
            return True
        except Error:
            return False
    return False

def add_log_entry(log_type, message):
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("INSERT INTO system_logs (log_type, message) VALUES (%s, %s)", (log_type, message))
            connection.commit()
            cursor.close(); connection.close()
        except Error:
            pass

def should_save_to_database():
    return (datetime.now() - st.session_state.last_database_save).total_seconds() >= DATABASE_SAVE_INTERVAL

# -------------------------
# Quality / Score Helpers
# -------------------------
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

def get_network_status(score):
    if score >= 80: return "EXCELLENT"
    elif score >= 60: return "GOOD"
    elif score >= 40: return "FAIR"
    elif score >= 20: return "POOR"
    else: return "CRITICAL"

def score_color(score):
    if score >= 80: return "#00ff88"
    elif score >= 60: return "#00f5ff"
    elif score >= 40: return "#ffe600"
    elif score >= 20: return "#ff6b00"
    else: return "#ff003c"

def score_shadow(score):
    c = score_color(score)
    return f"0 0 20px {c}80, 0 0 40px {c}40"

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

            if g_lat == 0 and y_lat == 0:
                return None, time_diff, last_update, "offline"

            d = {
                'google_latency': g_lat, 'google_packet_loss': g_loss, 'google_bandwidth': g_bw,
                'google_quality': calculate_quality_score(g_lat, g_loss, g_bw, 'google'),
                'youtube_latency': y_lat, 'youtube_packet_loss': y_loss, 'youtube_bandwidth': y_bw,
                'youtube_quality': calculate_quality_score(y_lat, y_loss, y_bw, 'youtube'),
                'combined_speed': combined_speed,
                'network_score': network_score,
                'network_status': get_network_status(network_score)
            }
            status = "online" if time_diff <= ONLINE_THRESHOLD_SECONDS else "recent"
            return d, time_diff, last_update, status
        return None, OFFLINE_THRESHOLD_SECONDS, None, "offline"
    except Exception:
        return None, OFFLINE_THRESHOLD_SECONDS, None, "offline"

def save_classified_metrics(data, prediction):
    connection = get_db_connection()
    if not connection: return False
    try:
        cursor = connection.cursor()
        now = datetime.now()
        cursor.execute("SELECT COUNT(*) FROM network_metrics WHERE timestamp > %s AND ABS(google_latency-%s)<5 AND ABS(youtube_latency-%s)<5",
                       (now - timedelta(minutes=1), data['google_latency'], data['youtube_latency']))
        if cursor.fetchone()[0] == 0:
            cursor.execute("""INSERT INTO network_metrics
                (timestamp,google_latency,google_packet_loss,google_bandwidth,google_quality_score,
                 youtube_latency,youtube_packet_loss,youtube_bandwidth,youtube_quality_score,
                 combined_speed,network_score,network_status,congestion_prediction)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (now, data['google_latency'], data['google_packet_loss'], data['google_bandwidth'], data['google_quality'],
                 data['youtube_latency'], data['youtube_packet_loss'], data['youtube_bandwidth'], data['youtube_quality'],
                 data['combined_speed'], data['network_score'], data['network_status'], prediction))
            mid = cursor.lastrowid
            for rec in generate_recommendations(data):
                cursor.execute("INSERT INTO recommendations (metric_id,service,recommendation,severity) VALUES (%s,%s,%s,%s)",
                               (mid, rec['service'], rec['message'], rec['severity']))
            connection.commit()
            st.session_state.last_database_save = now
            return True
        return False
    except Error:
        return False
    finally:
        if cursor: cursor.close()
        connection.close()

@st.cache_data(ttl=30, show_spinner=False)
def load_historical_data(limit=100):
    connection = get_db_connection()
    if connection:
        try:
            df = pd.read_sql("SELECT * FROM network_metrics ORDER BY timestamp DESC LIMIT %s",
                             connection, params=(int(limit),))
            connection.close()
            if not df.empty: df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
        except: return pd.DataFrame()
    return pd.DataFrame()

@st.cache_data(ttl=30, show_spinner=False)
def load_recommendations_history(limit=50):
    connection = get_db_connection()
    if connection:
        try:
            df = pd.read_sql("""SELECT r.*, n.timestamp, n.network_score, n.network_status
                FROM recommendations r JOIN network_metrics n ON r.metric_id=n.id
                ORDER BY r.created_at DESC LIMIT %s""", connection, params=(limit,))
            connection.close()
            return df
        except: return pd.DataFrame()
    return pd.DataFrame()

@st.cache_data(ttl=30, show_spinner=False)
def load_system_logs(limit=100):
    connection = get_db_connection()
    if connection:
        try:
            df = pd.read_sql("SELECT * FROM system_logs ORDER BY created_at DESC LIMIT %s",
                             connection, params=(limit,))
            connection.close()
            return df
        except: return pd.DataFrame()
    return pd.DataFrame()

def format_time_diff(s):
    if s < 60: return f"{int(s)}s ago"
    elif s < 3600: return f"{int(s/60)}m ago"
    elif s < 86400: return f"{int(s/3600)}h ago"
    else: return f"{int(s/86400)}d ago"

def refresh_data():
    data, td, lu, status = fetch_thingspeak_data()
    if data and data['network_score'] > 0:
        # Detect if data actually changed
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
        if changed:
            st.session_state.update_count += 1
            st.session_state.pulse_triggered = True
            # Send email notifications if conditions met
            check_and_send_alerts(data)
        if should_save_to_database():
            save_classified_metrics(data, 1 if data['network_score'] < 50 else 0)
        return True
    return False

# -------------------------
# Model + Init
# -------------------------
@st.cache_resource
def load_model():
    try: return joblib.load("network_congestion_model.pkl")
    except: return None

model = load_model()
initialize_database()

# -------------------------
# Auto Refresh
# -------------------------
now = datetime.now()
since_refresh = (now - st.session_state.last_refresh).total_seconds()
next_refresh = max(0, REFRESH_INTERVAL - since_refresh)
since_save = (now - st.session_state.last_database_save).total_seconds()
time_until_save = max(0, DATABASE_SAVE_INTERVAL - since_save)

if since_refresh >= REFRESH_INTERVAL and st.session_state.auto_refresh:
    refresh_data()
    st.rerun()

# -------------------------
# MAIN APP
# -------------------------
def main():

    # ── Header ──
    pulse_class = "data-updated" if st.session_state.pulse_triggered else ""
    st.session_state.pulse_triggered = False

    st.markdown(f"""
    <div class="netpulse-header {pulse_class}">
        <div class="header-title">🛰 NETPULSE AI MONITOR</div>
        <div class="header-sub">GOOGLE &amp; YOUTUBE SERVICE CLASSIFICATION SYSTEM · THINGSPEAK LIVE FEED</div>
        <div class="header-badge">
            <span class="pulse-dot"></span>
            LIVE · AUTO-REFRESH {REFRESH_INTERVAL}S · UPDATE #{st.session_state.update_count}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Sidebar ──
    with st.sidebar:
        st.markdown("""
        <div style="font-family:'Orbitron',monospace; font-size:0.75rem; letter-spacing:0.2rem;
             color:#00f5ff; margin-bottom:1rem; padding-bottom:8px;
             border-bottom:1px solid rgba(0,245,255,0.15);">
            ⬡ SYSTEM STATUS
        </div>
        """, unsafe_allow_html=True)

        auto_refresh = st.toggle("AUTO REFRESH", value=st.session_state.auto_refresh)
        if auto_refresh != st.session_state.auto_refresh:
            st.session_state.auto_refresh = auto_refresh
            st.rerun()

        # Email Configuration Section
        st.markdown('<div class="cyber-divider"></div>', unsafe_allow_html=True)
        st.markdown("""
        <div style="font-family:'Orbitron',monospace; font-size:0.7rem; letter-spacing:0.15rem;
             color:#00f5ff; margin-bottom:8px;">
            ✉ EMAIL NOTIFICATIONS
        </div>
        """, unsafe_allow_html=True)
        
        # Email configuration inputs
        email_sender = st.text_input("Gmail Address", value=EMAIL_CONFIG['sender_email'], 
                                      placeholder="your.email@gmail.com", type="default")
        email_password = st.text_input("App Password", value=EMAIL_CONFIG['sender_password'],
                                        placeholder="16-character app password", type="password")
        
        if email_sender != EMAIL_CONFIG['sender_email'] or email_password != EMAIL_CONFIG['sender_password']:
            EMAIL_CONFIG['sender_email'] = email_sender
            EMAIL_CONFIG['sender_password'] = email_password
            st.session_state.email_configured = False
        
        # Test email connection button
        if st.button("📧 TEST EMAIL", use_container_width=True):
            success, msg = test_email_connection()
            if success:
                st.success(f"✅ {msg}")
                # Send test email
                test_subject = "NetPulse Monitor - Test Notification"
                test_body = """
                <div class="good">
                <strong>✅ Email Configuration Test Successful!</strong><br><br>
                This is a test notification from your NetPulse AI Monitor.<br>
                You will receive real-time alerts when:<br>
                • Network score drops below 40/100<br>
                • Congestion is detected (score below 50)<br>
                • High latency (>150ms) or packet loss (>3%)<br>
                • Service recovery after issues<br>
                • ThingSpeak feed goes stale/offline<br><br>
                Your network is being monitored continuously.
                </div>
                """
                send_email_notification(test_subject, test_body, "test")
                st.session_state.email_configured = True
                add_log_entry("INFO", "Email notification test sent successfully")
            else:
                st.error(f"❌ {msg}")
                st.info("💡 For Gmail, use an App Password: https://myaccount.google.com/apppasswords")
        
        # Show notification status
        if EMAIL_CONFIG['sender_email'] and EMAIL_CONFIG['sender_password']:
            st.markdown(f"""
            <div class="sidebar-stat">
                <span class="sidebar-stat-label">📧 NOTIFICATIONS</span>
                <span class="sidebar-stat-value" style="color:#00ff88;">ACTIVE</span>
            </div>
            <div class="sidebar-stat">
                <span class="sidebar-stat-label">📬 RECIPIENT</span>
                <span class="sidebar-stat-value" style="font-size:0.7rem;">{EMAIL_CONFIG['recipient_email']}</span>
            </div>
            """, unsafe_allow_html=True)
            
            # Display cooldown status for different alert types
            st.markdown("""
            <div style="font-family:'Share Tech Mono',monospace; font-size:0.6rem; color:#5a7a9a; margin-top:8px;">
                ⏱ Alert cooldown: 5 minutes per type
            </div>
            """, unsafe_allow_html=True)
        else:
            st.warning("⚠ Configure Gmail credentials to receive alerts")

        st.markdown('<div class="cyber-divider"></div>', unsafe_allow_html=True)

        if st.session_state.auto_refresh:
            st.markdown(f"""
            <div class="sidebar-stat">
                <span class="sidebar-stat-label">NEXT UPDATE</span>
                <span class="sidebar-stat-value">{int(next_refresh)}s</span>
            </div>
            <div class="sidebar-stat">
                <span class="sidebar-stat-label">DB SAVE IN</span>
                <span class="sidebar-stat-value" style="color:#00ff88;">{int(time_until_save)}s</span>
            </div>
            """, unsafe_allow_html=True)

        if st.button("⟳  REFRESH NOW"):
            refresh_data()
            st.rerun()

        st.markdown('<div class="cyber-divider"></div>', unsafe_allow_html=True)

        # Init if needed
        if st.session_state.data is None:
            refresh_data()

        status = st.session_state.status
        td = st.session_state.time_diff

        status_map = {
            'online': ('status-online', '◉ THINGSPEAK ONLINE'),
            'recent': ('status-online', '◎ THINGSPEAK RECENT'),
            'stale':  ('status-stale',  '◌ THINGSPEAK STALE'),
            'offline':('status-offline','✕ THINGSPEAK OFFLINE'),
        }
        sc, sl = status_map.get(status, ('status-offline', '✕ OFFLINE'))
        st.markdown(f'<div class="sidebar-stat"><span class="{sc}" style="font-family:\'Share Tech Mono\',monospace; font-size:0.7rem;">{sl}</span><span class="sidebar-stat-label">{format_time_diff(td) if td else "—"}</span></div>', unsafe_allow_html=True)

        db_ok = get_db_connection()
        db_txt = '◉ DB CONNECTED' if db_ok else '✕ DB OFFLINE'
        db_cls = 'status-online' if db_ok else 'status-offline'
        if db_ok: db_ok.close()
        st.markdown(f'<div class="sidebar-stat"><span class="{db_cls}" style="font-family:\'Share Tech Mono\',monospace; font-size:0.7rem;">{db_txt}</span></div>', unsafe_allow_html=True)

        st.markdown('<div class="cyber-divider"></div>', unsafe_allow_html=True)

        df_hist = load_historical_data(1000)
        if not df_hist.empty and 'network_score' in df_hist.columns:
            st.markdown("""<div style="font-family:'Orbitron',monospace; font-size:0.65rem;
                letter-spacing:0.15rem; color:#5a7a9a; margin-bottom:8px;">⬡ ANALYTICS</div>""", unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            with col1: st.metric("RECORDS", len(df_hist))
            with col2: st.metric("AVG SCORE", f"{df_hist['network_score'].mean():.0f}")
            st.metric("AVG SPEED", f"{df_hist['combined_speed'].mean():.1f} Mbps")

        st.markdown('<div class="cyber-divider"></div>', unsafe_allow_html=True)
        st.caption(f"LAST REFRESH · {st.session_state.last_refresh.strftime('%H:%M:%S')}")

    # ── Tabs ──
    tab1, tab2, tab3, tab4 = st.tabs(["🛰 LIVE MONITOR", "📊 HISTORICAL", "💡 RECOMMENDATIONS", "📝 SYSTEM LOGS"])

    # ══════════════════════════════════
    # TAB 1 — LIVE MONITOR
    # ══════════════════════════════════
    with tab1:
        data = st.session_state.data

        if data and data['network_score'] > 0:
            # Display notification status
            if st.session_state.email_configured:
                st.success("📧 Email notifications active - You'll receive alerts at " + EMAIL_CONFIG['recipient_email'])
            
            # ── Top row: score + prediction ──
            ns = data['network_score']
            nc = score_color(ns)
            ns_shadow = score_shadow(ns)
            network_status = data['network_status']
            status_border = {"EXCELLENT": "#00ff88", "GOOD": "#00f5ff", "FAIR": "#ffe600", "POOR": "#ff6b00", "CRITICAL": "#ff003c"}
            sb = status_border.get(network_status, "#00f5ff")

            col_score, col_pred = st.columns([1, 2])

            with col_score:
                st.markdown(f"""
                <div class="score-ring-wrap" style="border-color: {sb}40;">
                    <div class="score-label">NETWORK HEALTH SCORE</div>
                    <div class="score-number" style="color:{nc}; text-shadow:{ns_shadow};">{ns:.0f}</div>
                    <div class="score-label">/ 100</div>
                    <div class="score-status" style="color:{nc}; background:{nc}15; border:1px solid {nc}40;">{network_status}</div>
                    <div style="margin-top:10px; font-family:'Share Tech Mono',monospace; font-size:0.7rem; color:#5a7a9a;">
                        ↔ {data['combined_speed']:.1f} MBPS COMBINED
                    </div>
                </div>
                """, unsafe_allow_html=True)

            with col_pred:
                prediction = 1 if ns < 50 else 0
                if prediction == 1:
                    st.markdown(f"""
                    <div class="pred-congestion">
                        <div class="pred-title" style="color:#ff003c;">🚨 CONGESTION RISK DETECTED</div>
                        <div class="pred-sub">Multiple services show degraded performance below 50/100 threshold.
                        Network score: {ns:.0f}/100. Immediate action recommended.</div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="pred-normal">
                        <div class="pred-title" style="color:#00ff88;">✓ NETWORK OPERATING NORMALLY</div>
                        <div class="pred-sub">All monitored services within acceptable parameters.
                        Network score: {ns:.0f}/100. No congestion predicted.</div>
                    </div>
                    """, unsafe_allow_html=True)

                # Mini metric row for speed
                c1, c2, c3 = st.columns(3)
                with c1: st.metric("GOOGLE Q", f"{data['google_quality']}/100")
                with c2: st.metric("YOUTUBE Q", f"{data['youtube_quality']}/100")
                with c3: st.metric("SPEED", f"{data['combined_speed']:.0f} Mbps")

            st.markdown('<div class="cyber-divider"></div>', unsafe_allow_html=True)

            # ── Service Panels ──
            col_g, col_y = st.columns(2)

            def svc_panel(col, name, css_class, icon, quality, latency, packet_loss, bandwidth, accent):
                qc = score_color(quality)
                bar_pct = quality
                with col:
                    st.markdown(f"""
                    <div class="svc-panel {css_class}" style="border-color:{accent}25;">
                        <div class="svc-title" style="color:{accent};">
                            <span>{icon}</span> {name}
                        </div>
                        <div class="quality-bar-wrap">
                            <div class="quality-bar-top">
                                <span class="quality-bar-name">QUALITY SCORE</span>
                                <span class="quality-bar-score" style="color:{qc}; text-shadow:0 0 15px {qc}80;">{quality}</span>
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
                            <div class="metric-cell" style="grid-column:span 2;">
                                <div class="metric-cell-label">BANDWIDTH</div>
                                <div class="metric-cell-value">{bandwidth:.1f}<span class="metric-cell-unit">Mbps</span></div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

            svc_panel(col_g, "GOOGLE", "google", "🔍",
                      data['google_quality'], data['google_latency'], data['google_packet_loss'], data['google_bandwidth'], "#4285f4")
            svc_panel(col_y, "YOUTUBE", "youtube", "▶",
                      data['youtube_quality'], data['youtube_latency'], data['youtube_packet_loss'], data['youtube_bandwidth'], "#ff4444")

            st.markdown('<div class="cyber-divider"></div>', unsafe_allow_html=True)

            # ── Real-time Recommendations ──
            st.markdown("### 💡 REAL-TIME DIAGNOSTICS")
            recs = generate_recommendations(data)
            for rec in recs:
                cls = {'critical': 'alert-critical', 'warning': 'alert-warning', 'good': 'alert-good'}.get(rec['severity'], 'alert-good')
                prefix = {'critical': '⬡', 'warning': '◈', 'good': '◉'}.get(rec['severity'], '◉')
                st.markdown(f'<div class="{cls}"><strong>[{rec["service"].upper()}]</strong> {prefix} {rec["message"]}</div>', unsafe_allow_html=True)

        elif data and data['network_score'] == 0:
            st.warning("⬡ DEVICE ACTIVE — Network score transmitting as 0. Awaiting valid reading.")
            st.info(f"Latest feed — Google: {data['google_latency']:.1f}ms · YouTube: {data['youtube_latency']:.1f}ms")
        else:
            st.markdown("""
            <div style="text-align:center; padding:3rem; background:rgba(0,245,255,0.02);
                 border:1px solid rgba(0,245,255,0.1); border-radius:4px; margin-top:1rem;">
                <div style="font-family:'Orbitron',monospace; font-size:1.5rem; color:#5a7a9a; margin-bottom:1rem;">
                    ◌ AWAITING FEED
                </div>
                <div style="font-family:'Share Tech Mono',monospace; color:#3a5a7a; font-size:0.8rem;">
                    Connecting to ThingSpeak Channel 3381959...
                </div>
            </div>
            """, unsafe_allow_html=True)
            with st.expander("📡 THINGSPEAK CHANNEL CONFIG"):
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

    # ══════════════════════════════════
    # TAB 2 — HISTORICAL
    # ══════════════════════════════════
    with tab2:
        st.markdown("### 📊 HISTORICAL SERVICE ANALYTICS")
        hist = load_historical_data(100)

        if not hist.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=hist['timestamp'], y=hist['network_score'],
                mode='lines', name='Network Score',
                line=dict(color='#00f5ff', width=2),
                fill='tozeroy', fillcolor='rgba(0,245,255,0.05)'
            ))
            if 'google_latency' in hist.columns:
                fig.add_trace(go.Scatter(
                    x=hist['timestamp'], y=hist['google_latency'],
                    mode='lines', name='Google Latency (ms)',
                    yaxis='y2', line=dict(color='#4285f4', width=1.5, dash='dot')
                ))
            if 'youtube_latency' in hist.columns:
                fig.add_trace(go.Scatter(
                    x=hist['timestamp'], y=hist['youtube_latency'],
                    mode='lines', name='YouTube Latency (ms)',
                    yaxis='y2', line=dict(color='#ff4444', width=1.5, dash='dot')
                ))
            fig.update_layout(
                title=dict(text='NETWORK HEALTH · LATENCY OVERLAY', font=dict(family='Orbitron', size=13, color='#00f5ff')),
                xaxis=dict(gridcolor='rgba(0,245,255,0.05)', color='#5a7a9a', tickfont=dict(family='Share Tech Mono', size=10)),
                yaxis=dict(title='Network Score', gridcolor='rgba(0,245,255,0.05)', color='#5a7a9a', tickfont=dict(family='Share Tech Mono', size=10)),
                yaxis2=dict(title='Latency (ms)', overlaying='y', side='right', color='#5a7a9a', tickfont=dict(family='Share Tech Mono', size=10)),
                template='plotly_dark',
                height=420,
                hovermode='x unified',
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                legend=dict(font=dict(family='Share Tech Mono', size=10, color='#5a7a9a'), bgcolor='rgba(0,0,0,0)'),
                margin=dict(l=50, r=50, t=50, b=40)
            )
            st.plotly_chart(fig, use_container_width=True)

            # Score distribution donut
            if 'network_status' in hist.columns:
                status_counts = hist['network_status'].value_counts()
                color_map = {'EXCELLENT':'#00ff88','GOOD':'#00f5ff','FAIR':'#ffe600','POOR':'#ff6b00','CRITICAL':'#ff003c'}
                fig2 = go.Figure(go.Pie(
                    labels=status_counts.index,
                    values=status_counts.values,
                    hole=0.6,
                    marker=dict(colors=[color_map.get(s,'#5a7a9a') for s in status_counts.index]),
                    textfont=dict(family='Share Tech Mono', size=10),
                ))
                fig2.update_layout(
                    title=dict(text='STATUS DISTRIBUTION', font=dict(family='Orbitron', size=12, color='#00f5ff')),
                    template='plotly_dark',
                    height=300,
                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                    legend=dict(font=dict(family='Share Tech Mono', size=10, color='#5a7a9a'), bgcolor='rgba(0,0,0,0)'),
                    margin=dict(l=20, r=20, t=50, b=20)
                )
                col1, col2 = st.columns([2,1])
                with col2: st.plotly_chart(fig2, use_container_width=True)
                with col1:
                    st.markdown("#### RECENT RECORDS")
                    cols = [c for c in ['timestamp','google_latency','youtube_latency','combined_speed','network_score','network_status'] if c in hist.columns]
                    st.dataframe(hist[cols].head(30), use_container_width=True)

            csv = hist.to_csv(index=False)
            st.download_button("⬇ EXPORT CSV", csv, "netpulse_metrics.csv", "text/csv")
        else:
            st.info("◌ No historical data yet. Records save every 60 seconds after first live reading.")

    # ══════════════════════════════════
    # TAB 3 — RECOMMENDATIONS
    # ══════════════════════════════════
    with tab3:
        st.markdown("### 💡 DIAGNOSTICS HISTORY")
        recs_df = load_recommendations_history(50)
        if not recs_df.empty:
            for _, row in recs_df.iterrows():
                sev_map = {'critical':('#ff003c','⬡'), 'warning':('#ff6b00','◈'), 'good':('#00ff88','◉')}
                c, sym = sev_map.get(row.get('severity','good'), ('#00f5ff','◎'))
                ts = row['created_at'].strftime('%Y-%m-%d %H:%M:%S') if pd.notna(row.get('created_at')) else '—'
                with st.expander(f"{sym} {ts} · {row['service']}"):
                    st.markdown(f"""
                    <div style="background:rgba(0,0,0,0.3); border-left:3px solid {c}; padding:14px 18px; border-radius:0 3px 3px 0;">
                        <div style="font-family:'Rajdhani',sans-serif; color:#e8f4fd;">{row['recommendation']}</div>
                        <div style="font-family:'Share Tech Mono',monospace; font-size:0.65rem; color:#5a7a9a; margin-top:10px;">
                            NETWORK SCORE AT TIME: {row.get('network_score',0):.0f}/100 · {row.get('network_status','—')}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.info("◌ No recommendations logged yet.")

    # ══════════════════════════════════
    # TAB 4 — SYSTEM LOGS
    # ══════════════════════════════════
    with tab4:
        st.markdown("### 📝 SYSTEM LOGS")
        logs_df = load_system_logs(100)
        if not logs_df.empty:
            for _, row in logs_df.iterrows():
                lc = {'ERROR':'#ff003c','WARNING':'#ff6b00','INFO':'#00ff88', 'ALERT':'#ff6b00'}.get(row['log_type'],'#00f5ff')
                ts = row['created_at'].strftime('%Y-%m-%d %H:%M:%S') if pd.notna(row.get('created_at')) else '—'
                st.markdown(f"""
                <div style="background:rgba(0,0,0,0.25); border-left:2px solid {lc}40;
                     padding:8px 14px; margin:4px 0; border-radius:0 2px 2px 0; display:flex; gap:14px; align-items:baseline;">
                    <span style="font-family:'Share Tech Mono',monospace; font-size:0.65rem; color:#3a5a7a; white-space:nowrap;">{ts}</span>
                    <span style="font-family:'Orbitron',monospace; font-size:0.6rem; color:{lc}; min-width:65px;">[{row['log_type']}]</span>
                    <span style="font-family:'Rajdhani',sans-serif; font-size:0.9rem; color:#a0b8cc;">{row['message']}</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("◌ No system logs yet.")


if __name__ == "__main__":
    main()