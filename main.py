# Multi-Agent Code Generation & Visualization Critic System
# Main LangGraph Workflow Implementation

from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
import json
import subprocess
import os
import re
from datetime import datetime

# ============================================================================
# STATE DEFINITION
# ============================================================================

class VisualizationState(TypedDict):
    """State object for multi-agent visualization workflow"""
    user_request: str
    dataset_url: str
    iteration: int
    max_iterations: int
    generated_code: str
    execution_result: dict
    critic_evaluation: dict
    final_viz_path: str
    status: str  # "in_progress", "completed", "failed"
    error_message: str


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def extract_code_block(text: str) -> str:
    """Extract Python code from markdown code blocks"""
    # Look for ```python...``` pattern
    pattern = r'```python\n(.*?)\n```'
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        return matches[0]
    
    # Fallback: look for just ``` ... ```
    pattern = r'```\n(.*?)\n```'
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        return matches[0]
    
    # If no code block, return as-is (might be plain code)
    return text


def execute_code_safely(code: str, timeout: int = 30) -> dict:
    """Execute Python code safely using subprocess with timeout"""
    try:
        # Create a temporary file for the code
        temp_file = f"/tmp/viz_code_{datetime.now().timestamp()}.py"
        with open(temp_file, 'w') as f:
            f.write(code)
        
        # Execute with timeout
        result = subprocess.run(
            ["python", temp_file],
            timeout=timeout,
            capture_output=True,
            text=True,
            cwd="/tmp"
        )
        
        # Clean up
        if os.path.exists(temp_file):
            os.remove(temp_file)
        
        return {
            "status": "success" if result.returncode == 0 else "error",
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "files_created": []  # In production, scan /tmp for generated files
        }
    
    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "returncode": -1,
            "stdout": "",
            "stderr": "Code execution exceeded 30-second timeout",
            "files_created": []
        }
    except Exception as e:
        return {
            "status": "error",
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
            "files_created": []
        }


def parse_json_evaluation(text: str) -> dict:
    """Parse JSON evaluation from LLM response"""
    try:
        # Try to extract JSON from the text
        pattern = r'\{.*\}'
        match = re.search(pattern, text, re.DOTALL)
        if match:
            json_str = match.group(0)
            return json.loads(json_str)
    except json.JSONDecodeError:
        pass
    
    # Fallback if JSON parsing fails
    return {
        "scores": {
            "bugs": 5,
            "transformation": 5,
            "compliance": 5,
            "type": 5,
            "encoding": 5,
            "aesthetics": 5
        },
        "average_score": 5.0,
        "feedback": "Unable to parse evaluation",
        "approve": False
    }


# ============================================================================
# CODER AGENT NODE
# ============================================================================

CODER_SYSTEM_PROMPT = """You are an expert data visualization engineer. Generate production-ready Python code for data visualizations.

REQUIREMENTS:
- Import all necessary libraries (pandas, matplotlib, seaborn, plotly)
- Load data from provided URL using pandas.read_csv()
- Handle missing/null values appropriately with .dropna() or .fillna()
- Print dataset fields using print(df.columns)
- Create appropriate visualization based on request
- Add proper labels, titles, and legends
- Save plot to file with plt.savefig('visualization.png')
- Use best practices for chosen visualization type
- Ensure code is executable without errors

OUTPUT FORMAT:
Provide ONLY executable Python code in a ```python code block.
No explanations, no markdown outside code block.
No comments unless absolutely necessary.
"""

def coder_node(state: VisualizationState) -> VisualizationState:
    """Generate visualization code using Coder Agent"""
    llm = ChatOpenAI(model="gpt-4", temperature=0.3)
    
    # Build context from previous feedback
    feedback_context = ""
    if state.get("critic_evaluation"):
        feedback = state["critic_evaluation"].get("feedback", "")
        if feedback:
            feedback_context = f"\n\nPrevious Critic Feedback:\n{feedback}\n\nIMPORTANT: Address all feedback points in your improved code."
    
    prompt = f"""Generate Python visualization code for:

Request: {state['user_request']}
Dataset URL: {state['dataset_url']}
{feedback_context}
"""
    
    try:
        response = llm.invoke(prompt)
        raw_code = response.content
        state["generated_code"] = extract_code_block(raw_code)
        state["iteration"] += 1
        state["status"] = "in_progress"
    except Exception as e:
        state["error_message"] = f"Coder Agent Error: {str(e)}"
        state["status"] = "failed"
    
    return state


# ============================================================================
# EXECUTOR NODE
# ============================================================================

def executor_node(state: VisualizationState) -> VisualizationState:
    """Execute generated code in sandbox"""
    try:
        execution_result = execute_code_safely(state["generated_code"], timeout=30)
        state["execution_result"] = execution_result
        
        if execution_result["status"] != "success":
            state["error_message"] = execution_result.get("stderr", "Unknown execution error")
    
    except Exception as e:
        state["execution_result"] = {
            "status": "error",
            "stderr": str(e),
            "stdout": ""
        }
        state["error_message"] = str(e)
    
    return state


# ============================================================================
# CRITIC AGENT NODE
# ============================================================================

CRITIC_SYSTEM_PROMPT = """You are a visualization code critic. Evaluate code across 6 dimensions:

1. bugs (1-10): Syntax errors, logic errors, runtime issues
   - Score < 5 if ANY bugs exist
   - Check: imports, syntax, variable definitions
   
2. transformation (1-10): Proper data filtering, aggregation, type conversion
   - Check: null handling, data filtering, aggregation
   
3. compliance (1-10): Meets specified visualization goals
   - Check: Does output match the user's request?
   
4. type (1-10): Appropriate chart type for data/intent
   - Score < 5 if wrong visualization type
   - Examples: scatter for correlation, bar for comparison, line for trends
   
5. encoding (1-10): Correct variable mapping (x, y, color, size, etc.)
   - Check: Proper axis assignments, meaningful color encoding
   
6. aesthetics (1-10): Proper labels, colors, layout, readability
   - Check: titles, labels, legends, font sizes, color scheme

OUTPUT FORMAT (ONLY valid JSON, no other text):
{
  "scores": {
    "bugs": NUMBER,
    "transformation": NUMBER,
    "compliance": NUMBER,
    "type": NUMBER,
    "encoding": NUMBER,
    "aesthetics": NUMBER
  },
  "average_score": FLOAT,
  "feedback": "Specific, actionable improvements. If score < 8, provide concrete suggestions.",
  "approve": BOOLEAN
}

IMPORTANT: Return ONLY the JSON object, nothing else."""

def critic_node(state: VisualizationState) -> VisualizationState:
    """Evaluate code quality using Critic Agent"""
    llm = ChatOpenAI(model="gpt-4", temperature=0)
    
    # Prepare evaluation context
    execution_context = ""
    if state.get("execution_result"):
        exec_result = state["execution_result"]
        execution_context = f"""
Execution Status: {exec_result.get('status', 'unknown')}
Stdout: {exec_result.get('stdout', '')[:500]}
Stderr: {exec_result.get('stderr', '')[:500]}
"""
    
    prompt = f"""Evaluate this visualization code:

User Request: {state['user_request']}
Dataset: {state['dataset_url']}

Generated Code:
```python
{state['generated_code']}
```
{execution_context}

Provide structured evaluation as JSON."""
    
    try:
        response = llm.invoke(prompt)
        evaluation = parse_json_evaluation(response.content)
        state["critic_evaluation"] = evaluation
    except Exception as e:
        state["critic_evaluation"] = {
            "scores": {"bugs": 3, "transformation": 3, "compliance": 3, 
                      "type": 3, "encoding": 3, "aesthetics": 3},
            "average_score": 3.0,
            "feedback": f"Critic evaluation failed: {str(e)}",
            "approve": False
        }
        state["error_message"] = f"Critic Error: {str(e)}"
    
    return state


# ============================================================================
# DECISION NODE
# ============================================================================

def should_continue(state: VisualizationState) -> Literal["coder", "end"]:
    """Decide whether to iterate or finish"""
    
    # Check max iterations
    if state["iteration"] >= state["max_iterations"]:
        state["status"] = "completed"
        return "end"
    
    # Check quality threshold
    avg_score = state.get("critic_evaluation", {}).get("average_score", 0)
    exec_success = state.get("execution_result", {}).get("status") == "success"
    
    if avg_score >= 8.0 and exec_success:
        state["status"] = "completed"
        state["final_viz_path"] = "visualization.png"  # In production: use S3
        return "end"
    
    # Continue iterating
    return "coder"


# ============================================================================
# BUILD LANGGRAPH WORKFLOW
# ============================================================================

def build_workflow():
    """Construct the LangGraph workflow"""
    workflow = StateGraph(VisualizationState)
    
    # Add nodes
    workflow.add_node("coder", coder_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("critic", critic_node)
    
    # Set entry point
    workflow.set_entry_point("coder")
    
    # Add edges
    workflow.add_edge("coder", "executor")
    workflow.add_edge("executor", "critic")
    workflow.add_conditional_edges(
        "critic",
        should_continue,
        {"coder": "coder", "end": END}
    )
    
    # Compile
    return workflow.compile()


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def run_visualization_workflow(user_request: str, dataset_url: str, max_iterations: int = 5) -> dict:
    """Run the complete multi-agent visualization workflow"""
    
    # Initialize state
    initial_state = VisualizationState(
        user_request=user_request,
        dataset_url=dataset_url,
        iteration=0,
        max_iterations=max_iterations,
        generated_code="",
        execution_result={},
        critic_evaluation={},
        final_viz_path="",
        status="in_progress",
        error_message=""
    )
    
    # Build and run workflow
    app = build_workflow()
    final_state = app.invoke(initial_state)
    
    return final_state


if __name__ == "__main__":
    # Example usage
    user_request = "Create a scatter plot showing the relationship between weight and horsepower from the cars dataset"
    dataset_url = "https://raw.githubusercontent.com/vega/vega-datasets/main/data/cars.json"
    
    print("Starting Multi-Agent Visualization Workflow...")
    print(f"Request: {user_request}\n")
    
    result = run_visualization_workflow(user_request, dataset_url, max_iterations=5)
    
    print(f"\nWorkflow Complete!")
    print(f"Status: {result['status']}")
    print(f"Iterations: {result['iteration']}")
    print(f"Final Score: {result['critic_evaluation'].get('average_score', 'N/A')}")
    print(f"Visualization Path: {result['final_viz_path']}")
    
    if result.get("error_message"):
        print(f"Errors: {result['error_message']}")
