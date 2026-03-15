# Project: "SDE-3 Personal Mentor Agent"
## Goal: A Multi-Agent system to bridge the 10% gap in DSA and System Design.

### 1. Core Architecture
- **Framework:** LangGraph (Stateful Orchestrator)
- **API:** FastAPI
- **Database:** PostgreSQL with pgvector (via SQLAlchemy)
- **LLMs:** - Primary Brain (Critic/Grader): Claude 3.5 Sonnet (for coding precision)
    - Researcher/Strategist: Gemini 1.5 Pro (for long context memory)

### 2. Multi-Agent Nodes (The Crew)
1. **The Strategist (Researcher):** - Role: Scans the user's `knowledge_graph` in the Vector DB.
   - Task: Identifies gaps (e.g., "Weak in Reactive Patterns/Vert.x" or "Needs work on Trie Hard").
2. **The Trend Scraper:**
   - Role: Uses Tavily API to fetch real-time interview questions from LeetCode Discuss/Reddit for companies like Visa, Google, and Meta.
3. **The Question Setter:**
   - Role: Generates a custom task or mock interview prompt based on Researcher findings and Scraper trends.
4. **The Evaluator (The Senior Lead):**
   - Role: Reviews user code/diagrams. 
   - Strict Criteria: Must check for Time/Space Complexity, Thread Safety, and Distributed System constraints (Sharding, Rate Limiting, Saga patterns).

### 3. Integrations (The Data Plane)
- **WhatsApp:** Use Twilio/FastAPI Webhook for daily communication.
- **LeetCode/GitHub:** Read a local directory or Git repo to track daily problem-solving progress.
- **State Persistence:** Use `SqliteSaver` or `PostgresSaver` in LangGraph so the "Teacher" remembers the user's progress across days.

### 4. Shared State Definition
```python
class AgentState(TypedDict):
    user_id: str
    current_topic: str
    interview_stage: str # 'idle', 'testing', 'review'
    knowledge_gap_score: float
    recent_trend_context: str
    feedback_history: List[dict]
```

### 5. Execution Instructions for Cursor
1. Generate a Python FastAPI project structure.
2. Implement langgraph state machine logic as described above.
3. Integrate pgvector for the "Memory" layer.
4. Create a specialized system prompt for the "Evaluator" that mimics a Senior Staff Engineer at a fintech company (Visa-style rigor).
5. Set up a Mock WhatsApp Webhook endpoint to simulate interactions.

#### Context Note for AI:
The user is a Senior Software Engineer at Visa/Grid Dynamics with 7+ years of experience. He knows 90% of DSA/System Design. Do not waste time on basics. Focus on edge cases, high-concurrency bugs, and distributed system trade-offs.

---

### What to do after the code is generated:
Once Cursor builds the files, your next move should be to connect the "Eyes" of the system.

**Would you like me to help you write the specific "Scraper Logic" using Tavily so your agent can start finding those trending Visa/Goyesogle interview questions right away?**