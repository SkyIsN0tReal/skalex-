import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

try:
    with open("/Users/sky/Desktop/skalex/agent/sat2.json", "r") as f:
        sat_docs = json.load(f)
except FileNotFoundError:
    sat_docs = {"error": "SAT docs not found"}

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

sessions = {}

def get_session(session_id):
    if session_id not in sessions:
        sessions[session_id] = {
            "message_history": [
                {
                    "role": "system", 
                    "content": f"You are a helpful assistant that can execute python code. When executing code, always *print* the result. NEVER use notebook style output. Here are some relevant SAT docs: {json.dumps(sat_docs)}"
                }
            ]
        }
    return sessions[session_id]

def execute_python_code(code):
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        result = subprocess.run([sys.executable, temp_file], capture_output=True, text=True, timeout=30)
        os.unlink(temp_file)
        
        return {
            "result": result.stdout,
            "error": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "result": "",
            "error": "Code execution timed out after 30 seconds",
            "returncode": 1
        }
    except Exception as e:
        return {
            "result": "",
            "error": str(e),
            "returncode": 1
        }

@app.route('/')
def serve_frontend():
    return send_from_directory('../frontend/chat', 'index.html')

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json(silent=True) or {}
        user_message = str(data.get('message', '')).strip()
        session_id = data.get('session_id', 'default')
        
        if not user_message:
            return jsonify({"error": "Message is required"}), 400
        
        session = get_session(session_id)
        message_history = session["message_history"]
        
        message_history.append({
            "role": "user", 
            "content": [{"type": "input_text", "text": user_message}]
        })
        
        timeline = []
        timeline.append({"t": time.time(), "type": "user_message", "data": user_message})
        
        max_tool_iterations = 5
        final_response_text = None
        last_executed_code = None
        last_execution_result = None

        for _ in range(max_tool_iterations):
            response = client.responses.create(
                model="gpt-4.1",
                input=message_history,
                text={"format": {"type": "text"}},
                reasoning={},
                tools=[
                    {
                        "type": "function",
                        "name": "run_python_code",
                        "description": "Execute a given Python code snippet and return the result.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "code": {
                                    "type": "string",
                                    "description": "Python code to execute"
                                }
                            },
                            "required": ["code"],
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
                function_call_data = dictionary["output"][0]
                if "arguments" in function_call_data:
                    timeline.append({
                        "t": time.time(),
                        "type": "function_call",
                        "name": function_call_data.get("name"),
                        "arguments": function_call_data.get("arguments")
                    })
                    message_history.append({
                        "type": "function_call",
                        "id": function_call_data.get("id"),
                        "call_id": function_call_data.get("call_id"),
                        "name": function_call_data.get("name"),
                        "arguments": function_call_data.get("arguments")
                    })

                    args_json = function_call_data.get("arguments") or "{}"
                    code_to_execute = json.loads(args_json).get("code", "")
                    last_executed_code = code_to_execute
                    timeline.append({"t": time.time(), "type": "code_executed", "code": code_to_execute})
                    execution_result = execute_python_code(code_to_execute)
                    last_execution_result = execution_result
                    timeline.append({"t": time.time(), "type": "tool_result", "output": execution_result})

                    message_history.append({
                        "type": "function_call_output",
                        "call_id": function_call_data.get("call_id"),
                        "output": json.dumps(execution_result)
                    })
                    continue
                else:
                    raise Exception("No function call")
            except Exception:
                content = dictionary["output"][0]["content"]
                final_response_text = content[0]["text"] if isinstance(content, list) else str(content)
                timeline.append({"t": time.time(), "type": "assistant_message", "content": final_response_text})
                message_history.append({
                    "id": dictionary["output"][0].get("id"),
                    "role": "assistant",
                    "content": content
                })
                break

        if final_response_text is None and last_execution_result is not None:
            if last_execution_result.get("error") and last_execution_result.get("returncode") != 0:
                final_response_text = f"Code Output:\n{last_execution_result.get('result', '')}\n\nError:\n{last_execution_result.get('error', '')}"
            else:
                final_response_text = f"Code Output:\n{last_execution_result.get('result', '')}"

        timeline.sort(key=lambda e: e.get("t", 0))
        return jsonify({
            "response": final_response_text or "",
            "code_executed": last_executed_code,
            "execution_result": last_execution_result,
            "timeline": timeline
        })
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/sessions/<session_id>/history', methods=['GET'])
def get_history(session_id):
    session = get_session(session_id)
    return jsonify({"history": session["message_history"]})

@app.route('/sessions/<session_id>/clear', methods=['POST'])
def clear_session(session_id):
    if session_id in sessions:
        del sessions[session_id]
    return jsonify({"message": "Session cleared"})

if __name__ == "__main__":
    print("Starting chat agent server...")
    print("Frontend available at: http://localhost:8000")
    print("API endpoint: http://localhost:8000/chat")
    app.run(debug=True, host='0.0.0.0', port=8000)