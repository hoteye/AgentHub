#!/bin/bash

# Detailed comparison script for Reference vs AgentHub
PROMPT="看看仓库的规模和质量"
TEST_DIR="/home/lyc/project/AgentHub/cli"

echo "========================================="
echo "Testing Reference (with tool call tracking)"
echo "========================================="
cd "$TEST_DIR"
timeout 120 reference exec "$PROMPT" 2>&1 | tee /tmp/reference_detailed.log

echo ""
echo "========================================="
echo "Testing AgentHub (with tool call tracking)"
echo "========================================="
cd "$TEST_DIR"
timeout 120 ./scripts/start_agent_cli.sh -- --headless --prompt "$PROMPT" --approval-policy never 2>&1 | tee /tmp/agenthub_detailed.log

echo ""
echo "========================================="
echo "Detailed Comparison"
echo "========================================="

echo "Reference:"
echo "  Total lines: $(wc -l < /tmp/reference_detailed.log)"
echo "  Tool calls (exec): $(grep -c '^exec$' /tmp/reference_detailed.log || echo 0)"
echo "  Agent responses: $(grep -c '^reference$' /tmp/reference_detailed.log || echo 0)"

echo ""
echo "AgentHub:"
echo "  Total lines: $(wc -l < /tmp/agenthub_detailed.log)"
echo "  Tool calls: $(grep -c 'tool_name=' /tmp/agenthub_detailed.log || echo 0)"
echo "  Commands executed: $(grep -c 'command=' /tmp/agenthub_detailed.log || echo 0)"

echo ""
echo "========================================="
echo "Response Quality Comparison"
echo "========================================="
echo "Reference final response:"
tail -50 /tmp/reference_detailed.log | grep -A 50 "^reference$" | tail -30

echo ""
echo "AgentHub final response:"
cat /tmp/agenthub_detailed.log
