# AI Agent Orchestrator - Quick Start Guide

## Prerequisites Check

Before starting, verify these prerequisites:

### 1. Python Installation (REQUIRED)

**Check if Python is installed:**
```bash
python --version
# or
python3 --version
```

**Expected output:** `Python 3.10.x` or higher

**If not installed:**
- Windows: Download from [python.org](https://www.python.org/downloads/)
  - ✅ Check "Add Python to PATH" during installation
- macOS: `brew install python@3.11`
- Linux: `sudo apt install python3.11` or `sudo yum install python311`

### 2. AI Model Access

Choose one option:

**Option A: GitHub Models (Free - For Development)**
- Create a GitHub Personal Access Token: https://github.com/settings/tokens
- Free tier with rate limits
- Good for development and testing

**Option B: Microsoft Foundry (Recommended - For Production)**
- Requires Azure subscription
- Access to premium models (gpt-5.1, o3, claude-opus-4-5)
- Better performance and higher limits
- Explore models: Open Command Palette → `AI Toolkit: View Model Catalog`

## Quick Setup (5 Minutes)

### Step 1: Create Virtual Environment

```bash
cd Q:\hcsshim\ai-agent-orchestrator

# Create virtual environment
python -m venv .venv

# Activate it
.venv\Scripts\activate  # Windows
# or
source .venv/bin/activate  # Linux/Mac
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- Microsoft Agent Framework (core + Azure AI)
- HTTP server support
- Debugging tools
- Azure authentication

### Step 3: Configure Environment

```bash
# Copy template
copy .env.example .env  # Windows
# or
cp .env.example .env  # Linux/Mac

# Edit .env file and add your configuration
```

**For GitHub Models (Free):**
```bash
# In .env file:
GITHUB_TOKEN=ghp_your_token_here
AZURE_AI_PROJECT_ENDPOINT=https://models.github.ai/inference/
AZURE_AI_MODEL_DEPLOYMENT_NAME=openai/gpt-5.1

# Specialized Copilot routing
ARCHITECT_MODEL=anthropic/claude-opus-4.6
DEVELOPER_MODEL=anthropic/claude-opus-4.6
QA_MODEL=auto
```

**For Microsoft Foundry:**
```bash
# In .env file:
AZURE_AI_PROJECT_ENDPOINT=https://your-project.api.azureml.ms
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-5.1
```

### Step 4: Test the Orchestrator

**CLI Mode (Test with sample task):**
```bash
python orchestrator.py
```

**HTTP Server Mode:**
```bash
python orchestrator.py --server
```

**MCP Server Mode (for Copilot specialized tools):**
```bash
uv run --prerelease=allow --with "mcp[cli]>=1.6.0,<2.0.0" --with-requirements requirements.txt mcp run mcp_server.py
```

**Autonomous Mode (CLI - for self-healing tasks):**
```bash
python autonomous_orchestrator.py
```

**Debug in VS Code:**
1. Open the project in VS Code
2. Press `F5` or go to Run and Debug
3. Select "Debug Local Agent/Workflow HTTP Server"
4. Agent Inspector will open automatically

## Execution Modes Explained

### Legacy Mode (Simple Feedback Loop)

When you run the standard orchestrator with a sample task:

1. **Manager** receives the task: "Create a REST API endpoint for user authentication..."
2. **Architect** designs the solution:
   - Authentication architecture
   - JWT token strategy
   - Security considerations
   - Scalability requirements
3. **Developer** implements based on the design:
   - Code implementation
   - Tests
   - Documentation
4. **QA** reviews the implementation:
   - Code quality analysis
   - Security vulnerability check
   - Test coverage review
   - Performance assessment
5. **Feedback Loop** (if issues found):
   - QA → Developer: "Fix these security issues..."
   - Developer → Architect: "Should I use approach A or B?"
   - Architect → Developer: "Use approach B because..."
   - Developer implements fixes
   - QA re-reviews
6. **Completion**: Task approved with high-quality output

### Autonomous Mode (Self-Healing PEGEV Loop) ⚡

When you run the autonomous orchestrator, you get a **fully autonomous system**:

**Example task:** "Design a secure user authentication API" or "Fix this bug"

**What happens:**

1. **PLAN Phase** (Planner Agent)
   - Breaks down task into executable steps
   - Defines success criteria
   - Identifies required context
   - Anticipates risks
   - **Learns from past similar tasks in memory**

2. **EVALUATE Phase** (Evaluator Agent)
   - Assesses if plan is complete
   - Checks for missing information
   - Decides: proceed, gather more, or revise
   - Prevents infinite loops

3. **GATHER Phase** (Researcher Agent)
   - Collects missing context
   - Researches best practices
   - Analyzes relevant code/docs
   - Fills knowledge gaps

4. **EXECUTE Phase** (Architect + Developer Agents)
   - Architect designs solution
   - Developer implements code
   - Follows plan and research findings
   - Addresses identified risks

5. **VERIFY Phase** (Verifier Agent)
   - Tests implementation thoroughly
   - Identifies bugs and security issues
   - Provides specific fix instructions
   - **Stores lessons learned in memory**

6. **EVALUATE Phase (again)**
   - Checks if success criteria met
   - If passed → COMPLETE
   - If failed → loop back to PLAN with improvements

7. **LEARN Phase**
   - Stores what worked and what didn't
   - Future executions use these lessons
   - **Agents continuously improve**

**Key Differences from Legacy Mode:**
- ✅ Fully autonomous - continues until success
- ✅ Self-healing - learns from mistakes
- ✅ Persistent memory - remembers past solutions
- ✅ Context gathering - researches automatically
- ✅ Strategic planning - breaks down complex tasks
- ✅ Decision-making - evaluates progress at each step

**Use Autonomous Mode When:**
- Task says "design something", "fix this bug", "debug this"
- Requirements may evolve during execution
- You need iterative improvement with learning
- Task is complex and multi-faceted
- Self-correction is valuable

## What Happens During Execution?

### Legacy Mode Execution


1. **Manager** receives the task: "Create a REST API endpoint for user authentication..."
2. **Architect** designs the solution:
   - Authentication architecture
   - JWT token strategy
   - Security considerations
   - Scalability requirements
3. **Developer** implements based on the design:
   - Code implementation
   - Tests
   - Documentation
4. **QA** reviews the implementation:
   - Code quality analysis
   - Security vulnerability check
   - Test coverage review
   - Performance assessment
5. **Feedback Loop** (if issues found):
   - QA → Developer: "Fix these security issues..."
   - Developer → Architect: "Should I use approach A or B?"
   - Architect → Developer: "Use approach B because..."
   - Developer implements fixes
   - QA re-reviews
6. **Completion**: Task approved with high-quality output

## Troubleshooting

### "python: The term 'python' is not recognized"
- Python is not installed or not in PATH
- Install Python from python.org
- Ensure "Add to PATH" is checked during installation

### "ModuleNotFoundError: No module named 'agent_framework'"
- Virtual environment not activated
- Run: `.venv\Scripts\activate` (Windows) or `source .venv/bin/activate` (Linux/Mac)
- Then: `pip install -r requirements.txt`

### "Authentication failed"
- **For GitHub**: Verify GITHUB_TOKEN in .env
- **For Azure**: Run `az login` to authenticate

### "Model not found"
- Verify model deployment name in .env
- For Foundry: Ensure model is deployed in your project
- Use AI Toolkit Model Catalog to browse available models

## Model Recommendations by Agent Type

| Agent Type | Best Model | Alternative | Premium |
|-----------|------------|-------------|---------|
| **Architect** (Design & Review) | `gpt-5.1` | `o3` | `claude-opus-4-5` |
| **Developer** (Coding) | `gpt-5.1-codex` | `gpt-5.1-codex-max` | `claude-sonnet-4-5` |
| **QA** (Testing & Security) | `o3` | `gpt-5.1` | `claude-opus-4-5` |

**Why different models?**
- Architect needs strong reasoning for design decisions
- Developer needs coding-specific optimization
- QA needs analytical depth for security review

## Next Steps

1. **Customize Agents**: Edit agent instructions in `orchestrator.py`
2. **Add Skills**: Integrate with your skills library
3. **Deploy to Production**: Use Microsoft Foundry deployment
4. **Monitor Performance**: Use AI Toolkit Agent Inspector

## Support

- **Documentation**: See [README.md](README.md) for full documentation
- **Agent Framework**: https://github.com/microsoft/agent-framework
- **AI Toolkit**: Built into VS Code

---

**Note**: This orchestrator uses Agent Framework preview (v1.0.0b260107). Pin versions in requirements.txt to avoid breaking changes.
