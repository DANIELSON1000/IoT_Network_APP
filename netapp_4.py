# -*- coding: utf-8 -*-
"""
AI Network Monitor - Google & YouTube
Cloud-Optimized Version - No problematic dependencies
"""

import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json
import os

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
REFRESH_INTERVAL = 30

SERVICE_THRESHOLDS = {
    'google': {'latency_good': 50, 'latency_warning': 100, 'loss_good': 1, 'loss_warning': 2, 'bw_good': 50, 'bw_warning': 20},
    'youtube': {'latency_good': 70, 'latency_warning': 140, 'loss_good': 0.5, 'loss_warning': 1.5, 'bw_good': 75, 'bw_warning': 30}
}

# Email Configuration - from Streamlit secrets
try:
    EMAIL_SENDER = st.secrets["EMAIL_SENDER"]
    EMAIL_PASSWORD = st.secrets["EMAIL_PASSWORD"]
    EMAIL_RECIPIENT = st.secrets.get("EMAIL_RECIPIENT", "ndahabonimanadaniel13@gmail.com")
except:
    EMAIL_SENDER = ""
    EMAIL_PASSWORD = ""
    EMAIL_RECIPIENT = "ndahabonimanadaniel13@gmail.com"

NOTIFICATION_COOLDOWN = 300

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
    'pulse_triggered': False,
    'update_count': 0,
    'last_notification_sent': {}
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

# -------------------------
# Data Storage using Session State (no database)
# -------------------------
def save_metric_to_history(data):
    """Store metrics in session state instead of database"""
    if 'metrics_history' not in st.session_state:
        st.session_state.metrics_history = []
    
    # Add timestamp
    metric_entry = {
        'timestamp': datetime.now().isoformat(),
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
        'network_status': data['network_status']
    }
    
    st.session_state.metrics_history.insert(0, metric_entry)
    
    # Keep only last 1000 entries
    if len(st.session_state.metrics_history) > 1000:
        st.session_state.metrics_history = st.session_state.metrics_history[:1000]
    
    return True

def load_historical_data(limit=100):
    """Load historical data from session state"""
    if 'metrics_history' not in st.session_state or not st.session_state.metrics_history:
        return pd.DataFrame()
    
    df = pd.DataFrame(st.session_state.metrics_history[:limit])
    if not df.empty:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    return df

def add_system_log(message, log_type="INFO"):
    """Add system log to session state"""
    if 'system_logs' not in st.session_state:
        st.session_state.system_logs = []
    
    st.session_state.system_logs.insert(0, {
        'timestamp': datetime.now().isoformat(),
        'type': log_type,
        'message': message
    })
    
    # Keep only last 500 logs
    if len(st.session_state.system_logs) > 500:
        st.session_state.system_logs = st.session_state.system_logs[:500]

def load_system_logs(limit=100):
    """Load system logs from session state"""
    if 'system_logs' not in st.session_state:
        return pd.DataFrame()
    
    logs = st.session_state.system_logs[:limit]
    df = pd.DataFrame(logs)
    if not df.empty:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    return df

# -------------------------
# Email Functions
# -------------------------
def send_email_notification(subject, body, alert_type="general"):
    """Send email notification"""
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        return False, "Email not configured"
    
    # Check cooldown
    last_sent = st.session_state.last_notification_sent.get(alert_type, datetime.min)
    if (datetime.now() - last_sent).total_seconds() < NOTIFICATION_COOLDOWN:
        return False, "Cooldown active"
    
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_RECIPIENT
        msg['Subject'] = f"[NetPulse] {subject}"
        
        body_html = f"""
        <html>
        <body style="font-family: monospace;">
            <h2>🛰 NetPulse Monitor Alert</h2>
            <hr>
            <pre>{body}</pre>
            <hr>
            <small>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</small>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(body_html, 'html'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        st.session_state.last_notification_sent[alert_type] = datetime.now()
        add_system_log(f"Email sent: {subject}", "INFO")
        return True, "Sent"
        
    except Exception as e:
        add_system_log(f"Email failed: {str(e)}", "ERROR")
        return False, str(e)

def check_alerts(data):
    """Check and send alerts"""
    if not data:
        return
    
    if data['network_score'] < 40:
        subject = "CRITICAL: Network Score Low"
        body = f"""
Network Score: {data['network_score']:.0f}/100
Status: {data['network_status']}

Google: {data['google_quality']}/100 (Latency: {data['google_latency']:.1f}ms)
YouTube: {data['youtube_quality']}/100 (Latency: {data['youtube_latency']:.1f}ms)
Speed: {data['combined_speed']:.1f} Mbps
        """
        send_email_notification(subject, body, "critical")
    
    elif data['network_score'] < 60:
        subject = "WARNING: Network Degraded"
        body = f"""
Network Score: {data['network_score']:.0f}/100
Check your connection for potential issues.
        """
        send_email_notification(subject, body, "warning")

# -------------------------
# Quality Score Functions
# -------------------------
def calculate_quality_score(latency, packet_loss, bandwidth, service):
    t = SERVICE_THRESHOLDS.get(service, SERVICE_THRESHOLDS['google'])
    
    # Latency score
    if latency <= t['latency_good']:
        latency_score = 100
    elif latency <= t['latency_warning']:
        latency_score = 60 - (latency - t['latency_good']) / (t['latency_warning'] - t['latency_good']) * 40
    else:
        latency_score = max(0, 20 - (latency - t['latency_warning']) / 10)
    
    # Packet loss score
    if packet_loss <= t['loss_good']:
        loss_score = 100
    elif packet_loss <= t['loss_warning']:
        loss_score = 70 - (packet_loss - t['loss_good']) / (t['loss_warning'] - t['loss_good']) * 30
    else:
        loss_score = max(0, 40 - (packet_loss - t['loss_warning']) * 20)
    
    # Bandwidth score
    if bandwidth >= t['bw_good']:
        bw_score = 100
    elif bandwidth >= t['bw_warning']:
        bw_score = 60 + (bandwidth - t['bw_warning']) / (t['bw_good'] - t['bw_warning']) * 40
    else:
        bw_score = max(0, (bandwidth / t['bw_warning']) * 60)
    
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

# -------------------------
# ThingSpeak Data Fetch
# -------------------------
def fetch_thingspeak_data():
    try:
        CHANNEL_ID = "3381959"
        READ_API_KEY = "8F8XKE0PABJFF6GG"
        url = f"https://api.thingspeak.com/channels/{CHANNEL_ID}/feeds.json?api_key={READ_API_KEY}&results=1"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if 'feeds' in data and data['feeds']:
            latest = data['feeds'][0]
            
            # Parse fields
            google_latency = float(latest.get('field1', 0) or 0)
            google_loss = float(latest.get('field2', 0) or 0)
            google_bw = float(latest.get('field3', 0) or 0)
            youtube_latency = float(latest.get('field4', 0) or 0)
            youtube_loss = float(latest.get('field5', 0) or 0)
            youtube_bw = float(latest.get('field6', 0) or 0)
            combined_speed = float(latest.get('field7', 0) or 0)
            network_score = float(latest.get('field8', 0) or 0)
            
            if google_latency == 0 and youtube_latency == 0:
                return None, 300, None, "offline"
            
            result = {
                'google_latency': google_latency,
                'google_packet_loss': google_loss,
                'google_bandwidth': google_bw,
                'google_quality': calculate_quality_score(google_latency, google_loss, google_bw, 'google'),
                'youtube_latency': youtube_latency,
                'youtube_packet_loss': youtube_loss,
                'youtube_bandwidth': youtube_bw,
                'youtube_quality': calculate_quality_score(youtube_latency, youtube_loss, youtube_bw, 'youtube'),
                'combined_speed': combined_speed,
                'network_score': network_score if network_score > 0 else calculate_quality_score(google_latency, google_loss, google_bw, 'google'),
                'network_status': get_network_status(network_score)
            }
            
            # Fix network score if needed
            if result['network_score'] == 0:
                result['network_score'] = (result['google_quality'] + result['youtube_quality']) / 2
                result['network_status'] = get_network_status(result['network_score'])
            
            # Calculate time difference
            if latest.get('created_at'):
                last_update = datetime.strptime(latest['created_at'], '%Y-%m-%dT%H:%M:%SZ')
                time_diff = (datetime.utcnow() - last_update).total_seconds()
                status = "online" if time_diff < ONLINE_THRESHOLD_SECONDS else "recent"
            else:
                time_diff = 0
                status = "online"
            
            return result, time_diff, None, status
        
        return None, 300, None, "offline"
        
    except Exception as e:
        add_system_log(f"Fetch error: {str(e)}", "ERROR")
        return None, 300, None, "offline"

def refresh_data():
    """Refresh data from ThingSpeak"""
    data, td, lu, status = fetch_thingspeak_data()
    
    if data and data['network_score'] > 0:
        st.session_state.prev_data = st.session_state.data
        st.session_state.data = data
        st.session_state.time_diff = td
        st.session_state.status = status
        st.session_state.last_refresh = datetime.now()
        st.session_state.update_count += 1
        st.session_state.pulse_triggered = True
        
        # Save to history
        save_metric_to_history(data)
        
        # Check and send alerts
        check_alerts(data)
        
        add_system_log(f"Data updated - Score: {data['network_score']:.0f}", "INFO")
        return True
    
    return False

def format_time_diff(seconds):
    if seconds < 60:
        return f"{int(seconds)}s ago"
    elif seconds < 3600:
        return f"{int(seconds/60)}m ago"
    else:
        return f"{int(seconds/3600)}h ago"

# -------------------------
# CSS Styling
# -------------------------
st.markdown("""
<style>
.stApp {
    background: linear-gradient(135deg, #020818 0%, #040f2a 100%);
    color: #e8f4fd;
}
.metric-card {
    background: rgba(0, 245, 255, 0.04);
    border: 1px solid rgba(0, 245, 255, 0.2);
    border-radius: 8px;
    padding: 1rem;
    margin: 0.5rem 0;
}
.status-online { color: #00ff88; }
.status-warning { color: #ff6b00; }
.status-critical { color: #ff003c; }
</style>
""", unsafe_allow_html=True)

# -------------------------
# Main App
# -------------------------
def main():
    # Header
    st.title("🛰 NETPULSE AI MONITOR")
    st.caption("Google & YouTube Service Classification | Live ThingSpeak Data")
    
    # Sidebar
    with st.sidebar:
        st.markdown("### ⚙️ CONTROL PANEL")
        
        # Auto refresh toggle
        auto_refresh = st.toggle("Auto Refresh", value=st.session_state.auto_refresh)
        if auto_refresh != st.session_state.auto_refresh:
            st.session_state.auto_refresh = auto_refresh
            st.rerun()
        
        # Manual refresh button
        if st.button("🔄 Refresh Now", use_container_width=True):
            if refresh_data():
                st.success("Data refreshed!")
                st.rerun()
            else:
                st.error("Failed to fetch data")
        
        st.markdown("---")
        
        # Email status
        st.markdown("### ✉️ Notifications")
        if EMAIL_SENDER and EMAIL_PASSWORD:
            st.success(f"📧 Active: {EMAIL_SENDER[:5]}...@{EMAIL_SENDER.split('@')[-1]}")
            st.caption(f"Recipient: {EMAIL_RECIPIENT}")
        else:
            st.warning("⚠️ Email not configured")
            st.info("Add EMAIL_SENDER and EMAIL_PASSWORD to Streamlit secrets")
        
        st.markdown("---")
        
        # System info
        st.markdown("### 📊 Statistics")
        if st.session_state.update_count > 0:
            st.metric("Total Updates", st.session_state.update_count)
        
        if st.session_state.data:
            st.metric("Current Score", f"{st.session_state.data['network_score']:.0f}/100")
        
        st.caption(f"Last refresh: {st.session_state.last_refresh.strftime('%H:%M:%S')}")
    
    # Main content
    if st.session_state.data:
        data = st.session_state.data
        
        # Score display
        col1, col2, col3 = st.columns(3)
        
        with col1:
            score = data['network_score']
            color = score_color(score)
            st.markdown(f"""
            <div class="metric-card" style="text-align: center;">
                <h3>NETWORK HEALTH</h3>
                <h1 style="font-size: 4rem; color: {color};">{score:.0f}</h1>
                <h2>{data['network_status']}</h2>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div class="metric-card">
                <h3>📡 GOOGLE</h3>
                <p>Quality: <b>{data['google_quality']}/100</b></p>
                <p>Latency: {data['google_latency']:.1f} ms</p>
                <p>Loss: {data['google_packet_loss']:.2f}%</p>
                <p>Bandwidth: {data['google_bandwidth']:.1f} Mbps</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown(f"""
            <div class="metric-card">
                <h3>▶️ YOUTUBE</h3>
                <p>Quality: <b>{data['youtube_quality']}/100</b></p>
                <p>Latency: {data['youtube_latency']:.1f} ms</p>
                <p>Loss: {data['youtube_packet_loss']:.2f}%</p>
                <p>Bandwidth: {data['youtube_bandwidth']:.1f} Mbps</p>
            </div>
            """, unsafe_allow_html=True)
        
        # Combined speed
        st.info(f"⚡ Combined Speed: {data['combined_speed']:.1f} Mbps")
        
        # Historical chart
        st.markdown("---")
        st.markdown("### 📈 Historical Data")
        
        hist_df = load_historical_data(50)
        if not hist_df.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=hist_df['timestamp'],
                y=hist_df['network_score'],
                mode='lines+markers',
                name='Network Score',
                line=dict(color='#00f5ff', width=2),
                marker=dict(size=4, color='#00f5ff')
            ))
            fig.update_layout(
                title="Network Score Over Time",
                xaxis_title="Time",
                yaxis_title="Score",
                template="plotly_dark",
                height=400,
                hovermode='x unified'
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Real-time diagnostics
        st.markdown("---")
        st.markdown("### 💡 Real-time Diagnostics")
        
        if data['network_score'] < 40:
            st.error("🚨 CRITICAL: Network severely degraded. Immediate action recommended!")
        elif data['network_score'] < 60:
            st.warning("⚠️ WARNING: Network performance below optimal levels.")
        else:
            st.success("✅ All services operating normally.")
        
        if data['google_quality'] < 60:
            st.warning(f"Google performance degraded (Score: {data['google_quality']}/100)")
        if data['youtube_quality'] < 60:
            st.warning(f"YouTube performance degraded (Score: {data['youtube_quality']}/100)")
    
    else:
        st.info("🔄 Waiting for data from ThingSpeak...")
        st.caption("Channel ID: 3381959 | Auto-refresh every 30 seconds")
        
        # Show channel info
        with st.expander("📡 ThingSpeak Channel Configuration"):
            st.code("""
Channel ID: 3381959
API Key: 8F8XKE0PABJFF6GG

Field 1: Google Latency (ms)
Field 2: Google Packet Loss (%)
Field 3: Google Bandwidth (Mbps)
Field 4: YouTube Latency (ms)
Field 5: YouTube Packet Loss (%)
Field 6: YouTube Bandwidth (Mbps)
Field 7: Combined Speed (Mbps)
Field 8: Network Score (0-100)
            """)
    
    # Auto refresh logic
    if st.session_state.auto_refresh:
        time_since_refresh = (datetime.now() - st.session_state.last_refresh).total_seconds()
        if time_since_refresh >= REFRESH_INTERVAL:
            refresh_data()
            st.rerun()
        else:
            time_remaining = int(REFRESH_INTERVAL - time_since_refresh)
            st.sidebar.caption(f"Next refresh in: {time_remaining}s")

if __name__ == "__main__":
    # Initial data load
    if st.session_state.data is None:
        refresh_data()
    
    main()
