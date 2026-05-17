# -*- coding: utf-8 -*-
"""
AI Network Monitor - Google & YouTube
Ultra-Modern UI with Live ThingSpeak Animations & Email Notifications
Cloud-Optimized Version with SQLite
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
import sqlite3
import os
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
REFRESH_INTERVAL = 30  # Increased for cloud deployment
DATABASE_SAVE_INTERVAL = 60

SERVICE_THRESHOLDS = {
    'google': {'latency_good': 50, 'latency_warning': 100, 'loss_good': 1, 'loss_warning': 2, 'bw_good': 50, 'bw_warning': 20},
    'youtube': {'latency_good': 70, 'latency_warning': 140, 'loss_good': 0.5, 'loss_warning': 1.5, 'bw_good': 75, 'bw_warning': 30}
}

# Email Configuration - Load from Streamlit secrets
EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'sender_email': st.secrets.get("EMAIL_SENDER", ""),
    'sender_password': st.secrets.get("EMAIL_PASSWORD", ""),
    'recipient_email': st.secrets.get("EMAIL_RECIPIENT", "ndahabonimanadaniel13@gmail.com")
}

# Notification cooldown (seconds)
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
    'db_initialized': False
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

# -------------------------
# SQLite Database Functions (Cloud-Friendly)
# -------------------------
def get_db_path():
    """Get database path - works locally and on cloud"""
    # Use a persistent directory if available, otherwise current directory
    if os.path.exists('/mount'):
        db_dir = '/mount'
    else:
        db_dir = os.path.dirname(__file__)
    
    db_path = os.path.join(db_dir, 'network_monitor.db')
    return db_path

def get_db_connection():
    """Returns SQLite connection"""
    try:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        st.error(f"Database connection error: {e}")
        return None

def initialize_database():
    """Initialize SQLite database with all tables"""
    if st.session_state.db_initialized:
        return True
    
    try:
        conn = get_db_connection()
        if not conn:
            return False
        
        cursor = conn.cursor()
        
        # Create network_metrics table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS network_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                google_latency REAL,
                google_packet_loss REAL,
                google_bandwidth REAL,
                google_quality_score INTEGER,
                youtube_latency REAL,
                youtube_packet_loss REAL,
                youtube_bandwidth REAL,
                youtube_quality_score INTEGER,
                combined_speed REAL,
                network_score REAL,
                network_status TEXT,
                congestion_prediction INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create recommendations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_id INTEGER,
                service TEXT,
                recommendation TEXT,
                severity TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create system_logs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_type TEXT,
                message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        
        st.session_state.db_initialized = True
        return True
    except Exception as e:
        st.error(f"Database initialization error: {e}")
        return False

def add_log_entry(log_type, message):
    """Add entry to system logs"""
    try:
        conn = get_db_connection()
        if not conn:
            return
        
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO system_logs (log_type, message) VALUES (?, ?)",
            (log_type, message)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

def save_classified_metrics(data, prediction):
    """Save metrics to database"""
    if not initialize_database():
        return False
    
    try:
        conn = get_db_connection()
        if not conn:
            return False
        
        cursor = conn.cursor()
        now = datetime.now()
        
        # Check for duplicate recent entry
        cursor.execute("""
            SELECT COUNT(*) FROM network_metrics 
            WHERE timestamp > ? 
            AND ABS(google_latency - ?) < 5 
            AND ABS(youtube_latency - ?) < 5
        """, (now - timedelta(minutes=1), data['google_latency'], data['youtube_latency']))
        
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO network_metrics (
                    timestamp, google_latency, google_packet_loss, google_bandwidth, 
                    google_quality_score, youtube_latency, youtube_packet_loss, 
                    youtube_bandwidth, youtube_quality_score, combined_speed, 
                    network_score, network_status, congestion_prediction
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                now, data['google_latency'], data['google_packet_loss'], 
                data['google_bandwidth'], data['google_quality'], data['youtube_latency'],
                data['youtube_packet_loss'], data['youtube_bandwidth'], 
                data['youtube_quality'], data['combined_speed'], data['network_score'],
                data['network_status'], prediction
            ))
            
            mid = cursor.lastrowid
            
            # Save recommendations
            for rec in generate_recommendations(data):
                cursor.execute("""
                    INSERT INTO recommendations (metric_id, service, recommendation, severity)
                    VALUES (?, ?, ?, ?)
                """, (mid, rec['service'], rec['message'], rec['severity']))
            
            conn.commit()
            st.session_state.last_database_save = now
            return True
        
        conn.close()
        return False
    except Exception as e:
        print(f"Error saving metrics: {e}")
        return False

def should_save_to_database():
    return (datetime.now() - st.session_state.last_database_save).total_seconds() >= DATABASE_SAVE_INTERVAL

@st.cache_data(ttl=60, show_spinner=False)
def load_historical_data(limit=100):
    """Load historical data from database"""
    if not initialize_database():
        return pd.DataFrame()
    
    try:
        conn = get_db_connection()
        if not conn:
            return pd.DataFrame()
        
        df = pd.read_sql_query(
            "SELECT * FROM network_metrics ORDER BY timestamp DESC LIMIT ?",
            conn, params=[limit]
        )
        conn.close()
        
        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=60, show_spinner=False)
def load_recommendations_history(limit=50):
    """Load recommendations history"""
    if not initialize_database():
        return pd.DataFrame()
    
    try:
        conn = get_db_connection()
        if not conn:
            return pd.DataFrame()
        
        df = pd.read_sql_query("""
            SELECT r.*, n.timestamp, n.network_score, n.network_status
            FROM recommendations r 
            JOIN network_metrics n ON r.metric_id = n.id
            ORDER BY r.created_at DESC LIMIT ?
        """, conn, params=[limit])
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=60, show_spinner=False)
def load_system_logs(limit=100):
    """Load system logs"""
    if not initialize_database():
        return pd.DataFrame()
    
    try:
        conn = get_db_connection()
        if not conn:
            return pd.DataFrame()
        
        df = pd.read_sql_query(
            "SELECT * FROM system_logs ORDER BY created_at DESC LIMIT ?",
            conn, params=[limit]
        )
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()

# -------------------------
# Email Notification Functions
# -------------------------
def test_email_connection():
    """Test email configuration"""
    if not EMAIL_CONFIG['sender_email'] or not EMAIL_CONFIG['sender_password']:
        return False, "Email credentials not configured. Please add them in Streamlit Cloud Secrets."
    
    try:
        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        server.starttls()
        server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
        server.quit()
        return True, "Email configured successfully!"
    except Exception as e:
        return False, f"Email configuration error: {str(e)}"

def send_email_notification(subject, body, alert_type="general"):
    """Send email notification with cooldown"""
    if not EMAIL_CONFIG['sender_email'] or not EMAIL_CONFIG['sender_password']:
        return False, "Email credentials not configured"
    
    # Check cooldown
    last_sent = st.session_state.last_notification_sent.get(alert_type, datetime.min)
    cooldown_remaining = NOTIFICATION_COOLDOWN - (datetime.now() - last_sent).total_seconds()
    
    if cooldown_remaining > 0:
        return False, f"Notification on cooldown"
    
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_CONFIG['sender_email']
        msg['To'] = EMAIL_CONFIG['recipient_email']
        msg['Subject'] = f"[NetPulse Monitor] {subject}"
        
        html_body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: monospace; }}
                .container {{ padding: 20px; border: 1px solid #00ff88; background: #0a0a0a; color: #00ff88; }}
                .critical {{ color: #ff003c; }}
                .warning {{ color: #ff6b00; }}
                .good {{ color: #00ff88; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>🛰 NETPULSE AI ALERT</h2>
                <hr>
                {body}
                <hr>
                <small>Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</small>
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
        return True, "Notification sent"
    except Exception as e:
        return False, f"Failed to send: {str(e)}"

def check_and_send_alerts(data):
    """Check conditions and send alerts"""
    if not data or data['network_score'] == 0:
        return
    
    # Critical Score Alert
    if data['network_score'] < ALERT_THRESHOLDS['critical_score']:
        subject = "🚨 CRITICAL: Network Health Degraded"
        body = f"""
        <div class="critical">
        <strong>CRITICAL ALERT</strong><br>
        Network Score: {data['network_score']:.1f}/100<br>
        Google Quality: {data['google_quality']}/100<br>
        YouTube Quality: {data['youtube_quality']}/100<br>
        Speed: {data['combined_speed']:.1f} Mbps
        </div>
        """
        send_email_notification(subject, body, "critical_score")
        add_log_entry("ALERT", f"Critical score alert - Score: {data['network_score']:.1f}")
    
    # Congestion Alert
    elif data['network_score'] < ALERT_THRESHOLDS['congestion_alert']:
        subject = "⚠️ Congestion Detected"
        body = f"""
        <div class="warning">
        Network Score: {data['network_score']:.1f}/100<br>
        Immediate attention recommended.
        </div>
        """
        send_email_notification(subject, body, "congestion")

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
            recs.append({'service': svc, 'message': f"CRITICAL — {svc} severely degraded (Score: {q}/100)", 'severity': 'critical'})
        elif q < 60:
            recs.append({'service': svc, 'message': f"DEGRADED — {svc} performance below threshold", 'severity': 'warning'})
    if data['network_score'] < 50:
        recs.append({'service': 'Network', 'message': f"SYSTEM ALERT — Network health critical ({data['network_score']:.0f}/100)", 'severity': 'critical'})
    return recs

# -------------------------
# ThingSpeak Fetch
# -------------------------
def fetch_thingspeak_data():
    try:
        CHANNEL_ID = "3381959"
        READ_API_KEY = "8F8XKE0PABJFF6GG"
        url = f"http://api.thingspeak.com/channels/{CHANNEL_ID}/feeds.json?api_key={READ_API_KEY}&results=1"
        response = requests.get(url, timeout=10)
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
    except Exception as e:
        print(f"Fetch error: {e}")
        return None, OFFLINE_THRESHOLD_SECONDS, None, "offline"

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
        if changed:
            st.session_state.update_count += 1
            st.session_state.pulse_triggered = True
            check_and_send_alerts(data)
        if should_save_to_database():
            save_classified_metrics(data, 1 if data['network_score'] < 50 else 0)
        return True
    return False

def format_time_diff(s):
    if s < 60: return f"{int(s)}s ago"
    elif s < 3600: return f"{int(s/60)}m ago"
    elif s < 86400: return f"{int(s/3600)}h ago"
    else: return f"{int(s/86400)}d ago"

# -------------------------
# Model + Init
# -------------------------
@st.cache_resource
def load_model():
    try: 
        return joblib.load("network_congestion_model.pkl")
    except: 
        return None

# Initialize database
initialize_database()

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
# CSS (same as your original - shortened for brevity)
# -------------------------
st.markdown("""
<style>
/* Your existing CSS styles here - copy from your original code */
</style>
""", unsafe_allow_html=True)

# -------------------------
# MAIN APP
# -------------------------
def main():
    # Header
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, rgba(0,245,255,0.06) 0%, rgba(191,0,255,0.04) 100%);
         border: 1px solid rgba(0,245,255,0.25); border-radius: 4px; padding: 2rem; margin-bottom: 1.5rem;">
        <h1 style="font-family: monospace; color: #00f5ff;">🛰 NETPULSE AI MONITOR</h1>
        <p>GOOGLE & YOUTUBE SERVICE CLASSIFICATION · CLOUD DEPLOYMENT</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.markdown("### ⬡ SYSTEM STATUS")
        
        auto_refresh = st.toggle("AUTO REFRESH", value=st.session_state.auto_refresh)
        if auto_refresh != st.session_state.auto_refresh:
            st.session_state.auto_refresh = auto_refresh
            st.rerun()
        
        # Email Configuration Section
        st.markdown("---")
        st.markdown("### ✉ EMAIL NOTIFICATIONS")
        
        if st.button("📧 TEST EMAIL", use_container_width=True):
            success, msg = test_email_connection()
            if success:
                st.success(f"✅ {msg}")
            else:
                st.error(f"❌ {msg}")
                st.info("💡 Add EMAIL_SENDER and EMAIL_PASSWORD to Streamlit Cloud Secrets")
        
        if st.button("⟳ REFRESH NOW", use_container_width=True):
            refresh_data()
            st.rerun()
        
        st.markdown("---")
        
        # Initialize data
        if st.session_state.data is None:
            refresh_data()
        
        data = st.session_state.data
        if data:
            st.metric("Network Score", f"{data['network_score']:.0f}/100")
            st.metric("Combined Speed", f"{data['combined_speed']:.1f} Mbps")
        
        st.caption(f"Last refresh: {st.session_state.last_refresh.strftime('%H:%M:%S')}")
    
    # Main content
    data = st.session_state.data
    
    if data and data['network_score'] > 0:
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"""
            <div style="background: rgba(0,245,255,0.04); border: 1px solid rgba(0,245,255,0.25); 
                 border-radius: 4px; padding: 1.5rem; text-align: center;">
                <h3>NETWORK HEALTH SCORE</h3>
                <h1 style="font-size: 4rem; color: {score_color(data['network_score'])};">
                    {data['network_score']:.0f}
                </h1>
                <h4>{data['network_status']}</h4>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div style="background: rgba(0,245,255,0.04); border: 1px solid rgba(0,245,255,0.25); 
                 border-radius: 4px; padding: 1.5rem;">
                <h3>SERVICE METRICS</h3>
                <p><strong>Google:</strong> {data['google_quality']}/100 
                (Latency: {data['google_latency']:.1f}ms)</p>
                <p><strong>YouTube:</strong> {data['youtube_quality']}/100 
                (Latency: {data['youtube_latency']:.1f}ms)</p>
            </div>
            """, unsafe_allow_html=True)
        
        # Recommendations
        st.markdown("### 💡 DIAGNOSTICS")
        recs = generate_recommendations(data)
        for rec in recs:
            if rec['severity'] == 'critical':
                st.error(f"**{rec['service']}**: {rec['message']}")
            elif rec['severity'] == 'warning':
                st.warning(f"**{rec['service']}**: {rec['message']}")
            else:
                st.success(f"**{rec['service']}**: {rec['message']}")
    
    else:
        st.info("◌ AWAITING DATA FROM THINGSPEAK...")
        with st.expander("📡 THINGSPEAK CHANNEL INFO"):
            st.code("""Channel ID: 3381959
field1 → Google Latency (ms)
field2 → Google Packet Loss (%)
field3 → Google Bandwidth (Mbps)
field4 → YouTube Latency (ms)
field5 → YouTube Packet Loss (%)
field6 → YouTube Bandwidth (Mbps)
field7 → Combined Speed (Mbps)
field8 → Network Score (0-100)""")

if __name__ == "__main__":
    main()
