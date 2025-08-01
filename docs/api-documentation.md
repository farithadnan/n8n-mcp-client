# API Documentation

This document provides detailed documentation for the functions and classes in the main.py file.

## Table of Contents

1. [Global Functions](#global-functions)
2. [N8nMCPClient Class](#n8nmcpclient-class)
3. [Telegram Bot Handlers](#telegram-bot-handlers)
4. [Helper Functions](#helper-functions)
5. [Main Function](#main-function)

## Global Functions

### build_url(host, port=DEFAULT_PORT, path="")
Constructs a URL from host, port, and path components.

**Parameters:**
- `host` (str): Hostname or IP address
- `port` (int, optional): Port number (default: DEFAULT_PORT)
- `path` (str, optional): URL path (default: "")

**Returns:**
- `str`: Complete URL string

### extract_mcp_path(webhook_url)
Extracts the MCP endpoint path from a webhook URL.

**Parameters:**
- `webhook_url` (str): Full webhook URL

**Returns:**
- `tuple[str, str]`: Tuple containing (mcp_endpoint, direct_webhook)

## N8nMCPClient Class

The main MCP client class that handles communication with n8n's MCP server.

### \_\_init\_\_(endpoint_path)
Initializes the MCP client.

**Parameters:**
- [endpoint_path](file:///workspaces/n8n-mcp-client/main.py#L0-L0) (str): The MCP endpoint path

### get_available_tools()
Returns a list of available tool names.

**Returns:**
- `List[str]`: List of tool names

### test_n8n_connectivity()
Tests connectivity to n8n across different host configurations.

**Returns:**
- `tuple[bool, str]`: Tuple containing (success status, base URL or error message)

### parse_sse_response(response_text)
Parses Server-Sent Events response according to MCP specification.

**Parameters:**
- `response_text` (str): Raw SSE response text

**Returns:**
- `Optional[Dict]`: Parsed JSON data or None

### send_mcp_request(request)
Sends an MCP request using Streamable HTTP transport.

**Parameters:**
- `request` (Dict[str, Any]): JSON-RPC request object

**Returns:**
- `Optional[Dict]`: Response from MCP server or None

### initialize()
Initializes the MCP client connection.

**Returns:**
- `bool`: True if initialization successful, False otherwise

### fetch_available_tools()
Fetches available tools from the MCP server.

**Returns:**
- `bool`: True if tools fetched successfully, False otherwise

### call_tool(tool_name, arguments)
Calls a specific tool via MCP.

**Parameters:**
- `tool_name` (str): Name of the tool to call
- `arguments` (Dict[str, Any]): Arguments for the tool

**Returns:**
- `str`: Tool execution result or error message

## Telegram Bot Handlers

### help_command(message)
Handles the `/help` command. Displays help information to the user.

**Parameters:**
- `message` (Message): Telegram message object

### status_command(message)
Handles the `/status` command. Shows bot status information.

**Parameters:**
- `message` (Message): Telegram message object

### tools_command(message)
Handles the `/tools` command. Lists available tools.

**Parameters:**
- `message` (Message): Telegram message object

### handle_message(message)
Handles all incoming messages that are not commands.

**Parameters:**
- `message` (Message): Telegram message object

## Helper Functions

### classify_query(query)
Classifies user query type to determine processing approach.

**Parameters:**
- `query` (str): User's query text

**Returns:**
- `str`: Query classification ("n8n_workflows" or "general")

### process_with_llm(query, endpoint_type=None)
Processes a query with the LLM through OpenWebUI.

**Parameters:**
- `query` (str): User's query
- `endpoint_type` (str, optional): Type of endpoint to use

**Returns:**
- `str`: LLM response

### extract_tool_call(text)
Extracts tool call information from LLM response.

**Parameters:**
- `text` (str): LLM response text

**Returns:**
- `tuple[Optional[str], Dict[str, Any]]`: Tool name and arguments

## Main Function

### main()
Main application function that starts the Telegram bot.

**Returns:**
- None

### if \_\_name\_\_ == "\_\_main\_\_"
Entry point that runs the main function with asyncio.