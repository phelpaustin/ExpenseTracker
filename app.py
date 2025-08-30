import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

# ----------------- CONFIG -----------------
USE_GOOGLE_SHEETS = True
SHEET_NAME = "ExpenseTracker"
WORKSHEET_NAME = "Transactions"
CREDENTIALS_FILE = "credentials.json"
LOCAL_CSV_FILE = "expenses_local.csv"

# ----------------- STORAGE SETUP -----------------
if USE_GOOGLE_SHEETS:
    try:
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials

        @st.cache_resource
        def init_gspread():
            scope = ["https://spreadsheets.google.com/feeds",
                     "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                CREDENTIALS_FILE, scope)
            client = gspread.authorize(creds)
            return client

        client = init_gspread()
        try:
            sheet = client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            sh = client.open(SHEET_NAME)
            sheet = sh.add_worksheet(title=WORKSHEET_NAME, rows="1000", cols="10")
            sheet.append_row(["Date","Category","Item","Shop","PricePaid","Quantity","QuantityUnit","User"])

        def load_data():
            records = sheet.get_all_records()
            if not records:
                return pd.DataFrame(columns=["Date","Category","Item","Shop","PricePaid","Quantity","QuantityUnit","User"])
            return pd.DataFrame(records)

        def save_data(df):
            sheet.clear()
            sheet.append_row(df.columns.tolist())
            sheet.append_rows(df.astype(str).values.tolist())

    except Exception as e:
        st.warning(f"Google Sheets not available ({e}). Using local CSV fallback.")
        USE_GOOGLE_SHEETS = False

if not USE_GOOGLE_SHEETS:
    def load_data():
        try:
            return pd.read_csv(LOCAL_CSV_FILE, parse_dates=["Date"])
        except FileNotFoundError:
            return pd.DataFrame(columns=["Date","Category","Item","Shop","PricePaid","Quantity","QuantityUnit","User"])

    def save_data(df):
        df.to_csv(LOCAL_CSV_FILE, index=False)

# ----------------- SESSION STATE -----------------
if "history" not in st.session_state:
    st.session_state.history = []
if "redo_stack" not in st.session_state:
    st.session_state.redo_stack = []

def save_state():
    st.session_state.history.append(st.session_state.df.copy())
    st.session_state.redo_stack.clear()

def undo():
    if st.session_state.history:
        st.session_state.redo_stack.append(st.session_state.df.copy())
        st.session_state.df = st.session_state.history.pop()

def redo():
    if st.session_state.redo_stack:
        st.session_state.history.append(st.session_state.df.copy())
        st.session_state.df = st.session_state.redo_stack.pop()

# ----------------- USER LOGIN -----------------
st.sidebar.header("👤 User Login")
username = st.sidebar.text_input("Enter your name", value="User1").strip()
if username == "":
    st.warning("Please enter your username to continue.")
    st.stop()

# ----------------- LOAD DATA -----------------
df = load_data()
if "User" not in df.columns:
    df["User"] = "User1"

# Filter only current user's data
user_df = df[df["User"] == username].copy()
st.session_state.df = user_df

# ----------------- ADD NEW EXPENSE -----------------
st.sidebar.header(f"➕ Add Expense ({username})")
date = st.sidebar.date_input("Date", datetime.today())
categories = user_df["Category"].unique().tolist()
category = st.sidebar.text_input("Category (new or existing)")
if category == "" and categories:
    category = st.sidebar.selectbox("Or select existing Category", categories)

item = st.sidebar.text_input("Item")
shop = st.sidebar.text_input("Shop")

# Units
units = user_df["QuantityUnit"].unique().tolist()
default_units = ["Kg", "Liter", "Count"]
all_units = sorted(set(default_units + units))
unit = st.sidebar.selectbox("Quantity Unit", all_units)
new_unit = st.sidebar.text_input("Or add new Unit")
if new_unit:
    unit = new_unit

# Quantity input with precision
if unit.lower() in ["kg", "liter"]:
    quantity = st.sidebar.number_input("Quantity", min_value=0.0, format="%.3f")
else:
    quantity = st.sidebar.number_input("Quantity", min_value=0, step=1, format="%d")

# Price Paid
price = st.sidebar.number_input("Price Paid", min_value=0.0, format="%.2f")

if st.sidebar.button("Add Expense"):
    new_row = {
        "Date": pd.to_datetime(date).strftime("%Y-%m-%d"),
        "Category": category if category else "Uncategorized",
        "Item": item,
        "Shop": shop,
        "PricePaid": price,
        "Quantity": quantity,
        "QuantityUnit": unit,
        "User": username
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_data(df)
    st.success(f"Expense Added for {username} ✅")

# ----------------- UNDO / REDO -----------------
col1, col2 = st.columns(2)
with col1:
    if st.button("↩️ Undo"):
        undo()
with col2:
    if st.button("↪️ Redo"):
        redo()

# ----------------- EDITABLE TABLE -----------------
st.subheader(f"📋 Transactions Table ({username})")
if not user_df.empty:
    edited_user_df = st.data_editor(user_df, num_rows="dynamic", use_container_width=True)
    if st.button("💾 Save Changes"):
        # Merge edited user data back into full sheet
        df = df[df["User"] != username]
        df = pd.concat([df, edited_user_df], ignore_index=True)
        save_data(df)
        st.success("Saved successfully ✅")
        user_df = edited_user_df

# ----------------- YEAR / MONTH SUMMARY -----------------
st.subheader("📅 Expenses by Year → Month")
if not user_df.empty:
    user_df["Date"] = pd.to_datetime(user_df["Date"])
    user_df["Year"] = user_df["Date"].dt.year
    user_df["Month"] = user_df["Date"].dt.strftime("%B")
    user_df["MonthNum"] = user_df["Date"].dt.month

    for year, year_df in user_df.groupby("Year"):
        with st.expander(f"📆 {year}", expanded=False):
            total_year = year_df["PricePaid"].sum()
            st.markdown(f"### 🏆 Total Spent in {year}: `${total_year:,.2f}`")

            year_cat_pie = px.pie(year_df, names="Category", values="PricePaid", title=f"Category Split - {year}")
            st.plotly_chart(year_cat_pie, use_container_width=True)

            year_item_bar = px.bar(
                year_df.groupby("Item")["PricePaid"].sum().reset_index(),
                x="Item", y="PricePaid", title=f"Item Breakdown - {year}"
            )
            st.plotly_chart(year_item_bar, use_container_width=True)

            # Monthly Breakdown
            for month, month_df in year_df.groupby(["MonthNum", "Month"]):
                month_num, month_name = month
                with st.expander(f"🗓️ {month_name} {year}", expanded=False):
                    total_month = month_df["PricePaid"].sum()
                    st.markdown(f"**Total Spent in {month_name} {year}:** `${total_month:,.2f}`")

                    cat_pie = px.pie(month_df, names="Category", values="PricePaid",
                                     title=f"Category Split - {month_name} {year}")
                    st.plotly_chart(cat_pie, use_container_width=True)

                    item_bar = px.bar(
                        month_df.groupby("Item")["PricePaid"].sum().reset_index(),
                        x="Item", y="PricePaid",
                        title=f"Item Breakdown - {month_name} {year}"
                    )
                    st.plotly_chart(item_bar, use_container_width=True)

                    with st.expander("📋 Show Transactions"):
                        st.dataframe(month_df.drop(columns=["Year", "Month", "MonthNum"]))

# ----------------- MULTI-YEAR PRICE TREND -----------------
st.subheader("📈 Multi-Year Price Trend per Item")
if not user_df.empty:
    user_df["PricePaid"] = user_df["PricePaid"].astype(float)
    user_df["Quantity"] = user_df["Quantity"].replace(0, 1).astype(float)
    user_df["PricePerUnit"] = user_df["PricePaid"] / user_df["Quantity"]
    item_options = user_df["Item"].unique().tolist()
    selected_item = st.selectbox("🔎 Select an Item to view trend:", item_options)

    if selected_item:
        item_df = user_df[user_df["Item"] == selected_item].copy()
        item_df["YearMonth"] = item_df["Date"].dt.to_period("M").astype(str)
        trend_df = item_df.groupby("YearMonth")["PricePerUnit"].mean().reset_index()

        trend_line = px.line(trend_df, x="YearMonth", y="PricePerUnit",
                             title=f"📊 Price Trend for {selected_item}", markers=True)
        trend_line.update_layout(xaxis_title="Year-Month", yaxis_title="Avg Price per Unit")
        st.plotly_chart(trend_line, use_container_width=True)
