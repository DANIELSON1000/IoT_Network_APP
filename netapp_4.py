# -*- coding: utf-8 -*-
"""
NetPulse AI Monitor - Zero Dependency Version
Uses only Streamlit built-in functions
"""

import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# -------------------------
# Page Config
# -------------------------
st.set_page_config(
    page_title="NetPulse Monitor",
    page_icon="📡",
    layout="wide"
)

# -------------------------
# Constants
# -------------------------
REFRESH_INTERVAL = 30
THINGSPEAK_CHANNEL = "3381959"
THINGSPEAK_KEY = "8F8XKE0PABJFF6GG"

# Email config (set in Streamlit secrets)
try:
    EMAIL_SENDER = st.secrets["EMAIL_SENDER"]
    EMAIL_PASSWORD = st.secrets["EMAIL_PASSWORD"]
    EMAIL_TO = st.secrets.get("EMAIL_TO", "ndahabonimanadaniel13@gmail.com")
except:
    EMAIL_SENDER = ""
    EMAIL_PASSWORD = ""
    EMAIL_TO = "ndahabonimanadaniel13@gmail.com"

# -------------------------
# Session State
# -------------------------
if 'data' not in st.session_state:
    st.session_state.data = None
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = datetime.now()
if 'history' not in st.session_state:
    st.session_state.history = []
if 'update_count' not in st.session_state:
    st.session_state.update_count = 0
if 'auto_refresh' not in st.session_state:
    st.session_state.auto_refresh = True

# -------------------------
# Functions
# -------------------------
def fetch_data():
    """Fetch data from ThingSpeak"""
    try:
        url = f"https://api.thingspeak.com/channels/{THINGSPEAK_CHANNEL}/feeds/last.json?api_key={THINGSPEAK_KEY}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Parse fields
            result = {
                'timestamp': datetime.now(),
                'google_latency': float(data.get('field1', 0) or 0),
                'google_loss': float(data.get('field2', 0) or 0),
                'google_bw': float(data.get('field3', 0) or 0),
                'youtube_latency': float(data.get('field4', 0) or 0),
                'youtube_loss': float(data.get('field5', 0) or 0),
                'youtube_bw': float(data.get('field6', 0) or 0),
                'combined_speed': float(data.get('field7', 0) or 0),
                'raw_score': float(data.get('field8', 0) or 0)
            }
            
            # Calculate quality scores
            result['google_score'] = calculate_score(
                result['google_latency'], 
                result['google_loss'], 
                result['google_bw'],
                'google'
            )
            result['youtube_score'] = calculate_score(
                result['youtube_latency'],
                result['youtube_loss'],
                result['youtube_bw'],
                'youtube'
            )
            
            # Final network score
            if result['raw_score'] > 0:
                result['network_score'] = result['raw_score']
            else:
                result['network_score'] = (result['google_score'] + result['youtube_score']) / 2
            
            # Status
            if result['network_score'] >= 80:
                result['status'] = "EXCELLENT"
                result['status_color'] = "#00ff88"
            elif result['network_score'] >= 60:
                result['status'] = "GOOD"
                result['status_color'] = "#00f5ff"
            elif result['network_score'] >= 40:
                result['status'] = "FAIR"
                result['status_color'] = "#ffe600"
            elif result['network_score'] >= 20:
                result['status'] = "POOR"
                result['status_color'] = "#ff6b00"
            else:
                result['status'] = "CRITICAL"
                result['status_color'] = "#ff003c"
            
            return result
        else:
            return None
    except Exception as e:
        return None

def calculate_score(latency, loss, bandwidth, service):
    """Calculate quality score (0-100)"""
    # Google thresholds
    if service == 'google':
        if latency <= 50:
            latency_score = 100
        elif latency <= 100:
            latency_score = 60 - (latency - 50) / 50 * 40
        else:
            latency_score = max(0, 20 - (latency - 100) / 10)
        
        if loss <= 1:
            loss_score = 100
        elif loss <= 2:
            loss_score = 70 - (loss - 1) / 1 * 30
        else:
            loss_score = max(0, 40 - (loss - 2) * 20)
        
        if bandwidth >= 50:
            bw_score = 100
        elif bandwidth >= 20:
            bw_score = 60 + (bandwidth - 20) / 30 * 40
        else:
            bw_score = (bandwidth / 20) * 60
    else:  # YouTube
        if latency <= 70:
            latency_score = 100
        elif latency <= 140:
            latency_score = 60 - (latency - 70) / 70 * 40
        else:
            latency_score = max(0, 20 - (latency - 140) / 10)
        
        if loss <= 0.5:
            loss_score = 100
        elif loss <= 1.5:
            loss_score = 70 - (loss - 0.5) / 1 * 30
        else:
            loss_score = max(0, 40 - (loss - 1.5) * 20)
        
        if bandwidth >= 75:
            bw_score = 100
        elif bandwidth >= 30:
            bw_score = 60 + (bandwidth - 30) / 45 * 40
        else:
            bw_score = (bandwidth / 30) * 60
    
    return int(latency_score * 0.4 + loss_score * 0.3 + bw_score * 0.3)

def send_alert(subject, message):
    """Send email alert"""
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_TO
        msg['Subject'] = f"[NetPulse] {subject}"
        
        body = f"""
NetPulse Monitor Alert
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{message}

---
NetPulse AI Monitor - Real-time Network Monitoring
"""
        
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except:
        return False

def check_alerts(data):
    """Check conditions and send alerts"""
    if not data:
        return
    
    alerts = []
    
    if data['network_score'] < 40:
        alerts.append(f"🚨 CRITICAL: Network score is {data['network_score']:.0f}/100")
    elif data['network_score'] < 60:
        alerts.append(f"⚠️ WARNING: Network score is {data['network_score']:.0f}/100")
    
    if data['google_latency'] > 150:
        alerts.append(f"📡 High Google latency: {data['google_latency']:.0f}ms")
    
    if data['youtube_latency'] > 150:
        alerts.append(f"📡 High YouTube latency: {data['youtube_latency']:.0f}ms")
    
    if data['google_loss'] > 3:
        alerts.append(f"📡 Google packet loss: {data['google_loss']:.1f}%")
    
    if data['youtube_loss'] > 3:
        alerts.append(f"📡 YouTube packet loss: {data['youtube_loss']:.1f}%")
    
    if alerts and st.session_state.update_count % 6 == 0 and st.session_state.update_count > 0:
        send_alert("Network Alert", "\n".join(alerts))

def get_score_color(score):
    if score >= 80: return "#00ff88"
    if score >= 60: return "#00f5ff"
    if score >= 40: return "#ffe600"
    if score >= 20: return "#ff6b00"
    return "#ff003c"

# -------------------------
# CSS Styling
# -------------------------
st.markdown("""
<style>
.big-score {
    font-size: 4rem;
    font-weight: bold;
    text-align: center;
}
.metric-card {
    background: rgba(0, 245, 255, 0.05);
    border: 1px solid rgba(0, 245, 255, 0.2);
    border-radius: 10px;
    padding: 1rem;
    margin: 0.5rem 0;
}
.status-badge {
    display: inline-block;
    padding: 0.25rem 1rem;
    border-radius: 20px;
    font-weight: bold;
}
</style>
""", unsafe_allow_html=True)

# -------------------------
# Main App
# -------------------------
def main():
    # Title
    st.markdown("""
    <div style="text-align: center; padding: 2rem; background: linear-gradient(135deg, #0a0a2a, #1a1a3a); border-radius: 10px; margin-bottom: 2rem;">
        <h1 style="color: #00f5ff; margin: 0;">🛰 NetPulse AI Monitor</h1>
        <p style="color: #88aaff; margin-top: 0.5rem;">Real-time Google & YouTube Network Monitoring</p>
        <p style="color: #556688; font-size: 0.8rem;">Data Source: ThingSpeak Channel 3381959</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.markdown("### ⚙️ Controls")
        
        # Auto refresh toggle
        auto_refresh = st.toggle("Auto Refresh", value=st.session_state.auto_refresh)
        if auto_refresh != st.session_state.auto_refresh:
            st.session_state.auto_refresh = auto_refresh
        
        # Manual refresh button
        if st.button("🔄 Refresh Now", use_container_width=True):
            with st.spinner("Fetching data from ThingSpeak..."):
                data = fetch_data()
                if data:
                    st.session_state.data = data
                    st.session_state.history.insert(0, data)
                    # Keep only last 100 records
                    if len(st.session_state.history) > 100:
                        st.session_state.history = st.session_state.history[:100]
                    st.session_state.update_count += 1
                    st.session_state.last_refresh = datetime.now()
                    check_alerts(data)
                    st.success("✅ Data updated successfully!")
                    st.rerun()
                else:
                    st.error("❌ Failed to fetch data. Check ThingSpeak channel.")
        
        st.markdown("---")
        
        # Statistics
        st.markdown("### 📊 Statistics")
        
        if st.session_state.update_count > 0:
            st.metric("Total Updates", st.session_state.update_count)
        
        if st.session_state.data:
            st.metric("Current Score", f"{st.session_state.data['network_score']:.0f}/100")
            st.metric("Combined Speed", f"{st.session_state.data['combined_speed']:.1f} Mbps")
        
        st.markdown("---")
        
        # Email notifications
        st.markdown("### ✉️ Notifications")
        
        if EMAIL_SENDER and EMAIL_PASSWORD:
            st.success("✅ Email configured")
            st.caption(f"📧 Sending alerts to: {EMAIL_TO}")
            st.caption("⏱️ Alerts sent every 3 minutes when issues detected")
        else:
            st.warning("⚠️ Email not configured")
            st.info("""
            To receive email alerts:
            1. Go to Streamlit Cloud → Settings → Secrets
            2. Add:
               - EMAIL_SENDER = "your.email@gmail.com"
               - EMAIL_PASSWORD = "your_app_password"
               - EMAIL_TO = "recipient@email.com"
            """)
        
        st.markdown("---")
        st.caption(f"🕐 Last refresh: {st.session_state.last_refresh.strftime('%H:%M:%S')}")
        st.caption(f"📊 History records: {len(st.session_state.history)}")
    
    # Main content area
    if st.session_state.data:
        data = st.session_state.data
        score_color = get_score_color(data['network_score'])
        
        # Main score card
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown(f"""
            <div style="text-align: center; padding: 2rem; background: rgba(0,245,255,0.05); border-radius: 15px; border: 2px solid {score_color};">
                <h2 style="color: #aaa; margin: 0;">Network Health Score</h2>
                <div class="big-score" style="color: {score_color};">{data['network_score']:.0f}</div>
                <div class="status-badge" style="background: {score_color}20; color: {score_color}; border: 1px solid {score_color};">
                    {data['status']}
                </div>
                <hr style="margin: 1rem 0;">
                <p style="font-size: 1.2rem;">⚡ Combined Speed: <strong>{data['combined_speed']:.1f} Mbps</strong></p>
                <p style="font-size: 0.9rem; color: #88aaff;">📡 Last reading: {data['timestamp'].strftime('%H:%M:%S')}</p>
            </div>
            """, unsafe_allow_html=True)
        
        # Service metrics - Two columns
        col1, col2 = st.columns(2)
        
        with col1:
            google_color = "#4285f4"
            google_score_color = get_score_color(data['google_score'])
            st.markdown(f"""
            <div class="metric-card" style="border-left: 4px solid {google_color};">
                <h3 style="color: {google_color}; margin: 0 0 1rem 0;">🔍 Google Services</h3>
                <p><strong>Quality Score:</strong> 
                    <span style="color: {google_score_color}; font-size: 1.2rem; font-weight: bold;">{data['google_score']}/100</span>
                </p>
                <p>📡 <strong>Latency:</strong> {data['google_latency']:.1f} ms</p>
                <p>📊 <strong>Packet Loss:</strong> {data['google_loss']:.2f}%</p>
                <p>⚡ <strong>Bandwidth:</strong> {data['google_bw']:.1f} Mbps</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            youtube_color = "#ff0000"
            youtube_score_color = get_score_color(data['youtube_score'])
            st.markdown(f"""
            <div class="metric-card" style="border-left: 4px solid {youtube_color};">
                <h3 style="color: {youtube_color}; margin: 0 0 1rem 0;">▶️ YouTube Services</h3>
                <p><strong>Quality Score:</strong> 
                    <span style="color: {youtube_score_color}; font-size: 1.2rem; font-weight: bold;">{data['youtube_score']}/100</span>
                </p>
                <p>📡 <strong>Latency:</strong> {data['youtube_latency']:.1f} ms</p>
                <p>📊 <strong>Packet Loss:</strong> {data['youtube_loss']:.2f}%</p>
                <p>⚡ <strong>Bandwidth:</strong> {data['youtube_bw']:.1f} Mbps</p>
            </div>
            """, unsafe_allow_html=True)
        
        # Alerts and recommendations
        st.markdown("---")
        st.markdown("### 💡 Status & Recommendations")
        
        if data['network_score'] < 40:
            st.error("🚨 **CRITICAL**: Network severely degraded! Immediate investigation required.")
            st.markdown("""
            **Recommended actions:**
            - Check physical router/modem connections
            - Contact your ISP if issue persists
            - Review bandwidth usage on your network
            """)
        elif data['network_score'] < 60:
            st.warning("⚠️ **WARNING**: Network performance is below optimal levels.")
            st.markdown("""
            **Recommended actions:**
            - Monitor for pattern (time of day issues)
            - Check for background downloads/uploads
            - Consider restarting your router
            """)
        else:
            st.success("✅ **GOOD**: All services are operating within normal parameters.")
        
        # Individual service issues
        if data['google_score'] < 60:
            st.warning(f"🔍 **Google Alert**: Performance degraded (Score: {data['google_score']}/100)")
        
        if data['youtube_score'] < 60:
            st.warning(f"▶️ **YouTube Alert**: Performance degraded (Score: {data['youtube_score']}/100)")
        
        if data['google_latency'] > 100:
            st.info(f"📡 High Google latency ({data['google_latency']:.0f}ms) may affect browsing experience")
        
        if data['youtube_latency'] > 100:
            st.info(f"📡 High YouTube latency ({data['youtube_latency']:.0f}ms) may affect streaming quality")
        
        # Historical chart using native Streamlit
        if len(st.session_state.history) > 1:
            st.markdown("---")
            st.markdown("### 📈 Historical Performance Trend")
            
            # Create dataframe
            df = pd.DataFrame(st.session_state.history[:50])
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp')
            
            # Display line chart using native Streamlit
            chart_data = pd.DataFrame({
                'Time': df['timestamp'],
                'Network Score': df['network_score'],
                'Google Score': df['google_score'],
                'YouTube Score': df['youtube_score']
            })
            chart_data = chart_data.set_index('Time')
            
            st.line_chart(chart_data, use_container_width=True)
            
            # Show recent data table
            with st.expander("📊 View Recent Data Table"):
                recent_df = pd.DataFrame(st.session_state.history[:20])
                recent_df['timestamp'] = pd.to_datetime(recent_df['timestamp'])
                display_df = recent_df[['timestamp', 'network_score', 'google_score', 'youtube_score', 'combined_speed']]
                display_df.columns = ['Time', 'Network Score', 'Google Score', 'YouTube Score', 'Speed (Mbps)']
                st.dataframe(display_df, use_container_width=True)
    
    else:
        # No data - show setup and auto-fetch
        st.info("🔄 Click 'Refresh Now' in the sidebar to start monitoring your network!")
        
        # Show channel info
        with st.expander("📡 ThingSpeak Channel Configuration", expanded=True):
            st.markdown("""
            ### Channel Information
            - **Channel ID:** 3381959
            - **API Key:** 8F8XKE0PABJFF6GG
            
            ### Field Mapping
            | Field | Metric |
            |-------|--------|
            | field1 | Google Latency (ms) |
            | field2 | Google Packet Loss (%) |
            | field3 | Google Bandwidth (Mbps) |
            | field4 | YouTube Latency (ms) |
            | field5 | YouTube Packet Loss (%) |
            | field6 | YouTube Bandwidth (Mbps) |
            | field7 | Combined Speed (Mbps) |
            | field8 | Network Score (0-100) |
            """)
        
        # Auto-fetch initial data
        if st.button("🔄 Fetch Initial Data", use_container_width=True):
            with st.spinner("Fetching data from ThingSpeak..."):
                data = fetch_data()
                if data:
                    st.session_state.data = data
                    st.session_state.history.append(data)
                    st.session_state.last_refresh = datetime.now()
                    st.session_state.update_count += 1
                    st.success("✅ Data loaded successfully!")
                    st.rerun()
                else:
                    st.error("❌ Failed to fetch data. Please check ThingSpeak channel status.")

# Auto-refresh logic
if st.session_state.auto_refresh and st.session_state.data:
    time_diff = (datetime.now() - st.session_state.last_refresh).total_seconds()
    if time_diff >= REFRESH_INTERVAL:
        data = fetch_data()
        if data:
            st.session_state.data = data
            st.session_state.history.insert(0, data)
            if len(st.session_state.history) > 100:
                st.session_state.history = st.session_state.history[:100]
            st.session_state.update_count += 1
            st.session_state.last_refresh = datetime.now()
            check_alerts(data)
            st.rerun()

if __name__ == "__main__":
    main()
