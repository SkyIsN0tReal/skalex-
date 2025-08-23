import json
import os
import subprocess
import sys
import tempfile
import threading
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
        data = request.json
        user_message = data.get('message', '').strip()
        session_id = data.get('session_id', 'default')
        
        if not user_message:
            return jsonify({"error": "Message is required"}), 400
        
        session = get_session(session_id)
        message_history = session["message_history"]
        
        message_history.append({
            "role": "user", 
            "content": [{"type": "input_text", "text": user_message}]
        })
        
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
                message_history.append({
                    "type": "function_call",
                    "id": function_call_data["id"],
                    "call_id": function_call_data["call_id"],
                    "name": function_call_data["name"],
                    "arguments": function_call_data["arguments"]
                })
                
                code_to_execute = json.loads(function_call_data["arguments"])["code"]
                execution_result = execute_python_code(code_to_execute)
                
                message_history.append({
                    "type": "function_call_output",
                    "call_id": function_call_data["call_id"],
                    "output": json.dumps(execution_result)
                })
                
                if execution_result["error"] and execution_result["returncode"] != 0:
                    assistant_response = f"Code Output:\n{execution_result['result']}\n\nError:\n{execution_result['error']}"
                else:
                    assistant_response = f"Code Output:\n{execution_result['result']}"
                
                return jsonify({
                    "response": assistant_response,
                    "code_executed": code_to_execute,
                    "execution_result": execution_result
                })
            else:
                raise Exception("No function call")
                
        except:
            content = dictionary["output"][0]["content"]
            assistant_response = content[0]["text"] if isinstance(content, list) else str(content)
            
            message_history.append({
                "id": dictionary["output"][0]["id"],
                "role": "assistant",
                "content": content
            })
            
            return jsonify({"response": assistant_response})
            
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