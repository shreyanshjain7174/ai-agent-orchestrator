"""
Usage Examples for AI Agent Orchestrator

This file demonstrates various ways to use the multi-agent orchestrator
for different software development tasks.
"""

# Example 1: REST API Development
task_api_development = """
Create a REST API endpoint for user authentication with JWT tokens.

Requirements:
- Support login, logout, and token refresh endpoints
- Implement rate limiting (max 5 requests per minute per IP)
- Include proper error handling with meaningful error messages
- Add comprehensive unit and integration tests
- Follow security best practices (password hashing, token expiration)
- Use modern Python frameworks (FastAPI or Flask)
- Include API documentation (OpenAPI/Swagger)

Expected output:
- Production-ready code
- Test suite with >80% coverage
- API documentation
- Security analysis report
"""

# Example 2: Database Schema Design
task_database_design = """
Design a database schema for an e-commerce platform.

Requirements:
- Support for products, categories, users, orders, and payments
- Handle inventory management
- Support for multiple payment methods
- Include audit trails for all transactions
- Optimize for read-heavy workloads
- Design for horizontal scalability
- Include migration scripts

Consider:
- Data integrity and consistency
- Performance optimization (indexes, partitioning)
- Security (PII protection, encryption at rest)
- Compliance (GDPR, PCI-DSS)
"""

# Example 3: Microservice Architecture
task_microservice = """
Architect and implement a notification microservice.

Requirements:
- Support multiple notification channels (email, SMS, push notifications)
- Implement message queue for async processing
- Include retry logic with exponential backoff
- Add rate limiting and circuit breaker patterns
- Support notification templates
- Provide delivery status tracking
- Include monitoring and observability

Technical requirements:
- Use containerization (Docker)
- Implement health checks
- Add comprehensive logging
- Include performance metrics
- Support graceful shutdown
"""

# Example 4: Security Enhancement
task_security_review = """
Review and enhance the security of an existing authentication system.

Current implementation:
[Provide your code here]

Requirements:
- Identify all security vulnerabilities
- Implement fixes for OWASP Top 10 risks
- Add security headers
- Implement CSRF protection
- Add input validation and sanitization
- Set up secure session management
- Add security logging and monitoring
- Provide security test suite

Deliverables:
- Security audit report
- Fixed implementation
- Security testing suite
- Security best practices documentation
"""

# Example 5: Performance Optimization
task_performance = """
Optimize the performance of a data processing pipeline.

Current implementation:
- Processes 1000 records/second
- High memory usage (8GB for 100k records)
- Slow database queries (avg 500ms)

Target performance:
- Process 10,000 records/second
- Reduce memory usage by 50%
- Database queries under 50ms

Requirements:
- Profile current implementation
- Identify bottlenecks
- Implement optimizations:
  * Database query optimization
  * Caching strategy
  * Parallel processing
  * Memory optimization
- Provide before/after benchmarks
- Add performance tests
"""

# Example 6: Testing Strategy
task_testing = """
Create a comprehensive testing strategy for a web application.

Components:
- React frontend
- Python backend (FastAPI)
- PostgreSQL database
- Redis cache

Requirements:
- Unit testing framework
- Integration testing
- End-to-end testing
- Performance testing
- Security testing
- Test data management
- CI/CD integration

Deliverables:
- Testing framework setup
- Sample tests for each type
- Test data fixtures
- CI/CD pipeline configuration
- Testing documentation
"""

# Example 7: Code Refactoring
task_refactoring = """
Refactor a legacy monolithic application into a modular architecture.

Current state:
- Single file with 5000+ lines
- No separation of concerns
- Hard-coded configurations
- No tests
- Poor error handling

Target state:
- Modular architecture with clear separation
- Dependency injection
- Configuration management
- Comprehensive test coverage
- Proper error handling and logging
- Documentation

Requirements:
- Maintain backward compatibility
- No breaking changes to API
- Incremental refactoring approach
- Add tests before refactoring
- Document architectural decisions
"""

# Example 8: Feature Implementation
task_feature = """
Implement a real-time chat feature for a web application.

Requirements:
- Support 1-on-1 and group chats
- Real-time message delivery (WebSocket)
- Message history and search
- File sharing support
- Read receipts and typing indicators
- Message encryption (end-to-end)
- Offline support with message queuing

Technical requirements:
- WebSocket connection management
- Message persistence (database)
- Scalability (handle 10k concurrent users)
- Error handling and reconnection logic
- Security (authentication, authorization)

Deliverables:
- Backend implementation
- Frontend components
- Database schema
- API documentation
- Test suite
- Deployment guide
"""


# How to use these examples:

def run_example(task_description: str):
    """
    Run the orchestrator with a specific task.
    
    Usage:
        python -c "from examples import *; run_example(task_api_development)"
    """
    import asyncio
    from orchestrator import create_orchestrator_workflow
    from agent_framework import Message
    
    async def execute():
        workflow = create_orchestrator_workflow()
        
        print("=" * 60)
        print("Starting Multi-Agent Orchestration")
        print("=" * 60)
        print(f"\nTask:\n{task_description}\n")
        print("=" * 60)
        
        async for event in workflow.run_stream([Message("user", text=task_description)]):
            from agent_framework import WorkflowOutputEvent, WorkflowStatusEvent
            if isinstance(event, WorkflowOutputEvent):
                print(f"\n[OUTPUT] {event.data}\n")
            elif isinstance(event, WorkflowStatusEvent):
                print(f"[STATUS] {event.state}")
    
    asyncio.run(execute())


# Advanced usage: Customize agent behavior

def create_custom_orchestrator(
    architect_model: str = "openai/gpt-5.1",
    developer_model: str = "openai/gpt-5.1-codex", 
    qa_model: str = "openai/o3"
):
    """
    Create orchestrator with different models for each agent.
    
    Args:
        architect_model: Model for architectural design and review
        developer_model: Model optimized for code generation
        qa_model: Model for quality and security analysis
    
    Returns:
        Workflow configured with specialized models
    """
    import os
    from agent_framework.azure import AzureOpenAIResponsesClient
    from azure.identity import DefaultAzureCredential
    
    # Create separate clients for each agent with appropriate models
    endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    
    architect_client = AzureOpenAIResponsesClient(
        project_endpoint=endpoint,
        deployment_name=architect_model,
        credential=DefaultAzureCredential()
    )
    
    developer_client = AzureOpenAIResponsesClient(
        project_endpoint=endpoint,
        deployment_name=developer_model,
        credential=DefaultAzureCredential()
    )
    
    qa_client = AzureOpenAIResponsesClient(
        project_endpoint=endpoint,
        deployment_name=qa_model,
        credential=DefaultAzureCredential()
    )
    
    # Create agents with specialized clients
    from orchestrator import (
        OrchestratorManager,
        PrincipalArchitect,
        DeveloperAgent,
        QualityAssuranceAgent,
        FeedbackCoordinator,
        WorkflowBuilder
    )
    
    manager = OrchestratorManager(id="manager")
    architect = PrincipalArchitect(architect_client, id="architect")
    developer = DeveloperAgent(developer_client, id="developer")
    qa_agent = QualityAssuranceAgent(qa_client, id="qa")
    coordinator = FeedbackCoordinator(id="coordinator")
    
    workflow = (
        WorkflowBuilder(start_executor=manager)
        .add_edge(manager, coordinator)
        .add_edge(coordinator, architect)
        .add_edge(architect, coordinator)
        .add_edge(coordinator, developer)
        .add_edge(developer, coordinator)
        .add_edge(coordinator, qa_agent)
        .add_edge(qa_agent, coordinator)
        .build()
    )
    
    return workflow


# Parallel task execution example

async def run_parallel_tasks():
    """
    Execute multiple independent tasks in parallel.
    
    This demonstrates how to process multiple tasks concurrently,
    useful for batch processing or handling multiple user requests.
    """
    import asyncio
    from orchestrator import create_orchestrator_workflow
    from agent_framework import Message
    
    tasks = [
        task_api_development,
        task_database_design,
        task_security_review
    ]
    
    workflow = create_orchestrator_workflow()
    
    # Run tasks in parallel
    results = await asyncio.gather(
        *[workflow.run([Message("user", text=task)]) for task in tasks]
    )
    
    print(f"Completed {len(results)} tasks in parallel")
    return results


if __name__ == "__main__":
    # Example: Run API development task
    run_example(task_api_development)
