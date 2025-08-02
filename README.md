# n8n MCP Client Project

This project involves creating a Python-based Model Context Protocol (MCP) client that connects to n8n's MCP Server Trigger while handling Telegram bot interactions. The solution replaces the existing MCP Client Node in n8n to avoid Telegram Trigger conflicts by managing all Telegram I/O directly in the Python script.

The main goal is to establish a communication flow that goes: 

```bash
Telegram Bot 
    ↓↑ 
Python MCP Client 
    ↓↑
Local OpenWebUi/OpenRouter
    ↓↑ 
(SSE) n8n MCP Server 
    ↓↑ 
n8n Workflows
```

This approach allows for better integration with local AI models while maintaining the powerful workflow capabilities of n8n.

Before diving into the technical details, we recommend checking out our documentation:

- [Project Guide](./docs/project-guide.md) - High-level overview of the project, implementation status, and key findings
- [API Documentation](./docs/api-documentation.md) - Detailed documentation of all functions and classes


## Prerequisites

Before you begin working on this project, ensure you have the following installed:

- **Docker Desktop**: Required for containerization and running the development environment
- **Visual Studio Code**: Recommended IDE for development
- **Dev Containers Extension**: VS Code extension that enables containerized development environments
- **Python 3.11+**: For local development and testing (if not using containerized environment)
- **Git**: For version control

> This project uses Docker for development with the help of VS Code's Dev Containers extension. The development environment is fully containerized, ensuring consistency across different development setups.


## Setup Instructions

1. Clone the Repository

    ```bash
    git clone https://github.com/farithadnan/n8n-mcp-client
    cd n8n-mcp-client
    ```

2. Set up n8n Locally

    Before running the MCP client, you need to have n8n running locally via Docker:

    ```bash
    # Create a docker network for communication between containers
    docker network create n8n-network

    # Run n8n with Docker
    docker run -it --rm \
    --name n8n \
    --network n8n-network \
    -p 5678:5678 \
    -v ~/.n8n:/home/node/.n8n \
    n8nio/n8n
    ```

3. Configure Environment Variables

    Create a .env file in the config directory based on the sample:

    ```bash
    cp config/.env.sample config/.env
    ```

    Then edit config/.env with your actual values:

    - `TELEGRAM_BOT_TOKEN`: Your Telegram bot token from BotFather
    - `OPWEBUI_URL`: URL to your OpenWebUI instance (e.g., http://localhost:3000/api/chat)
    - `OPWEBUI_API_KEY`: API key for your OpenWebUI instance
    - `OPWEBUI_MODEL`: Model to use (e.g., gpt-4, llama3, etc.)
    - `N8N_WEBHOOK_URL`: URL to your n8n MCP webhook endpoint

4. Open in VS Code with Dev Container

    1. Open this project in Visual Studio Code
    2. When prompted, click "Reopen in Container" or use the Command Palette (Ctrl+Shift+P) and select "Dev Containers: Reopen in Container"
    3. VS Code will build the development container and install all necessary dependencies
    4. Once the container is ready, you can start developing within the isolated environment.

5. Install Dependencies

    Inside the dev container, install the project dependencies using uv:

    ```bash
    uv pip install -r pyproject.toml
    ```

6. Running the Application

    After setting up the environment variables, you can run the application:

    ```bash
    python main.py
    ```

## Making Changes

If you make changes to the dependencies or Dockerfile:

1. Use `Ctrl+Shift+P` in VS Code
2. Choose "**Dev Containers: Rebuild Container**"
3. This will rebuild the container with your changes

The container includes:

- Python 3.11 with necessary dependencies
- uv package manager for fast dependency resolution
- All required Python packages for MCP client development



