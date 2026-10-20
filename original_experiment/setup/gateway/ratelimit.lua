-- ---------------------------------------------------------------------------
-- Three rate-limit windows enforced before each proxy_pass.  Matches §VI.B
-- of Sivakumar & Thilagam (IJACSA 16/3, 2025):
--
--   X-API-KEY prefix AX001*  →  100 req / min
--   X-API-KEY prefix BX001*  →   70 req / min
--   X-API-KEY other          →   50 req / min
--   per-IP                   →  100 req / min
--   per-X-User-Id            →  100 req / min
--
-- The window uses a fixed-window counter stored in lua_shared_dict to keep
-- the implementation small and predictable for the lab — the *vulnerability*
-- being demonstrated by Algorithms 3-5 is that, regardless of which of the
-- algorithms below picks for the limit, an attacker that rotates the key
-- header bypasses all of them.
-- ---------------------------------------------------------------------------
local function ip_limit()   return 100 end
local function user_limit() return 100 end
local function key_limit(k)
    if not k or k == "" then return 50 end
    if k:sub(1,5) == "AX001" then return 100 end
    if k:sub(1,5) == "BX001" then return 70  end
    return 50
end

local function bump(dict_name, key, limit, window)
    local dict = ngx.shared[dict_name]
    if not dict then return true end
    local bucket = math.floor(ngx.time() / window)
    local id = key .. ":" .. tostring(bucket)
    local cur, err = dict:incr(id, 1, 0, window + 1)
    if not cur then
        ngx.log(ngx.ERR, "ratelimit incr failed: ", err)
        return true
    end
    return cur <= limit
end

-- ---------------------------------------------------------------------------
local key  = ngx.var.http_x_api_key   or ""
local user = ngx.var.http_x_user_id   or ""
local xff  = ngx.var.http_x_forwarded_for
local ip   = (xff and xff:match("([^,]+)")) or ngx.var.remote_addr or ""

-- Skip RL on probe endpoints so the algorithms can introspect.
local uri = ngx.var.uri
if uri == "/health" or uri == "/v3/api-docs" then return end

if not bump("ratelimit_keys", "K:" .. key,  key_limit(key),  60) then
    ngx.status = 429
    ngx.header["Retry-After"] = "60"
    ngx.header["X-RateLimit-Bucket"] = "api-key"
    ngx.say('{"error":"rate_limited","scope":"api-key"}')
    return ngx.exit(429)
end
if ip ~= "" and not bump("ratelimit_ip",  "IP:" .. ip,  ip_limit(),  60) then
    ngx.status = 429
    ngx.header["Retry-After"] = "60"
    ngx.header["X-RateLimit-Bucket"] = "ip"
    ngx.say('{"error":"rate_limited","scope":"ip"}')
    return ngx.exit(429)
end
if user ~= "" and not bump("ratelimit_usr", "U:" .. user, user_limit(), 60) then
    ngx.status = 429
    ngx.header["Retry-After"] = "60"
    ngx.header["X-RateLimit-Bucket"] = "user"
    ngx.say('{"error":"rate_limited","scope":"user"}')
    return ngx.exit(429)
end
