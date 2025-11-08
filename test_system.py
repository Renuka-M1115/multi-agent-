# Unit and Integration Tests for Multi-Agent Visualization System

import pytest
from fastapi.testclient import TestClient
from api import app
from main import (
    extract_code_block,
    parse_json_evaluation,
    VisualizationState,
    coder_node,
    critic_node,
    should_continue
)

# ============================================================================
# TEST SETUP
# ============================================================================

client = TestClient(app)


# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================

class TestHelperFunctions:
    """Tests for utility functions"""
    
    def test_extract_code_block_with_python_marker(self):
        """Test extraction of python code block"""
        text = """
        Some explanation here.
        ```python
        import pandas as pd
        print("Hello")
        ```
        More text.
        """
        result = extract_code_block(text)
        assert "import pandas" in result
        assert "print" in result
    
    def test_extract_code_block_generic(self):
        """Test extraction of generic code block"""
        text = """
        ```
        x = 5
        y = 10
        ```
        """
        result = extract_code_block(text)
        assert "x = 5" in result
    
    def test_parse_json_evaluation_valid(self):
        """Test parsing valid JSON evaluation"""
        text = '''
        {
          "scores": {
            "bugs": 8,
            "transformation": 9,
            "compliance": 8,
            "type": 9,
            "encoding": 8,
            "aesthetics": 7
          },
          "average_score": 8.17,
          "feedback": "Good code",
          "approve": true
        }
        '''
        result = parse_json_evaluation(text)
        assert result["average_score"] == 8.17
        assert result["approve"] is True
    
    def test_parse_json_evaluation_invalid(self):
        """Test parsing invalid JSON returns fallback"""
        text = "This is not JSON"
        result = parse_json_evaluation(text)
        assert "average_score" in result
        assert result["average_score"] == 5.0


# ============================================================================
# API ENDPOINT TESTS
# ============================================================================

class TestAPIEndpoints:
    """Tests for FastAPI endpoints"""
    
    def test_health_check(self):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_create_visualization_valid(self):
        """Test creating a valid visualization job"""
        response = client.post(
            "/api/v1/visualizations",
            json={
                "user_request": "Create a scatter plot of x vs y",
                "dataset_url": "https://example.com/data.csv",
                "max_iterations": 3
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "queued"
    
    def test_create_visualization_invalid_request(self):
        """Test creating visualization with invalid request"""
        response = client.post(
            "/api/v1/visualizations",
            json={
                "user_request": "too short",
                "dataset_url": "not-a-url",
                "max_iterations": 3
            }
        )
        assert response.status_code == 400
    
    def test_get_job_status_not_found(self):
        """Test getting status of non-existent job"""
        response = client.get("/api/v1/visualizations/invalid_job_id")
        assert response.status_code == 404
    
    def test_list_jobs(self):
        """Test listing jobs"""
        response = client.get("/api/v1/jobs")
        assert response.status_code == 200
        assert "jobs" in response.json()


# ============================================================================
# WORKFLOW STATE TESTS
# ============================================================================

class TestWorkflowState:
    """Tests for workflow state management"""
    
    def test_initial_state_creation(self):
        """Test creating initial state"""
        state = VisualizationState(
            user_request="Create a bar chart",
            dataset_url="https://example.com/data.csv",
            iteration=0,
            max_iterations=5,
            generated_code="",
            execution_result={},
            critic_evaluation={},
            final_viz_path="",
            status="in_progress",
            error_message=""
        )
        assert state["iteration"] == 0
        assert state["status"] == "in_progress"
    
    def test_should_continue_completed(self):
        """Test should_continue returns 'end' when completed"""
        state = VisualizationState(
            user_request="test",
            dataset_url="https://example.com/data.csv",
            iteration=2,
            max_iterations=5,
            generated_code="code",
            execution_result={"status": "success"},
            critic_evaluation={"average_score": 9.0},
            final_viz_path="path.png",
            status="in_progress",
            error_message=""
        )
        result = should_continue(state)
        assert result == "end"
        assert state["status"] == "completed"
    
    def test_should_continue_iterate(self):
        """Test should_continue returns 'coder' when iterating"""
        state = VisualizationState(
            user_request="test",
            dataset_url="https://example.com/data.csv",
            iteration=1,
            max_iterations=5,
            generated_code="code",
            execution_result={"status": "success"},
            critic_evaluation={"average_score": 5.0},
            final_viz_path="",
            status="in_progress",
            error_message=""
        )
        result = should_continue(state)
        assert result == "coder"
    
    def test_should_continue_max_iterations(self):
        """Test should_continue ends at max iterations"""
        state = VisualizationState(
            user_request="test",
            dataset_url="https://example.com/data.csv",
            iteration=5,
            max_iterations=5,
            generated_code="code",
            execution_result={"status": "success"},
            critic_evaluation={"average_score": 5.0},
            final_viz_path="",
            status="in_progress",
            error_message=""
        )
        result = should_continue(state)
        assert result == "end"


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """Integration tests"""
    
    @pytest.mark.asyncio
    async def test_full_workflow_simulation(self):
        """Test a complete workflow (with mocked LLM)"""
        # This would require mocking ChatOpenAI
        pass
    
    def test_api_workflow_end_to_end(self):
        """Test complete API workflow"""
        # Create job
        create_response = client.post(
            "/api/v1/visualizations",
            json={
                "user_request": "Create a bar chart showing sales by region",
                "dataset_url": "https://example.com/sales.csv",
                "max_iterations": 2
            }
        )
        assert create_response.status_code == 200
        job_id = create_response.json()["job_id"]
        
        # Check status
        status_response = client.get(f"/api/v1/visualizations/{job_id}")
        assert status_response.status_code == 200
        assert status_response.json()["job_id"] == job_id


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

class TestPerformance:
    """Performance and reliability tests"""
    
    def test_concurrent_job_creation(self):
        """Test creating multiple jobs concurrently"""
        job_ids = []
        for i in range(5):
            response = client.post(
                "/api/v1/visualizations",
                json={
                    "user_request": f"Create chart {i}",
                    "dataset_url": "https://example.com/data.csv"
                }
            )
            if response.status_code == 200:
                job_ids.append(response.json()["job_id"])
        
        assert len(job_ids) == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
