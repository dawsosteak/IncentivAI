#!/bin/bash
#SBATCH --job-name=incentivai
#SBATCH --account=stf
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --time=24:00:00
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err

mkdir -p logs results

echo "Job started at:      $(date)"
echo "Running on node:     $(hostname)"
echo "Job ID:              $SLURM_JOB_ID"
echo "Working directory:   $(pwd)"

# ── LLM provider config ───────────────────────────────────────────────────────
# Set PROVIDER and MODEL to whichever backend you want to use for this run.
# Supported: ollama | openai | anthropic | google | gemini
#
#   OpenAI:    export OPENAI_API_KEY=...
#   Anthropic: export ANTHROPIC_API_KEY=...
#   Google:    export GOOGLE_API_KEY=...
#   Ollama:    no key needed, but Ollama must be reachable on the node

PROVIDER="${INCENTIVAI_PROVIDER:-openai}"
MODEL="${INCENTIVAI_MODEL:-gpt-4o}"

echo "Provider:            $PROVIDER"
echo "Model:               $MODEL"

# ── Key checks (warn only — don't block the job) ──────────────────────────────
if [ "$PROVIDER" = "openai" ]; then
    test -n "$OPENAI_API_KEY" \
        && echo "OPENAI_API_KEY:      set" \
        || echo "WARNING: OPENAI_API_KEY is NOT set"
fi

if [ "$PROVIDER" = "anthropic" ]; then
    test -n "$ANTHROPIC_API_KEY" \
        && echo "ANTHROPIC_API_KEY:   set" \
        || echo "WARNING: ANTHROPIC_API_KEY is NOT set"
fi

if [ "$PROVIDER" = "google" ] || [ "$PROVIDER" = "gemini" ]; then
    test -n "$GOOGLE_API_KEY" \
        && echo "GOOGLE_API_KEY:      set" \
        || echo "WARNING: GOOGLE_API_KEY is NOT set"
fi

echo ""

# ── Run pipeline ──────────────────────────────────────────────────────────────
PYTHONUNBUFFERED=1 uv run python -u cli.py \
    --file ../Testing_links_incentivai.xlsx \
    --provider "$PROVIDER" \
    --model "$MODEL" \
    --temperature 0.0 \
    --truncation 150000 \
    --output results/ \
    --output-name "incentives_${SLURM_JOB_ID}.csv" \
    2>&1 | tee logs/run_${SLURM_JOB_ID}.log

echo ""
echo "Job finished at: $(date)"
