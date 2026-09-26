# AI Agent Research Engine

> Multi-agent autonomous systems for high-throughput research report generation, code synthesis, and intelligent orchestration.

## Architecture

This repository implements a production-grade multi-agent AI pipeline architecture featuring:

### Core Engines

| Module | Description |
|--------|-------------|
| `deep_research_engine.py` | Autonomous research pipeline with PlanningAgent, RetrievalAgent, VerificationCriticAgent, and SynthesisAgent |
| `run_100_reports.py` | Batch execution pipeline generating 100 concurrent technical research reports |
| `multi_agent_orchestrator.py` | Stateful graph-based agent engine with self-correction, schema validation, and cycle routing |
| `batch_pipeline.py` | Enterprise batch pipeline with exponential backoff, failure recovery, and telemetry |
| `mcp_tool_server.py` | FastMCP protocol server for sandboxed code execution and report persistence |

### Key Capabilities

- **Multi-Agent Orchestration**: Graph-based routing with PlannerAgent → ResearcherAgent → CodeArchitectAgent → CriticAgent pipeline
- **Hallucination Filtering**: VerificationCriticAgent validates all claims against retrieved evidence with confidence scoring
- **Concurrent Execution**: Async semaphore-bounded pipelines with configurable concurrency limits
- **Self-Correction**: Automatic retry with backoff on validation failures (up to 3 retries)
- **Structured Output**: Pydantic-enforced schemas for all agent contracts and data models
- **MCP Integration**: Model Context Protocol server for sandboxed execution and artifact persistence

## Quick Start

```bash
# Install dependencies
pip install pydantic httpx

# Run 100 research reports
python run_100_reports.py

# Run batch orchestration pipeline
python batch_pipeline.py

# Start MCP tool server
pip install mcp
python mcp_tool_server.py
```

## System Design

```
┌─────────────────────────────────────────────────┐
│              DeepResearchPipeline                │
│  ┌──────────┐  ┌───────────┐  ┌──────────────┐  │
│  │ Planning │→ │ Retrieval │→ │ Verification │  │
│  │  Agent   │  │   Agent   │  │ Critic Agent │  │
│  └──────────┘  └───────────┘  └──────────────┘  │
│                                      ↓           │
│                              ┌──────────────┐    │
│                              │  Synthesis   │    │
│                              │    Agent     │    │
│                              └──────────────┘    │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│              AgentGraphEngine                    │
│  ┌──────────┐  ┌────────────┐  ┌──────────────┐ │
│  │ Planner  │→ │ Researcher │→ │    Code      │ │
│  │  Agent   │  │   Agent    │  │  Architect   │ │
│  └──────────┘  └────────────┘  └──────────────┘ │
│                                      ↓    ↑     │
│                              ┌──────────────┐   │
│                              │   Critic     │   │
│                              │   Agent      │───┘
│                              └──────────────┘
└─────────────────────────────────────────────────┘
```

## CI/CD

Includes GitHub Actions workflow for automated daily profile metric synchronization.

## License

MIT
