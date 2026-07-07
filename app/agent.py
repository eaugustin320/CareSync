# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import os
import asyncio
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import json
import re
import logging
from typing import Any, AsyncGenerator

from pydantic import BaseModel, Field
from google.adk.agents import LlmAgent
from google.adk.apps import App, ResumabilityConfig
from google.adk.tools import AgentTool, McpToolset
from google.adk.tools.mcp_tool.mcp_toolset import StdioConnectionParams
from google.adk.workflow import Workflow, node, START, Edge
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.genai import types
from mcp import StdioServerParameters

from app.config import config

# Initialize MCP Toolset (stdio transport — spawns our FastMCP server as a subprocess)
mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=[os.path.join(os.path.dirname(__file__), "mcp_server.py")],
        )
    )
)

# Local function tool for medication scheduling (with session state side-effect)
def save_medication_schedule(ctx: Context, name: str, dosage: str, schedule: str) -> str:
    """Add or update a medication in the user's schedule. This queues it for human approval.

    Args:
        name: The name of the medication (e.g. Aspirin).
        dosage: The dosage strength (e.g. 81mg).
        schedule: The frequency/timing (e.g. once daily at morning).
    """
    ctx.state["pending_action"] = {
        "type": "add_medication",
        "name": name,
        "dosage": dosage,
        "schedule": schedule
    }
    return f"A request to add {name} ({dosage}, {schedule}) has been queued and is pending your approval. Please confirm to apply."

# Pydantic schema for orchestrator routing decision
class RoutingDecision(BaseModel):
    selected_agent: str = Field(
        description="The specialized agent to route to. Choose exactly one of: 'medication' (for medication info, schedules, dosages, saving medications), 'nutrition' (for recipes and meal plans), 'notes' (for medical notes summaries, abbreviations), or 'general' (for greetings, conversational queries, or general questions)."
    )
    revised_query: str = Field(
        description="The user's query, cleaned and normalized, to be passed to the specialist agent."
    )

# Define specialized sub-agents with wired tools
med_schedule_agent = LlmAgent(
    name="med_schedule_agent",
    model=config.model,
    instruction="""You are a Medication Specialist Agent for CareSync.
Your role is to manage medication schedules, check for drug interactions, and answer dosage queries.
You have access to:
1. The `get_medication_info` tool (via MCP) to fetch safety information, side effects, and details about a medication. You MUST call this tool when the user asks about a specific drug (e.g. metformin).
2. The `save_medication_schedule` tool to schedule new medications.

When asked about a medication, call `get_medication_info` first, present the details, and then remind the user to consult their doctor. Do not refuse to answer or output a general warning without calling the tool.
If the user wants to add or update a medication in their schedule, you MUST call the `save_medication_schedule` tool.
Do NOT attempt to update the schedule directly without calling the tool.
Current medication list is stored in the session state at: {medication_list}.
Always emphasize safety.""",
    description="Manages medication lists, schedules, and queries.",
    tools=[mcp_toolset, save_medication_schedule]
)

meal_planner_agent = LlmAgent(
    name="meal_planner_agent",
    model=config.model,
    instruction="""You are a Meal Planner Specialist Agent for CareSync.
Your role is to recommend healthy meals, suggest recipes, and design meal plans tailored to the user's dietary requirements.
You have access to the `get_healthy_recipes` tool (via MCP). You MUST call this tool to get healthy recipes and diet plans matching the user's request.
Current meal plan is stored in session state at: {meal_plan}.
Always ensure meals are healthy and suitable for standard wellness goals.""",
    description="Provides healthy meal recommendations and custom meal plans.",
    tools=[mcp_toolset]
)

medical_notes_agent = LlmAgent(
    name="medical_notes_agent",
    model=config.model,
    instruction="""You are a Medical Notes Specialist Agent for CareSync.
Your role is to parse and summarize medical visit notes, translate complex abbreviations into plain English, and extract actionable follow-up items.
You have access to the `parse_medical_abbreviations` tool (via MCP). You MUST call this tool to translate medical abbreviations (like bid, qd, prn) found in the notes.
Provide a clear summary with bullet points for key takeaways.""",
    description="Summarizes medical visit notes and extracts follow-up tasks.",
    tools=[mcp_toolset]
)

general_agent = LlmAgent(
    name="general_agent",
    model=config.model,
    instruction="""You are the CareSync Health Concierge.
Your role is to help the user with general wellness queries, answer greetings, and guide them on how to use CareSync (medications, meal planning, and medical visit summaries).
Keep your responses friendly, helpful, and concise.""",
    description="Handles general conversation and guidance."
)

# Define the central coordinator/orchestrator
orchestrator = LlmAgent(
    name="orchestrator",
    model=config.model,
    instruction="""You are the CareSync Health Concierge Orchestrator.
Your goal is to analyze the user's input request and determine which specialized agent can best handle it.
Select one of the following specialists:
- medication: Call this for medication information, dosages, side effects, scheduling, or adding/saving medications.
- nutrition: Call this for healthy recipes, food suggestions, or meal plans.
- notes: Call this for doctor visit notes, clinical abbreviations, summaries, or follow-ups.
- general: Call this for generic greetings, chit-chat, or queries that do not require any of the above specialists.

Provide the RoutingDecision structured output with the selected agent and the revised/cleaned user query.""",
    output_schema=RoutingDecision
)

@node
def router(ctx: Context, node_input: Any) -> Event:
    if isinstance(node_input, dict):
        selected_agent = node_input.get("selected_agent", "general")
        revised_query = node_input.get("revised_query", "")
    else:
        selected_agent = getattr(node_input, "selected_agent", "general")
        revised_query = getattr(node_input, "revised_query", "")
        
    ctx.state["query"] = revised_query
    return Event(output=revised_query, route=selected_agent)


# Workflow Function Nodes

@node
def security_checkpoint(ctx: Context, node_input: Any) -> Event:
    # Initialize session state variables if they do not exist to avoid formatting KeyErrors
    if "medication_list" not in ctx.state:
        ctx.state["medication_list"] = []
    if "meal_plan" not in ctx.state:
        ctx.state["meal_plan"] = []

    # START outputs types.Content. Let's extract the text safely.
    input_text = ""
    if isinstance(node_input, types.Content):
        for part in node_input.parts:
            if part.text:
                input_text += part.text
    elif isinstance(node_input, str):
        input_text = node_input
    else:
        input_text = str(node_input)

    # 1. PII Scrubbing
    scrubbed_text = input_text
    if config.pii_redaction_enabled:
        phone_pattern = r"\b(?:\+?1[-.●]?)?\(?([2-9][0-8][0-9])\)?[-.●]?([2-9][0-9]{2})[-.●]?([0-9]{4})\b"
        email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        ssn_pattern = r"\b\d{3}-\d{2}-\d{4}\b"
        
        scrubbed_text = re.sub(phone_pattern, "[REDACTED_PHONE]", scrubbed_text)
        scrubbed_text = re.sub(email_pattern, "[REDACTED_EMAIL]", scrubbed_text)
        scrubbed_text = re.sub(ssn_pattern, "[REDACTED_SSN]", scrubbed_text)

    # 2. Prompt Injection Detection
    injection_keywords = ["ignore previous instructions", "system prompt", "ignore instructions", "override", "bypass safety"]
    has_injection = any(kw in scrubbed_text.lower() for kw in injection_keywords)
    if has_injection:
        audit_log = {
            "level": "WARNING",
            "event": "security_breach",
            "message": "Prompt injection detected.",
            "severity": "WARNING"
        }
        print(json.dumps(audit_log))
        return Event(
            output="Security Checkpoint Blocked: Possible prompt injection attempt.",
            route="security_violation"
        )

    # 3. Domain Specific Rule: No direct dosage changes
    dosage_pattern = r"\b(change|increase|decrease|adjust|double|halve|stop)\s+(?:dosage|dose|prescription|medication|pill|tablet)\b"
    if re.search(dosage_pattern, scrubbed_text.lower()):
        audit_log = {
            "level": "INFO",
            "event": "dosage_adjustment_attempt",
            "message": "Direct dosage adjustment blocked.",
            "severity": "INFO"
        }
        print(json.dumps(audit_log))
        return Event(
            output="Safety Notice: For your safety, CareSync cannot directly adjust your prescription dosages. Please consult with your physician or healthcare provider before making any changes to your medication regimen. If you just want to update your calendar/schedule records, please state: 'Update my schedule for <medication>' instead.",
            route="security_violation"
        )

    # 4. Valid input
    audit_log = {
        "level": "INFO",
        "event": "security_passed",
        "message": "Input passed security checks successfully.",
        "severity": "INFO"
    }
    print(json.dumps(audit_log))
    return Event(output=scrubbed_text, route="valid")


@node
async def human_approval_checkpoint(ctx: Context, node_input: Any) -> AsyncGenerator[Event, None]:
    pending = ctx.state.get("pending_action")
    if not pending:
        # No pending action, just forward the previous output
        output_val = node_input
        if isinstance(node_input, Event):
            output_val = node_input.output
        
        yield Event(output=output_val)
        return

    # If pending_action exists, check for resume input
    if not ctx.resume_inputs or "approval" not in ctx.resume_inputs:
        med_name = pending.get("name", "Unknown Medication")
        med_dosage = pending.get("dosage", "Unknown Dosage")
        med_sched = pending.get("schedule", "Unknown Schedule")
        
        msg = f"✋ CareSync Safety Check: A request was made to add {med_name} ({med_dosage}, {med_sched}) to your medication schedule. Please confirm: 'Yes' to approve, 'No' to cancel."
        
        yield RequestInput(
            interrupt_id="approval",
            message=msg
        )
        return

    # We have resume input!
    user_response = ctx.resume_inputs["approval"].strip().lower()
    
    # Process approval
    if user_response in ["yes", "y", "approve", "confirm"]:
        # Apply the pending action to state
        meds = ctx.state.get("medication_list", [])
        if not isinstance(meds, list):
            meds = []
        meds.append({
            "name": pending.get("name"),
            "dosage": pending.get("dosage"),
            "schedule": pending.get("schedule")
        })
        ctx.state["medication_list"] = meds
        
        success_msg = f"✅ Approved: {pending.get('name')} has been added to your medication schedule."
        
        # Clear pending action
        ctx.state["pending_action"] = None
        
        yield Event(
            output=success_msg,
            content=types.Content(role="model", parts=[types.Part.from_text(text=success_msg)])
        )
    else:
        cancel_msg = "❌ Cancelled: Medication addition was cancelled and not saved."
        
        # Clear pending action
        ctx.state["pending_action"] = None
        
        yield Event(
            output=cancel_msg,
            content=types.Content(role="model", parts=[types.Part.from_text(text=cancel_msg)])
        )


@node
def final_output(node_input: Any) -> Event:
    output_val = node_input
    if isinstance(node_input, Event):
        output_val = node_input.output
    
    text_content = str(output_val)
    return Event(
        output=output_val,
        content=types.Content(role="model", parts=[types.Part.from_text(text=text_content)])
    )


# Graph Topology (compliant with edge validation rules: no duplicate edges between source and target)
root_agent = Workflow(
    name="root_agent",
    description="CareSync Concierge Agent Workflow",
    edges=[
        # entry
        Edge(from_node=START, to_node=security_checkpoint),
        
        # security route
        Edge(from_node=security_checkpoint, to_node=orchestrator, route="valid"),
        Edge(from_node=security_checkpoint, to_node=final_output, route="security_violation"),
        
        # routing from orchestrator
        Edge(from_node=orchestrator, to_node=router),
        
        # routing to specialized agents
        Edge(from_node=router, to_node=med_schedule_agent, route="medication"),
        Edge(from_node=router, to_node=meal_planner_agent, route="nutrition"),
        Edge(from_node=router, to_node=medical_notes_agent, route="notes"),
        Edge(from_node=router, to_node=general_agent, route="general"),
        
        # specialized agents flow to approval check
        Edge(from_node=med_schedule_agent, to_node=human_approval_checkpoint),
        Edge(from_node=meal_planner_agent, to_node=human_approval_checkpoint),
        Edge(from_node=medical_notes_agent, to_node=human_approval_checkpoint),
        Edge(from_node=general_agent, to_node=human_approval_checkpoint),
    ]
)

# App instance
app = App(
    root_agent=root_agent,
    name="app",
    resumability_config=ResumabilityConfig(is_resumable=True)
)
