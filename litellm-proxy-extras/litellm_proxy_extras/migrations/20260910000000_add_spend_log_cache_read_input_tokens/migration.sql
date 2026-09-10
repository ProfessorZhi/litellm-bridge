-- AlterTable
ALTER TABLE "LiteLLM_SpendLogs"
ADD COLUMN IF NOT EXISTS "cache_read_input_tokens" BIGINT NOT NULL DEFAULT 0;
