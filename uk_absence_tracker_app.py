import streamlit as st
import pandas as pd
import json
import gspread
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
import streamlit.components.v1 as components
import time

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

st.set_page_config(page_title="UK Absence Tracker", layout="wide")
st.title("UK Absence Tracker")

# === Load Trip Data ===
refresh = st.sidebar.checkbox("🔄 Auto-refresh every 60 seconds")
st.sidebar.header("📤 Upload Your Trip Data")
uploaded_file = st.sidebar.file_uploader("Upload CSV", type="csv")
use_google_sheet = st.sidebar.checkbox("Load from Google Sheet", value=True)

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

# === Process Data ===
df = df.sort_values("Departure").reset_index(drop=True)
df['Length'] = (df['Return'] - df['Departure']).dt.days - 1
allowance = 180
balances = []

for i, row in df.iterrows():
    allowance -= row['Length']
    balances.append(allowance)
df['Allowance'] = balances

# === Build Daily Allowance Tracker (Past + Future) ===
end_future = datetime.today() + timedelta(days=365)
all_dates = pd.date_range(df['Departure'].min(), end_future)
daily_events = []
used_ranges = [pd.date_range(row.Departure + timedelta(days=1), row.Return - timedelta(days=1)) for row in df.itertuples()]
flat_abroad = pd.concat([pd.Series(x) for x in used_ranges], ignore_index=True)

for day in all_dates:
    days_abroad = (flat_abroad <= day).sum()
    remaining = max(180 - days_abroad, 0)
    daily_events.append({
        "title": f"📉 {remaining} days left",
        "start": day.strftime("%Y-%m-%d"),
        "end": day.strftime("%Y-%m-%d"),
        "allDay": True,
        "display": "background",
        "backgroundColor": "#f0f9ff"
    })

# === Main Events (Trips) ===
events = []
for i, row in df.iterrows():
    if pd.isnull(row['Departure']) or pd.isnull(row['Return']):
        continue
    events.append({
        "id": str(i),
        "title": f"{row['Departure'].date()} - {row['Return'].date()}",
        "start": row['Departure'].strftime("%Y-%m-%d"),
        "end": (row['Return'] + timedelta(days=1)).strftime("%Y-%m-%d"),
        "color": "#dc3545",
        "allDay": True,
        "extendedProps": {
            "length": f"{(row['Return'] - row['Departure']).days} days",
            "type": "Abroad",
            "allowance": row['Allowance']
        }
    })

# === Styled Table Helper ===
def styled_table(df_subset):
    return df_subset.style \
        .format({
            'Departure': lambda x: x.strftime('%Y-%m-%d'),
            'Return': lambda x: x.strftime('%Y-%m-%d'),
            'Length': '{:.0f}'.format,
            'Allowance': '{:.0f}'.format,
            'Restored': '{:.0f}'.format,
            'New Balance': '{:.0f}'.format,
            'Date': lambda x: x.strftime('%Y-%m-%d') if isinstance(x, pd.Timestamp) else x
        }) \
        .set_table_styles([
            {'selector': 'thead th', 'props': [('background-color', '#0f4c81'), ('color', 'white'), ('text-align', 'center')]},
            {'selector': 'tbody td', 'props': [('text-align', 'center')]},
            {'selector': 'tr:nth-child(even)', 'props': [('background-color', '#f2f2f2')]},
            {'selector': 'tr:nth-child(odd)', 'props': [('background-color', '#ffffff')]}
        ]) \
        .set_properties(**{'border': '1px solid #ccc', 'border-radius': '6px', 'padding': '6px'})

# === Show Tables ===
st.subheader("📋 Trip History")
st.dataframe(styled_table(df[['Departure', 'Return', 'Length', 'Allowance']]), use_container_width=True)

# === Restoration Dates ===
restoration = []
current_balance = df['Allowance'].iloc[-1]
for row in df.itertuples():
    date = row.Return + timedelta(days=365)
    current_balance += row.Length
    restoration.append({
        "Date": date,
        "Restored": row.Length,
        "New Balance": current_balance
    })
restoration_df = pd.DataFrame(restoration).sort_values(by='Date').head(10)

st.subheader("📈 Next 10 Balance Increase Dates")
st.dataframe(styled_table(restoration_df[['Date', 'Restored', 'New Balance']]), use_container_width=True)

# === FullCalendar Embed ===
st.subheader("📅 Calendar with Daily Allowance")
fullcalendar_html = f"""
<!DOCTYPE html>
<html>
<head>
  <link href='https://cdn.jsdelivr.net/npm/fullcalendar@6.1.8/index.global.min.css' rel='stylesheet' />
  <script src='https://cdn.jsdelivr.net/npm/fullcalendar@6.1.8/index.global.min.js'></script>
  <style>
    #calendar {{ max-width: 1000px; margin: 20px auto; }}
    .fc-daygrid-day-number {{ font-size: 1.5em; }}
    .day-allowance {{ font-size: 0.8em; text-align: center; display: block; margin-top: 20px; color: #333; }}
    .fc-event-title {{ font-weight: bold; }}
  </style>
  <script>
    document.addEventListener('DOMContentLoaded', function() {{
      var calendarEl = document.getElementById('calendar');
      var calendar = new FullCalendar.Calendar(calendarEl, {{
        initialView: 'dayGridMonth',
        headerToolbar: {{
          left: 'prev,next today',
          center: 'title',
          right: 'multiMonthYear,dayGridMonth,timeGridWeek,timeGridDay'
        }},
        views: {{
          multiMonthYear: {{ type: 'multiMonth', duration: {{ months: 12 }}, buttonText: 'Yearly' }}
        }},
        events: {json.dumps(events + daily_events)},
        eventContent: function(arg) {{
          let container = document.createElement('div');
          container.innerHTML = arg.event.title;
          return {{ domNodes: [container] }};
        }},
        eventMouseEnter: function(info) {{
          if (info.event.extendedProps) {{
            const tooltip = document.createElement('div');
            tooltip.id = 'tooltip';
            tooltip.style.position = 'absolute';
            tooltip.style.background = '#333';
            tooltip.style.color = 'white';
            tooltip.style.padding = '6px';
            tooltip.style.borderRadius = '4px';
            tooltip.style.zIndex = 10001;
            tooltip.innerHTML = `<b>${{info.event.title}}</b><br>Type: ${{info.event.extendedProps.type}}<br>Duration: ${{info.event.extendedProps.length}}<br>Allowance: ${{info.event.extendedProps.allowance}} days`;
            document.body.appendChild(tooltip);
            info.el.onmousemove = function(e) {{
              tooltip.style.left = e.pageX + 10 + 'px';
              tooltip.style.top = e.pageY + 10 + 'px';
            }};
          }}
        }},
        eventMouseLeave: function(info) {{
          const tooltip = document.getElementById('tooltip');
          if (tooltip) tooltip.remove();
        }}
      }});
      calendar.render();
    }});
  </script>
</head>
<body>
  <div id='calendar'></div>
</body>
</html>
"""
components.html(fullcalendar_html, height=950, scrolling=True)

# === Auto-Refresh ===
if refresh:
    time.sleep(60)
    st.experimental_rerun()
