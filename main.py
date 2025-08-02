import os
import json
import asyncio
import logging
import sys
import aiohttp
import requests
import uuid
import pytz

from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from telebot.types import Message
from telebot.async_telebot import AsyncTeleBot
from typing import Dict, List, Any, Optional


# Load environment variables
root_dir = Path(__file__).parent
load_dotenv(root_dir / "config" / ".env")

# Get environment variables
OPWEBUI_URL = os.getenv("OPWEBUI_URL")
OPWEBUI_MODEL = os.getenv("OPWEBUI_MODEL")
OPWEBUI_API_KEY = os.getenv("OPWEBUI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")

def validate_config():
    """Validate required environment variables"""
    required_vars = {
        "TELEGRAM_BOT_TOKEN": TELEGRAM_TOKEN,
        "OPWEBUI_URL": OPWEBUI_URL,
        "OPWEBUI_API_KEY": OPWEBUI_API_KEY,
        "N8N_WEBHOOK_URL": N8N_WEBHOOK_URL
    }
    
    missing_vars = [name for name, value in required_vars.items() if not value]
    
    if missing_vars:
        logger.error(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        return False
    
    logger.info("✅ All required environment variables are set")
    return True

# Configuration constants
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 5678
DOCKER_HOSTS = [
    "host.docker.internal",
    "localhost", 
    "127.0.0.1",
    "172.17.0.1",   # Docker default bridge
    "n8n"           # If container named 'n8n'
]
MAX_RETRIES = 3

def build_url(host: str, port: int = DEFAULT_PORT, path: str = "") -> str:
    """Build URL with proper formatting"""
    return f"http://{host}:{port}{path}"

def extract_mcp_path(webhook_url: str) -> tuple[str, str]:
    """Extract MCP path from webhook URL and return (mcp_url, direct_webhook)"""
    # Handle different URL patterns
    if "/mcp/" in webhook_url:
        mcp_path = webhook_url.split("/mcp/")[1]
        mcp_endpoint = f"/mcp/{mcp_path}"
    elif "/webhook-test/" in webhook_url:
        mcp_path = webhook_url.split("/webhook-test/")[1]
        mcp_endpoint = f"/webhook-test/{mcp_path}"
    elif "/mcp-test/" in webhook_url:
        mcp_path = webhook_url.split("/mcp-test/")[1]
        mcp_endpoint = f"/mcp-test/{mcp_path}"
    else:
        # Fallback
        mcp_endpoint = "/api/mcp"
    
    return mcp_endpoint, mcp_endpoint

# Extract MCP configuration
MCP_ENDPOINT_PATH, DIRECT_WEBHOOK_PATH = extract_mcp_path(N8N_WEBHOOK_URL)

# Initialize the bot
bot = AsyncTeleBot(TELEGRAM_TOKEN)

# Configure logging
log_dir = root_dir / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "telegram_mcp_client.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("telegram_mcp_client")

class N8nMCPClient:
    """MCP Client implementing Streamable HTTP transport for n8n"""
    
    def __init__(self, endpoint_path: str):
        self.endpoint_path = endpoint_path
        self.base_url = None  # Will be set after connectivity test
        self.available_tools: List[Dict] = []
        self.initialized = False
        self.server_capabilities = {}
        self._session_lock = asyncio.Lock()
        self.session_id = None
        tz = pytz.timezone("Asia/Kuala_Lumpur")
        self.protocol_version = datetime.now(tz).strftime("%Y-%m-%d")
    
    def get_available_tools(self) -> List[str]:
        """Get list of available tool names"""
        return [tool.get("name", "") for tool in self.available_tools if tool.get("name")]
    
    async def test_n8n_connectivity(self) -> tuple[bool, str]:
        """Test n8n connectivity across different host configurations"""
        for host in DOCKER_HOSTS:
            test_url = build_url(host, DEFAULT_PORT)
            try:
                logger.debug(f"🔍 Testing connectivity at: {test_url}")
                
                connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
                timeout = aiohttp.ClientTimeout(total=5)
                
                async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                    async with session.get(test_url) as response:
                        if response.status == 200:
                            logger.info(f"✅ n8n accessible at: {test_url}")
                            return True, test_url
                            
            except Exception as e:
                logger.debug(f"❌ Failed to connect to {test_url}: {e}")
                continue
        
        return False, "No n8n instance accessible"

    def parse_sse_response(self, response_text: str) -> Optional[Dict]:
        """Parse Server-Sent Events response according to MCP spec"""
        try:
            lines = response_text.strip().split('\n')
            for line in lines:
                if line.startswith('data: '):
                    data_part = line[6:]  # Remove 'data: ' prefix
                    if data_part and data_part != '[DONE]':
                        return json.loads(data_part)
        except Exception as e:
            logger.debug(f"Error parsing SSE: {e}")
        return None

    async def send_mcp_request(self, request: Dict[str, Any]) -> Optional[Dict]:
        """Send MCP request using Streamable HTTP transport"""
        if not self.base_url:
            logger.error("❌ Base URL not set - run connectivity test first")
            return None
            
        # Add retry logic
        for attempt in range(MAX_RETRIES):
            try:
                mcp_url = f"{self.base_url}{self.endpoint_path}"
                
                connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
                timeout = aiohttp.ClientTimeout(total=30)
                
                async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                    headers = {
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                        "MCP-Protocol-Version": self.protocol_version,
                        "User-Agent": "n8n-mcp-telegram-client/1.0"
                    }
                    
                    # Add session ID if available
                    if self.session_id:
                        headers["Mcp-Session-Id"] = self.session_id
                    
                    logger.debug(f"📡 Sending MCP request to: {mcp_url}")
                    logger.debug(f"📤 Request: {json.dumps(request, indent=2)}")
                    
                    async with session.post(mcp_url, json=request, headers=headers) as response:
                        response_text = await response.text()
                        
                        # Handle session ID from server
                        if "Mcp-Session-Id" in response.headers:
                            self.session_id = response.headers["Mcp-Session-Id"]
                            logger.debug(f"🔑 Session ID: {self.session_id[:8]}...")
                        
                        if response.status == 200:
                            # Parse SSE or JSON response
                            if "text/event-stream" in response.headers.get("Content-Type", ""):
                                sse_data = self.parse_sse_response(response_text)
                                if sse_data:
                                    logger.info("✅ MCP SSE response received")
                                    return sse_data
                            else:
                                try:
                                    result = json.loads(response_text)
                                    logger.info("✅ MCP JSON response received")
                                    return result
                                except json.JSONDecodeError:
                                    logger.warning("Failed to parse JSON response")
                        
                        elif response.status == 202:
                            logger.info("✅ MCP notification accepted")
                            return {"status": "accepted"}
                        
                        elif response.status == 400:
                            logger.error(f"❌ MCP Bad Request: {response_text[:200]}...")
                            return None
                        
                        elif response.status == 404:
                            logger.error("❌ MCP Session expired, reinitializing...")
                            self.session_id = None
                            self.initialized = False
                            # Don't retry on session expiration
                            return None
                        
                        else:
                            logger.error(f"❌ MCP error {response.status}: {response_text[:200]}...")
                            # Only retry on server errors (5xx)
                            if response.status >= 500 and attempt < MAX_RETRIES - 1:
                                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                                continue
                            return None
                            
            except asyncio.TimeoutError:
                logger.warning(f"⏰ Request timeout (attempt {attempt + 1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return None
            except Exception as e:
                logger.error(f"❌ MCP request error: {str(e)}")
                # Only retry on network-related errors
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return None

    async def initialize(self) -> bool:
        """Initialize MCP client"""
        async with self._session_lock:
            try:
                # Test connectivity and set base URL
                n8n_running, n8n_url = await self.test_n8n_connectivity()
                if not n8n_running:
                    logger.error("❌ n8n server not accessible")
                    return False
                
                self.base_url = n8n_url
                logger.info(f"✅ Using n8n at: {n8n_url}")
                
                # Send MCP initialize request
                init_request = {
                    "jsonrpc": "2.0",
                    "id": f"init-{uuid.uuid4()}",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": self.protocol_version,
                        "capabilities": {"tools": {}},
                        "clientInfo": {
                            "name": "n8n-mcp-telegram-client",
                            "version": "1.0.0"
                        }
                    }
                }
                
                logger.info("🔄 Initializing MCP connection...")
                init_response = await self.send_mcp_request(init_request)
                
                if not init_response or "result" not in init_response:
                    logger.error("❌ MCP initialization failed")
                    return False
                
                # Parse server info
                result = init_response["result"]
                self.server_capabilities = result.get("capabilities", {})
                server_info = result.get("serverInfo", {})
                
                logger.info(f"✅ Connected to {server_info.get('name', 'Unknown')} v{server_info.get('version', '?')}")
                
                # Send initialized notification
                await asyncio.sleep(0.1)
                await self.send_mcp_request({
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized"
                })
                
                # Fetch available tools
                await self.fetch_available_tools()
                
                self.initialized = True
                return True
                        
            except Exception as e:
                logger.error(f"❌ MCP initialization error: {e}")
                return False

    async def fetch_available_tools(self) -> bool:
        """Fetch available tools from MCP server"""
        try:
            tools_request = {
                "jsonrpc": "2.0",
                "id": f"tools-{uuid.uuid4()}",
                "method": "tools/list",
                "params": {}
            }
            
            logger.info("🔍 Fetching available tools...")
            tools_response = await self.send_mcp_request(tools_request)
            
            if tools_response and "result" in tools_response:
                tools = tools_response["result"].get("tools", [])
                if tools:
                    self.available_tools = tools
                    logger.info(f"✅ Found {len(tools)} tools")
                    
                    # Log tool details
                    for tool in tools:
                        name = tool.get("name", "Unknown")
                        description = tool.get("description", "No description")
                        schema = tool.get("inputSchema", {})
                        properties = list(schema.get("properties", {}).keys())
                        required = schema.get("required", [])
                        
                        logger.info(f"🔧 {name}: {description}")
                        if properties:
                            logger.debug(f"   Parameters: {properties} (required: {required})")
                    
                    return True
            
            # Fallback to predefined tools
            logger.warning("⚠️ Using predefined tools as fallback")
            self.available_tools = [
                {"name": "Find_Emails", "description": "Find and retrieve emails from Gmail"},
                {"name": "Send_Email", "description": "Send an email via Gmail"},
                {"name": "Create_an_event", "description": "Create a calendar event in Google Calendar"},
                {"name": "Find_single_event", "description": "Find a specific calendar event"},
                {"name": "Find_multiple_events", "description": "Find multiple calendar events"},  
                {"name": "Update_event", "description": "Update an existing calendar event"}
            ]
            logger.info(f"✅ Using {len(self.available_tools)} predefined tools")
            return True
                
        except Exception as e:
            logger.error(f"❌ Error fetching tools: {e}")
            return False

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool via MCP"""
        if not self.initialized and not await self.initialize():
            return "❌ MCP client not initialized"
        
        logger.info(f"🔧 Calling tool: {tool_name}")
        logger.debug(f"📤 Arguments: {json.dumps(arguments, indent=2)}")
        
        try:
            tool_request = {
                "jsonrpc": "2.0",
                "id": f"tool-{uuid.uuid4()}",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
            
            tool_response = await self.send_mcp_request(tool_request)
            
            if not tool_response:
                return "❌ No response from MCP server"
            
            if "error" in tool_response:
                error = tool_response["error"]
                error_msg = f"❌ MCP error {error.get('code', 'unknown')}: {error.get('message', 'Unknown error')}"
                logger.error(error_msg)
                return error_msg
            
            if "result" in tool_response:
                logger.info("✅ Tool executed successfully")
                return json.dumps(tool_response["result"], indent=2, ensure_ascii=False)
            
            return "❌ Unexpected response format"
                
        except Exception as e:
            error_msg = f"❌ Tool execution error: {str(e)}"
            logger.error(error_msg)
            return error_msg

# Initialize MCP client
mcp_client = N8nMCPClient(MCP_ENDPOINT_PATH)

def classify_query(query: str) -> str:
    """Classify user query type"""
    query_lower = query.lower()
    workflow_keywords = [
        'workflow', 'automation', 'process', 'trigger', 'n8n', 'run', 
        'email', 'calendar', 'gmail', 'send', 'find', 'create', 'search'
    ]
    
    if any(keyword in query_lower for keyword in workflow_keywords):
        return "n8n_workflows"
    
    return "general"

async def process_with_llm(query: str, endpoint_type: str = None) -> str:
    """Process query with LLM"""
    if endpoint_type == "n8n_workflows":
        # Build tool information for prompt
        tools_info = []
        for tool in mcp_client.available_tools:
            name = tool.get("name", "Unknown")
            description = tool.get("description", "No description")
            schema = tool.get("inputSchema", {})
            
            # Extract parameter information
            properties = schema.get("properties", {})
            required = schema.get("required", [])
            
            param_info = []
            for param_name, param_details in properties.items():
                param_type = param_details.get("type", "string")
                param_desc = param_details.get("description", "")
                is_required = " (required)" if param_name in required else " (optional)"
                param_line = f'"{param_name}": {param_type}{is_required}'
                if param_desc:
                    param_line += f' - {param_desc}'
                param_info.append(param_line)
            
            params_str = ", ".join(param_info) if param_info else "No parameters"
            tools_info.append(f"• **{name}**: {description}\n  Parameters: {{{params_str}}}")
        
        tools_list = "\n".join(tools_info) if tools_info else "No tools available"
        
        system_prompt = f"""You are an assistant that can call tools through an MCP server.

                        Available tools:
                        {tools_list}

                        IMPORTANT: Use EXACT tool names and parameter names (with underscores).

                        Response format for tool calls:
                        ACTION: call_tool
                        TOOL: exact_tool_name
                        ARGUMENTS: {{
                            "parameter": value
                        }}

                        Examples:
                        - Find emails: Find_Emails with {{"Return_All": true}}
                        - Send email: Send_Email with {{"To": "email", "Subject": "text", "Message": "text"}}
                        - Calendar events: Find_multiple_events with {{}}
                        - Create event: Create_an_event with {{"Start": "ISO_date", "End": "ISO_date", "Description": "text"}}"""
    else:
        system_prompt = "You are a helpful assistant. Answer questions conversationally."
    
    try:
        headers = {
            "Authorization": f"Bearer {OPWEBUI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            OPWEBUI_URL,
            headers=headers,
            json={
                "model": OPWEBUI_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ]
            }
        )
        
        response.raise_for_status()
        response_json = response.json()
        
        if 'choices' in response_json and len(response_json['choices']) > 0:
            choice = response_json['choices'][0]
            if 'message' in choice and 'content' in choice['message']:
                return choice['message']['content'].strip()
            elif 'text' in choice:
                return choice['text'].strip()
        
        return "Sorry, I couldn't process your request."
        
    except Exception as e:
        logger.error(f"LLM processing error: {e}")
        return "❌ Error connecting to AI service."

def extract_tool_call(text: str) -> tuple[Optional[str], Dict[str, Any]]:
    """Extract tool call information from LLM response"""
    if "ACTION:" not in text or "call_tool" not in text:
        return None, {}
    
    try:
        # Extract tool name
        tool_name = None
        if "TOOL:" in text:
            after_tool = text.split("TOOL:", 1)[1].strip()
            tool_name = after_tool.split("\n", 1)[0].strip()
        
        # Extract arguments
        arguments = {}
        if "ARGUMENTS:" in text:
            args_text = text.split("ARGUMENTS:", 1)[1].strip()
            
            # Find JSON object
            start_idx = args_text.find("{")
            if start_idx != -1:
                brace_count = 0
                end_idx = -1
                
                for i in range(start_idx, len(args_text)):
                    if args_text[i] == '{':
                        brace_count += 1
                    elif args_text[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_idx = i
                            break
                
                if end_idx != -1:
                    args_json = args_text[start_idx:end_idx+1]
                    try:
                        arguments = json.loads(args_json)
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse arguments for {tool_name}")
        
        return tool_name, arguments
        
    except Exception as e:
        logger.warning(f"Error extracting tool call: {e}")
        return None, {}

# Bot command handlers
@bot.message_handler(commands=['start', 'help'])
async def help_command(message: Message):
    """Show help information"""
    help_text = """🤖 **n8n MCP Telegram Bot**
Available commands:
• `/help` - Show this help
• `/status` - Check bot status  
• `/tools` - List available tools

**Examples:**
• "Send an email to john@example.com with subject 'Hello'"
• "Find my recent emails"
• "Create a calendar event for tomorrow"
• "What's the weather like?"

_Note: For best results, be specific about what you want to do._

"""
    await bot.reply_to(message, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['status'])
async def status_command(message: Message):
    """Show bot status"""
    # Check connectivity
    n8n_running, n8n_url = await mcp_client.test_n8n_connectivity()
    
    status_text = f"""📊 *Bot Status*
    
✅ Bot is running
🌐 n8n Connectivity: {'✅ Connected' if n8n_running else '❌ Disconnected'}
🔗 MCP Endpoint: `{MCP_ENDPOINT_PATH}`
🤖 AI Model: `{OPWEBUI_MODEL or 'Not configured'}`
🛠️ Available Tools: {len(mcp_client.available_tools)}
🔌 MCP Client: {'✅ Initialized' if mcp_client.initialized else '❌ Not initialized'}
"""
    
    if n8n_running:
        status_text += f"\n📍 n8n URL: `{n8n_url}`"
    
    if mcp_client.session_id:
        status_text += f"\n🔑 Session ID: `{mcp_client.session_id[:8]}...`"
    
    await bot.reply_to(message, status_text, parse_mode="Markdown")

@bot.message_handler(commands=['tools'])
async def tools_command(message: Message):
    """List available tools"""
    if not mcp_client.available_tools:
        await bot.reply_to(message, "🔍 No tools discovered yet. Try sending a message first.")
        return
    
    tools_text = "🛠️ **Available Tools:**\n\n"
    for tool in mcp_client.available_tools:
        name = tool.get("name", "Unknown")
        description = tool.get("description", "No description")
        # Escape markdown characters in name and description
        escaped_name = name.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)')
        escaped_description = description.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)')
        tools_text += f"• **{escaped_name}**: {escaped_description}\n"
    
    await bot.reply_to(message, tools_text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
async def handle_message(message):
    """Handle all messages"""
    user_id = message.from_user.id
    query = message.text.strip()

    await bot.send_chat_action(message.chat.id, "typing")
    logger.info(f"📨 User {user_id}: {query}")

    try:
        # Initialize MCP client if needed
        if not mcp_client.initialized:
            if not await mcp_client.initialize():
                await bot.reply_to(message, "❌ Could not connect to n8n server")
                return
        
        # Process query
        query_type = classify_query(query)
        logger.info(f"🔍 Query type: {query_type}")
        
        llm_response = await process_with_llm(query, query_type)
        logger.info(f"🤖 LLM response received")
        
        # Check for tool call
        tool_name, arguments = extract_tool_call(llm_response)
        
        if tool_name and query_type == "n8n_workflows":
            # Execute tool
            await bot.send_chat_action(message.chat.id, "typing")
            result = await mcp_client.call_tool(tool_name, arguments)
            
            # Format response
            if result.startswith("❌"):
                # Error message
                if len(result) > 4000:
                    result = result[:3900] + "...\n\n[Message truncated]"
                await bot.reply_to(message, result)
            else:
                # Success - try to format as JSON
                try:
                    json_result = json.loads(result)
                    formatted_result = json.dumps(json_result, indent=2, ensure_ascii=False)
                    
                    response_message = f"✅ **Tool: {tool_name}**\n\n```json\n{formatted_result}\n```"
                    if len(response_message) > 4000:
                        response_message = f"✅ Tool: {tool_name}\n\n{formatted_result[:3500]}...\n\n[Truncated]"
                        await bot.reply_to(message, response_message)
                    else:
                        await bot.reply_to(message, response_message, parse_mode="Markdown")
                except:
                    # Plain text response
                    response_message = f"✅ **Tool: {tool_name}**\n\n{result}"
                    if len(response_message) > 4000:
                        response_message = f"✅ Tool: {tool_name}\n\n{result[:3500]}...\n\n[Truncated]"
                    await bot.reply_to(message, response_message)
        else:
            # Regular LLM response
            await bot.reply_to(message, llm_response)
    
    except Exception as e:
        logger.error(f"Message handling error: {e}")
        await bot.reply_to(message, "❌ Error processing your request.")

async def main():
    """Main function"""
    if not validate_config():
        print("❌ Error: Configuration validation failed")
        return
    
    logger.info("🚀 Starting n8n MCP Telegram Client")
    logger.info(f"🐍 Python version: {sys.version}")
    logger.info(f"📁 Working directory: {os.getcwd()}")   
    logger.info(f"🔗 MCP endpoint: {MCP_ENDPOINT_PATH}")
    logger.info(f"🤖 AI model: {OPWEBUI_MODEL}")

    try:
        await bot.polling(none_stop=True)
    except KeyboardInterrupt:
        logger.info("🛑 Received interrupt signal")
    except Exception as e:
        logger.error(f"Runtime error: {e}")
    finally:
        logger.info("🛑 Shutting down")
        await bot.close_session()

if __name__ == "__main__":
    print("🚀 Starting application...")
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()