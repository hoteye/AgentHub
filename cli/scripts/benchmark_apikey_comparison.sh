#!/bin/bash

# Comparison test for finding OPENAI_API_KEY
PROMPT="找一找环境变量 OPENAI_API_KEY 是在哪里设置的？"
TEST_DIR="/home/lyc/project/AgentHub/cli"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="/tmp/agenthub_reference_comparison_apikey_${TIMESTAMP}"
TIMEOUT=400

mkdir -p "${LOG_DIR}"

echo "========================================="
echo "Comparison Test - OPENAI_API_KEY Search"
echo "Timestamp: ${TIMESTAMP}"
echo "Log directory: ${LOG_DIR}"
echo "Timeout: ${TIMEOUT} seconds"
echo "========================================="
echo ""

# Test Reference
echo "========================================="
echo "Testing Reference"
echo "========================================="
cd "$TEST_DIR"

echo "Starting Reference at $(date +%H:%M:%S)" | tee "${LOG_DIR}/reference_timeline.log"
timeout ${TIMEOUT} reference exec "$PROMPT" 2>&1 | tee "${LOG_DIR}/reference_full_output.log"
REFERENCE_EXIT=$?
echo "Reference finished at $(date +%H:%M:%S) with exit code: ${REFERENCE_EXIT}" | tee -a "${LOG_DIR}/reference_timeline.log"

# Extract Reference tool calls
echo "" | tee "${LOG_DIR}/reference_tool_calls.log"
echo "=== Reference Tool Calls ===" | tee -a "${LOG_DIR}/reference_tool_calls.log"
grep -n "^exec$" "${LOG_DIR}/reference_full_output.log" | tee -a "${LOG_DIR}/reference_tool_calls.log"
echo "" | tee -a "${LOG_DIR}/reference_tool_calls.log"
echo "Total tool calls: $(grep -c '^exec$' "${LOG_DIR}/reference_full_output.log")" | tee -a "${LOG_DIR}/reference_tool_calls.log"

# Extract Reference agent responses
echo "" | tee "${LOG_DIR}/reference_agent_responses.log"
echo "=== Reference Agent Responses ===" | tee -a "${LOG_DIR}/reference_agent_responses.log"
grep -n "^reference$" "${LOG_DIR}/reference_full_output.log" | tee -a "${LOG_DIR}/reference_agent_responses.log"
echo "" | tee -a "${LOG_DIR}/reference_agent_responses.log"
echo "Total agent responses: $(grep -c '^reference$' "${LOG_DIR}/reference_full_output.log")" | tee -a "${LOG_DIR}/reference_agent_responses.log"

# Extract Reference commands with context
echo "" | tee "${LOG_DIR}/reference_commands_detail.log"
echo "=== Reference Commands Detail ===" | tee -a "${LOG_DIR}/reference_commands_detail.log"
awk '/^exec$/{getline; print NR-1 ": " $0}' "${LOG_DIR}/reference_full_output.log" | tee -a "${LOG_DIR}/reference_commands_detail.log"

echo ""
echo "========================================="
echo "Testing AgentHub"
echo "========================================="
cd "$TEST_DIR"

echo "Starting AgentHub at $(date +%H:%M:%S)" | tee "${LOG_DIR}/agenthub_timeline.log"
timeout ${TIMEOUT} ./scripts/start_agent_cli.sh -- --headless --prompt "$PROMPT" --approval-policy never 2>&1 | tee "${LOG_DIR}/agenthub_full_output.log"
AGENTHUB_EXIT=$?
echo "AgentHub finished at $(date +%H:%M:%S) with exit code: ${AGENTHUB_EXIT}" | tee -a "${LOG_DIR}/agenthub_timeline.log"

# Check for background task output
if [ -d "/tmp/claude-1000/-home-lyc-project-AgentHub/tasks" ]; then
    LATEST_TASK=$(ls -t /tmp/claude-1000/-home-lyc-project-AgentHub/tasks/*.output 2>/dev/null | head -1)
    if [ -n "$LATEST_TASK" ]; then
        echo "Found background task output: $LATEST_TASK" | tee -a "${LOG_DIR}/agenthub_timeline.log"
        cp "$LATEST_TASK" "${LOG_DIR}/agenthub_background_output.log"
    fi
fi

echo ""
echo "========================================="
echo "Comparison Summary"
echo "========================================="

# Generate summary report
cat > "${LOG_DIR}/comparison_summary.txt" <<EOF
=== Comparison Summary ===
Timestamp: ${TIMESTAMP}
Timeout: ${TIMEOUT} seconds
Prompt: ${PROMPT}

--- Reference ---
Exit code: ${REFERENCE_EXIT}
Total output lines: $(wc -l < "${LOG_DIR}/reference_full_output.log")
Tool calls (exec): $(grep -c '^exec$' "${LOG_DIR}/reference_full_output.log" || echo 0)
Agent responses: $(grep -c '^reference$' "${LOG_DIR}/reference_full_output.log" || echo 0)

--- AgentHub ---
Exit code: ${AGENTHUB_EXIT}
Total output lines: $(wc -l < "${LOG_DIR}/agenthub_full_output.log")
Background task exists: $([ -f "${LOG_DIR}/agenthub_background_output.log" ] && echo "Yes" || echo "No")

--- Files Generated ---
${LOG_DIR}/reference_full_output.log
${LOG_DIR}/reference_timeline.log
${LOG_DIR}/reference_tool_calls.log
${LOG_DIR}/reference_agent_responses.log
${LOG_DIR}/reference_commands_detail.log
${LOG_DIR}/agenthub_full_output.log
${LOG_DIR}/agenthub_timeline.log
${LOG_DIR}/agenthub_background_output.log (if exists)
${LOG_DIR}/comparison_summary.txt

EOF

cat "${LOG_DIR}/comparison_summary.txt"

echo ""
echo "========================================="
echo "Detailed logs saved to: ${LOG_DIR}"
echo "========================================="
