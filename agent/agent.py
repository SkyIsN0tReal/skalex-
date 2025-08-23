import json
from openai import OpenAI
import os
import subprocess
import sys
with open("sat_docs.json", "r") as f:
    sat_docs = json.load(f)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

message_history = [{"role": "system", "content": "You are a helpful assistant that can execute python code. When executing code, always *print* the result. NEVER use notebook style output. Here are sone relevant SAT docs: " + json.dumps(sat_docs)}]
skip_input = False
while True:
    if not skip_input:
        user_input = input("You: ")
        if user_input == "exit":
            break
        message_history.append({"role": "user", "content": [{"type": "input_text", "text": user_input}]})
    else:
        skip_input = False
        

    response = client.responses.create(
    model="gpt-4.1",
    input=message_history,
    text={
        "format": {
        "type": "text"
        }
    },
    reasoning={},
    tools=[
        {
        "type": "function",
        "name": "run_python_code",
        "description": "Execute a given Python code snippet and return the result. ",
        "parameters": {
            "type": "object",
            "properties": {
            "code": {
                "type": "string",
                "description": "Python code to execute"
            }
            },
            "required": [
            "code"
            ],
            "additionalProperties": False
        },
        "strict": True
        }
    ],
    temperature=1,
    max_output_tokens=2048,
    top_p=1,
    store=True
    )
    dictionary = response.model_dump()
    try:
        function_call = dictionary["output"][0]["arguments"]
        function_call = True
        message_history.append({"type": "function_call", "id": dictionary["output"][0]["id"], "call_id": dictionary["output"][0]["call_id"], "name": dictionary["output"][0]["name"], "arguments": dictionary["output"][0]["arguments"]})
        code_to_execute = json.loads(dictionary["output"][0]["arguments"])["code"]
        with open("temp_code.py", "w") as f:
            f.write(code_to_execute)
        result = subprocess.run([sys.executable, "temp_code.py"], capture_output=True, text=True)
        output = result.stdout
        error = result.stderr
        print("Output: " + output)
        if error or result.returncode != 0:
            print("Error: " + error)
        message_history.append({"type": "function_call_output", "call_id": dictionary["output"][0]["call_id"], "output": json.dumps({"result": output, "error": error, "returncode": result.returncode})})
        skip_input = True
    except:

        function_call = False
        message_history.append({"id": dictionary["output"][0]["id"], "role": "assistant", "content": dictionary["output"][0]["content"]})
        print(dictionary["output"][0]["content"][0]["text"])


print(json.dumps(message_history, indent=4))