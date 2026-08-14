# Module 2 Phase 1 Mini-Project — Study Guide Agent

This project implements the same Study Guide Agent using LangGraph and CrewAI.
The agent explains a topic, provides a practical example and a common misconception, and creates a three-question quiz with answers.

## Setup and Run Commands

Create and activate the virtual environment:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the required dependencies:

```powershell
pip install -r requirements.txt
```

Create a `.env` file and add the OpenRouter API key:

```text
OPENROUTER_API_KEY=your_api_key_here
```

Run the LangGraph implementation:

```powershell
python .\study_guide_langgraph.py "Model Context Protocol"
```

Run the CrewAI implementation:

```powershell
python .\study_guide_crewai.py "Model Context Protocol"
```

## Tested Topics

Both implementations were tested using the same topics:

- Model Context Protocol
- Temperature in language models

## Observations

1. **LangGraph made the control flow explicit.**  
   I had to create the three nodes and manually connect them with edges. I also used the state to pass the explanation.

2. **CrewAI automated more of the orchestration.**  
   Instead of creating nodes and edges, I defined one agent and three tasks, used context to pass previous results, and used a sequential process to control the task order.

3. **For this three-task pipeline, I would choose CrewAI.**  
   I found it simpler and faster because the workflow is sequential and does not require complex branching. LangGraph would be more useful if I needed more control, conditions, or loops.