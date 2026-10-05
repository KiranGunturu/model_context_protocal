from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

response = client.responses.create(
    model="gpt-5",
    input="what is the price of AAPL?",
    tools = [
        {
            "type": "mcp", # tells OpenAI: use your built-in MCP client
            "server_label": "datagpt",
            "server_url": "https://smartness-protozoan-container.ngrok-free.dev/mcp",
            "require_approval": "never"
            
        }
    ]
)

print(response.output_text)