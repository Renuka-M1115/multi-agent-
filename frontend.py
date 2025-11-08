# Streamlit Frontend for Multi-Agent Visualization System
# Run with: streamlit run frontend.py

import streamlit as st
import requests
import json
import time
from datetime import datetime
import pandas as pd

# ============================================================================
# PAGE CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="Multi-Agent Visualization Critic",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# CONFIGURATION
# ============================================================================

API_BASE_URL = st.secrets.get("api_url", "http://localhost:8000")

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def call_api(method: str, endpoint: str, data: dict = None) -> dict:
    """Call FastAPI backend"""
    try:
        url = f"{API_BASE_URL}{endpoint}"
        if method == "POST":
            response = requests.post(url, json=data)
        elif method == "GET":
            response = requests.get(url)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        response.raise_for_status()
        return {"success": True, "data": response.json()}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": str(e)}

def format_scores(scores: dict) -> pd.DataFrame:
    """Format critic scores for display"""
    if not scores:
        return pd.DataFrame()
    
    df = pd.DataFrame({
        "Dimension": list(scores.keys()),
        "Score": list(scores.values())
    })
    return df

# ============================================================================
# SIDEBAR
# ============================================================================

with st.sidebar:
    st.title("🎨 Visualization Critic")
    st.markdown("---")
    
    page = st.radio(
        "Select Page",
        ["🏠 Home", "📝 Create Visualization", "📊 Job Status", "📈 Metrics"]
    )
    
    st.markdown("---")
    st.markdown("### Settings")
    api_url = st.text_input("API URL", value=API_BASE_URL)
    if api_url != API_BASE_URL:
        API_BASE_URL = api_url
    
    st.markdown("---")
    st.markdown("""
    ### About
    Multi-Agent Code Generation & Visualization Critic System
    
    - **Coder Agent**: Generates Python visualization code
    - **Critic Agent**: Evaluates code quality
    - **Supervisor**: Orchestrates iterative refinement
    """)

# ============================================================================
# PAGE: HOME
# ============================================================================

if page == "🏠 Home":
    st.title("🎨 Multi-Agent Visualization Critic")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        ### Welcome! 👋
        
        This system automatically generates, evaluates, and refines data visualization code using AI agents.
        
        **How it works:**
        1. You describe the visualization you want
        2. The Coder Agent generates Python code
        3. Code is executed in a safe sandbox
        4. Critic Agent evaluates quality across 6 dimensions
        5. System iterates until code meets quality standards
        6. You download the final visualization
        
        ### Getting Started
        - Go to **📝 Create Visualization** to generate a chart
        - Check **📊 Job Status** to monitor your jobs
        - View **📈 Metrics** for system statistics
        """)
    
    with col2:
        st.info("✨ **AI-Powered Visualization Generation**")
        
        # Quick start example
        st.markdown("### Quick Example")
        example = st.selectbox(
            "Choose a template:",
            [
                "Scatter plot (Weight vs Horsepower)",
                "Bar chart (Weather frequency)",
                "Line chart (Stock prices)",
                "Heatmap (Correlation matrix)"
            ]
        )
        
        if st.button("Use Template", key="template_btn"):
            st.session_state.template = example
            st.switch_page("pages/2_📝_Create_Visualization.py")

# ============================================================================
# PAGE: CREATE VISUALIZATION
# ============================================================================

elif page == "📝 Create Visualization":
    st.title("📝 Create New Visualization")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Input form
        st.markdown("### Visualization Request")
        
        user_request = st.text_area(
            "Describe what visualization you want:",
            placeholder="E.g., 'Create a scatter plot showing the relationship between weight and horsepower from the cars dataset'",
            height=120,
            key="user_request"
        )
        
        dataset_url = st.text_input(
            "Dataset URL:",
            placeholder="E.g., https://raw.githubusercontent.com/vega/vega-datasets/main/data/cars.json",
            key="dataset_url"
        )
        
        max_iterations = st.slider(
            "Max iterations:",
            min_value=1,
            max_value=10,
            value=5,
            key="max_iterations"
        )
    
    with col2:
        st.markdown("### Examples")
        examples = {
            "Cars Dataset": {
                "request": "Create a scatter plot showing weight vs horsepower with different colors for different origins",
                "url": "https://raw.githubusercontent.com/vega/vega-datasets/main/data/cars.json"
            },
            "Weather Data": {
                "request": "Show a bar chart of the frequency of each weather type in Seattle",
                "url": "https://raw.githubusercontent.com/vega/vega/main/docs/data/seattle-weather.csv"
            },
            "Iris Dataset": {
                "request": "Create a pair plot showing relationships between iris features colored by species",
                "url": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/iris.csv"
            }
        }
        
        if st.selectbox("Quick examples:", [""] + list(examples.keys())) != "":
            selected = st.selectbox("Quick examples:", list(examples.keys()))
            if selected:
                user_request = examples[selected]["request"]
                dataset_url = examples[selected]["url"]
    
    st.markdown("---")
    
    # Submit button
    col1, col2 = st.columns([1, 4])
    
    with col1:
        submit_btn = st.button("🚀 Generate Visualization", type="primary")
    
    if submit_btn:
        if not user_request or not dataset_url:
            st.error("Please fill in all required fields")
        else:
            with st.spinner("Creating visualization job..."):
                result = call_api("POST", "/api/v1/visualizations", {
                    "user_request": user_request,
                    "dataset_url": dataset_url,
                    "max_iterations": max_iterations
                })
                
                if result["success"]:
                    job_id = result["data"]["job_id"]
                    st.success(f"✅ Job created: `{job_id}`")
                    st.info("Redirecting to job status page...")
                    st.session_state.job_id = job_id
                    time.sleep(1)
                    st.switch_page("pages/3_📊_Job_Status.py")
                else:
                    st.error(f"Failed to create job: {result['error']}")

# ============================================================================
# PAGE: JOB STATUS
# ============================================================================

elif page == "📊 Job Status":
    st.title("📊 Job Status & Results")
    
    # Job ID input
    col1, col2 = st.columns([3, 1])
    
    with col1:
        job_id = st.text_input(
            "Job ID:",
            placeholder="Enter job ID to check status",
            key="status_job_id"
        )
    
    with col2:
        refresh_btn = st.button("🔄 Refresh", key="refresh_btn")
    
    if job_id:
        with st.spinner("Fetching job status..."):
            result = call_api("GET", f"/api/v1/visualizations/{job_id}")
            
            if result["success"]:
                job_data = result["data"]
                
                # Status cards
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Status", job_data["status"].upper(), delta=f"Iter {job_data['iteration']}/{job_data['max_iterations']}")
                
                with col2:
                    score = job_data.get("average_score", "N/A")
                    st.metric("Quality Score", f"{score}/10" if score != "N/A" else "Pending")
                
                with col3:
                    st.metric("Iterations", f"{job_data['iteration']}/{job_data['max_iterations']}")
                
                with col4:
                    if job_data["status"] == "completed":
                        st.metric("Result", "✅ Ready")
                    elif job_data["status"] == "processing":
                        st.metric("Result", "⏳ In Progress")
                    else:
                        st.metric("Result", "❌ Failed")
                
                st.markdown("---")
                
                # Detailed result
                if job_data["status"] == "completed":
                    st.success("✅ Visualization completed successfully!")
                    
                    # Fetch detailed result
                    detail_result = call_api("GET", f"/api/v1/visualizations/{job_id}/result")
                    
                    if detail_result["success"]:
                        details = detail_result["data"]
                        
                        # Tabs for different views
                        tab1, tab2, tab3, tab4 = st.tabs(
                            ["📊 Visualization", "🔍 Code", "📈 Scores", "💬 Feedback"]
                        )
                        
                        with tab1:
                            st.markdown("### Generated Visualization")
                            # In production: display actual image
                            st.info("Visualization preview would display here")
                            
                            if st.button("⬇️ Download Visualization"):
                                st.success("Download link generated")
                        
                        with tab2:
                            st.markdown("### Generated Python Code")
                            st.code(details.get("generated_code", ""), language="python")
                        
                        with tab3:
                            st.markdown("### Critic Evaluation Scores")
                            scores = details.get("critic_evaluation", {}).get("scores", {})
                            
                            if scores:
                                # Display as dataframe
                                scores_df = format_scores(scores)
                                st.dataframe(scores_df, use_container_width=True)
                                
                                # Display as chart
                                st.bar_chart(
                                    pd.DataFrame({
                                        "Dimension": list(scores.keys()),
                                        "Score": list(scores.values())
                                    }).set_index("Dimension")
                                )
                                
                                avg_score = details.get("critic_evaluation", {}).get("average_score", 0)
                                st.metric("Average Score", f"{avg_score:.2f}/10")
                        
                        with tab4:
                            st.markdown("### Critic Feedback")
                            feedback = details.get("critic_evaluation", {}).get("feedback", "No feedback")
                            st.info(feedback)
                
                elif job_data["status"] == "processing":
                    st.warning("⏳ Job is still processing...")
                    st.progress(job_data["iteration"] / job_data["max_iterations"])
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Continue Waiting"):
                            st.rerun()
                    with col2:
                        if st.button("Cancel Job"):
                            cancel_result = call_api("POST", f"/api/v1/visualizations/{job_id}/cancel")
                            if cancel_result["success"]:
                                st.info("Job cancelled")
                
                else:
                    st.error(f"❌ Job failed: {job_data.get('error_message', 'Unknown error')}")
            
            else:
                st.error(f"Failed to fetch job: {result['error']}")

# ============================================================================
# PAGE: METRICS
# ============================================================================

elif page == "📈 Metrics":
    st.title("📈 System Metrics")
    
    # Fetch recent jobs
    jobs_result = call_api("GET", "/api/v1/jobs?limit=100")
    
    if jobs_result["success"]:
        jobs = jobs_result["data"]["jobs"]
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Jobs", len(jobs))
        
        with col2:
            completed = len([j for j in jobs if j["status"] == "completed"])
            st.metric("Completed", completed)
        
        with col3:
            success_rate = (completed / len(jobs) * 100) if jobs else 0
            st.metric("Success Rate", f"{success_rate:.1f}%")
        
        st.markdown("---")
        
        # Job timeline
        st.markdown("### Recent Jobs")
        jobs_df = pd.DataFrame(jobs)
        if not jobs_df.empty:
            st.dataframe(jobs_df, use_container_width=True)
        else:
            st.info("No jobs yet")

