"""FastMCP Tool Server: Sandboxed Execution and Report Persistence Layer.

Provides protocol-compliant primitives for running untrusted Python code
and saving verified analytical reports.
"""

from typing import Dict, Any, List
import subprocess
import sys
import json
from mcp.server.fastmcp import FastMCP

# Initialize protocol server instance
mcp = FastMCP(
    name="EnterpriseReportTools",
    description="Model Context Protocol server for code evaluation and report persistence."
)

# In-memory artifact repository
REPORT_REGISTRY: Dict[str, Dict[str, Any]] = {}

@mcp.tool()
def execute_sandboxed_python(code_snippet: str) -> Dict[str, Any]:
    """Execute arbitrary Python source code within an isolated subprocess.
    
    Args:
        code_snippet: Valid Python code string to execute.
        
    Returns:
        Structured payload containing stdout, stderr, execution duration, and exit status.
    """
    try:
        process = subprocess.run(
            [sys.executable, "-c", code_snippet],
            capture_output=True,
            text=True,
            timeout=10,
            check=False
        )
        return {
            "success": process.returncode == 0,
            "stdout": process.stdout.strip(),
            "stderr": process.stderr.strip(),
            "exit_code": process.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Execution terminated: Execution boundary of 10 seconds exceeded.",
            "exit_code": -1
        }
    except Exception as exc:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Runtime exception encountered: {str(exc)}",
            "exit_code": -1
        }

@mcp.tool()
def persist_report_artifact(report_id: str, title: str, domain: str, markdown_content: str) -> Dict[str, Any]:
    """Save a synthesized analytical report to the artifact registry.
    
    Args:
        report_id: Unique deterministic identifier for the report.
        title: Formal technical title of the analysis.
        domain: Target technical or business domain.
        markdown_content: Complete markdown-formatted analytical report.
        
    Returns:
        Persistence confirmation metadata including word count and storage key.
    """
    word_count = len(markdown_content.split())
    record = {
        "report_id": report_id,
        "title": title,
        "domain": domain,
        "content": markdown_content,
        "word_count": word_count
    }
    REPORT_REGISTRY[report_id] = record
    return {
        "status": "persisted",
        "report_id": report_id,
        "word_count": word_count
    }

@mcp.resource("reports://catalog")
def get_reports_catalog() -> str:
    """Read-only resource returning the active catalog of all saved reports."""
    catalog = [
        {"report_id": k, "title": v["title"], "domain": v["domain"], "word_count": v["word_count"]}
        for k, v in REPORT_REGISTRY.items()
    ]
    return json.dumps(catalog, indent=2)

if __name__ == "__main__":
    mcp.run()
