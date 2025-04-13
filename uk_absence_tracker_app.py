import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import plotly.express as px
from datetime import datetime, timedelta
from io import StringIO
import json
import os

# === Load Google Credentials from Streamlit Secrets if available ===
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
if uploaded_file:
    df = pd.read_csv(uploaded_file, parse_dates=["Departure", "Return"], dayfirst=True)
else:
    st.sidebar.info("Using example data. Upload a file to override.")
    df = pd.read_csv(StringIO(example_csv), parse_dates=["Departure", "Return"], dayfirst=True)

# === What-if Simulation ===
st.sidebar.subheader("🕵️ Add a Planned Trip")
with st.sidebar.form("what_if_form"):
    new_departure = st.date_input("Planned
