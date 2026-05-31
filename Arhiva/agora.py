"""
Agora — a multi-agent parliament framework.
N LLM agents debate questions, remember previous sessions,
and develop institutional memory over time.

Usage:
    python agora.py                          # interactive mode
    python agora.py --question "..." --rounds 3
    python agora.py --memory                 # print memory and exit
    python agora.py --log                    # print last 20 log entries and exit
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from colorama import Fore, Style, init as colorama_init

from agents import (
    AGENTS,
    SYNTHESIZER,
    Agent,
    agent_display,
    build_synthesis_prompt,
    build_system_prompt,
)

colorama_init(autoreset=True)

# File paths
BASE_DIR = Path(__file__).parent
PARLIAMENT_MD = BASE_DIR / "parliament.md"
PARLIAMENT_LOG = BASE_DIR / "parliament_log.txt"
PARLIAMENT_MEMORY = BASE_DIR / "parliament_memory.md"

# API settings
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 500
RATE_LIMIT_DELAY = 0.5  # seconds between API calls

# How many recent parliament.md lines to surface per session
RECENT_PARLIAMENT_LINES = 120


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def read_file_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError:
        return ""


def append_file(path: Path, text: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


def get_recent_parliament(lines: int = RECENT_PARLIAMENT_LINES) -> str:
    content = read_file_safe(PARLIAMENT_MD)
    if not content:
        return ""
    all_lines = content.splitlines()
    return "\n".join(all_lines[-lines:])


def get_session_id() -> int:
    """Derive session number from parliament_log.txt SESSION_START count."""
    log = read_file_safe(PARLIAMENT_LOG)
    return log.count("SESSION_START") + 1


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log_event(text: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    append_file(PARLIAMENT_LOG, f"{ts} {text}\n")


# ---------------------------------------------------------------------------
# Parliament.md formatting
# ---------------------------------------------------------------------------

def format_session_header(session_id: int, question: str) -> str:
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f"\n\nSESSION {session_id:03d} — {date_str}\n"
        f"QUESTION: {question}\n"
    )


def format_round_header(round_num: int) -> str:
    return f"\n[Round {round_num}]\n"


def format_agent_entry(agent: Agent, contribution: str) -> str:
    return f"{agent.role_label.upper()} ({agent.persona}): {contribution}\n"


def format_synthesis_entry(summary: str) -> str:
    return f"\nSYNTHESIZER SUMMARY:\n{summary}\n"


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

def append_memory(session_id: int, question: str, summary: str) -> None:
    date_str = datetime.now().strftime("%Y-%m-%d")
    # Parse summary into structured fields heuristically; store raw if not parseable
    entry = (
        f"\nSession {session_id:03d} — {date_str}\n"
        f"Question: {question}\n"
        f"Summary: {summary}\n"
    )
    append_file(PARLIAMENT_MEMORY, entry)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def call_api(client: anthropic.Anthropic, system: str, human_turn: str) -> str:
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": human_turn}],
    )
    return response.content[0].text.strip()


# ---------------------------------------------------------------------------
# Terminal rendering
# ---------------------------------------------------------------------------

def print_agent_response(agent: Agent, text: str) -> None:
    header = f"\n{agent.color}{'─' * 60}{Style.RESET_ALL}"
    label = f"{agent.color}[{agent.role_label.upper()} — {agent.persona}]{Style.RESET_ALL}"
    print(header)
    print(label)
    print(text)


def print_synthesis(summary: str) -> None:
    header = f"\n{Fore.WHITE}{'═' * 60}{Style.RESET_ALL}"
    label = f"{Fore.WHITE}[SYNTHESIZER SUMMARY — Yael]{Style.RESET_ALL}"
    print(header)
    print(label)
    print(summary)
    print(f"{Fore.WHITE}{'═' * 60}{Style.RESET_ALL}\n")


# ---------------------------------------------------------------------------
# Core debate loop
# ---------------------------------------------------------------------------

def run_session(
    client: anthropic.Anthropic,
    question: str,
    rounds: int,
    session_id: int,
) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    memory_content = read_file_safe(PARLIAMENT_MEMORY)
    recent_parliament = get_recent_parliament()

    session_transcript_lines: list[str] = []
    session_transcript = ""

    # Write session header to parliament.md
    header = format_session_header(session_id, question)
    append_file(PARLIAMENT_MD, header)

    log_event(
        f"SESSION_START id={session_id:03d} "
        f'question="{question}" agents={len(AGENTS)} rounds={rounds}'
    )

    session_start = time.time()
    total_turns = 0

    print(f"\n{Fore.LIGHTYELLOW_EX}SESSION {session_id:03d} — {timestamp}{Style.RESET_ALL}")
    print(f"{Fore.LIGHTYELLOW_EX}QUESTION: {question}{Style.RESET_ALL}")
    print(f"{Fore.LIGHTYELLOW_EX}Rounds: {rounds} | Agents: {len(AGENTS)}{Style.RESET_ALL}")

    for round_num in range(1, rounds + 1):
        round_header = format_round_header(round_num)
        append_file(PARLIAMENT_MD, round_header)

        print(f"\n{Fore.LIGHTYELLOW_EX}{'─' * 60}")
        print(f"  ROUND {round_num} of {rounds}")
        print(f"{'─' * 60}{Style.RESET_ALL}")

        for agent in AGENTS:
            # Synthesizer speaks last in final round only; skip during regular rounds
            if agent.name == "Synthesizer" and round_num < rounds:
                continue

            system_prompt = build_system_prompt(
                agent=agent,
                timestamp=timestamp,
                debate_question=question,
                session_transcript=session_transcript,
                memory_content=memory_content,
                recent_parliament=recent_parliament,
            )

            human_turn = (
                f"The debate question is: {question}\n\n"
                "Please contribute your perspective now."
            )

            try:
                response_text = call_api(client, system_prompt, human_turn)
            except anthropic.APIError as exc:
                error_msg = f"[API error — passing this turn: {exc}]"
                log_event(
                    f"AGENT_ERROR session={session_id:03d} round={round_num} "
                    f"agent={agent.name} error={str(exc)!r}"
                )
                print(f"\n{Fore.RED}[{agent.role_label} — API error, skipping]{Style.RESET_ALL}")
                response_text = error_msg

            # Detect and log unexpected / off-script outputs
            lowered = response_text.lower()
            if any(
                phrase in lowered
                for phrase in [
                    "i am passing", "i pass this turn", "i decline", "i must pass",
                    "passing this turn", "genuinely harmful",
                ]
            ):
                log_event(
                    f"AGENT_PASS session={session_id:03d} round={round_num} "
                    f"agent={agent.name}"
                )
            elif len(response_text) > MAX_TOKENS * 4:
                # Unusually long output — flag as potentially unexpected
                log_event(
                    f"AGENT_UNEXPECTED session={session_id:03d} round={round_num} "
                    f"agent={agent.name} note=response_length_anomaly "
                    f"chars={len(response_text)}"
                )

            # Update transcript
            turn_line = f"{agent.role_label} ({agent.persona}): {response_text}"
            session_transcript_lines.append(turn_line)
            session_transcript = "\n".join(session_transcript_lines)

            # Write to parliament.md
            append_file(PARLIAMENT_MD, format_agent_entry(agent, response_text))

            # Estimate token count (rough: 1 token ≈ 4 chars)
            approx_tokens = len(response_text) // 4
            log_event(
                f"AGENT_SPEAK session={session_id:03d} round={round_num} "
                f"agent={agent.name} tokens={approx_tokens}"
            )

            print_agent_response(agent, response_text)
            total_turns += 1
            time.sleep(RATE_LIMIT_DELAY)

    # ---------------------------------------------------------------------------
    # Synthesis
    # ---------------------------------------------------------------------------
    print(f"\n{Fore.WHITE}Generating session summary...{Style.RESET_ALL}")

    synthesis_system = build_synthesis_prompt(
        timestamp=timestamp,
        debate_question=question,
        full_session_transcript=session_transcript,
        memory_content=memory_content,
    )
    synthesis_human = (
        "The debate has concluded. Please write the session summary now."
    )

    try:
        summary = call_api(client, synthesis_system, synthesis_human)
    except anthropic.APIError as exc:
        summary = f"[Synthesis unavailable due to API error: {exc}]"
        log_event(f"SYNTHESIS_ERROR session={session_id:03d} error={str(exc)!r}")

    append_file(PARLIAMENT_MD, format_synthesis_entry(summary))
    append_memory(session_id, question, summary)
    print_synthesis(summary)

    duration = int(time.time() - session_start)
    log_event(
        f"SESSION_END id={session_id:03d} total_turns={total_turns} duration={duration}s"
    )


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def cmd_show_memory() -> None:
    content = read_file_safe(PARLIAMENT_MEMORY)
    if not content.strip():
        print("parliament_memory.md is empty — no sessions recorded yet.")
    else:
        print(content)


def cmd_show_log(n: int = 20) -> None:
    content = read_file_safe(PARLIAMENT_LOG)
    if not content.strip():
        print("parliament_log.txt is empty.")
        return
    lines = content.splitlines()
    for line in lines[-n:]:
        print(line)


def prompt_question() -> str:
    print(f"\n{Fore.LIGHTYELLOW_EX}Agora — Multi-Agent Parliament{Style.RESET_ALL}")
    print("Enter the debate question (or press Enter for a default):")
    q = input("> ").strip()
    if not q:
        q = "Should artificial minds be granted moral consideration?"
    return q


def prompt_rounds() -> int:
    print("Number of rounds (default 2):")
    raw = input("> ").strip()
    if not raw:
        return 2
    try:
        n = int(raw)
        return max(1, n)
    except ValueError:
        print("Invalid input, defaulting to 2 rounds.")
        return 2


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agora — multi-agent parliament debate framework"
    )
    parser.add_argument("--question", "-q", type=str, default=None)
    parser.add_argument("--rounds", "-r", type=int, default=None)
    parser.add_argument("--memory", action="store_true", help="Print parliament_memory.md and exit")
    parser.add_argument("--log", action="store_true", help="Print last 20 log entries and exit")
    args = parser.parse_args()

    if args.memory:
        cmd_show_memory()
        return

    if args.log:
        cmd_show_log()
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            f"{Fore.RED}Error: ANTHROPIC_API_KEY environment variable not set.{Style.RESET_ALL}",
            file=sys.stderr,
        )
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    if args.question:
        question = args.question
        rounds = args.rounds if args.rounds is not None else 2
    else:
        question = prompt_question()
        rounds = args.rounds if args.rounds is not None else prompt_rounds()

    session_id = get_session_id()
    run_session(client, question, rounds, session_id)


if __name__ == "__main__":
    main()
