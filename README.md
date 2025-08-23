# Chat Agent

A web-based chat interface that connects to an AI agent capable of executing Python code.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up your OpenAI API key:
```bash
cp env_example.txt .env
# Edit .env and add your OpenAI API key
```

3. Run the server:
```bash
cd agent
python agent.py
```

4. Open your browser to `http://localhost:5000`

## Features

- Web-based chat interface
- AI agent with Python code execution capabilities
- Session management
- Real-time code execution with output display
- Modern, responsive UI

## API Endpoints

- `GET /` - Serves the chat interface
- `POST /chat` - Send messages to the agent
- `GET /sessions/<session_id>/history` - Get chat history
- `POST /sessions/<session_id>/clear` - Clear session

## Usage

Simply type your questions or requests in the chat interface. The agent can:
- Answer questions about SAT topics
- Execute Python code
- Perform calculations
- Help with programming tasks
