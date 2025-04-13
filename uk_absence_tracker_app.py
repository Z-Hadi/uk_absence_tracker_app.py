import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import plotly.express as px
from datetime import datetime, timedelta
from io import StringIO
import json
import os

# === Optional Google Sheets Setup ===
import gspread
from google.oauth2.service_account import Credentials

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

# === Upload or Use Example Data ===
st.sidebar.header("📤 Upload Your Trip Data")
example_csv = """Departure,Return
21/04/2024,25/04/2024
30/05/2024,05/06/2024
16/06/2024,20/06/2024
04/08/2024,07/08/2024
04/10/2024,20/10/2024
30/10/2024,08/11/2024
11/11/2024,17/12/2024
10/01/2025,15/01/2025
02/02/2025,27/02/2025
14/04/2025,20/04/2025
"""

uploaded_file = st.sidebar.file_uploader("Upload CSV with Departure and Return dates", type="csv")
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
            if not data:
                raise ValueError("Sheet is empty or headers are missing.")
            df = pd.DataFrame(data)
            if "Departure" not in df.columns or "Return" not in df.columns:
                raise ValueError("Sheet must contain 'Departure' and 'Return' columns.")
            df['Departure'] = pd.to_datetime(df['Departure'], dayfirst=True)
            df['Return'] = pd.to_datetime(df['Return'], dayfirst=True)
            st.sidebar.success("✅ Loaded data from Google Sheet")
        except Exception as e:
            st.sidebar.error(f"❌ Failed to load from Google Sheet: {e}")
            df = pd.read_csv(StringIO(example_csv), parse_dates=["Departure", "Return"], dayfirst=True)
    else:
        st.sidebar.error("❌ No Google credentials found in Streamlit secrets")
        df = pd.read_csv(StringIO(example_csv), parse_dates=["Departure", "Return"], dayfirst=True)
else:
    st.sidebar.info("Using example data. Upload a file to override.")
    df = pd.read_csv(StringIO(example_csv), parse_dates=["Departure", "Return"], dayfirst=True)

# === What-if Simulation ===
st.sidebar.subheader("🕵️ Add a Planned Trip")
with st.sidebar.form("what_if_form"):
    new_departure = st.date_input("Planned Departure")
    new_return = st.date_input("Planned Return")
    add_trip = st.form_submit_button("Add Trip")

if add_trip and new_departure < new_return:
    new_row = pd.DataFrame({"Departure": [new_departure], "Return": [new_return]})
    df = pd.concat([df, new_row], ignore_index=True)

# === Calculations ===
df = df.sort_values(by='Departure').reset_index(drop=True)
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

# === Calendar Visualization ===
st.subheader("📆 Calendar of Absences")
days_outside = []
for row in df.itertuples():
    days_outside.extend(pd.date_range(row.Departure + timedelta(days=1), row.Return - timedelta(days=1)))
days_df = pd.DataFrame(days_outside, columns=["Date"])
days_df["Status"] = "Abroad"

fig = px.timeline(days_df, x_start="Date", x_end="Date", y="Status", color="Status")
fig.update_layout(showlegend=False, xaxis_title="", yaxis_title="")
fig.update_yaxes(visible=False)
st.plotly_chart(fig, use_container_width=True)

# === Graph ===
st.subheader("📈 Absence Allowance Over Time")
fig2, ax = plt.subplots(figsize=(10, 4))
trip_dates = df['Return']
trip_allowance = df['Allowance']
ax.plot(trip_dates, trip_allowance, marker='o', label="Allowance After Trip", color='blue')

restore_dates = pd.to_datetime(restoration_df['Date'])
restore_balances = restoration_df['New Balance']
ax.plot(restore_dates, restore_balances, marker='s', label="Restored Balance", color='green')

for x, y in zip(trip_dates, trip_allowance):
    ax.text(x, y-5, str(y), ha='center', fontsize=8)
for x, y in zip(restore_dates, restore_balances):
    ax.text(x, y+2, str(y), ha='center', fontsize=8)

ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
plt.xticks(rotation=45)
plt.ylabel("Days Remaining")
plt.grid(True)
plt.legend()
st.pyplot(fig2)

# === Summary Statistics ===
st.subheader("📊 Summary Statistics")
total_days_abroad = df['Length'].sum()
avg_trip_length = df['Length'].mean()
busiest_months = df['Departure'].dt.month.value_counts().sort_index().rename(index=lambda x: datetime(1900, x, 1).strftime('%B'))

col1, col2 = st.columns(2)
col1.metric("Total Days Abroad", total_days_abroad)
col2.metric("Average Trip Length", f"{avg_trip_length:.1f} days")

st.bar_chart(busiest_months)

# === Tables ===
st.subheader("📋 Trip History Table")
st.dataframe(df[['Departure', 'Return', 'Length', 'Allowance']])

st.subheader("📈 Next 10 Balance Increase Dates")
st.dataframe(restoration_df[['Date', 'Restored', 'New Balance', 'Reason']])
