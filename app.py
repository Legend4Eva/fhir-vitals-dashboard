import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from fhirclient.models.observation import Observation
import json
import os
from datetime import datetime, timedelta

# --- Configuration ---
FHIR_SERVER_URL = "https://hapi.fhir.org/baseR4"
# A placeholder ID, will be replaced with a real one after initial search
PATIENT_ID = "3000000000000000000000000000000000000000000000000000000000000000"
VITAL_SIGNS_MAP = {
    "8480-6": {"name": "Systolic Blood Pressure", "unit": "mm[Hg]", "thresholds": {"high": 140, "low": 90}},
    "8462-4": {"name": "Diastolic Blood Pressure", "unit": "mm[Hg]", "thresholds": {"high": 90, "low": 60}},
    "8867-4": {"name": "Heart Rate", "unit": "/min", "thresholds": {"high": 100, "low": 60}},
    "8310-5": {"name": "Body Temperature", "unit": "Cel", "thresholds": {"high": 38.0, "low": 35.0}},
    "2708-6": {"name": "Oxygen Saturation", "unit": "%", "thresholds": {"high": 100, "low": 90}},
    "29463-7": {"name": "Body Weight", "unit": "kg", "thresholds": {"high": 150, "low": 30}},
    "8302-1": {"name": "Body Height", "unit": "cm", "thresholds": {"high": 200, "low": 100}},
}

# --- FHIR API Integration (Week 2) ---


@st.cache_data(ttl=3600)
def fetch_patient_ids():
    """Fetch a list of patient IDs with recent vital-signs observations from HAPI FHIR."""
    try:
        params = {
            "_count": 50,
            "date": f"gt{datetime.now().date() - timedelta(days=365)}",
            "category": "vital-signs",  # make sure these patients have vital signs
        }
        url = f"{FHIR_SERVER_URL}/Observation"
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        bundle_json = resp.json()

        patient_ids = set()
        for entry in bundle_json.get("entry", []):
            resource = entry.get("resource", {})
            subject = resource.get("subject", {})
            ref = subject.get("reference", "")
            if ref.startswith("Patient/"):
                patient_ids.add(ref.split("/")[-1])

        if patient_ids:
            st.success("Successfully fetched patient IDs from HAPI FHIR server.")
            return sorted(list(patient_ids))
        else:
            st.warning("FHIR server returned no recent patient data. Falling back to local data.")
            return ["synth-pat-1"]  # Fallback ID
    except Exception as e:
        st.error(f"Error fetching patient IDs from FHIR server: {e}. Falling back to local data.")
        return ["synth-pat-1"]  # Fallback ID


def fetch_vitals_data(patient_id):
    # Fallback for synthetic data
    if patient_id == "synth-pat-1":
        try:
            file_path = os.path.join(os.path.dirname(__file__), "synthetic_data.json")
            with open(file_path, "r") as f:
                bundle_json = json.load(f)

            observations = []
            for entry in bundle_json.get("entry", []):
                resource = entry.get("resource")
                if resource and resource.get("resourceType") == "Observation":
                    # Create an Observation object from the dict
                    obs = Observation(resource)
                    observations.append(obs)
            st.success(f"Successfully loaded {len(observations)} observations from local synthetic data.")
            return observations
        except Exception as e:
            st.error(f"Error loading local synthetic data: {e}")
            return []

    # Try to fetch from FHIR server
    try:
        # Do NOT filter by category here – some valid vitals may be missing the category tag
        params = {
            "patient": patient_id,
            "_count": 1000,
        }
        url = f"{FHIR_SERVER_URL}/Observation"
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        bundle_json = resp.json()

        observations = []
        for entry in bundle_json.get("entry", []):
            resource = entry.get("resource")
            if resource and resource.get("resourceType") == "Observation":
                observations.append(Observation(resource))
        return observations
    except Exception as e:
        st.error(f"Error fetching vitals for Patient/{patient_id} from FHIR server: {e}")
        return []


# --- Data Parser Module (Week 3) ---
def parse_and_normalize_vitals(observations):
    """Parses FHIR Observation objects into a clean DataFrame and normalizes units."""
    data = []
    for obs in observations:
        try:
            code = obs.code.coding[0].code
            if code in VITAL_SIGNS_MAP:
                vital_info = VITAL_SIGNS_MAP[code]

                # Extract value and unit
                value = None
                unit = None
                if getattr(obs, "valueQuantity", None):
                    value = obs.valueQuantity.value
                    unit = obs.valueQuantity.unit
                elif getattr(obs, "component", None):
                    # Handle components for things like Blood Pressure
                    for component in obs.component:
                        comp_code = component.code.coding[0].code
                        if comp_code == code and component.valueQuantity:
                            value = component.valueQuantity.value
                            unit = component.valueQuantity.unit
                            break

                if value is not None:
                    # Attempt to parse date
                    if getattr(obs, "effectiveDateTime", None):
                        date_time = datetime.fromisoformat(
                            obs.effectiveDateTime.isostring.replace("Z", "+00:00")
                        )
                    elif getattr(obs, "effectivePeriod", None) and obs.effectivePeriod.start:
                        date_time = datetime.fromisoformat(
                            obs.effectivePeriod.start.isostring.replace("Z", "+00:00")
                        )
                    else:
                        continue  # Skip if no effective date

                    # Simple unit normalization (assuming HAPI FHIR uses standard units,
                    # but this is where more complex conversion logic would go)

                    data.append(
                        {
                            "Date/Time": date_time,
                            "Vital Sign Code": code,
                            "Vital Sign Name": vital_info["name"],
                            "Value": float(value),
                            "Unit": unit if unit else vital_info["unit"],
                            "Thresholds": vital_info["thresholds"],
                        }
                    )
        except Exception:
            # st.warning(f"Skipping observation due to parsing error: {e}")
            continue

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)
    df = df.sort_values(by="Date/Time", ascending=False).reset_index(drop=True)
    return df


# --- Rule-based Logic (Week 4) ---
def flag_anomalies(df):
    """Applies rule-based thresholds to flag anomalies."""
    if df.empty:
        return df

    df["Anomaly Flag"] = "Normal"

    for index, row in df.iterrows():
        thresholds = row["Thresholds"]
        value = row["Value"]

        if "high" in thresholds and value > thresholds["high"]:
            df.loc[index, "Anomaly Flag"] = "High Anomaly"
        elif "low" in thresholds and value < thresholds["low"]:
            df.loc[index, "Anomaly Flag"] = "Low Anomaly"

    return df


# --- Visualization UI (Week 5) ---
def display_dashboard(df):
    """Displays the Streamlit dashboard components."""
    if df.empty:
        st.warning("No vital signs data found for the selected patient in the specified date range.")
        return

    st.subheader("Vitals Trend Analysis")

    # Dropdown: Select Observation Type
    vital_signs = df["Vital Sign Name"].unique()
    selected_vital = st.selectbox("Select Vital Sign to View", vital_signs)

    df_filtered = df[df["Vital Sign Name"] == selected_vital].copy()

    # Date Range Picker
    min_date = df_filtered["Date/Time"].min().date() if not df_filtered.empty else datetime.now().date()
    max_date = df_filtered["Date/Time"].max().date() if not df_filtered.empty else datetime.now().date()

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", min_date, min_value=min_date, max_value=max_date)
    with col2:
        end_date = st.date_input("End Date", max_date, min_value=min_date, max_value=max_date)

    # Filter by date range
    df_filtered["Date_Only"] = df_filtered["Date/Time"].dt.date
    df_filtered = df_filtered[(df_filtered["Date_Only"] >= start_date) & (df_filtered["Date_Only"] <= end_date)]

    if df_filtered.empty:
        st.info(f"No data for {selected_vital} in the selected date range.")
        return

    # Chart Area: Vitals Trend Line + Color flags for anomalies
    color_map = {"Normal": "green", "High Anomaly": "red", "Low Anomaly": "blue"}

    fig = px.line(
        df_filtered,
        x="Date/Time",
        y="Value",
        title=f"{selected_vital} Trend Over Time",
        markers=True,
        color="Anomaly Flag",
        color_discrete_map=color_map,
    )

    # Add threshold lines
    thresholds = df_filtered["Thresholds"].iloc[0]
    if "high" in thresholds:
        fig.add_hline(
            y=thresholds["high"],
            line_dash="dash",
            line_color="red",
            annotation_text=f"High: {thresholds['high']}",
        )
    if "low" in thresholds:
        fig.add_hline(
            y=thresholds["low"],
            line_dash="dash",
            line_color="blue",
            annotation_text=f"Low: {thresholds['low']}",
        )

    fig.update_layout(yaxis_title=f"Value ({df_filtered['Unit'].iloc[0]})")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Latest Readings with Threshold Indicators")

    # Table: Latest Readings with Threshold Indicators
    df_table = df_filtered[["Date/Time", "Vital Sign Name", "Value", "Unit", "Anomaly Flag"]].head(10)

    # Custom styling for the table
    def color_anomalies(val):
        if val == "High Anomaly":
            return "background-color: #ffcccc"  # Light Red
        elif val == "Low Anomaly":
            return "background-color: #ccccff"  # Light Blue
        return ""

    st.dataframe(
        df_table.style.applymap(color_anomalies, subset=["Anomaly Flag"]),
        hide_index=True,
        column_config={
            "Date/Time": st.column_config.DatetimeColumn("Date/Time", format="YYYY-MM-DD HH:mm:ss"),
            "Value": st.column_config.NumberColumn("Value", format="%.2f"),
        },
    )

    # Button: Download Results (CSV / JSON)
    col_csv, col_json = st.columns(2)

    csv = df_filtered.to_csv(index=False).encode("utf-8")
    col_csv.download_button(
        label="Download Data as CSV",
        data=csv,
        file_name=f"{selected_vital}_vitals_data.csv",
        mime="text/csv",
    )

    json_data = df_filtered.to_json(orient="records")
    col_json.download_button(
        label="Download Data as JSON",
        data=json_data,
        file_name=f"{selected_vital}_vitals_data.json",
        mime="application/json",
    )


# --- Main Application Logic ---
def main():
    st.set_page_config(page_title="FHIR Vitals Dashboard", layout="wide")
    st.title("FHIR Vitals Dashboard with Rule-Based Anomaly Detection")
    st.markdown("---")

    # Find a patient with data to use as a default
    patient_ids = fetch_patient_ids()

    if not patient_ids:
        st.error("Could not find any patient IDs with recent vital signs data on the HAPI FHIR server.")
        st.info(
            "The dashboard requires a patient with 'vital-signs' observations. "
            "Please try again later or check the server status."
        )
        return

    # Dropdown: Select Patient
    # Use the first patient ID as default, or the synthetic one if only one is available
    default_index = 0
    if "synth-pat-1" in patient_ids and len(patient_ids) == 1:
        default_index = patient_ids.index("synth-pat-1")

    selected_patient_id = st.selectbox(
        "Select Patient ID",
        patient_ids,
        index=default_index,
        help="Patient IDs are fetched from the HAPI FHIR server. 'synth-pat-1' is a local fallback.",
    )

    if selected_patient_id:
        st.info(f"Fetching vital signs for Patient/{selected_patient_id} from {FHIR_SERVER_URL}...")

        # Fetch data
        observations = fetch_vitals_data(selected_patient_id)

        if not observations:
            st.warning(f"No vital signs observations found for Patient/{selected_patient_id}.")
            return

        # Parse and Normalize
        vitals_df = parse_and_normalize_vitals(observations)

        if vitals_df.empty:
            st.warning(f"Could not parse any vital signs data for Patient/{selected_patient_id}.")
            return

        # Apply Rule-based Logic
        vitals_df_flagged = flag_anomalies(vitals_df)

        # Display Dashboard
        display_dashboard(vitals_df_flagged)


if __name__ == "__main__":
    main()
