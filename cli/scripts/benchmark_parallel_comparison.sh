#!/bin/bash

# Parallel comparison test for Reference and AgentHub
PROMPT="找一找环境变量 OPENAI_API_KEY 是在哪里设置的？"
TEST_DIR="/home/lyc/project/AgentHub/cli"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="/tmp/parallel_comparison_${TIMESTAMP}"
TIMEOUT=400

mkdir -p "${LOG_DIR}"

echo "========================================="
echo "Parallel Comparison Test"
echo "Timestamp: ${TIMESTAMP}"
echo "Log directory: ${LOG_DIR}"
echo "Timeout: ${TIMEOUT} seconds"
echo "Prompt: ${PROMPT}"
echo "========================================="
echo ""

cd "$TEST_DIR"

# Function to run Reference
run_reference() {
    echo "Starting Reference at $(date +%H:%M:%S)" > "${LOG_DIR}/reference_timeline.log"
    timeout ${TIMEOUT} reference exec "$PROMPT" 2>&1 | tee "${LOG_DIR}/reference_full_output.log"
    REFERENCE_EXIT=$?
    echo "Reference finished at $(date +%H:%M:%S) with exit code: ${REFERENCE_EXIT}" >> "${LOG_DIR}/reference_timeline.log"

    # Extract statistics
    echo "Total tool calls: $(grep -c '^exec$' "${LOG_DIR}/reference_full_output.log" || echo 0)" >> "${LOG_DIR}/reference_timeline.log"
    echo "Total agent responses: $(grep -c '^reference$' "${LOG_DIR}/reference_full_output.log" || echo 0)" >> "${LOG_DIR}/reference_timeline.log"
}

# Function to run AgentHub
run_agenthub() {
    echo "Starting AgentHub at $(date +%H:%M:%S)" > "${LOG_DIR}/agenthub_timeline.log"
    timeout ${TIMEOUT} ./scripts/start_agent_cli.sh --sandbox-mode danger-full-access --approval-policy never --headless --prompt "$PROMPT" 2>&1 | tee "${LOG_DIR}/agenthub_full_output.log"
    AGENTHUB_EXIT=$?
    echo "AgentHub finished at $(date +%H:%M:%S) with exit code: ${AGENTHUB_EXIT}" >> "${LOG_DIR}/agenthub_timeline.log"

    # Check for background task output
    if [ -d "/tmp/claude-1000/-home-lyc-project-AgentHub/tasks" ]; then
        LATEST_TASK=$(ls -t /tmp/claude-1000/-home-lyc-project-AgentHub/tasks/*.output 2>/dev/null | head -1)
        if [ -n "$LATEST_TASK" ]; then
            echo "Found background task output: $LATEST_TASK" >> "${LOG_DIR}/agenthub_timeline.log"
            cp "$LATEST_TASK" "${LOG_DIR}/agenthub_background_output.log"
        fi
    fi
}

# Run both in parallel
echo "Starting both systems in parallel..."
run_reference &
REFERENCE_PID=$!
run_agenthub &
AGENTHUB_PID=$!

# Wait for both to complete
echo "Waiting for Reference (PID: $REFERENCE_PID)..."
wait $REFERENCE_PID
echo "Reference completed"

echo "Waiting for AgentHub (PID: $AGENTHUB_PID)..."
wait $AGENTHUB_PID
echo "AgentHub completed"

echo ""
echo "========================================="
echo "Generating Comparison Report"
echo "========================================="

# Extract Reference statistics
REFERENCE_LINES=$(wc -l < "${LOG_DIR}/reference_full_output.log" 2>/dev/null || echo 0)
REFERENCE_TOOLS=$(grep -c '^exec$' "${LOG_DIR}/reference_full_output.log" 2>/dev/null || echo 0)
REFERENCE_RESPONSES=$(grep -c '^reference$' "${LOG_DIR}/reference_full_output.log" 2>/dev/null || echo 0)
REFERENCE_START=$(head -1 "${LOG_DIR}/reference_timeline.log" | grep -oP '\d{2}:\d{2}:\d{2}')
REFERENCE_END=$(tail -2 "${LOG_DIR}/reference_timeline.log" | head -1 | grep -oP '\d{2}:\d{2}:\d{2}')

# Extract AgentHub statistics
AGENTHUB_LINES=$(wc -l < "${LOG_DIR}/agenthub_full_output.log" 2>/dev/null || echo 0)
AGENTHUB_START=$(head -1 "${LOG_DIR}/agenthub_timeline.log" | grep -oP '\d{2}:\d{2}:\d{2}')
AGENTHUB_END=$(tail -2 "${LOG_DIR}/agenthub_timeline.log" | head -1 | grep -oP '\d{2}:\d{2}:\d{2}')

# Generate summary report
cat > "${LOG_DIR}/comparison_summary.txt" <<EOF
=== Parallel Comparison Summary ===
Timestamp: ${TIMESTAMP}
Timeout: ${TIMEOUT} seconds
Prompt: ${PROMPT}

--- Reference ---
Start time: ${REFERENCE_START}
End time: ${REFERENCE_END}
Total output lines: ${REFERENCE_LINES}
Tool calls (exec): ${REFERENCE_TOOLS}
Agent responses: ${REFERENCE_RESPONSES}

--- AgentHub ---
Start time: ${AGENTHUB_START}
End time: ${AGENTHUB_END}
Total output lines: ${AGENTHUB_LINES}
Background task exists: $([ -f "${LOG_DIR}/agenthub_background_output.log" ] && echo "Yes" || echo "No")

--- Files Generated ---
${LOG_DIR}/reference_full_output.log
${LOG_DIR}/reference_timeline.log
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
echo ""
echo "To view results:"
echo "  Reference output: cat ${LOG_DIR}/reference_full_output.log"
echo "  AgentHub output: cat ${LOG_DIR}/agenthub_full_output.log"
echo "  Summary: cat ${LOG_DIR}/comparison_summary.txt"
