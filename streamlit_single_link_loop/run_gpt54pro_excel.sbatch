#!/bin/bash
#SBATCH --job-name=gpt54pro_excel
#SBATCH --account=stf
#SBATCH --partition=compute
#SBATCH --nodes=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --time=24:00:00
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err

mkdir -p logs

echo "Job started at: $(date)"
echo "Running on node: $(hostname)"
echo "Job ID: $SLURM_JOB_ID"
echo "Working directory: $(pwd)"

echo "Checking UW SSEC environment variables..."
test -n "$UW_SSEC_AI_GATEWAY_KEY" && echo "UW_SSEC_AI_GATEWAY_KEY is set" || echo "UW_SSEC_AI_GATEWAY_KEY is NOT set"
echo "UW_SSEC_AI_GATEWAY_BASE_URL=$UW_SSEC_AI_GATEWAY_BASE_URL"

PYTHONUNBUFFERED=1 uv run python -u run_excel_urls.py \
  --excel ../Testing_links_incentivai.xlsx \
  --provider uw_ssec \
  --model gpt-5.4-pro \
  --deep-crawl \
  2>&1 | tee gpt54pro_excel_deep_run_${SLURM_JOB_ID}.log

echo "Job finished at: $(date)"

