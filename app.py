import streamlit as st
import pandas as pd
import plotly.express as px
from fhirclient import client
from fhirclient.models.observation import Observation
import json
import os
from datetime import datetime, timedelta

# ------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------
FHIR_SERVER_URL = "https://hapi.fhir.org/baseR4"

# Expanded, curated vital signs list (Option 2B)
VITAL_SIGNS_MAP = {
    "8480-6": {"name": "Systolic Blood Pressure", "unit": "mmHg", "thresholds": {"high": 140, "low": 90}},
    "8462-4": {"name": "Diastolic Blood Pressure", "unit": "mmHg", "thresholds": {"high": 90, "low": 60}},
    "8867-4": {"name": "Heart Rate", "unit": "/min", "thresholds": {"high": 100, "low": 60}},
    "9279-1": {"name": "Respiratory Rate", "unit": "/min", "thresholds": {"high": 24, "low": 12}},
    "8310-5": {"name": "Body Temperature", "unit": "Cel", "thresholds": {"high": 38.0, "low": 35.0}},
    "2708-6": {"name": "Oxygen Saturation", "unit": "%", "thresholds": {"high": 100, "low": 90}},
    "29463-7": {"name": "Body Weight", "unit": "kg", "thresholds": {"high": 150, "low": 30}},
    "8302-1": {"name": "Body Height", "unit": "cm", "thresholds": {"high": 220, "low": 100}},
    "39156-5": {"name": "Body Mass Index (BMI)", "unit": "kg/m2", "thresholds": {"high": 30, "low": 18.5}},
    "41653-7": {"name": "Glucose", "unit": "mg/dL", "thresholds": {"high": 180, "low": 70}}
}


# ------------------------------------------------------
# FHIR CLIENT
# ------------------------------------------------------
@st.cache_resource(ttl=3600)
def get_fhir_client():
    settings = {
        'app_id': 'my_vitals_dashboard',
        'api_base': FHIR_SERVER_URL
    }
    return client.FHIRClient(settings=settings)

# ------------------------------------------------------
# LOAD SYNTHETIC FALLBACK
# ------------------------------------------------------
def load_synthetic_data():
    try:
        file_path = os.path.join(os.path.dirname(__file__), "synthetic_data.json")
        with open(file_path, 'r') as f:
            bundle_json = json.load(f)

        observations = []
        for entry in bundle_json.get('entry', []):
            resource = entry.get('resource')
            if resource and resource.get('resourceType') == 'Observation':
                obs = Observation(resource)
                observations.append(obs)

        st.warning("Using synthetic fallback data due to malformed FHIR observations.")
        return observations
    except Exception as e:
        st.error(f"Error loading synthetic fallback data: {e}")
        return []


# ------------------------------------------------------
# FETCH ONLY PATIENTS WITH VALID VITAL SIGNS  (Option 1A)
# ------------------------------------------------------
def fetch_valid_patient_ids(client_obj):
    st.info("Searching FHIR server for valid patients with usable vital-sign data...")

    try:
        search = Observation.where(struct={'category': 'vital-signs', '_count': 200})
        bundle = search.perform(client_obj.server)

        raw_ids = set()
        if bundle and bundle.entry:
            for entry in bundle.entry:
                if entry.resource and entry.resource.subject:
                    ref = entry.resource.subject.reference
                    if ref and "Patient/" in ref:
                        raw_ids.add(ref.split("/")[-1])

        valid_ids = []
        for pid in raw_ids:
            obs = fetch_vitals_data(client_obj, pid, validate_only=True)
            if obs:  # keep only patients with valid vitals
                valid_ids.append(pid)

        if not valid_ids:
            st.warning("No valid patients found on FHIR server. Using synthetic fallback.")
            return ["synth-pat-1"]

        st.success("Successfully fetched valid patient IDs.")
        return sorted(valid_ids)

    except Exception as e:
        st.error(f"Error fetching patient list: {e}")
        return ["synth-pat-1"]


# ------------------------------------------------------
# FETCH VITALS (with Option 3C – switch to fallback on malformed dates)
# ------------------------------------------------------
def fetch_vitals_data(client_obj, patient_id, validate_only=False):
    if patient_id == "synth-pat-1":
        return load_synthetic_data()

    try:
        search = Observation.where(struct={
            'patient': patient_id,
            'category': 'vital-signs',
            '_count': 200
        })
        bundle = search.perform(client_obj.server)

        observations = []
        for entry in (bundle.entry or []):
            if entry.resource and entry.resource.resource_type == 'Observation':
                obs = entry.resource

                # detect malformed datetime → Option 3C fallback
                try:
                    if obs.effectiveDateTime:
                        datetime.fromisoformat(obs.effectiveDateTime.isostring.replace("Z", "+00:00"))
                except:
                    return load_synthetic_data()

                observations.append(obs)

        if validate_only:
            return observations

        return observations

    except Exception:
        return load_synthetic_data()


# ------------------------------------------------------
# DATA PARSING
# ------------------------------------------------------
def parse_and_normalize_vitals(observations):
    data = []

    for obs in observations:
        try:
            code = obs.code.coding[0].code

            if code not in VITAL_SIGNS_MAP:
                continue

            vital_info = VITAL_SIGNS_MAP[code]

            value = None
            unit = None

            # Quantity
            if obs.valueQuantity:
                value = obs.valueQuantity.value
                unit = obs.valueQuantity.unit

            # Component type structures
            elif obs.component:
                for comp in obs.component:
                    ccode = comp.code.coding[0].code
                    if ccode == code and comp.valueQuantity:
                        value = comp.valueQuantity.value
                        unit = comp.valueQuantity.unit
                        break

            if value is None:
                continue

            # Date parsing safe
            if obs.effectiveDateTime:
                dt = datetime.fromisoformat(obs.effectiveDateTime.isostring.replace("Z", "+00:00"))
            else:
                continue

            data.append({
                "Date/Time": dt,
                "Vital Sign Code": code,
                "Vital Sign Name": vital_info["name"],
                "Value": float(value),
                "Unit": unit or vital_info["unit"],
                "Thresholds": vital_info["thresholds"]
            })
        except:
            continue

    df = pd.DataFrame(data)
    if df.empty:
        return df

    return df.sort_values(by="Date/Time", ascending=False).reset_index(drop=True)


# ------------------------------------------------------
# ANOMALY LOGIC
# ------------------------------------------------------
def flag_anomalies(df):
    if df.empty:
        return df

    df["Anomaly Flag"] = "Normal"

    for i, row in df.iterrows():
        t = row["Thresholds"]
        v = row["Value"]

        if v > t["high"]:
            df.loc[i, "Anomaly Flag"] = "High Anomaly"
        elif v < t["low"]:
            df.loc[i, "Anomaly Flag"] = "Low Anomaly"

    return df


# ------------------------------------------------------
# DASHBOARD UI
# ------------------------------------------------------
def display_dashboard(df):
    if df.empty:
        st.warning("No vital signs available for this patient.")
        return

    st.subheader("Vitals Trend Analysis")

    vital_signs = sorted(df["Vital Sign Name"].unique())
    selected_vital = st.selectbox("Select Vital Sign to View", vital_signs)

    df2 = df[df["Vital Sign Name"] == selected_vital].copy()

    min_date = df2["Date/Time"].min().date()
    max_date = df2["Date/Time"].max().date()

    col1, col2 = st.columns(2)
    start_date = col1.date_input("Start Date", min_date)
    end_date = col2.date_input("End Date", max_date)

    df2["Date_Only"] = df2["Date/Time"].dt.date
    df2 = df2[(df2["Date_Only"] >= start_date) & (df2["Date_Only"] <= end_date)]

    if df2.empty:
        st.info("No data in selected date range.")
        return

    fig = px.line(
        df2,
        x="Date/Time",
        y="Value",
        color="Anomaly Flag",
        markers=True,
        title=f"{selected_vital} Trend Over Time"
    )

    t = df2["Thresholds"].iloc[0]
    fig.add_hline(y=t["high"], line_dash="dash", line_color="red", annotation_text="High Threshold")
    fig.add_hline(y=t["low"], line_dash="dash", line_color="blue", annotation_text="Low Threshold")

    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Latest Readings")
    df_table = df2[["Date/Time", "Vital Sign Name", "Value", "Unit", "Anomaly Flag"]].head(10)
    st.dataframe(df_table, hide_index=True)

    col_csv, col_json = st.columns(2)
    col_csv.download_button("Download CSV", df2.to_csv(index=False), file_name="vitals.csv")
    col_json.download_button("Download JSON", df2.to_json(orient="records"), file_name="vitals.json")


# ------------------------------------------------------
# MAIN
# ------------------------------------------------------
def main():
    st.set_page_config(page_title="FHIR Vitals Dashboard", layout="wide")
    st.title("FHIR Vitals Dashboard with Rule-Based Anomaly Detection")
    st.markdown("---")

    fhir_client = get_fhir_client()

    patient_ids = fetch_valid_patient_ids(fhir_client)

    selected_patient = st.selectbox("Select Patient ID", patient_ids)

    observations = fetch_vitals_data(fhir_client, selected_patient)
    df = parse_and_normalize_vitals(observations)
    df = flag_anomalies(df)

    display_dashboard(df)


if __name__ == "__main__":
    main()
