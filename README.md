# Banking Agent

A conversational AI agent system for banking operations, built with LangChain and LangGraph. The system provides intelligent query routing, SQL database access, RAG, web search, and fraud detection capabilities.

## Features

- **Intelligent Routing**: Automatically routes user queries to appropriate agents
- **SQL Database Access**: Query customer transaction database
- **RAG (Retrieval-Augmented Generation)**: Knowledge base search using Pinecone
- **Web Search**: Real-time web search using Tavily
- **Fraud Detection**: ML-based transaction fraud detection
- **Conversation Memory**: Redis-backed conversation history management

## Prerequisites

- Python 3.10+
- Docker (for running Redis)
- PostgreSQL database access
- API keys for:
  - OpenAI (for LLM)
  - Pinecone (optional, for RAG)
  - Tavily (optional, for web search)

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/NaNa7Miiii/Banking_Agent.git
   cd Banking_Agent
   git checkout jiarui
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

## Setting Up Redis with Docker

The project uses Redis for conversation memory storage. Redis runs locally using Docker.

### Using Docker to Run Redis

1. **Pull and run Redis container**
   ```bash
   docker run -d \
     --name redis-banking-agent \
     -p 6379:6379 \
     redis:latest
   ```

2. **Verify Redis is running**
   ```bash
   docker ps
   # You should see redis-banking-agent container running
   ```

3. **Test Redis connection** (optional)
   ```bash
   docker exec -it redis-banking-agent redis-cli ping
   # Should return: PONG
   ```

### Redis Management Commands

- **Stop Redis container**:
  ```bash
  docker stop redis-banking-agent
  ```

- **Start Redis container**:
  ```bash
  docker start redis-banking-agent
  ```

- **Remove Redis container** (when you no longer need it):
  ```bash
  docker stop redis-banking-agent
  docker rm redis-banking-agent
  ```

### Redis Configuration

The application connects to Redis at `localhost:6379` by default. This is configured in `src/graph/utils/memory.py`:

```python
REDIS_HOST = "localhost"
REDIS_PORT = 6379
```

If you need to change the Redis configuration, modify these values in `src/graph/utils/memory.py`.

## Environment Configuration

Create a `.env` file in the project root directory with the following variables:

```env
# Database Configuration (Required)
DB_HOST=your-database-host.rds.amazonaws.com
DB_PASSWORD=your-database-password

# Optional Database Settings (have defaults)
DB_USERNAME=postgres
DB_PORT=5432
DB_DATABASE=customer_transaction_db
DB_TABLE_NAME=transactions

# API Keys (Optional)
OPENAI_API_KEY=your-openai-api-key
PINECONE_API_KEY=your-pinecone-api-key
TAVILY_SEARCH_KEY=your-tavily-api-key
```

## Usage

### Basic Chat Interface

```bash
python src/chat_interface.py "<user_query>" <customer_id_number> [session_id] [--summary]
```

**Example**:
```bash
python src/chat_interface.py "What are my recent transactions?" "12345"
```

**Arguments**:
- `user_query`: The user's question or request
- `customer_id_number`: Customer ID for the query
- `session_id`: (Optional) Session ID for conversation continuity
- `--summary`: (Optional) Enable conversation summary

### Using as Python Module

```python
from src.chat_interface import chat

result = chat(
    user_input="What are my recent transactions?",
    customer_id_number="12345",
    session_id="session-123",
    summary=True
)

print(result["final_answer"])
```

## Project Structure

```
agent_bank/
├── src/
│   ├── chat_interface.py      # Main chat interface
│   ├── config.py               # Configuration management
│   ├── graph/                  # LangGraph components
│   │   ├── graphs/            # Main graph definitions
│   │   ├── modules/           # Agent modules
│   │   ├── models/            # LLM models
│   │   ├── prompts/           # Prompt templates
│   │   ├── rag/               # RAG utilities
│   │   └── utils/             # Utilities (including Redis memory)
│   └── data/                  # Data processing utilities
├── requirements.txt            # Python dependencies
└── README.md                  # This file
```

## Agent Capabilities

1. **Router Agent**: Determines the appropriate agent for each query
2. **SQL Agent**: Executes SQL queries on the transaction database
3. **RAG Agent**: Searches knowledge base using vector similarity
4. **Tavily Agent**: Performs web searches for real-time information
5. **Fraud Agent**: Detects potentially fraudulent transactions
