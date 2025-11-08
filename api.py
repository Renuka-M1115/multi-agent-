# FastAPI Backend for Multi-Agent Visualization System

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from urllib.parse import urlparse
import requests
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
import uuid
import json
import os
from datetime import datetime
import asyncio
from dotenv import load_dotenv
load_dotenv()  # 👈 loads the .env file automatically

import os

print("Loaded OpenAI Key:", os.getenv("OPENAI_API_KEY"))
print("Database URL:", os.getenv("DATABASE_URL"))


from main import run_visualization_workflow

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class VisualizationRequest(BaseModel):
    """User request for visualization generation"""
    user_request: str
    dataset_url: str
    max_iterations: int = 5


class VisualizationResponse(BaseModel):
    """Response containing job info"""
    job_id: str
    status: str
    message: str


class JobStatus(BaseModel):
    """Job status and progress"""
    job_id: str
    status: str
    iteration: int
    max_iterations: int
    average_score: Optional[float]
    final_visualization_path: Optional[str]
    error_message: Optional[str]


# ============================================================================
# INITIALIZATION
# ============================================================================

app = FastAPI(
    title="Multi-Agent Visualization Critic",
    description="AI-powered visualization code generation and evaluation",
    version="1.0.0"
)

# Add this root endpoint here
@app.get("/")
async def root():
    return {"message": "Welcome to the Multi-Agent Visualization Critic API"}


# In-memory job storage (use Redis/Postgres in production)
jobs_store = {}
UPLOAD_DIR = "/tmp/visualizations"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.post("/api/v1/visualizations", response_model=VisualizationResponse)
async def create_visualization(
    request: VisualizationRequest,
    background_tasks: BackgroundTasks
):
    """
    Create a new visualization job.
    
    Args:
        request: VisualizationRequest with user_request and dataset_url
        background_tasks: FastAPI background tasks
    
    Returns:
        VisualizationResponse with job_id
    """
        # Validate request text
    if not request.user_request or len(request.user_request.strip()) < 5:
        raise HTTPException(status_code=400, detail="Request too short")

    # Normalize dataset_url
    dataset_url = (request.dataset_url or "").strip()
    if not dataset_url:
        raise HTTPException(status_code=400, detail="dataset_url is required")

    # Validate dataset_url: accept http(s) URLs or existing local file path
    parsed = urlparse(dataset_url)
    if parsed.scheme in ("http", "https"):
        # Optional quick reachability check
        try:
            r = requests.head(dataset_url, allow_redirects=True, timeout=5)
            if r.status_code >= 400:
                r = requests.get(dataset_url, allow_redirects=True, timeout=5)
                if r.status_code >= 400:
                    raise HTTPException(status_code=400, detail="Dataset URL not reachable (status >= 400)")
        except requests.RequestException:
            raise HTTPException(status_code=400, detail="Dataset URL not reachable or timed out")
    else:
        # Not an http(s) URL — treat as a local file path
        if not os.path.exists(dataset_url):
            raise HTTPException(
                status_code=400,
                detail="Invalid dataset URL (must be an http(s) URL or an existing local file path)"
            )

    # Create job
    job_id = str(uuid.uuid4())[:8]
    jobs_store[job_id] = {
        "status": "queued",
        "user_request": request.user_request,
        "dataset_url": dataset_url,
        "max_iterations": request.max_iterations,
        "created_at": datetime.now().isoformat(),
        "result": None,
        "error": None
    }

    
    # Queue background task
    background_tasks.add_task(
        run_job,
        job_id,
        request.user_request,
        request.dataset_url,
        request.max_iterations
    )
    
    return VisualizationResponse(
        job_id=job_id,
        status="queued",
        message=f"Visualization job {job_id} created"
    )


@app.get("/api/v1/visualizations/{job_id}", response_model=JobStatus)
async def get_visualization_status(job_id: str):
    job = jobs_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
    result = job.get("result", {})
    
    return JobStatus(
        job_id=job_id,
        status=job["status"],
        iteration=result.get("iteration", 0),
        max_iterations=result.get("max_iterations", 5),
        average_score=result.get("critic_evaluation", {}).get("average_score"),
        final_visualization_path=result.get("final_viz_path"),
        error_message=job.get("error") or result.get("error_message")
    )


@app.get("/api/v1/visualizations/{job_id}/result")
async def get_job_result(job_id: str):
    """
    Get detailed result of a completed job.
    
    Args:
        job_id: Job identifier
    
    Returns:
        Complete job result with code, scores, and feedback
    """
    if job_id not in jobs_store:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs_store[job_id]
    
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")
    
    return JSONResponse(content=job.get("result", {}))


@app.post("/api/v1/visualizations/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a running job"""
    if job_id not in jobs_store:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs_store[job_id]
    if job["status"] in ["completed", "failed"]:
        raise HTTPException(status_code=400, detail="Cannot cancel completed job")
    
    job["status"] = "cancelled"
    return {"message": f"Job {job_id} cancelled"}


@app.post("/api/v1/visualizations/{job_id}/download")
async def download_visualization(job_id: str):
    """Download the generated visualization"""
    if job_id not in jobs_store:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs_store[job_id]
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")
    
    result = job.get("result", {})
    viz_path = result.get("final_viz_path")
    
    if not viz_path or not os.path.exists(viz_path):
        raise HTTPException(status_code=404, detail="Visualization file not found")
    
    return FileResponse(
        path=viz_path,
        filename=f"visualization_{job_id}.png",
        media_type="image/png"
    )


@app.get("/api/v1/jobs")
async def list_jobs(limit: int = 50):
    """List recent jobs"""
    jobs = list(jobs_store.items())[-limit:]
    return {
        "total": len(jobs_store),
        "jobs": [
            {
                "job_id": jid,
                "status": j["status"],
                "created_at": j["created_at"]
            }
            for jid, j in jobs
        ]
    }


# ============================================================================
# BACKGROUND TASK
# ============================================================================

async def run_job(job_id: str, user_request: str, dataset_url: str, max_iterations: int):
    """Run visualization workflow as background task"""
    try:
        jobs_store[job_id]["status"] = "processing"
        
        # Run workflow
        result = run_visualization_workflow(
            user_request=user_request,
            dataset_url=dataset_url,
            max_iterations=max_iterations
        )
        
        jobs_store[job_id]["result"] = result
        jobs_store[job_id]["status"] = "completed"
    
    except Exception as e:
        jobs_store[job_id]["error"] = str(e)
        jobs_store[job_id]["status"] = "failed"


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle general exceptions"""
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )


# ============================================================================
# STARTUP/SHUTDOWN
# ============================================================================

@app.on_event("startup")
async def startup():
    """Initialize on startup"""
    print("Multi-Agent Visualization API starting...")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown"""
    print("Multi-Agent Visualization API shutting down...")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
