FHIR Vitals Dashboard — User Manual 

This user manual explains how to fully access and evaluate the FHIR Vitals Dashboard using only a web browser. No installation or technical setup is required.

1. Accessing the Application

Go to the deployed live URL:

Deployed URL: https://fhir-vitals-dashboard-dh8aqrnkwp3ucjgs7dun8f.streamlit.app/

You may use any modern browser such as Chrome, Firefox, Edge, or Safari.

No login, installation, or setup is needed.
The app typically loads in 3–10 seconds depending on FHIR server response time.

2. Initial Loading Behavior

When the application loads, it attempts to connect to the live HAPI FHIR server.
Depending on server response, different banners may appear:

• Green message: Live patient list successfully fetched from HAPI
• Yellow message: HAPI did not return recent patients → synthetic fallback dataset activated
• Red message: HAPI unreachable → synthetic dataset automatically loaded
• “synth-pat-1” in dropdown: App is currently running in offline/demo mode

This feature ensures the dashboard always remains functional for testing and grading.

3. How to Use the Dashboard

Step A — Selecting a Patient
Open the patient selection dropdown. Choose any available ID. The system retrieves the patient’s vital signs and loads them automatically.
If the patient has no vital signs data, a message will appear indicating that no observations were found.
Recommended patients for testing are: eda-workflow-1 or eda-workflow-2.

Step B — Selecting a Vital Sign
After selecting a patient, choose a vital sign to visualize.
Supported vitals include systolic blood pressure, diastolic blood pressure, heart rate, body temperature, oxygen saturation, body weight, and body height.
Only vitals available for that patient will show up in the dropdown.

Step C — Filtering by Date Range
A start date and end date selector allow narrowing down the timeline.
If the selected range contains no data, the app will notify the user.

4. Understanding the Trend Chart

The trend chart displays all selected measurements over time.
It includes:

• A line with data points
• Red values for abnormally high readings
• Blue values for abnormally low readings
• Green values indicating normal measurements
• Dashed threshold lines showing clinical boundary levels
• Tooltips that appear when hovering over data points to show timestamp, value, unit, and anomaly status

This enables fast detection of important patterns and health risks.

5. Latest Readings Table

Below the chart, the most recent 10 vital sign readings are shown.
Each row includes the timestamp, vital sign name, numerical value, measurement unit, and anomaly flag if abnormal.

This provides an immediate summary of current patient status.

6. Downloading Data

The dashboard supports exporting filtered data for additional analysis.
Two options are available:

• Download Data as CSV — for use in spreadsheets or statistical tools
• Download Data as JSON — for integration in other applications or dashboards

Exports always reflect:

• The selected patient
• The selected vital sign
• The selected date range

Support Notes

If live data fails to load due to temporary FHIR server issues, you may continue testing using the synthetic fallback dataset. All application features remain fully usable.
