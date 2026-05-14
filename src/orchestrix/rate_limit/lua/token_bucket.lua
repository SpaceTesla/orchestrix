-- KEYS
local bucket_key = KEYS[1]

-- ARGV
local current_time = tonumber(ARGV[1])
local max_tokens = tonumber(ARGV[2])
local refill_rate = tonumber(ARGV[3])
local tokens_requested = tonumber(ARGV[4])

-- FETCH CURRENT BUCKET STATE
local bucket = redis.call(
    "HMGET",
    bucket_key,
    "tokens",
    "last_refill"
)

local tokens = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])


-- INITIALIZE DEFAULTS
if tokens == nil then
    tokens = max_tokens
end

if last_refill == nil then
    last_refill = current_time
end


-- REFILL LOGIC
local elapsed_time = current_time - last_refill

local tokens_to_add = elapsed_time * refill_rate

local new_tokens = math.min(
    tokens + tokens_to_add,
    max_tokens
)


-- ALLOW / DENY
local allowed = 0
local remaining_tokens = new_tokens

if new_tokens >= tokens_requested then
    remaining_tokens = new_tokens - tokens_requested
    allowed = 1
end


-- RETRY HINT (deterministic; jitter belongs in application code)
local retry_after = 0
if allowed == 0 then
    if refill_rate > 0 then
        retry_after = (tokens_requested - new_tokens) / refill_rate
    else
        retry_after = -1
    end
end


-- PERSIST UPDATED STATE
redis.call(
    "HSET",
    bucket_key,
    "tokens",
    remaining_tokens,
    "last_refill",
    current_time
)

-- Prevent inactive buckets from living forever
redis.call(
    "EXPIRE",
    bucket_key,
    3600
)


-- RETURN RESULT
return {
    allowed,
    remaining_tokens,
    retry_after,
}
