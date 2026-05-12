#!/bin/bash

# Test comparison script for Reference vs AgentHub
PROMPT="看看仓库的规模和质量"
TEST_DIR="/home/lyc/project/AgentHub/cli"

echo "========================================="
echo "Testing Reference"
echo "========================================="
cd "$TEST_DIR"
timeout 120 reference exec "$PROMPT" 2>&1 | tee /tmp/reference_output.log

echo ""
echo "========================================="
echo "Testing AgentHub"
echo "========================================="
cd "$TEST_DIR"
timeout 120 ./scripts/start_agent_cli.sh -- --headless --prompt "$PROMPT" 2>&1 | tee /tmp/agenthub_output.log

echo ""
echo "========================================="
echo "Comparison Summary"
echo "========================================="
echo "Reference output lines: $(wc -l < /tmp/reference_output.log)"
echo "AgentHub output lines: $(wc -l < /tmp/agenthub_output.log)"
