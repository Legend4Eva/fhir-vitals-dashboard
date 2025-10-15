import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from datetime import datetime, timedelta
import json
from io import StringIO

# Page configuration
st.set_page_config(
    page_title="FHIR Vitals Dashboard",
    page_icon="🏥",
    layout="wide"
)

# Clinical thresholds for vital signs
THRESHOLDS = {
    'blood_pressure_systolic': {'high': 140, 'low': 90, 'unit': 'mmHg'},
    'blood_pressure_diastolic': {'high': 90, 'low': 60, 'unit': 'mmHg'},
    'heart_rate': {'high': 100, 'low': 60, 'unit': 'bpm'},
    'temperature': {'high': 38.0, 'low': 36.0, 'unit': '°C'},
    'respiratory_rate': {'high': 20, 'low': 12, 'unit': '/min'},
    'oxygen_saturation': {'high': 100, 'low': 95, 'unit': '%'},
    'body_weight': {'high': None, 'low': None, 'unit': 'kg'},
    'bmi': {'high': 30, 'low': 18.5, 'unit': 'kg/m²'}
}

# LOINC codes for common vitals
VITAL_CODES = {
    '85354-9': 'blood_pressure',
    '8480-6': 'blood_pressure_systolic',
    '8462-4': 'blood_pressure_diastolic',
    '8867-4': 'heart_rate',
    '8310-5': 'temperature',
    '9279-1': 'respiratory_rate',
    '2708-6': 'oxygen_saturation',
    '29463-7': 'body_weight',
    '39156-5': 'bmi'
}

def fetch_fhir_observations(base_url, patient_id, max_results=100):
    """Fetch observations from FHIR server"""
    try:
        url = f"{base_url}/Observation"
        params = {
            'patient': patient_id,
            'category': 'vital-signs',
            '_count': max_results,
            '_sort': '-date'
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching data: {str(e)}")
        return None

def parse_observation(obs):
    """Parse a FHIR Observation resource"""
    try:
        obs_id = obs.get('id', 'N/A')
        date_str = obs.get('effectiveDateTime') or obs.get('effectivePeriod', {}).get('start')
        
        if not date_str:
            return None
        
        date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        
        # Get the vital type from coding
        code_data = obs.get('code', {}).get('coding', [])
        vital_type = None
        for coding in code_data:
            loinc_code = coding.get('code')
            if loinc_code in VITAL_CODES:
                vital_type = VITAL_CODES[loinc_code]
                break
        
        if not vital_type:
            return None
        
        # Handle blood pressure specially (has components)
        if vital_type == 'blood_pressure':
            components = obs.get('component', [])
            results = []
            for comp in components:
                comp_code = comp.get('code', {}).get('coding', [{}])[0].get('code')
                if comp_code in VITAL_CODES:
                    comp_type = VITAL_CODES[comp_code]
                    value = comp.get('valueQuantity', {}).get('value')
                    unit = comp.get('valueQuantity', {}).get('unit', '')
                    if value is not None:
                        results.append({
                            'id': obs_id,
                            'date': date,
                            'vital_type': comp_type,
                            'value': float(value),
                            'unit': unit
                        })
            return results
        else:
            # Single value observation
            value_qty = obs.get('valueQuantity', {})
            value = value_qty.get('value')
            unit = value_qty.get('unit', '')
            
            if value is not None:
                return [{
                    'id': obs_id,
                    'date': date,
                    'vital_type': vital_type,
                    'value': float(value),
                    'unit': unit
                }]
        
        return None
    except Exception as e:
        return None

def determine_status(vital_type, value):
    """Determine if a vital sign is normal, high, or low"""
    if vital_type not in THRESHOLDS:
        return 'normal', '⚪'
    
    threshold = THRESHOLDS[vital_type]
    
    if threshold['high'] is not None and value > threshold['high']:
        return 'high', '🔴'
    elif threshold['low'] is not None and value < threshold['low']:
        return 'low', '🔵'
    else:
        return 'normal', '🟢'

def create_vitals_chart(df, vital_type):
    """Create an interactive time-series chart for a vital sign"""
    vital_df = df[df['vital_type'] == vital_type].sort_values('date')
    
    if vital_df.empty:
        return None
    
    fig = go.Figure()
    
    # Add traces for each status
    for status, color, symbol in [('high', 'red', 'triangle-up'), 
                                   ('low', 'blue', 'triangle-down'), 
                                   ('normal', 'green', 'circle')]:
        status_df = vital_df[vital_df['status'] == status]
        if not status_df.empty:
            fig.add_trace(go.Scatter(
                x=status_df['date'],
                y=status_df['value'],
                mode='markers+lines',
                name=status.capitalize(),
                marker=dict(size=10, symbol=symbol, color=color),
                line=dict(color=color, width=2)
            ))
    
    # Add threshold lines
    if vital_type in THRESHOLDS:
        threshold = THRESHOLDS[vital_type]
        if threshold['high'] is not None:
            fig.add_hline(y=threshold['high'], line_dash="dash", 
                         line_color="red", opacity=0.5,
                         annotation_text=f"High: {threshold['high']}")
        if threshold['low'] is not None:
            fig.add_hline(y=threshold['low'], line_dash="dash", 
                         line_color="blue", opacity=0.5,
                         annotation_text=f"Low: {threshold['low']}")
    
    fig.update_layout(
        title=f"{vital_type.replace('_', ' ').title()} Trend",
        xaxis_title="Date",
        yaxis_title=f"Value ({vital_df.iloc[0]['unit']})",
        hovermode='x unified',
        height=400
    )
    
    return fig

def load_sample_data():
    """Load sample FHIR data for testing"""
    sample_data = {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [
            {
                "resource": {
                    "resourceType": "Observation",
                    "id": "bp-1",
                    "status": "final",
                    "category": [{"coding": [{"code": "vital-signs"}]}],
                    "code": {"coding": [{"system": "http://loinc.org", "code": "85354-9"}]},
                    "effectiveDateTime": "2025-10-01T10:00:00Z",
                    "component": [
                        {"code": {"coding": [{"code": "8480-6"}]}, 
                         "valueQuantity": {"value": 145, "unit": "mmHg"}},
                        {"code": {"coding": [{"code": "8462-4"}]}, 
                         "valueQuantity": {"value": 92, "unit": "mmHg"}}
                    ]
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "id": "hr-1",
                    "status": "final",
                    "category": [{"coding": [{"code": "vital-signs"}]}],
                    "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]},
                    "effectiveDateTime": "2025-10-01T10:00:00Z",
                    "valueQuantity": {"value": 110, "unit": "bpm"}
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "id": "temp-1",
                    "status": "final",
                    "category": [{"coding": [{"code": "vital-signs"}]}],
                    "code": {"coding": [{"system": "http://loinc.org", "code": "8310-5"}]},
                    "effectiveDateTime": "2025-10-01T10:00:00Z",
                    "valueQuantity": {"value": 38.5, "unit": "°C"}
                }
            }
        ]
    }
    return sample_data

# Main App
st.title("🏥 FHIR Vitals Dashboard")
st.markdown("### Monitor and visualize patient vital signs with rule-based anomaly detection")

# Sidebar configuration
st.sidebar.header("Configuration")
data_source = st.sidebar.radio("Data Source", ["HAPI FHIR Server", "Sample Data"])

if data_source == "HAPI FHIR Server":
    fhir_server = st.sidebar.text_input("FHIR Server URL", "https://hapi.fhir.org/baseR4")
    patient_id = st.sidebar.text_input("Patient ID", "example")
    max_results = st.sidebar.slider("Max Results", 10, 200, 100)
    
    if st.sidebar.button("Fetch Data"):
        with st.spinner("Fetching data from FHIR server..."):
            bundle = fetch_fhir_observations(fhir_server, patient_id, max_results)
            if bundle:
                st.session_state['fhir_data'] = bundle
                st.success("Data fetched successfully!")
else:
    if st.sidebar.button("Load Sample Data"):
        st.session_state['fhir_data'] = load_sample_data()
        st.success("Sample data loaded!")

# Process data if available
if 'fhir_data' in st.session_state:
    bundle = st.session_state['fhir_data']
    
    # Parse observations
    all_observations = []
    entries = bundle.get('entry', [])
    
    for entry in entries:
        resource = entry.get('resource', {})
        if resource.get('resourceType') == 'Observation':
            parsed = parse_observation(resource)
            if parsed:
                if isinstance(parsed, list):
                    all_observations.extend(parsed)
                else:
                    all_observations.append(parsed)
    
    if all_observations:
        # Create DataFrame
        df = pd.DataFrame(all_observations)
        
        # Add status
        df['status'], df['indicator'] = zip(*df.apply(
            lambda row: determine_status(row['vital_type'], row['value']), axis=1
        ))
        
        # Filters
        st.sidebar.markdown("---")
        st.sidebar.header("Filters")
        
        vital_types = sorted(df['vital_type'].unique())
        selected_vitals = st.sidebar.multiselect("Select Vital Signs", vital_types, default=vital_types)
        
       min_date = df['date'].min().date()
       max_date = df['date'].max().date()
        
        date_range = st.sidebar.date_input(
            "Date Range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date
        )
        
        # Apply filters
        filtered_df = df[df['vital_type'].isin(selected_vitals)].copy()
        if len(date_range) == 2:
            start_date, end_date = date_range
            filtered_df = filtered_df[
                (filtered_df['date'].dt.date >= start_date) & 
                (filtered_df['date'].dt.date <= end_date)
            ]
        elif len(date_range) == 1:
            # If only one date selected, filter to that date
            filtered_df = filtered_df[filtered_df['date'].dt.date == date_range[0]]
        
        # Summary metrics
        st.header("📊 Summary Statistics")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Readings", len(filtered_df))
        with col2:
            high_count = len(filtered_df[filtered_df['status'] == 'high'])
            st.metric("High Alerts", high_count, delta=None if high_count == 0 else "⚠️")
        with col3:
            low_count = len(filtered_df[filtered_df['status'] == 'low'])
            st.metric("Low Alerts", low_count, delta=None if low_count == 0 else "⚠️")
        with col4:
            normal_count = len(filtered_df[filtered_df['status'] == 'normal'])
            st.metric("Normal Readings", normal_count)
        
        # Visualization
        st.header("📈 Vital Signs Trends")
        
        for vital in selected_vitals:
            chart = create_vitals_chart(filtered_df, vital)
            if chart:
                st.plotly_chart(chart, use_container_width=True)
        
        # Latest readings table
        st.header("📋 Latest Readings")
        latest_df = filtered_df.sort_values('date', ascending=False).groupby('vital_type').first().reset_index()
        
        display_df = latest_df[['indicator', 'vital_type', 'value', 'unit', 'date', 'status']].copy()
        display_df.columns = ['', 'Vital Sign', 'Value', 'Unit', 'Date', 'Status']
        display_df['Vital Sign'] = display_df['Vital Sign'].str.replace('_', ' ').str.title()
        display_df['Date'] = display_df['Date'].dt.strftime('%Y-%m-%d %H:%M')
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        # Export functionality
        st.header("💾 Export Data")
        col1, col2 = st.columns(2)
        
        with col1:
            csv = filtered_df.to_csv(index=False)
            st.download_button(
                label="Download as CSV",
                data=csv,
                file_name=f"vitals_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        
        with col2:
            json_data = filtered_df.to_json(orient='records', date_format='iso')
            st.download_button(
                label="Download as JSON",
                data=json_data,
                file_name=f"vitals_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )
        
    else:
        st.warning("No vital sign observations found in the data.")
else:
    st.info("👈 Please select a data source and fetch data to begin.")

# Footer
st.sidebar.markdown("---")
st.sidebar.markdown("### About")
st.sidebar.info(
    "This dashboard visualizes FHIR vital signs data with rule-based anomaly detection. "
    "It supports standard LOINC codes and highlights abnormal values based on clinical thresholds."
)
