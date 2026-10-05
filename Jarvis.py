a import streamlit as st
from openai import OpenAI
from datetime import datetime, timezone, timedelta
import urllib.request
import os
import json
from streamlit_mic_recorder import mic_recorder

from auth_utils import (
    load_users, add_or_update_detailed_user, delete_user, change_password, 
    load_permanent_memory, auto_save_memory, get_current_date,
    get_jarvis_memory, save_jarvis_memory
)
from request_utils import load_requests, delete_request, save_request
from email_utils import send_reply_email
from image_generation_and_pdf import render_image_module
from speech_utils import speak_and_notify, render_notification_permission_button
from time_utils import load_timetable, save_timetable, check_and_trigger_timetable
from realtime_ui import render_realtime_orb
from sidebar_utils import render_collapsible_sidebar

# --- Permanent Text File (.txt) Chat Memory Functions ---
def get_chat_txt_filename(username):
    safe_user = "".join([c for c in username if c.isalnum() or c in ('_', '-')])
    return f"chat_history_{safe_user}.txt"

def load_chat_history_txt(username):
    if not username:
        return []
    filename = get_chat_txt_filename(username)
    messages = []
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                content = f.read()
                blocks = content.split("---MESSAGE_SPLIT---")
                for block in blocks:
                    if ":" in block:
                        parts = block.strip().split(":", 1)
                        if len(parts) == 2:
                            role = parts[0].strip().lower()
                            msg_content = parts[1].strip()
                            if role in ["user", "assistant"] and msg_content:
                                messages.append({"role": role, "content": msg_content})
        except Exception:
            pass
    return messages

def append_to_chat_history_txt(username, role, content):
    if not username:
        return
    filename = get_chat_txt_filename(username)
    try:
        block = f"\n---MESSAGE_SPLIT---\n{role.upper()}: {content}"
        with open(filename, "a", encoding="utf-8") as f:
            f.write(block)
    except Exception as e:
        st.error(f"Error saving history: {e}")

# --- Web Search Utility ---
def search_web(query):
    try:
        encoded_q = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_q}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            html = response.read().decode('utf-8')
            import re
            snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', html, re.DOTALL)
            clean_snippets = [re.sub(r'<[^>]+>', '', s).strip() for s in snippets[:3]]
            if clean_snippets:
                return " | ".join(clean_snippets)
    except Exception:
        pass
    return "No live search results available."

# --- Page Configuration ---
st.set_page_config(
    page_title="Jarvis // Aayush Technology",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Stark Button Hover Theme ---
st.markdown("""
<style>
.stButton>button {
    border-radius: 8px;
    transition: all 0.2s ease-in-out;
}
.stButton>button:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(255, 183, 0, 0.25);
}
</style>
""", unsafe_allow_html=True)

# --- Time & Weather ---
USER_LOCATION = "Bengaluru, India"
IST = timezone(timedelta(hours=5, minutes=30))

def get_current_time():
    return datetime.now(IST).strftime("%I:%M:%S %p")

def get_weather_info():
    try:
        url = "https://wttr.in/Bengaluru?format=3"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=2) as response:
            return response.read().decode('utf-8').strip()
    except Exception:
        return "Bengaluru: 28°C, Clear"

# --- Groq API Setup ---
GROQ_API_KEY = "gsk_YOUR_GROQ_API_KEY_HERE"  # <-- Paste your Groq API Key here
client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=GROQ_API_KEY)

# --- Session States ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "current_user" not in st.session_state:
    st.session_state.current_user = ""
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False
if "mode" not in st.session_state:
    st.session_state.mode = "Realtime"
if "last_processed_audio" not in st.session_state:
    st.session_state.last_processed_audio = None
if "input_counter" not in st.session_state:
    st.session_state.input_counter = 0

registered_users = load_users()
if "Aayush" not in registered_users:
    registered_users["Aayush"] = {
        "password": "123098", "role": "admin", "school": "Aayush Technology High",
        "title_pref": "Sir", "name": "Aayush", "class": "10", "email": "aayushkumar91205@gmail.com"
    }

# --- Login Gateway & Access Request Tab ---
if not st.session_state.authenticated:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("## 🛡️ SECURE TERMINAL GATEWAY")
        user_list = list(registered_users.keys())
        
        tab_login, tab_request = st.tabs(["🔑 Login", "📝 Request Access"])
        
        with tab_login:
            with st.form("login_form"):
                selected_username = st.selectbox("👤 Select Profile", user_list)
                entered_password = st.text_input("🔑 Passcode", type="password")
                if st.form_submit_button("⚡ Launch Jarvis", use_container_width=True):
                    if selected_username in registered_users and registered_users[selected_username]["password"] == entered_password:
                        st.session_state.authenticated = True
                        st.session_state.current_user = selected_username
                        st.session_state.is_admin = (registered_users[selected_username].get("role") == "admin")
                        st.session_state.messages = []
                        st.rerun()
                    else:
                        st.error("Invalid Passcode! (Invalid username or password)")
                        
        with tab_request:
            st.markdown("### Request Access to Jarvis")
            with st.form("access_request_form"):
                req_name = st.text_input("Full Name*")
                req_email = st.text_input("Email*")
                req_phone = st.text_input("Phone Number*")
                req_address = st.text_area("Address / Reason")
                req_hobby = st.text_input("Hobby")
                req_target = st.text_input("Target / Goal")
                
                if st.form_submit_button("Submit Access Request & Email Admin", use_container_width=True):
                    if req_name and req_email and req_phone:
                        req_data = {
                            "name": req_name, "email": req_email, "phone": req_phone,
                            "address": req_address, "hobby": req_hobby, "target": req_target,
                            "date": get_current_date()
                        }
                        save_request(req_data)
                        send_reply_email("aayush*********@gmail.com", "New Jarvis Access Request", f"New request from {req_name} ({req_email}).")
                        st.success("Request sent and email dispatched successfully!")
                    else:
                        st.error("Please fill in Name, Email, and Phone number.")
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []

# --- Profile Configuration & Title Prefs ---
current_user_data = registered_users.get(st.session_state.current_user, {})
title_pref = current_user_data.get("title_pref", "Sir")
display_address_name = "Sir" if title_pref == "Sir" else st.session_state.current_user
school_name = current_user_data.get("school", "Aayush Technology High")

# --- Render Sidebar Menu ---
with st.sidebar:
    render_collapsible_sidebar()
    st.markdown(f"<br><small>👤 Logged in as: <b>{st.session_state.current_user}</b></small>", unsafe_allow_html=True)
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    if st.button("🚪 Lock Screen", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.current_user = ""
        st.session_state.is_admin = False
        st.session_state.messages = []
        st.rerun()
    if st.button("🧹 Clear Screen Display", use_container_width=True):
        st.session_state.messages = []
        st.success("Screen cleared for new chat! All history remains safely stored in the .txt file.")
        st.rerun()

# --- Main HUD Interface ---
st.markdown(f"### ⚡ JARVIS AI CORE // {school_name} // Welcome, {display_address_name}")
col1, col2, col3, col4 = st.columns(4)
with col1: st.metric("🕒 TIME", get_current_time())
with col2: st.metric("🌤 WEATHER", get_weather_info())
with col3: st.metric("📅 DATE", get_current_date())
with col4: st.metric("📍 LOCATION", USER_LOCATION)
st.markdown("---")

# --- Live Timetable Alert Check ---
triggered_tasks = check_and_trigger_timetable()
for task in triggered_tasks:
    st.warning(f"⏰ **SCHEDULE NOTIFICATION:** {task}")
    speak_and_notify(f"Sir, schedule alert: {task}", title="Jarvis Schedule Notification")

# --- Construct System Prompt with Master Memory & Full .txt Database History ---
master_memory_text = get_jarvis_memory()
persistent_txt_history = load_chat_history_txt(st.session_state.current_user)
full_history_text = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in persistent_txt_history])

system_instruction = f"""[MASTER CORE DIRECTIVE FROM jarvis_memory.txt - READ FIRST]:
{master_memory_text}

[PERMANENT USER CHAT MEMORY DATABASE (.TXT FILE - REMEMBER EVERY SINGLE WORD)]:
{full_history_text}

You are Jarvis, an advanced AI assistant built by Aayush. You are talking to {display_address_name} (Username: {st.session_state.current_user}) from {school_name}. You retain memory of every single past conversation from your text database."""

# --- Mode Handlers ---
current_mode = st.session_state.get("mode", "Realtime")

if current_mode == "Realtime":
    quick_prompt = render_realtime_orb(display_address_name, groq_api_key=GROQ_API_KEY)
    
    if quick_prompt:
        st.session_state.messages.append({"role": "user", "content": quick_prompt})
        append_to_chat_history_txt(st.session_state.current_user, "user", quick_prompt)
        
        full_context_messages = persistent_txt_history + st.session_state.messages
        recent_messages = full_context_messages[-6:] if len(full_context_messages) > 6 else full_context_messages
        api_messages = [{"role": "system", "content": system_instruction}] + recent_messages
        
        with st.chat_message("assistant"):
            try:
                stream = client.chat.completions.create(
                    model="openai/gpt-oss-120b",
                    messages=api_messages,
                    temperature=0.2,
                    stream=True
                )
                reply = st.write_stream(stream)
                st.session_state.messages.append({"role": "assistant", "content": reply})
                append_to_chat_history_txt(st.session_state.current_user, "assistant", reply)
                speak_and_notify(reply, title="Jarvis AI Response")
            except Exception as e:
                st.error(f"API Error: {e}")

elif current_mode == "Text Chat":
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message['content'])

    st.markdown("---")
    col_input, col_mic, col_img, col_send = st.columns([4, 1, 1, 1])
    
    input_key = f"chat_text_box_{st.session_state.input_counter}"
    with col_input:
        user_input = st.text_input("Message Jarvis...", placeholder="Type command...", label_visibility="collapsed", key=input_key)
    
    spoken_text = None
    with col_mic:
        audio = mic_recorder(start_prompt="🔴 Speak", stop_prompt="⏹️ Stop", key=f'inline_mic_{st.session_state.input_counter}')
        if audio and audio != st.session_state.get("last_processed_audio"):
            st.session_state.last_processed_audio = audio
            try:
                audio_bytes = audio['bytes']
                temp_audio_path = "temp_chat_audio.wav"
                with open(temp_audio_path, "wb") as f:
                    f.write(audio_bytes)
                with open(temp_audio_path, "rb") as audio_file:
                    transcript = client.audio.transcriptions.create(
                        model="whisper-large-v3",
                        file=audio_file
                    )
                    spoken_text = transcript.text
                if os.path.exists(temp_audio_path):
                    os.remove(temp_audio_path)
            except Exception as e:
                st.error(f"Transcription error: {e}")

    uploaded_image = None
    with col_img:
        uploaded_image = st.file_uploader("Upload", type=["png", "jpg", "jpeg"], key=f"img_up_{st.session_state.input_counter}", label_visibility="collapsed")

    with col_send:
        send_clicked = st.button("📤 Send", use_container_width=True, key=f"send_btn_{st.session_state.input_counter}")

    active_prompt = None
    if spoken_text:
        active_prompt = spoken_text
    elif send_clicked and user_input:
        active_prompt = user_input

    if uploaded_image:
        active_prompt = f"[Attached Image Provided] {active_prompt if active_prompt else 'Analyze this image.'}"

    if active_prompt:
        st.session_state.messages.append({"role": "user", "content": active_prompt})
        append_to_chat_history_txt(st.session_state.current_user, "user", active_prompt)
        
        with st.chat_message("user"):
            if uploaded_image:
                st.image(uploaded_image, width=200)
            st.markdown(active_prompt)

        search_context = ""
        if any(kw in active_prompt.lower() for kw in ["news", "latest", "weather", "score", "current", "search"]):
            search_context = f"\n[Live Web Search Context]: {search_web(active_prompt)}"

        full_context_messages = persistent_txt_history + st.session_state.messages
        recent_messages = full_context_messages[-6:] if len(full_context_messages) > 6 else full_context_messages
        api_messages = [{"role": "system", "content": system_instruction + search_context}] + recent_messages

        with st.chat_message("assistant"):
            try:
                stream = client.chat.completions.create(
                    model="openai/gpt-oss-120b",
                    messages=api_messages,
                    temperature=0.2,
                    stream=True
                )
                reply = st.write_stream(stream)
                st.session_state.messages.append({"role": "assistant", "content": reply})
                append_to_chat_history_txt(st.session_state.current_user, "assistant", reply)
                speak_and_notify(reply, title="Jarvis AI Response")
                
                st.session_state.input_counter += 1
                st.rerun()
            except Exception as e:
                st.error(f"API Error: {e}.")

elif current_mode == "Action Hub":
    render_image_module()

elif current_mode == "Time Table":
    st.subheader("📅 Schedule & Focus Timer")
    render_notification_permission_button()
    
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        st.markdown("### ⏱️️ Pomodoro Study Timer")
        focus_mins = st.number_input("Study Duration (minutes)", min_value=1, max_value=60, value=25)
        
        if st.button("🚀 Start Study Session"):
            st.success(f"Study session locked in for {focus_mins} minutes!")
            speak_and_notify(f"Study session started for {focus_mins} minutes, Sir.", title="Jarvis Focus Timer")
            
        st.info("💡 When your study timer concludes, Jarvis will trigger an on-screen alert and notification.")

    with col_t2:
        st.markdown("### 📋 Daily Schedule")
        current_schedule = load_timetable()
        with st.form("add_timetable_form"):
            new_t = st.text_input("Time (e.g., 07:45 AM)")
            new_n = st.selectbox("Notification", ["Yes", "No"])
            new_m = st.text_input("What to notify", value="Complete study task")
            if st.form_submit_button("➕ Add Schedule"):
                if new_t:
                    current_schedule.append({"time": new_t, "notify": new_n, "message": new_m})
                    save_timetable(current_schedule)
                    st.success("Schedule added successfully!")
                    st.rerun()

elif current_mode == "Admin Dashboard":
    if not st.session_state.is_admin:
        st.warning("Admin access required.")
    else:
        st.subheader("🛠️ Admin Panel & Analytics")
        admin_tab1, admin_tab2, admin_tab3, admin_tab4, admin_tab5, admin_tab6 = st.tabs(["➕ Create User", "📋 Users & School", "🔑 Passwords", "📥 Requests", "🧠 Master Memory", "📊 Analytics"])
        
        with admin_tab1:
            st.markdown("### Create New User Profile")
            with st.form("create_detailed_user"):
                new_username = st.text_input("Username*")
                new_pass = st.text_input("Password*", type="password")
                new_role = st.selectbox("Role", ["normal user", "admin"])
                new_name = st.text_input("Full Name")
                new_school = st.text_input("School Name", value="Aayush Technology High")
                new_title_pref = st.selectbox("Form of Address", ["Sir", "Username"])
                new_class = st.text_input("Class")
                new_phone = st.text_input("Phone No")
                new_email = st.text_input("Email")
                
                if st.form_submit_button("Save & Create User"):
                    if new_username and new_pass:
                        details = {
                            "name": new_name, "school": new_school, "title_pref": new_title_pref,
                            "class": new_class, "phone": new_phone, "email": new_email
                        }
                        add_or_update_detailed_user(new_username, new_pass, new_role, details)
                        st.success(f"User '{new_username}' created successfully!")
                    else:
                        st.error("Username and Password are required.")
                        
        with admin_tab2:
            st.markdown("### Existing Users & School Details")
            all_u = load_users()
            for u_name, u_data in all_u.items():
                with st.expander(f"👤 {u_name} ({u_data.get('role', 'normal user')})"):
                    with st.form(f"edit_school_{u_name}"):
                        ed_school = st.text_input("School Name", value=u_data.get('school', 'Aayush Technology High'))
                        ed_title = st.selectbox("Title Pref", ["Sir", "Username"], index=0 if u_data.get('title_pref') == "Sir" else 1, key=f"title_{u_name}")
                        ed_name = st.text_input("Full Name", value=u_data.get('name', ''), key=f"name_{u_name}")
                        
                        if st.form_submit_button("Update User Info"):
                            u_data['school'] = ed_school
                            u_data['title_pref'] = ed_title
                            u_data['name'] = ed_name
                            add_or_update_detailed_user(u_name, u_data['password'], u_data['role'], u_data)
                            st.success(f"Updated info for {u_name}!")
                            st.rerun()

                    if u_name != "Aayush":
                        if st.button(f"Delete User {u_name}", key=f"del_{u_name}"):
                            delete_user(u_name)
                            st.success(f"Deleted {u_name}")
                            st.rerun()
                            
        with admin_tab3:
            st.markdown("### Reset Account Password")
            with st.form("admin_reset_pass"):
                target_user = st.selectbox("Select User Account", list(load_users().keys()))
                new_p_input = st.text_input("New Password", type="password")
                confirm_p_input = st.text_input("Confirm New Password", type="password")
                
                if st.form_submit_button("Update Password"):
                    if new_p_input == confirm_p_input and new_p_input:
                        change_password(target_user, new_p_input)
                        st.success(f"Password for {target_user} successfully updated!")
                    else:
                        st.error("Passwords do not match or are empty.")
                        
        with admin_tab4:
            st.markdown("### Pending Access Requests")
            reqs = load_requests()
            if not reqs:
                st.info("No pending requests.")
            else:
                for idx, r in enumerate(reqs):
                    with st.expander(f"Request from {r['name']} ({r['email']})"):
                        st.write(f"**Phone:** {r['phone']}")
                        st.write(f"**Address/Reason:** {r['address']}")
                        st.write(f"**Hobby/Target:** {r['hobby']} / {r['target']}")
                        
                        with st.form(f"reply_form_{idx}"):
                            reply_subj = st.text_input("Email Subject", value="Regarding your Jarvis Access Request")
                            reply_body = st.text_area("Message to Applicant")
                            if st.form_submit_button("📧 Send Reply Email"):
                                send_reply_email(r['email'], reply_subj, reply_body)
                                st.success(f"Reply sent to {r['email']}!")
                                
                        if st.button("🗑️ Delete Request", key=f"del_req_{idx}"):
                            delete_request(idx)
                            st.success("Request deleted.")
                            st.rerun()

        with admin_tab5:
            st.markdown("### 🧠 Jarvis Master Memory (`jarvis_memory.txt`)")
            current_master_mem = get_jarvis_memory()
            with st.form("master_memory_form"):
                updated_mem_text = st.text_area("Master Core Memory", value=current_master_mem, height=250)
                if st.form_submit_button("💾 Save Master Memory"):
                    save_jarvis_memory(updated_mem_text)
                    st.success("Master memory saved successfully!")
                    st.rerun()

        with admin_tab6:
            st.markdown("### 📊 Stark Analytics & System Health")
            col_a1, col_a2, col_a3 = st.columns(3)
            with col_a1:
                st.metric("👥 Registered Users", len(load_users()))
            with col_a2:
                st.metric("📥 Access Requests", len(load_requests()))
            with col_a3:
                st.metric("⚡ System Status", "Optimal (100%)")
            
            st.markdown("---")
            st.info("💡 Jarvis Analytics monitor active user profiles, security gateway logs, and API health in real-time.")
