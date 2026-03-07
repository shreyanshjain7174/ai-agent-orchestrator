# Contributing to AI Agent Orchestrator

Thank you for your interest in contributing! This project is designed to be highly extensible.

## 🔧 Extensibility & Customization

### Adding New Agents

1. **Create a new agent class** in `autonomous_orchestrator.py`:
   ```python
   class MyCustomAgent(Executor):
       agent: Any
       
       def __init__(self, client: AzureOpenAIResponsesClient, id: str = "my_agent"):
           self.agent = client.as_agent(
               name="MyCustomAgent",
               instructions="Your custom instructions here..."
           )
           super().__init__(id=id)
       
       @handler
       async def handle(self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorResponse]) -> None:
           logger.info(f"[MyAgent] Processing")
           response = await self.agent.run(request.messages, should_respond=request.should_respond)
           await ctx.send_message(AgentExecutorResponse(agent_response=response, executor_id=self.id))
   ```

2. **Add model configuration** in `.env`:
   ```bash
   MY_CUSTOM_MODEL=auto  # or specific model
   ```

3. **Register in workflow** in `create_autonomous_workflow()`:
   ```python
   my_agent_model = resolve_deployment_name("MY_CUSTOM_MODEL", "auto", base_deployment)
   my_agent_client = create_ai_client(project_endpoint, my_agent_model, credential)
   my_agent = MyCustomAgent(my_agent_client, id="my_agent")
   ```

4. **Add to workflow edges**:
   ```python
   .add_edge(some_agent, my_agent)
   .add_edge(my_agent, next_agent)
   ```

### Changing Models

**At runtime via environment variables:**

```bash
# In .env - change anytime
ARCHITECT_MODEL=openai/gpt-5.1
DEVELOPER_MODEL=anthropic/claude-opus-4.6
PLANNER_MODEL=openai/o3-mini
EVALUATOR_MODEL=openai/o3
```

**Per-execution override:**
```python
os.environ["ARCHITECT_MODEL"] = "openai/gpt-5.1-codex"
workflow = create_autonomous_workflow()
```

**Supported model formats:**
- `auto` - falls back to `AZURE_AI_MODEL_DEPLOYMENT_NAME`
- `openai/gpt-5.1` - GitHub Models format
- `gpt-5.1` - Azure AI Model Deployment name

### Custom Memory Systems

Replace the default memory system:

```python
class CustomMemory(MemorySystem):
    def __init__(self, db_connection):
        self.db = db_connection
        # Your custom implementation
    
    def add_memory(self, ...):
        # Store in your database
        pass
```

Then in agents:
```python
planner = PlannerAgent(client, CustomMemory(db), id="planner")
```

### Adding MCP Tools

In `mcp_server.py`:

```python
@mcp.tool()
async def my_custom_tool(task: str, params: str = "") -> dict[str, Any]:
    """Your custom tool exposed to Copilot."""
    # Your implementation
    return {"result": "success"}
```

Restart MCP server - tool is immediately available in Copilot Chat.

### Workflow Customization

**Conditional routing:**
```python
# In create_autonomous_workflow()
workflow = (
    WorkflowBuilder(start_executor=orchestrator)
    .add_edge(planner, evaluator)
    .add_conditional_edge(
        evaluator,
        lambda ctx: "gather" if ctx.needs_context else "execute",
        {"gather": researcher, "execute": architect}
    )
    .build()
)
```

**Parallel execution:**
```python
# Execute multiple agents in parallel
.add_edge(planner, [architect, researcher])  # Both run simultaneously
```

### Extending the PEGEV Loop

Add new phases:

1. **Define phase** in `Phase` enum:
   ```python
   class Phase(str, Enum):
       PLAN = "plan"
       VALIDATE = "validate"  # New phase
       ...
   ```

2. **Create agent** for that phase

3. **Insert in workflow** at appropriate point

## 🚀 Development Workflow

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/my-feature`
3. **Make your changes**
4. **Test locally**:
   ```bash
   # Test CLI mode
   python autonomous_orchestrator.py
   
   # Test MCP mode
   uv run --prerelease=allow --with "mcp[cli]>=1.6.0,<2.0.0" --with-requirements requirements.txt mcp run mcp_server.py
   ```
5. **Commit with clear messages**: `git commit -m "Add: Custom agent for X"`
6. **Push**: `git push origin feature/my-feature`
7. **Open a Pull Request**

## 📝 Code Standards

- **Type hints**: Use for all function parameters and returns
- **Docstrings**: Required for all agents and public functions
- **Logging**: Use `logger.info()` for important events
- **Error handling**: Wrap risky operations in try/except
- **Configuration**: All tunables go in `.env`, not hardcoded

## 🧪 Testing

Before submitting:
```bash
# Syntax check
python -m py_compile autonomous_orchestrator.py
python -m py_compile mcp_server.py
python -m py_compile orchestrator.py

# Runtime test
python autonomous_orchestrator.py
```

## 🎯 Ideas for Contributions

- New specialized agents (SecurityAgent, DocumentationAgent, etc.)
- Alternative memory backends (SQLite, Redis, PostgreSQL)
- Workflow templates for common patterns
- Performance optimizations
- Better error recovery strategies
- Integration with additional AI providers
- Enhanced evaluation metrics
- Monitoring and observability tools

## 📞 Questions?

Open an issue for discussion before major changes. We're here to help!
