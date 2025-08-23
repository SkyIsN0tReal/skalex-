import asyncio
from playwright.async_api import async_playwright
from browser_use.llm import ChatOpenAI
from browser_use.llm import ChatGoogle
from browser_use import Agent
from browser_use.browser.session import BrowserSession
from pathlib import Path
import json

input_url = input("Enter the URL of the site you want to index: ")

custom_instructions = input("Enter any custom instructions for the agent (or enter to skip): ")



def truncate_strings_recursive(obj, max_length=1000):
    if isinstance(obj, str):
        return obj[:max_length] if len(obj) > max_length else obj
    elif isinstance(obj, dict):
        return {key: truncate_strings_recursive(value, max_length) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [truncate_strings_recursive(item, max_length) for item in obj]
    else:
        return obj

async def main():

    runs_dir = Path(__file__).resolve().parent / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    har_path = runs_dir / "session.har"
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(channel="chrome", headless=False)
    context = await browser.new_context(
        record_har_path=str(har_path),
        record_har_mode="full",
    )
    page = await context.new_page()
    
    # ✨ Then pass the working browser to browser_use
    browser_session = BrowserSession(
        page=page,
        browser_context=context,
        browser=browser,
        playwright=playwright,
    )

    llm = ChatOpenAI(model="o3")
    agent = Agent(
        task=f"""You are in a system that maps out the backends of websites. Interact with this site: {input_url}. {custom_instructions}""",
        llm=llm,
        browser_session=browser_session
    )
    
    result = await agent.run()
    print(result)
    
    # Close the context to flush the HAR file to disk
    await context.close()
    await browser.close()
    await playwright.stop()

asyncio.run(main())

with open("runs/session.har", "r") as f:
    har = json.load(f)

#recursively truncate all strings to 1000 characters
har_truncated = truncate_strings_recursive(har, 1000)


from filter import filter_har_data

har_filtered = filter_har_data(har_truncated)


with open("runs/session_filtered.har", "w") as f:
    json.dump(har_filtered, f, indent=2)



print("HAR file truncated and saved as session_filtered.har")



import base64
import json
import os
from google import genai
from google.genai import types


def generate():
    client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY"),
    )

    model = "gemini-2.5-pro"
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=str(har_filtered))
            ],
        ),
    ]
    tools = [
        types.Tool(googleSearch=types.GoogleSearch(
        )),
    ]
    generate_content_config = types.GenerateContentConfig(
        thinking_config = types.ThinkingConfig(
            thinking_budget=-1,
        ),
        tools=tools,
        system_instruction=[
            types.Part.from_text(text="""# Documentation Site JSON Generator

## Task
Reverse engineer the input network request data and generate a documentation site in JSON format. The JSON should contain multiple pages (e.g., *Quickstart*, *Endpoints*, *Authentication*, etc.), with each page containing a sequence of text blocks and optional code snippets. The authentication should document what has to be done to get cookies, etc.

---

## Output JSON Structure
{
  \"pages\": [
    {
      \"title\": \"Quickstart\",
      \"content\": [
        {
          \"type\": \"text\",
          \"value\": \"Some introduction text...\"
        },
        {
          \"type\": \"code_snippet\",
          \"languages\": {
            \"python\": \"import requests\\nresponse = requests.get('https://example.com')\",
            \"cURL\": \"curl https://example.com\"
          }
        }
      ]
    },
    {
      \"title\": \"Endpoints\",
      \"content\": [
        {
          \"type\": \"text\",
          \"value\": \"This section describes the API endpoints...\"
        },
        {
          \"type\": \"code_snippet\",
          \"languages\": {
            \"javascript\": \"fetch('https://example.com/api')\\n  .then(res => res.json())\",
            \"go\": \"resp, _ := http.Get(\\\"https://example.com/api\\\")\"
          }
        }
      ]
    }
  ]
}

---

## Formatting Rules
1. **Top-level structure:**  
   Must always be a JSON object with the key `\"pages\"` pointing to a list.

2. **Pages:**  
   Each page is an object with:  
   - `\"title\"`: string (e.g., `\"Quickstart\"`, `\"Endpoints\"`)  
   - `\"content\"`: list of objects (mix of text and code snippets, in any order)

3. **Content blocks:**  
   - Text block →  
     { \"type\": \"text\", \"value\": \"Some explanation...\" }  
   - Code snippet block →  
     {
       \"type\": \"code_snippet\",
       \"languages\": {
         \"python\": \"import requests\",
         \"cURL\": \"curl example\"
       }
     }  
     - `languages` may contain **up to 4 entries**.  
     - Keys = language names (e.g., `\"python\"`, `\"cURL\"`, `\"javascript\"`, `\"go\"`).  
     - Values = code as a string.  

4. **Flexibility:**  
   - You can create as many pages as needed.  
   - You can include any combination of text and code snippets per page.  
   - Order text/code in a way that feels natural for documentation.

---

## Example Input → Output

**Input:**  
This API lets you fetch user data. First, authenticate with your API key. Then, call the `/users` endpoint.

**Output:**  
{
  \"pages\": [
    {
      \"title\": \"Quickstart\",
      \"content\": [
        {
          \"type\": \"text\",
          \"value\": \"To begin, authenticate using your API key.\"
        },
        {
          \"type\": \"code_snippet\",
          \"languages\": {
            \"python\": \"import requests\\nrequests.get('https://api.example.com/users', headers={'Authorization': 'Bearer API_KEY'})\",
            \"cURL\": \"curl -H 'Authorization: Bearer API_KEY' https://api.example.com/users\"
          }
        }
      ]
    },
    {
      \"title\": \"Endpoints\",
      \"content\": [
        {
          \"type\": \"text\",
          \"value\": \"The `/users` endpoint fetches all users associated with your account.\"
        },
        {
          \"type\": \"code_snippet\",
          \"languages\": {
            \"javascript\": \"fetch('https://api.example.com/users', { headers: { Authorization: 'Bearer API_KEY' } })\",
            \"go\": \"resp, _ := http.Get(\\\"https://api.example.com/users\\\")\"
          }
        }
      ]
    }
  ]
}


### Bot detection and management
Most bot managers (e.g. Akamai Bot Manager) do not outright prevent the use of bots. Instead, they allow the 'nice' bots in, while denying the 'bad' bots. As long as requests are mirrored closely. most bot managers will allow bots to use the backend. 
IMPORTANT:
*Do not* include long requests such as sensor-data, etc. They are most likely optional."""),
        ],
    )

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=generate_content_config,
    )
    full_output_text = response.text or ""
    print(full_output_text)
    # Extract JSON from possible Markdown fences and write a real JSON object
    json_text = full_output_text.strip()
    if json_text.startswith("```"):
        first_brace = json_text.find("{")
        last_brace = json_text.rfind("}")
        if first_brace != -1 and last_brace != -1:
            json_text = json_text[first_brace:last_brace + 1]
    data = json.loads(json_text)
    with open("documentation.json", "w") as f:
        json.dump(data, f, indent=2)

if __name__ == "__main__":
    generate()
