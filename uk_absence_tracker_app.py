import streamlit as st
import pandas as pd
import json
import gspread
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
import streamlit.components.v1 as components

# === Google Sheets Credentials ===
def get_google_credentials():
    if "google_credentials" in st.secrets:
        creds_json = st.secrets["google_credentials"]
        creds_dict = json.loads(creds_json)
        scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        return Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return None

GOOGLE_SHEET_NAME = "UK Absence Tracker"
WORKSHEET_NAME = "Trips"

# === Page Setup ===
st.set_page_config(page_title="UK Absence Tracker", layout="wide")
st.title("🇬🇧 UK Absence Tracker (180-day Rule)")

# === Load Trip Data ===
st.sidebar.header("📤 Upload Your Trip Data")
uploaded_file = st.sidebar.file_uploader("Upload CSV", type="csv")
use_google_sheet = st.sidebar.checkbox("Load from Google Sheet", value=False)

if uploaded_file:
    df = pd.read_csv(uploaded_file, parse_dates=["Departure", "Return"], dayfirst=True)
elif use_google_sheet:
    credentials = get_google_credentials()
    if credentials:
        try:
            client = gspread.authorize(credentials)
            sheet = client.open(GOOGLE_SHEET_NAME).worksheet(WORKSHEET_NAME)
            data = sheet.get_all_records()
            df = pd.DataFrame(data)
            df['Departure'] = pd.to_datetime(df['Departure'], dayfirst=True)
            df['Return'] = pd.to_datetime(df['Return'], dayfirst=True)
            st.sidebar.success("✅ Loaded from Google Sheet")
        except Exception as e:
            st.sidebar.error(f"❌ Failed to load: {e}")
            st.stop()
    else:
        st.sidebar.error("❌ No credentials found")
        st.stop()
else:
    st.sidebar.warning("Please upload a CSV or connect to Google Sheets.")
    st.stop()

# === What-if Simulation ===
st.sidebar.subheader("🕵️ Add a Planned Trip")
with st.sidebar.form("what_if_form"):
    new_departure = st.date_input("Planned Departure")
    new_return = st.date_input("Planned Return")
    add_trip = st.form_submit_button("Add Trip")

if add_trip and new_departure < new_return:
    df = pd.concat([df, pd.DataFrame({"Departure": [new_departure], "Return": [new_return], "Planned": [True]})], ignore_index=True)
else:
    if "Planned" not in df:
        df["Planned"] = False

# === Calculations ===
df = df.sort_values("Departure").reset_index(drop=True)
df['Length'] = (df['Return'] - df['Departure']).dt.days - 1

allowance = 180
balances = []
for i, row in df.iterrows():
    allowance -= row['Length']
    balances.append(allowance)
df['Allowance'] = balances

# === Restoration Dates ===
restoration = []
current_balance = df['Allowance'].iloc[-1]
for row in df.itertuples():
    date = row.Return + timedelta(days=365)
    current_balance += row.Length
    restoration.append({
        "Date": date,
        "Restored": row.Length,
        "New Balance": current_balance,
        "Reason": f"{row.Departure.date()} – {row.Return.date()}"
    })
restoration_df = pd.DataFrame(restoration).sort_values(by='Date').head(10)

# === Show Tables First ===
st.subheader("📋 Trip History")
st.dataframe(df[['Departure', 'Return', 'Length', 'Planned', 'Allowance']])

st.subheader("📈 Next 10 Balance Increase Dates")
st.dataframe(restoration_df[['Date', 'Restored', 'New Balance', 'Reason']])

# === Calendar Filter ===
st.sidebar.subheader("📊 Calendar Filters")
show_real = st.sidebar.checkbox("Show Real Trips", value=True)
show_planned = st.sidebar.checkbox("Show Planned Trips", value=True)

# === Generate Calendar Events ===
events = []
for i, row in df.iterrows():
    if pd.isnull(row['Departure']) or pd.isnull(row['Return']):
        continue
    planned = row.get("Planned", False)
    if planned and not show_planned:
        continue
    if not planned and not show_real:
        continue
    title = f"Trip {i+1}: {row['Departure'].date()} to {row['Return'].date()}"
    color = "#fd7e14" if planned else "#dc3545"
    events.append({
        "id": str(i),
        "title": title,
        "start": row['Departure'].strftime("%Y-%m-%d"),
        "end": (row['Return'] + timedelta(days=1)).strftime("%Y-%m-%d"),
        "color": color,
        "allDay": True,
        "extendedProps": {
            "length": f"{(row['Return'] - row['Departure']).days} days",
            "type": "Planned" if planned else "Abroad"
        }
    })

# === FullCalendar with Popup, Edit/Delete, Animations ===
st.subheader("📅 Interactive Calendar")
fullcalendar_html = f"""
<!DOCTYPE html>
<html>
<head>
  <link href='https://cdn.jsdelivr.net/npm/fullcalendar@6.1.8/index.global.min.css' rel='stylesheet' />
  <script src='https://cdn.jsdelivr.net/npm/fullcalendar@6.1.8/index.global.min.js'></script>
  <style>
    #calendar {{ max-width: 1000px; margin: 20px auto; }}
    #popup {{
      display: none;
      position: fixed;
      top: 20%;
      left: 50%;
      transform: translate(-50%, -50%);
      background: #fff;
      padding: 20px;
      border-radius: 8px;
      box-shadow: 0 5px 15px rgba(0, 0, 0, 0.3);
      z-index: 1000;
      animation: fadeIn 0.4s ease-in-out;
    }}
    #popup-close {{ cursor: pointer; float: right; font-weight: bold; color: red; }}
    @keyframes fadeIn {{ from {{opacity: 0;}} to {{opacity: 1;}} }}
    button {{ margin-top: 10px; margin-right: 5px; }}
  </style>
  <script>
    document.addEventListener('DOMContentLoaded', function() {{
      var calendarEl = document.getElementById('calendar');
      var popup = document.getElementById('popup');
      var popupContent = document.getElementById('popup-content');
      var calendar = new FullCalendar.Calendar(calendarEl, {{
        initialView: 'dayGridMonth',
        headerToolbar: {{
          left: 'prev,next today',
          center: 'title',
          right: 'dayGridYear,dayGridMonth,timeGridWeek,timeGridDay'
        }},
        views: {{
          dayGridYear: {{ type: 'dayGrid', duration: {{ months: 12 }} }}
        }},
        events: {json.dumps(events)},
        eventClick: function(info) {{
          var details = `<b>` + info.event.title + `</b><br>` +
                        `Type: ` + info.event.extendedProps.type + `<br>` +
                        `Duration: ` + info.event.extendedProps.length + `<br><br>` +
                        `<button onclick='alert("Edit feature coming soon!")'>✏️ Edit</button>` +
                        `<button onclick='alert("Delete feature coming soon!")'>❌ Delete</button>`;
          popupContent.innerHTML = details;
          popup.style.display = 'block';
        }}
      }});
      calendar.render();
      document.getElementById('popup-close').onclick = function() {{ popup.style.display = 'none'; }};
    }});
  </script>
</head>
<body>
  <div id='calendar'></div>
  <div id='popup'>
    <span id='popup-close'>✖</span>
    <div id='popup-content'></div>
  </div>
</body>
</html>
"""
components.html(fullcalendar_html, height=800, scrolling=True)
